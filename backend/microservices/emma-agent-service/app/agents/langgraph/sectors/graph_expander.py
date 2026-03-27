"""
Sector-aware Graph Expander

Expands query context by querying the TrustGraph triple store for the
active sector. Uses extracted entities to build normalized URI slugs
and calls /triples/query on knowledge-tree-service to find linked documents.

No raw Cypher is constructed here — all graph logic lives in
knowledge-tree-service.
"""

import asyncio
import logging
import re
import unicodedata
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Maximum entities per type to expand (avoids runaway fan-out)
_MAX_ENTITIES_PER_TYPE = 5

# Predicate used to link :Node subjects to document :Literal objects
_MENTIONED_IN = "nouxcube://predicate/core/mentioned-in"
_DOCUMENT_URI_PREFIX = "nouxcube://document/"


def _slugify(text: str) -> str:
    """Normalize an entity name into a URI-safe slug."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    slug = re.sub(r"[^\w\s-]", "", ascii_text).strip().lower()
    return re.sub(r"[\s_-]+", "-", slug)


def _entity_uri(entity_type: str, value: str) -> str:
    """Build a TrustGraph URI for a named entity."""
    slug = _slugify(value)
    type_slug = _slugify(entity_type)
    return f"nouxcube://entity/{type_slug}/{slug}"


async def expand_with_sector_graph(
    query: str,
    entities: Dict[str, List[str]],
    sector_config: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Expand context using the TrustGraph triple store.

    For each extracted entity, builds a normalized URI slug and calls
    /triples/query with subject_uri=entity_uri and predicate_uri=mentioned-in
    to find linked documents.  Also calls /triples/context for general
    graph context to enrich LLM prompts.

    All entity lookups are batched with asyncio.gather() to avoid N+1.

    Args:
        query: User query
        entities: Extracted entities (from entity_extractor)
        sector_config: Serialized SectorConfig dict
        tenant_id: Tenant ID for graph isolation

    Returns:
        Dict with:
            - graph_context: str — textual context from graph expansion
            - related_entities: list — entity URIs found as subjects
            - paths: list — relationship paths found (subject → predicate → object)
            - expanded_doc_ids: list — document IDs found via entity lookup
    """
    if not entities:
        return {
            "graph_context": "",
            "related_entities": [],
            "paths": [],
            "expanded_doc_ids": [],
        }

    related_entities: List[str] = []
    paths: List[str] = []
    expanded_doc_ids: List[str] = []

    try:
        from app.clients.knowledge_tree_client import get_knowledge_tree_client

        client = get_knowledge_tree_client()

        # ------------------------------------------------------------------
        # Phase 1: Batch entity → document lookups via /triples/query
        # Each entity maps to a URI; we look for mentioned-in links to docs.
        # ------------------------------------------------------------------
        lookup_tasks = []
        lookup_meta: List[tuple] = []  # (entity_type, value, entity_uri)

        for entity_type, values in entities.items():
            for value in values[:_MAX_ENTITIES_PER_TYPE]:
                if not value or not value.strip():
                    continue
                uri = _entity_uri(entity_type, value.strip())
                lookup_tasks.append(
                    client.query_triples(
                        tenant_id=tenant_id,
                        subject_uri=uri,
                        predicate_uri=_MENTIONED_IN,
                        limit=50,
                    )
                )
                lookup_meta.append((entity_type, value, uri))

        if lookup_tasks:
            results = await asyncio.gather(*lookup_tasks, return_exceptions=True)
            for (etype, evalue, euri), result in zip(lookup_meta, results):
                if isinstance(result, Exception):
                    logger.warning(f"Triple query failed for {etype}={evalue}: {result}")
                    continue
                triples = result.get("triples", []) if isinstance(result, dict) else []
                if triples:
                    related_entities.append(euri)
                for triple in triples:
                    obj = triple.get("object_value") or triple.get("object_uri", "")
                    pred = triple.get("predicate_uri", _MENTIONED_IN)
                    paths.append(f"{euri} -[{pred}]-> {obj}")
                    # Extract document ID from URI: nouxcube://document/<id>
                    if obj.startswith(_DOCUMENT_URI_PREFIX):
                        doc_id = obj[len(_DOCUMENT_URI_PREFIX):]
                        if doc_id:
                            expanded_doc_ids.append(doc_id)

        # Deduplicate
        expanded_doc_ids = list(dict.fromkeys(expanded_doc_ids))
        related_entities = list(dict.fromkeys(related_entities))

        # ------------------------------------------------------------------
        # Phase 2: General triple context for LLM enrichment
        # ------------------------------------------------------------------
        context_result = await client.get_triple_context(tenant_id=tenant_id, limit=20)
        llm_context_text = context_result.get("context_for_llm", "") if isinstance(context_result, dict) else ""

    except Exception as e:
        logger.warning(f"Graph expansion failed: {e}")
        llm_context_text = ""

    # Build textual context from results
    graph_context = _build_context_text(related_entities, paths, llm_context_text)

    return {
        "graph_context": graph_context,
        "related_entities": related_entities,
        "paths": paths,
        "expanded_doc_ids": expanded_doc_ids,
    }


def _build_context_text(
    related_entities: List[str],
    paths: List[str],
    llm_context: str,
) -> str:
    """Build human-readable context from graph results."""
    if not related_entities and not paths and not llm_context:
        return ""

    parts: List[str] = []

    if llm_context:
        parts.append(llm_context.strip())

    if related_entities:
        parts.append("Entidades relacionadas encontradas en el grafo:")
        for uri in related_entities[:15]:
            parts.append(f"  - {uri}")

    if paths:
        parts.append("Relaciones encontradas:")
        for path in paths[:10]:
            parts.append(f"  - {path}")

    return "\n".join(parts)
