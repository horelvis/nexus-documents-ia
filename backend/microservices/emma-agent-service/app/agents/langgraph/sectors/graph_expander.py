"""
Sector-aware Graph Expander

Expands query context by querying the Apache AGE graph for the active sector.
Uses extracted entities to build Cypher queries and retrieves related
nodes/edges from the sector's knowledge graph.

Calls the knowledge-tree-service via HTTP.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def expand_with_sector_graph(
    query: str,
    entities: Dict[str, List[str]],
    sector_config: Dict[str, Any],
    tenant_id: str,
) -> Dict[str, Any]:
    """
    Expand context using the sector's Apache AGE graph.

    Builds Cypher queries from extracted entities and the sector's graph schema,
    then calls knowledge-tree-service to execute them.

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
            - cypher_queries: list — queries executed (for tracing)
    """
    graph_name = sector_config.get("graph_name", "")
    if not graph_name or not entities:
        return {
            "graph_context": "",
            "related_entities": [],
            "paths": [],
            "cypher_queries": [],
        }

    cypher_queries: List[str] = []
    related_entities: List[Dict[str, Any]] = []
    paths: List[str] = []

    try:
        from app.clients.knowledge_tree_client import get_knowledge_tree_client

        client = get_knowledge_tree_client()

        for entity_type, values in entities.items():
            for value in values[:5]:  # Limit per type
                cypher = _build_cypher_query(graph_name, entity_type, value)
                if not cypher:
                    continue

                cypher_queries.append(cypher)

                try:
                    data = await client.graph_query(
                        cypher=cypher,
                        graph_name=graph_name,
                        tenant_id=tenant_id,
                    )
                    for row in data.get("results", []):
                        related_entities.append(row)
                    for path in data.get("paths", []):
                        paths.append(str(path))
                except Exception as e:
                    logger.warning(f"Graph query failed for {entity_type}={value}: {e}")

    except Exception as e:
        logger.warning(f"Graph expansion failed: {e}")

    # Build textual context from results
    graph_context = _build_context_text(related_entities, paths)

    return {
        "graph_context": graph_context,
        "related_entities": related_entities,
        "paths": paths,
        "cypher_queries": cypher_queries,
    }


def _build_cypher_query(graph_name: str, entity_type: str, value: str) -> Optional[str]:
    """Build a Cypher query for an entity type and value."""
    # Escape single quotes in value
    safe_value = value.replace("'", "\\'")

    # Search across node properties for all sector graph types:
    # - Legal: title, short_name, boe_id, domain (LegalLaw/LegalArticle)
    # - Documental: name, associated_person (Persona, structural_document)
    return (
        f"SELECT * FROM cypher('{graph_name}', $$ "
        f"MATCH (n)-[r]-(m) "
        f"WHERE n.title =~ '(?i).*{safe_value}.*' "
        f"OR n.short_name =~ '(?i).*{safe_value}.*' "
        f"OR n.boe_id =~ '(?i).*{safe_value}.*' "
        f"OR n.domain =~ '(?i).*{safe_value}.*' "
        f"OR n.name =~ '(?i).*{safe_value}.*' "
        f"OR n.associated_person =~ '(?i).*{safe_value}.*' "
        f"RETURN n, type(r) as rel, m LIMIT 10 "
        f"$$) AS (n agtype, rel agtype, m agtype)"
    )


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
