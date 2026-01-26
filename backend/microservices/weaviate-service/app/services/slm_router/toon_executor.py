"""
TOON Executor: Execute TOON Plans Against Data Sources

This module executes validated TOON plans by:
1. Routing to the appropriate data source (Apache AGE, Weaviate, or both)
2. Executing parameterized queries with safety guardrails
3. Merging results for HYBRID routes
4. Formatting results for LLM consumption

The executor is designed to be:
- Safe: All queries are parameterized, limits are enforced
- Fast: Async execution, connection pooling, query optimization
- Observable: Detailed logging and metrics for debugging

Version 1.0 - January 2026
"""

import asyncio
import logging
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

from .toon_schema import (
    TOONPlan,
    TOONRoute,
    TOONExecutionResult,
    GraphOperation,
    VectorOperation,
    TOONGuardrails
)

logger = logging.getLogger(__name__)


# =============================================================================
# GRAPH EXECUTOR (Apache AGE)
# =============================================================================

class GraphExecutor:
    """
    Executes graph queries against Apache AGE.

    Uses the existing SIL graph infrastructure for connection management.
    """

    def __init__(self):
        self._graph_provider = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize connection to Apache AGE."""
        if self._initialized:
            return True

        try:
            # Try to import and use existing SIL graph provider
            from ..sil.graph import get_graph_provider

            self._graph_provider = await get_graph_provider()
            if self._graph_provider:
                self._initialized = True
                logger.info("Graph executor initialized with SIL graph provider")
                return True

        except ImportError:
            logger.warning("SIL graph provider not available, trying direct connection")

        # Fallback: direct connection (if SIL is not available)
        try:
            from ..sil.graph.age_provider import AGEProvider
            from ...core.config import settings

            self._graph_provider = AGEProvider(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                graph_name=settings.age_graph_name
            )
            await self._graph_provider.initialize()
            self._initialized = True
            logger.info("Graph executor initialized with direct AGE connection")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize graph executor: {e}")
            return False

    async def execute(
        self,
        plan: TOONPlan,
        timeout_ms: Optional[int] = None
    ) -> Tuple[Optional[Dict[str, Any]], int, float]:
        """
        Execute graph query from TOON plan.

        Returns:
            Tuple of (result_dict, row_count, execution_time_ms)
        """
        if not plan.graph.enabled:
            return None, 0, 0.0

        if not self._initialized:
            if not await self.initialize():
                logger.error("Graph executor not initialized")
                return None, 0, 0.0

        start_time = time.time()
        timeout = timeout_ms or plan.graph.timeout_ms

        try:
            cypher = plan.graph.cypher_template
            params = plan.graph.params.copy()

            # Ensure limit is applied
            if '$limit' not in cypher.lower() and plan.graph.limit:
                if 'LIMIT' not in cypher.upper():
                    cypher = f"{cypher} LIMIT {plan.graph.limit}"

            # Add tenant filter if not present
            tenant_id = plan.tenant_id
            if tenant_id and '$tenant_id' not in params:
                params['tenant_id'] = tenant_id

            logger.debug(f"Executing graph query: {cypher[:200]}... with params: {list(params.keys())}")

            # Execute with timeout
            result = await asyncio.wait_for(
                self._execute_cypher(cypher, params),
                timeout=timeout / 1000.0
            )

            execution_time_ms = (time.time() - start_time) * 1000
            row_count = len(result) if isinstance(result, list) else 1

            # Format result based on operation
            formatted = self._format_result(result, plan.graph.operation)

            logger.info(
                f"Graph query completed: {row_count} rows in {execution_time_ms:.1f}ms, "
                f"operation={plan.graph.operation.value}"
            )

            return formatted, row_count, execution_time_ms

        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.warning(f"Graph query timeout after {execution_time_ms:.1f}ms")
            return {"error": "timeout", "timeout_ms": timeout}, 0, execution_time_ms

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Graph query error: {e}")
            return {"error": str(e)}, 0, execution_time_ms

    async def _execute_cypher(
        self,
        cypher: str,
        params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Execute Cypher query against Apache AGE."""
        if self._graph_provider:
            return await self._graph_provider.execute_cypher(cypher, params)

        # Fallback: return empty if no provider
        logger.warning("No graph provider available for execution")
        return []

    def _format_result(
        self,
        result: Any,
        operation: GraphOperation
    ) -> Dict[str, Any]:
        """Format graph result based on operation type."""
        if not result:
            if operation == GraphOperation.COUNT:
                return {"count": 0}
            elif operation == GraphOperation.EXISTS:
                return {"exists": False}
            return {"items": [], "count": 0}

        if operation == GraphOperation.COUNT:
            # Extract count from result
            if isinstance(result, list) and len(result) > 0:
                first_row = result[0]
                if isinstance(first_row, dict):
                    # Look for count key
                    for key in ['count', 'total', 'cnt', 'n']:
                        if key in first_row:
                            return {"count": int(first_row[key])}
                    # If no count key, return row count
                    return {"count": len(result)}
            return {"count": 0}

        elif operation == GraphOperation.EXISTS:
            exists = bool(result) and len(result) > 0
            return {"exists": exists}

        elif operation == GraphOperation.LIST:
            items = []
            if isinstance(result, list):
                for row in result[:TOONGuardrails.GRAPH["limit"]["max"]]:
                    if isinstance(row, dict):
                        # Extract meaningful properties
                        item = {}
                        for key in ['id', 'document_id', 'title', 'name', 'folder_path', 'semantic_type', 'type']:
                            if key in row:
                                item[key] = row[key]
                        if not item:
                            item = row
                        items.append(item)
            return {"items": items, "count": len(items)}

        elif operation == GraphOperation.TRAVERSE:
            # Return paths/relationships
            return {"paths": result if isinstance(result, list) else [], "count": len(result) if result else 0}

        elif operation == GraphOperation.AGGREGATE:
            # Return aggregation results as-is
            return {"aggregation": result[0] if isinstance(result, list) and result else result}

        # Default: return as-is
        return {"result": result}


