"""
SIL Engine Stub for Emma Agent Service.

Delegates to knowledge-tree-service for structural queries.
"""

import logging
from typing import Dict, Any, Optional

from app.clients import get_knowledge_tree_client
from .schemas import ReasoningType, SILResult

logger = logging.getLogger(__name__)


class PreLLMEngine:
    """
    Pre-LLM Engine stub that delegates to knowledge-tree-service.

    In the original architecture, SIL (Structural Intelligence Layer)
    would process queries before the LLM to determine if they can be
    answered with structural data alone. This stub delegates that
    logic to weaviate-service via HTTP.
    """

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        """Initialize the engine."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("✅ PreLLMEngine stub initialized (delegates to knowledge-tree-service)")

    async def process_query(
        self,
        query: str,
        tenant_id: str,
        max_results: int = 20,
    ) -> SILResult:
        """
        Process a query to determine if it can be answered structurally.

        Args:
            query: User query
            tenant_id: Tenant identifier
            max_results: Maximum results

        Returns:
            SILResult with reasoning type and context
        """
        try:
            client = get_knowledge_tree_client()

            # Delegate to knowledge-tree-service structural query endpoint
            response = await client.structural_query(
                tenant_id=tenant_id,
                query=query,
                max_results=max_results,
            )

            route = response.get("route", "ERROR")
            confidence = response.get("confidence", 0.0)
            context = response.get("context", "")
            data = response.get("data", {})

            # Map route to reasoning type
            route_map = {
                "GRAPH_ONLY": ReasoningType.GRAPH_ONLY,
                "VECTOR_ONLY": ReasoningType.VECTOR_ONLY,
                "HYBRID": ReasoningType.HYBRID,
                "ERROR": ReasoningType.ERROR,
            }

            reasoning_type = route_map.get(route, ReasoningType.VECTOR_ONLY)

            return SILResult(
                reasoning_type=reasoning_type,
                context=context,
                data=data,
                confidence=confidence,
                metadata={"source": "knowledge-tree-service"},
            )

        except Exception as e:
            logger.warning(f"SIL query failed, falling back to vector: {e}")
            return SILResult(
                reasoning_type=ReasoningType.VECTOR_ONLY,
                context="",
                data={"error": str(e)},
                confidence=0.0,
                metadata={"source": "error", "error": str(e)},
            )


# Singleton instance
pre_llm_engine = PreLLMEngine()
