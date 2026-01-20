"""
Multi-Hop Query Executor

Executes planned multi-hop queries with:
- Adaptive timeouts based on complexity
- Result limiting to prevent runaway queries
- Path explanation for debugging
- Performance monitoring
"""

import logging
import time
from typing import Optional, List, Dict, Any

from .schemas import (
    QueryPlan,
    MultiHopResult,
    CypherQueryResult,
)
from .multihop_planner import MultiHopQueryPlanner, multihop_planner
from ...services.knowledge.age_graph_service import AGEKnowledgeGraphService, age_knowledge_graph

logger = logging.getLogger(__name__)


class MultiHopExecutor:
    """
    Executes multi-hop queries with safety controls.

    Features:
    - Adaptive timeouts (more hops = more time allowed)
    - Result limits to prevent memory issues
    - Path explanation for transparency
    - Performance monitoring
    """

    # Timeout limits by complexity
    TIMEOUT_BY_COMPLEXITY = {
        1: 1000,   # 1 second for simple queries
        2: 2000,   # 2 seconds for 2-hop
        3: 3000,   # 3 seconds for 3-hop
        4: 4000,   # 4 seconds for 4-hop
        5: 5000,   # 5 seconds for 5-hop (max)
    }

    # Result limits
    MAX_INTERMEDIATE_RESULTS = 1000
    MAX_FINAL_RESULTS = 100

    def __init__(
        self,
        planner: Optional[MultiHopQueryPlanner] = None,
        graph_service: Optional[AGEKnowledgeGraphService] = None,
    ):
        self._planner = planner or multihop_planner
        self._graph = graph_service or age_knowledge_graph
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the executor."""
        if self._initialized:
            return

        await self._planner.initialize()
        await self._graph.initialize()

        self._initialized = True
        logger.info("✅ MultiHopExecutor initialized")

    async def execute(
        self,
        plan: QueryPlan,
        tenant_id: str,
    ) -> MultiHopResult:
        """
        Execute a multi-hop query plan.

        Args:
            plan: The planned query with Cypher
            tenant_id: Tenant identifier

        Returns:
            MultiHopResult with results and metadata
        """
        await self.initialize()

        start_time = time.time()

        # Validate complexity
        if plan.estimated_complexity > 5:
            logger.warning(
                f"Complex multi-hop query: {plan.estimated_complexity} hops. "
                f"Performance may be impacted."
            )

        # Calculate timeout
        timeout_ms = self.TIMEOUT_BY_COMPLEXITY.get(
            min(plan.estimated_complexity, 5),
            5000
        )

        try:
            # Execute the query
            result = await self._execute_with_timeout(
                cypher=plan.cypher,
                tenant_id=tenant_id,
                timeout_ms=timeout_ms,
            )

            execution_time = (time.time() - start_time) * 1000

            if not result.success:
                return MultiHopResult(
                    hops_traversed=plan.estimated_complexity,
                    path_explanation=self._explain_path(plan),
                    results=[],
                    result_count=0,
                    execution_time_ms=execution_time,
                )

            # Limit final results
            results = result.rows[:self.MAX_FINAL_RESULTS]

            return MultiHopResult(
                hops_traversed=plan.estimated_complexity,
                path_explanation=self._explain_path(plan),
                results=results,
                result_count=len(results),
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.error(f"Multi-hop execution failed: {e}")
            return MultiHopResult(
                hops_traversed=plan.estimated_complexity,
                path_explanation=self._explain_path(plan),
                results=[],
                result_count=0,
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    async def _execute_with_timeout(
        self,
        cypher: str,
        tenant_id: str,
        timeout_ms: int,
    ) -> CypherQueryResult:
        """Execute Cypher query with timeout."""
        import asyncio
        start_time = time.time()

        try:
            # Extract return columns
            return_columns = self._extract_return_columns(cypher)

            # Execute with timeout
            async with self._graph._get_connection() as conn:
                # Set statement timeout
                await conn.execute(f"SET statement_timeout = {timeout_ms};")

                try:
                    results = await asyncio.wait_for(
                        self._graph._execute_cypher(conn, cypher, return_columns),
                        timeout=timeout_ms / 1000.0 + 0.5,  # Small buffer
                    )

                    return CypherQueryResult(
                        query=cypher,
                        success=True,
                        rows=results or [],
                        row_count=len(results) if results else 0,
                        execution_time_ms=(time.time() - start_time) * 1000,
                    )

                except asyncio.TimeoutError:
                    logger.warning(f"Multi-hop query timed out after {timeout_ms}ms")
                    return CypherQueryResult(
                        query=cypher,
                        success=False,
                        error=f"Query timed out after {timeout_ms}ms",
                        execution_time_ms=timeout_ms,
                    )

        except Exception as e:
            return CypherQueryResult(
                query=cypher,
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
            )

    def _explain_path(self, plan: QueryPlan) -> str:
        """Generate human-readable path explanation."""
        if not plan.hops:
            return "Direct query (no traversal needed)"

        explanations = []
        for i, hop in enumerate(plan.hops, 1):
            desc = hop.get("description", f"Step {i}")
            explanations.append(f"Paso {i}: {desc}")

        return "\n".join(explanations)

    def _extract_return_columns(self, cypher_query: str) -> List[tuple]:
        """Extract return columns from Cypher query."""
        import re

        return_match = re.search(
            r"RETURN\s+(.+?)(?:ORDER BY|LIMIT|$)",
            cypher_query,
            re.IGNORECASE | re.DOTALL,
        )

        if not return_match:
            return [("result", "agtype")]

        return_clause = return_match.group(1).strip()

        columns = []
        for col in return_clause.split(","):
            col = col.strip()
            alias_match = re.search(r"\s+as\s+(\w+)\s*$", col, re.IGNORECASE)
            if alias_match:
                col_name = alias_match.group(1)
            else:
                col_name = re.sub(r"[^\w]", "_", col.split(".")[-1])
            columns.append((col_name, "agtype"))

        return columns if columns else [("result", "agtype")]


# Global singleton instance
multihop_executor = MultiHopExecutor()