# =============================================================================
# VECTOR EXECUTOR (Weaviate)
# =============================================================================

class VectorExecutor:
    """
    Executes vector queries against Weaviate.

    Uses the existing RAG pipeline for semantic search.
    """

    def __init__(self):
        self._weaviate_client = None
        self._rag_pipeline = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize connection to Weaviate."""
        if self._initialized:
            return True

        try:
            # Try to use existing weaviate service
            from ..weaviate_service import get_weaviate_client

            self._weaviate_client = get_weaviate_client()
            if self._weaviate_client:
                self._initialized = True
                logger.info("Vector executor initialized with weaviate service")
                return True

        except ImportError:
            logger.warning("Weaviate service not available")

        except Exception as e:
            logger.error(f"Failed to initialize vector executor: {e}")

        return False

    async def execute(
        self,
        plan: TOONPlan,
        query_text: str
    ) -> Tuple[List[Dict[str, Any]], int, float]:
        """
        Execute vector query from TOON plan.

        Returns:
            Tuple of (results_list, result_count, execution_time_ms)
        """
        if not plan.vector.enabled:
            return [], 0, 0.0

        if not self._initialized:
            if not await self.initialize():
                logger.error("Vector executor not initialized")
                return [], 0, 0.0

        start_time = time.time()

        try:
            # Build Weaviate query
            top_k = min(plan.vector.top_k, TOONGuardrails.VECTOR["top_k"]["max"])
            filters = self._build_filters(plan)

            # Determine collection based on tenant scope
            if plan.vector.filters.tenant_scope:
                collection_name = self._get_tenant_collection(plan.tenant_id)
            else:
                collection_name = self._get_public_collection()

            logger.debug(
                f"Executing vector search: collection={collection_name}, "
                f"top_k={top_k}, filters={list(filters.keys()) if filters else 'none'}"
            )

            # Execute search
            results = await self._execute_search(
                collection_name=collection_name,
                query_text=query_text,
                top_k=top_k,
                filters=filters,
                rerank=plan.vector.rerank
            )

            execution_time_ms = (time.time() - start_time) * 1000
            result_count = len(results)

            logger.info(
                f"Vector search completed: {result_count} results in {execution_time_ms:.1f}ms"
            )

            return results, result_count, execution_time_ms

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Vector search error: {e}")
            return [], 0, execution_time_ms

    def _build_filters(self, plan: TOONPlan) -> Dict[str, Any]:
        """Build Weaviate filters from TOON plan."""
        filters = {}

        vector_filters = plan.vector.filters

        if vector_filters.document_types:
            filters['semantic_type'] = vector_filters.document_types

        if vector_filters.folder_paths:
            filters['folder_path'] = vector_filters.folder_paths

        if vector_filters.domains:
            filters['domain'] = vector_filters.domains

        if vector_filters.date_range:
            if vector_filters.date_range.start:
                filters['created_after'] = vector_filters.date_range.start.isoformat()
            if vector_filters.date_range.end:
                filters['created_before'] = vector_filters.date_range.end.isoformat()

        # Always add tenant filter for tenant scope
        if vector_filters.tenant_scope and plan.tenant_id:
            filters['tenant_id'] = plan.tenant_id

        return filters

    def _get_tenant_collection(self, tenant_id: str) -> str:
        """Get the collection name for a tenant."""
        # Use the standard collection naming convention
        from ...core.config import settings
        prefix = settings.collection_prefix
        return f"{prefix}documents"

    def _get_public_collection(self) -> str:
        """Get the public knowledge collection name."""
        from ...core.config import settings
        prefix = settings.collection_prefix
        return f"{prefix}public_knowledge"

    async def _execute_search(
        self,
        collection_name: str,
        query_text: str,
        top_k: int,
        filters: Dict[str, Any],
        rerank: bool = False
    ) -> List[Dict[str, Any]]:
        """Execute semantic search in Weaviate."""
        if not self._weaviate_client:
            return []

        try:
            # Use the RAG pipeline if available for better results
            try:
                from ..rag import get_rag_pipeline
                rag = get_rag_pipeline()
                if rag:
                    results = await rag.retrieve(
                        query=query_text,
                        tenant_id=filters.get('tenant_id', ''),
                        top_k=top_k,
                        filters=filters
                    )
                    return self._format_rag_results(results)
            except ImportError:
                pass

            # Direct Weaviate query as fallback
            collection = self._weaviate_client.collections.get(collection_name)
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: collection.query.near_text(
                    query=query_text,
                    limit=top_k,
                    return_metadata=['distance', 'certainty']
                )
            )

            return self._format_weaviate_results(response)

        except Exception as e:
            logger.error(f"Weaviate search error: {e}")
            return []

    def _format_rag_results(self, results: Any) -> List[Dict[str, Any]]:
        """Format RAG pipeline results."""
        formatted = []
        if hasattr(results, 'chunks'):
            for chunk in results.chunks:
                formatted.append({
                    "id": getattr(chunk, 'id', ''),
                    "document_id": getattr(chunk, 'document_id', ''),
                    "title": getattr(chunk, 'title', getattr(chunk, 'filename', 'Untitled')),
                    "content": getattr(chunk, 'content', getattr(chunk, 'text', '')),
                    "score": getattr(chunk, 'score', getattr(chunk, 'relevance', 0.0)),
                    "metadata": getattr(chunk, 'metadata', {})
                })
        elif isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    formatted.append(item)
        return formatted

    def _format_weaviate_results(self, response: Any) -> List[Dict[str, Any]]:
        """Format direct Weaviate results."""
        formatted = []
        if hasattr(response, 'objects'):
            for obj in response.objects:
                props = obj.properties if hasattr(obj, 'properties') else {}
                formatted.append({
                    "id": str(obj.uuid) if hasattr(obj, 'uuid') else '',
                    "document_id": props.get('document_id', ''),
                    "title": props.get('title', props.get('filename', 'Untitled')),
                    "content": props.get('content', props.get('text', '')),
                    "score": 1 - (obj.metadata.distance if hasattr(obj, 'metadata') and hasattr(obj.metadata, 'distance') else 0),
                    "metadata": props
                })
        return formatted


# =============================================================================
# MAIN TOON EXECUTOR
# =============================================================================

class TOONExecutor:
    """
    Main executor for TOON plans.

    Coordinates graph and vector execution, handles routing,
    and produces formatted results for the LLM.
    """

    def __init__(self):
        self._graph_executor = GraphExecutor()
        self._vector_executor = VectorExecutor()
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize all executors."""
        if self._initialized:
            return True

        graph_ok = await self._graph_executor.initialize()
        vector_ok = await self._vector_executor.initialize()

        # We can continue if at least one is available
        self._initialized = graph_ok or vector_ok

        if self._initialized:
            logger.info(
                f"TOON executor initialized: graph={graph_ok}, vector={vector_ok}"
            )
        else:
            logger.error("TOON executor initialization failed: no backends available")

        return self._initialized

    async def execute(self, plan: TOONPlan) -> TOONExecutionResult:
        """
        Execute a TOON plan and return results.

        This is the main entry point for plan execution.
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        result = TOONExecutionResult(plan=plan)

        try:
            # Handle clarification route (no execution needed)
            if plan.route == TOONRoute.ASK_CLARIFY:
                result.clarification_question = plan.clarify.question
                result.clarification_options = plan.clarify.options
                result.total_execution_time_ms = (time.time() - start_time) * 1000
                return result

            # Execute based on route
            if plan.route == TOONRoute.GRAPH_ONLY:
                await self._execute_graph_only(plan, result)

            elif plan.route == TOONRoute.VECTOR_ONLY:
                await self._execute_vector_only(plan, result)

            elif plan.route == TOONRoute.HYBRID:
                await self._execute_hybrid(plan, result)

            # Format context for LLM
            result.format_context()

            result.total_execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"TOON execution completed: route={plan.route.value}, "
                f"time={result.total_execution_time_ms:.1f}ms, "
                f"graph_rows={result.graph_row_count}, vector_results={result.vector_result_count}"
            )

            return result

        except Exception as e:
            logger.error(f"TOON execution error: {e}")
            result.success = False
            result.error = str(e)
            result.total_execution_time_ms = (time.time() - start_time) * 1000
            return result

    async def _execute_graph_only(
        self,
        plan: TOONPlan,
        result: TOONExecutionResult
    ):
        """Execute graph-only route."""
        graph_result, row_count, exec_time = await self._graph_executor.execute(plan)
        result.graph_result = graph_result
        result.graph_row_count = row_count
        result.graph_execution_time_ms = exec_time

        if graph_result and 'error' in graph_result:
            result.success = False
            result.error = graph_result.get('error')

    async def _execute_vector_only(
        self,
        plan: TOONPlan,
        result: TOONExecutionResult
    ):
        """Execute vector-only route."""
        vector_results, result_count, exec_time = await self._vector_executor.execute(
            plan,
            plan.original_query
        )
        result.vector_results = vector_results
        result.vector_result_count = result_count
        result.vector_execution_time_ms = exec_time

    async def _execute_hybrid(
        self,
        plan: TOONPlan,
        result: TOONExecutionResult
    ):
        """Execute hybrid route (graph + vector in parallel)."""
        # Execute both in parallel
        graph_task = self._graph_executor.execute(plan)
        vector_task = self._vector_executor.execute(plan, plan.original_query)

        graph_results, vector_results = await asyncio.gather(
            graph_task,
            vector_task,
            return_exceptions=True
        )

        # Process graph results
        if isinstance(graph_results, tuple):
            result.graph_result, result.graph_row_count, result.graph_execution_time_ms = graph_results
        elif isinstance(graph_results, Exception):
            logger.error(f"Graph execution error in hybrid: {graph_results}")
            result.graph_result = {"error": str(graph_results)}

        # Process vector results
        if isinstance(vector_results, tuple):
            result.vector_results, result.vector_result_count, result.vector_execution_time_ms = vector_results
        elif isinstance(vector_results, Exception):
            logger.error(f"Vector execution error in hybrid: {vector_results}")

    async def health_check(self) -> Dict[str, Any]:
        """Check executor health."""
        return {
            "initialized": self._initialized,
            "graph_available": self._graph_executor._initialized,
            "vector_available": self._vector_executor._initialized
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_toon_executor: Optional[TOONExecutor] = None


def get_toon_executor() -> TOONExecutor:
    """Get the singleton TOON executor instance."""
    global _toon_executor
    if _toon_executor is None:
        _toon_executor = TOONExecutor()
    return _toon_executor


async def initialize_toon_executor() -> TOONExecutor:
    """Initialize the singleton TOON executor."""
    global _toon_executor
    _toon_executor = TOONExecutor()
    await _toon_executor.initialize()
    return _toon_executor
