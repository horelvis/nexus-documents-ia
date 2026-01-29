"""
GRAPH EXPAND Node — Sector-aware Knowledge Graph Expansion

This node enriches the RAG context by querying the Apache AGE graph
for the active sector. It extracts entities from the query using
sector-specific regex patterns, then expands context via Cypher queries.

If no sector is active, this node is a no-op (returns empty dict).

Position in graph: retrieve → graph_expand → plan
"""

import logging
import time
from typing import Any, Dict

from ..state import RAGState

logger = logging.getLogger(__name__)


async def graph_expand_node(state: RAGState) -> Dict[str, Any]:
    """
    Expand context using the sector's knowledge graph.

    Steps:
        1. Read sector_config from state (loaded from singleton at startup)
        2. Extract entities with sector-specific regex
        3. Query Apache AGE graph for related context
        4. Store results in state.metadata.graph_expansion

    Args:
        state: Current RAG state with query and sector info

    Returns:
        State updates with graph expansion metadata.
        Empty dict if no sector is active (no-op).
    """
    sector_config = state.get("sector_config")
    if not sector_config:
        return {}

    start_time = time.time()
    query = state.get("query", "")
    tenant_id = state.get("tenant_id", "")

    logger.info(
        f"🌐 GRAPH_EXPAND: sector={sector_config.get('sector')} | "
        f"graph={sector_config.get('graph_name')}"
    )

    try:
        from ..sectors.entity_extractor import extract_entities
        from ..sectors.graph_expander import expand_with_sector_graph

        # Step 1: Extract entities
        entity_patterns = sector_config.get("entity_patterns", {})
        entities = extract_entities(query, entity_patterns)

        if not entities:
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"🌐 GRAPH_EXPAND: No entities found ({latency_ms:.1f}ms)")
            return {
                "metadata": {
                    **state.get("metadata", {}),
                    "graph_expansion": {
                        "entities_found": 0,
                        "graph_context": "",
                        "latency_ms": latency_ms,
                    },
                },
            }

        # Step 2: Expand via graph
        expansion = await expand_with_sector_graph(
            query=query,
            entities=entities,
            sector_config=sector_config,
            tenant_id=tenant_id,
        )

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"✅ GRAPH_EXPAND: {sum(len(v) for v in entities.values())} entities → "
            f"{len(expansion.get('related_entities', []))} related nodes | "
            f"{latency_ms:.1f}ms"
        )

        return {
            "metadata": {
                **state.get("metadata", {}),
                "graph_expansion": {
                    "entities_extracted": entities,
                    "graph_context": expansion.get("graph_context", ""),
                    "related_entities_count": len(expansion.get("related_entities", [])),
                    "paths_count": len(expansion.get("paths", [])),
                    "cypher_queries": expansion.get("cypher_queries", []),
                    "latency_ms": latency_ms,
                },
            },
        }

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ GRAPH_EXPAND failed: {e}")
        return {
            "metadata": {
                **state.get("metadata", {}),
                "graph_expansion": {
                    "error": str(e),
                    "latency_ms": latency_ms,
                },
            },
        }
