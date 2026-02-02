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
from ..reasoning_tracker import ReasoningTracker, StepType

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
    tracker = ReasoningTracker()
    tracker.set_source("graph_expand")

    sector_config = state.get("sector_config")
    if not sector_config:
        return {}

    start_time = time.time()

    tracker.add_step(
        StepType.SEARCH,
        f"Expandiendo contexto con grafo de conocimiento ({sector_config.get('sector')})...",
        confidence=1.0,
    )
    query = state.get("query", "")
    tenant_id = state.get("tenant_id", "")

    logger.info(
        f"🌐 GRAPH_EXPAND: sector={sector_config.get('sector')} | "
        f"graph={sector_config.get('graph_name')}"
    )

    try:
        from ..sectors.entity_extractor import extract_entities
        from ..sectors.graph_expander import expand_with_sector_graph
        from ..sectors.qa_index import get_sector_qa_index

        # Step 1: Try semantic concept matching via QA index (primary)
        sector_name = sector_config.get("sector", "")
        qa_index = get_sector_qa_index(sector_name) if sector_name else None
        concept_matches = qa_index.search(query, top_k=3, threshold=0.65) if qa_index else []

        if concept_matches:
            # Build keywords from matched concepts for Cypher expansion
            all_keywords = []
            for match in concept_matches:
                all_keywords.extend(match.graph_keywords)

            tracker.add_step(
                StepType.OBSERVATION,
                f"QA embedding: {len(concept_matches)} conceptos "
                f"({concept_matches[0].id}, score={concept_matches[0].score:.2f})",
                confidence=concept_matches[0].score,
            )

            # Build pseudo-entities from keywords for graph expansion
            entities = {"qa_concept": all_keywords}
        else:
            # Fallback: regex entity extraction (for formal citations like "Art. 54 ET")
            entity_patterns = sector_config.get("entity_patterns", {})
            entities = extract_entities(query, entity_patterns)

        if not entities:
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"🌐 GRAPH_EXPAND: No entities found ({latency_ms:.1f}ms)")
            tracker.add_step(
                StepType.OBSERVATION,
                "Sin entidades detectadas para expansión de grafo",
                confidence=1.0,
            )
            return {
                "reasoning_steps": tracker.get_steps(),
                "metadata": {
                    **state.get("metadata", {}),
                    "graph_expansion": {
                        "entities_found": 0,
                        "graph_context": "",
                        "latency_ms": latency_ms,
                        "qa_matches": [
                            {"id": m.id, "score": m.score}
                            for m in concept_matches
                        ] if concept_matches else [],
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

        entity_count = sum(len(v) for v in entities.values())
        related_count = len(expansion.get("related_entities", []))

        logger.info(
            f"✅ GRAPH_EXPAND: {entity_count} entities → "
            f"{related_count} related nodes | "
            f"{latency_ms:.1f}ms"
        )

        tracker.add_step(
            StepType.OBSERVATION,
            f"Entidades extraídas: {entity_count} → {related_count} nodos relacionados ({latency_ms:.0f}ms)",
            confidence=1.0,
            entities=[e for vals in entities.values() for e in vals[:5]],
        )

        return {
            "reasoning_steps": tracker.get_steps(),
            "metadata": {
                **state.get("metadata", {}),
                "graph_expansion": {
                    "entities_extracted": entities,
                    "graph_context": expansion.get("graph_context", ""),
                    "related_entities_count": len(expansion.get("related_entities", [])),
                    "paths_count": len(expansion.get("paths", [])),
                    "cypher_queries": expansion.get("cypher_queries", []),
                    "qa_matches": [
                        {"id": m.id, "score": m.score, "domain": m.domain}
                        for m in concept_matches
                    ] if concept_matches else [],
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
