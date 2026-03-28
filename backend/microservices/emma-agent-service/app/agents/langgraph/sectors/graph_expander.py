"""
DEPRECATED: Replaced by graph_rag tool in Phase 2.
Use GraphRAGTool for TrustGraph-validated retrieval via knowledge graph.
This module is kept for backward compatibility — SmartSearch still calls
KnowledgeTreeClient.extract_subgraph independently.

Sector-aware Graph Expander

Expands query context by querying the TrustGraph triple store for the
active sector. Uses extracted entities to build normalized URI slugs
and calls /triples/query on knowledge-tree-service to find linked documents.

No raw Cypher is constructed here — all graph logic lives in
knowledge-tree-service.

IMPORTANT: Entity URIs MUST match URIBuilder.entity(collection, name) format:
    nouxcube://entity/{collection}/{normalized-name}
The collection is typically "default" for the reindex pipeline.
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

# Default collection used by reindex pipeline (must match coordinator.py)
_DEFAULT_COLLECTION = "default"


_COMMA_NAME_RE = re.compile(r"^([^,]+),\s*(.+)$")


def _normalize_name(name: str) -> str:
    """Normalize a name to URI slug — mirrors URIBuilder.normalize_name().

    Includes "Last, First" → "First Last" reordering for person names.
    """
    stripped = name.strip()
    # Reorder "Last, First" if after-comma looks like a first name
    m = _COMMA_NAME_RE.match(stripped)
    if m:
        before, after = m.group(1).strip(), m.group(2).strip()
        _co = {"s.l.", "s.a.", "s.l.u.", "inc", "ltd", "gmbh", "corp"}
        if not any(ch.isdigit() for ch in after) and len(after.split()) <= 4 and after.lower() not in _co:
            stripped = f"{after} {before}"
    nfd = unicodedata.normalize("NFD", stripped)
    ascii_approx = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    lowered = ascii_approx.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    return hyphenated.strip("-")


def _entity_uri(entity_type: str, value: str, collection: str = _DEFAULT_COLLECTION) -> str:
    """Build a TrustGraph URI matching URIBuilder.entity(collection, name)."""
    slug = _normalize_name(value)
    if not slug:
        return ""
    return f"nouxcube://entity/{collection}/{slug}"


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
                if not uri:
                    continue
                lookup_tasks.append(
                    client.query_triples(
                        tenant_id=tenant_id,
                        subject_uri=uri,
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
                    obj = triple.get("object", "")
                    pred = triple.get("predicate", "")
                    paths.append(f"{euri} -[{pred}]-> {obj}")
                    # Extract document IDs from source_chunk provenance
                    # format: nouxcube://document/{collection}/{doc_id}#offset=N
                    source = triple.get("source_chunk", "")
                    if source and _DOCUMENT_URI_PREFIX in source:
                        doc_part = source.split("#")[0]  # strip #offset=N
                        doc_id = doc_part.split("/")[-1]  # last segment = UUID
                        if doc_id:
                            expanded_doc_ids.append(doc_id)
                    # Also check if object itself is a document URI
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
