"""
Sector-aware Graph Expander

Expands query context by querying the FalkorDB knowledge graph for the
active sector. Uses extracted entities and semantic HTTP endpoints on
knowledge-tree-service (get_documents_by_person, extract_subgraph).

No raw Cypher is constructed here — all graph logic lives in
knowledge-tree-service.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum entities per type to expand (avoids runaway fan-out)
_MAX_ENTITIES_PER_TYPE = 5


async def expand_with_sector_graph(
    query: str,
    entities: Dict[str, List[str]],
    sector_config: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Expand context using the sector's FalkorDB knowledge graph.

    Uses semantic HTTP endpoints on knowledge-tree-service:
    - get_documents_by_person() for person/entity lookups
    - extract_subgraph() for multi-hop graph expansion

    All entity lookups are batched with asyncio.gather() to avoid N+1.

    Args:
        query: User query
        entities: Extracted entities (from entity_extractor)
        sector_config: Serialized SectorConfig dict
        tenant_id: Tenant ID for graph isolation

    Returns:
        Dict with:
            - graph_context: str — textual context from graph expansion
            - related_entities: list — related nodes found
            - paths: list — relationship paths found
            - expanded_doc_ids: list — document IDs found via entity lookup
    """
    if not entities:
        return {
            "graph_context": "",
            "related_entities": [],
            "paths": [],
            "expanded_doc_ids": [],
        }

    related_entities: List[Dict[str, Any]] = []
    paths: List[str] = []
    expanded_doc_ids: List[str] = []

    try:
        from app.clients.knowledge_tree_client import get_knowledge_tree_client

        client = get_knowledge_tree_client()

        # ------------------------------------------------------------------
        # Phase 1: Batch entity → document lookups via asyncio.gather()
        # ------------------------------------------------------------------
        lookup_tasks = []
        lookup_meta = []  # Track (entity_type, value) for each task

        for entity_type, values in entities.items():
            for value in values[:_MAX_ENTITIES_PER_TYPE]:
                if not value or not value.strip():
                    continue
                # Map entity types to FalkorDB convention
                ft_type = _map_entity_type(entity_type)
                lookup_tasks.append(
                    client.get_documents_by_person(
                        tenant_id=tenant_id,
                        person_name=value.strip(),
                        entity_type=ft_type,
                    )
                )
                lookup_meta.append((entity_type, value))

        if lookup_tasks:
            results = await asyncio.gather(*lookup_tasks, return_exceptions=True)
            for (etype, evalue), result in zip(lookup_meta, results):
                if isinstance(result, Exception):
                    logger.warning(f"Entity lookup failed for {etype}={evalue}: {result}")
                    continue
                if result:
                    expanded_doc_ids.extend(result)

        # Deduplicate document IDs
        expanded_doc_ids = list(dict.fromkeys(expanded_doc_ids))

        # ------------------------------------------------------------------
        # Phase 2: Extract subgraph for richer context
        # ------------------------------------------------------------------
        subgraph_entities = []
        for entity_type, values in entities.items():
            for value in values[:_MAX_ENTITIES_PER_TYPE]:
                if value and value.strip():
                    subgraph_entities.append({
                        "name": value.strip(),
                        "type": _map_entity_type(entity_type),
                    })

        if subgraph_entities:
            subgraph = await client.extract_subgraph(
                tenant_id=tenant_id,
                entities=subgraph_entities,
                max_hops=2,
                max_nodes=30,
                include_legal=True,
            )

            for node in subgraph.get("nodes", []):
                related_entities.append(node)
            for edge in subgraph.get("edges", []):
                src = edge.get("source_id", "?")
                tgt = edge.get("target_id", "?")
                label = edge.get("label", "?")
                paths.append(f"{src} -[{label}]-> {tgt}")

    except Exception as e:
        logger.warning(f"Graph expansion failed: {e}")

    # Build textual context from results
    graph_context = _build_context_text(related_entities, paths)

    return {
        "graph_context": graph_context,
        "related_entities": related_entities,
        "paths": paths,
        "expanded_doc_ids": expanded_doc_ids,
    }


def _map_entity_type(entity_type: str) -> str:
    """Map extraction entity types to FalkorDB entity_type values."""
    mapping = {
        "persona": "person",
        "person": "person",
        "ley": "law",
        "law": "law",
        "sentencia": "ruling",
        "ruling": "ruling",
        "articulo": "article",
        "article": "article",
        "boe": "law",
        "expediente": "case",
        "case": "case",
        "cie10": "medical_code",
        "farmaco": "drug",
        "procedimiento": "procedure",
        "paciente": "patient",
        "nif": "person",
        "importe": "amount",
        "referencia": "reference",
        "fecha": "date",
    }
    return mapping.get(entity_type.lower(), "person")


def _build_context_text(
    related_entities: List[Dict[str, Any]],
    paths: List[str],
) -> str:
    """Build human-readable context from graph results."""
    if not related_entities and not paths:
        return ""

    parts: List[str] = []

    if related_entities:
        parts.append("Contexto del grafo de conocimiento:")
        seen = set()
        for entity in related_entities[:15]:
            desc = str(entity)
            if desc not in seen:
                parts.append(f"  - {desc}")
                seen.add(desc)

    if paths:
        parts.append("Relaciones encontradas:")
        for path in paths[:10]:
            parts.append(f"  - {path}")

    return "\n".join(parts)
