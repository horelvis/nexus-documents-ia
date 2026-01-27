"""
SLM Router: Main Router for Structured Query Planning

This is the main entry point for the SLM Router system.
It coordinates all components to:
1. Generate TOON plans using the SLM
2. Execute plans against Apache AGE and Weaviate
3. Manage conversation history for contextual queries
4. Provide tenant-aware schema context

The SLM Router replaces the fragmented routing approach with a single,
unified planning system that generates deterministic, validated plans.

Usage:
    router = get_slm_router()
    await router.initialize()

    # Plan only
    plan = await router.plan(query, tenant_id, session_id)

    # Plan and execute
    result = await router.route(query, tenant_id, session_id)

Version 1.0 - January 2026
"""

import asyncio
import json
import logging
import time
from typing import Optional, Dict, Any, List, Tuple, AsyncGenerator, Union
from datetime import datetime

from .toon_schema import (
    TOONPlan,
    TOONRoute,
    TOONExecutionResult,
    TOONPlanBuilder,
    GraphOperation,
    VectorOperation,
    ExtractedEntity,
    EntitySource,
    ThinkingStep,
    ChainOfThought
)
from .slm_client import SLMClient, SLMConfig, get_slm_client, initialize_slm_client
from .toon_executor import TOONExecutor, get_toon_executor, initialize_toon_executor
from .tenant_schema import TenantSchemaProvider, get_schema_provider, initialize_schema_provider
from .history_manager import HistoryManager, get_history_manager, initialize_history_manager

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class SLMRouterConfig:
    """Configuration for the SLM Router."""

    def __init__(
        self,
        enabled: bool = True,
        use_redis: bool = True,
        slm_config: Optional[SLMConfig] = None,
        fallback_to_vector: bool = True,
        min_confidence_threshold: float = 0.4,
        collect_training_data: bool = True
    ):
        self.enabled = enabled
        self.use_redis = use_redis
        self.slm_config = slm_config or SLMConfig()
        self.fallback_to_vector = fallback_to_vector
        self.min_confidence_threshold = min_confidence_threshold
        self.collect_training_data = collect_training_data


# =============================================================================
# MAIN SLM ROUTER
# =============================================================================

class SLMRouter:
    """
    Main SLM Router for structured query planning.

    This class orchestrates:
    - SLM Client: Generates TOON plans
    - TOON Executor: Executes plans against data sources
    - Schema Provider: Provides tenant context for planning
    - History Manager: Manages conversation state
    """

    def __init__(self, config: Optional[SLMRouterConfig] = None):
        self.config = config or SLMRouterConfig()

        # Components (lazy initialized)
        self._slm_client: Optional[SLMClient] = None
        self._executor: Optional[TOONExecutor] = None
        self._schema_provider: Optional[TenantSchemaProvider] = None
        self._history_manager: Optional[HistoryManager] = None

        self._initialized = False

        # Metrics
        self._metrics = {
            "total_requests": 0,
            "plans_generated": 0,
            "executions_completed": 0,
            "fallbacks_used": 0,
            "average_plan_time_ms": 0.0,
            "average_execution_time_ms": 0.0
        }

    async def initialize(self) -> bool:
        """
        Initialize all SLM Router components.

        Returns True if initialization succeeds.
        """
        if self._initialized:
            return True

        if not self.config.enabled:
            logger.info("SLM Router is disabled by configuration")
            return False

        try:
            logger.info("Initializing SLM Router components...")

            # Initialize components in parallel
            init_tasks = [
                initialize_slm_client(self.config.slm_config),
                initialize_toon_executor(),
                initialize_schema_provider(self.config.use_redis),
                initialize_history_manager(self.config.use_redis)
            ]

            results = await asyncio.gather(*init_tasks, return_exceptions=True)

            # Check results
            slm_client, executor, schema_provider, history_manager = results

            if isinstance(slm_client, Exception):
                logger.error(f"SLM client initialization failed: {slm_client}")
                slm_client = get_slm_client()
            self._slm_client = slm_client

            if isinstance(executor, Exception):
                logger.error(f"TOON executor initialization failed: {executor}")
                executor = get_toon_executor()
            self._executor = executor

            if isinstance(schema_provider, Exception):
                logger.error(f"Schema provider initialization failed: {schema_provider}")
                schema_provider = get_schema_provider()
            self._schema_provider = schema_provider

            if isinstance(history_manager, Exception):
                logger.error(f"History manager initialization failed: {history_manager}")
                history_manager = get_history_manager()
            self._history_manager = history_manager

            self._initialized = True
            logger.info("SLM Router initialized successfully")
            return True

        except Exception as e:
            logger.error(f"SLM Router initialization failed: {e}")
            return False

    async def plan(
        self,
        query: str,
        tenant_id: str,
        session_id: str = ""
    ) -> TOONPlan:
        """
        Generate a TOON plan for the given query.

        This is the planning phase only - no execution.

        Args:
            query: User's natural language query
            tenant_id: Tenant identifier for isolation
            session_id: Session identifier for history (optional)

        Returns:
            Validated TOONPlan
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        self._metrics["total_requests"] += 1

        try:
            # Get tenant schema context
            tenant_schema = await self._schema_provider.get_prompt_context(tenant_id)

            # Get conversation history
            conversation_history = ""
            last_toon_plan = ""
            reference_resolution = None

            if session_id:
                conversation_history = await self._history_manager.format_for_prompt(
                    session_id, tenant_id
                )
                last_toon_plan = await self._history_manager.get_last_toon_plan(
                    session_id, tenant_id
                )

                # Resolve references (is this a continuation?)
                reference_resolution = await self._history_manager.resolve_references(
                    query, session_id, tenant_id
                )

            # Check if this is a simple reference/continuation
            if reference_resolution and reference_resolution.get("is_continuation"):
                plan = self._create_continuation_plan(
                    query, reference_resolution, tenant_id, session_id
                )
                if plan:
                    self._update_plan_metrics(start_time)
                    return plan

            # Generate plan using SLM
            plan = await self._slm_client.generate_plan(
                query=query,
                tenant_schema=tenant_schema,
                conversation_history=conversation_history,
                last_toon_plan=last_toon_plan or "",
                tenant_id=tenant_id,
                session_id=session_id
            )

            # Augment plan with resolved entities from history
            if reference_resolution and reference_resolution.get("resolved_entities"):
                plan = self._augment_with_history_entities(plan, reference_resolution)

            # Apply confidence threshold
            if plan.confidence < self.config.min_confidence_threshold:
                logger.info(
                    f"Low confidence plan ({plan.confidence:.2f}), "
                    f"falling back to VECTOR_ONLY"
                )
                if self.config.fallback_to_vector:
                    plan.route = TOONRoute.VECTOR_ONLY
                    plan.vector.enabled = True
                    plan.reasoning = f"Low confidence ({plan.confidence:.2f}), fallback to vector search"
                    self._metrics["fallbacks_used"] += 1

            self._update_plan_metrics(start_time)
            self._metrics["plans_generated"] += 1

            logger.info(
                f"TOON plan generated: route={plan.route.value}, "
                f"confidence={plan.confidence:.2f}, "
                f"entities={len(plan.entities)}, "
                f"time={self._metrics['average_plan_time_ms']:.1f}ms"
            )

            return plan

        except Exception as e:
            logger.error(f"Plan generation error: {e}")
            # Return fallback plan
            return TOONPlanBuilder()\
                .with_route(TOONRoute.VECTOR_ONLY, confidence=0.3)\
                .with_vector_query(VectorOperation.SEMANTIC_SEARCH, top_k=5)\
                .with_context(
                    original_query=query,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    reasoning=f"Fallback due to error: {str(e)}"
                )\
                .build()

    async def execute(self, plan: TOONPlan) -> TOONExecutionResult:
        """
        Execute a TOON plan and return results.

        Args:
            plan: Validated TOON plan to execute

        Returns:
            TOONExecutionResult with data for LLM
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()

        try:
            result = await self._executor.execute(plan)
            self._metrics["executions_completed"] += 1

            execution_time = (time.time() - start_time) * 1000
            self._update_execution_metrics(execution_time)

            logger.info(
                f"TOON execution completed: route={plan.route.value}, "
                f"success={result.success}, "
                f"time={execution_time:.1f}ms"
            )

            return result

        except Exception as e:
            logger.error(f"TOON execution error: {e}")
            return TOONExecutionResult(
                plan=plan,
                success=False,
                error=str(e)
            )

    async def route(
        self,
        query: str,
        tenant_id: str,
        session_id: str = ""
    ) -> TOONExecutionResult:
        """
        Plan and execute in one call.

        This is the main entry point for most use cases.

        Args:
            query: User's natural language query
            tenant_id: Tenant identifier
            session_id: Session identifier (optional)

        Returns:
            TOONExecutionResult with data for LLM
        """
        # Generate plan
        plan = await self.plan(query, tenant_id, session_id)

        # Handle ASK_CLARIFY without execution
        if plan.route == TOONRoute.ASK_CLARIFY:
            return TOONExecutionResult(
                plan=plan,
                success=True,
                clarification_question=plan.clarify.question,
                clarification_options=plan.clarify.options
            )

        # Execute plan
        result = await self.execute(plan)

        # Store in history (async, don't wait)
        if session_id:
            task = asyncio.create_task(
                self._store_in_history(session_id, tenant_id, query, plan, result)
            )
            task.add_done_callback(self._handle_background_task_error)

        # Collect training data if enabled
        if self.config.collect_training_data:
            task = asyncio.create_task(
                self._collect_training_example(query, plan, result)
            )
            task.add_done_callback(self._handle_background_task_error)

        return result

    async def plan_stream(
        self,
        query: str,
        tenant_id: str,
        session_id: str = ""
    ) -> AsyncGenerator[Union[ThinkingStep, TOONPlan], None]:
        """
        Generate a TOON plan with streaming chain-of-thought.

        Yields ThinkingStep objects as the model reasons,
        then yields the final TOONPlan.

        This enables the UI to show visible reasoning progress.
        """
        if not self._initialized:
            await self.initialize()

        start_time = time.time()
        self._metrics["total_requests"] += 1

        try:
            # Get tenant schema context
            tenant_schema = await self._schema_provider.get_prompt_context(tenant_id)

            # Get conversation history
            conversation_history = ""
            last_toon_plan = ""

            if session_id:
                conversation_history = await self._history_manager.format_for_prompt(
                    session_id, tenant_id
                )
                last_toon_plan = await self._history_manager.get_last_toon_plan(
                    session_id, tenant_id
                )

            # Stream plan generation with CoT
            async for item in self._slm_client.generate_plan_stream(
                query=query,
                tenant_schema=tenant_schema,
                conversation_history=conversation_history,
                last_toon_plan=last_toon_plan or "",
                tenant_id=tenant_id,
                session_id=session_id
            ):
                if isinstance(item, ThinkingStep):
                    # Yield thinking steps directly
                    yield item
                elif isinstance(item, TOONPlan):
                    # Apply confidence threshold and guardrails
                    plan = item
                    if plan.confidence < self.config.min_confidence_threshold:
                        if self.config.fallback_to_vector:
                            plan.route = TOONRoute.VECTOR_ONLY
                            plan.vector.enabled = True
                            plan.reasoning = f"Low confidence ({plan.confidence:.2f}), fallback to vector search"
                            self._metrics["fallbacks_used"] += 1

                    self._update_plan_metrics(start_time)
                    self._metrics["plans_generated"] += 1
                    yield plan

        except Exception as e:
            logger.error(f"Plan stream error: {e}")
            # Yield fallback plan
            yield TOONPlanBuilder()\
                .with_route(TOONRoute.VECTOR_ONLY, confidence=0.3)\
                .with_vector_query(VectorOperation.SEMANTIC_SEARCH, top_k=5)\
                .with_context(
                    original_query=query,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    reasoning=f"Fallback due to error: {str(e)}"
                )\
                .build()

    async def route_stream(
        self,
        query: str,
        tenant_id: str,
        session_id: str = ""
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Plan and execute with streaming SSE events.

        Yields events in the format:
        - {"event": "thinking_start", "data": {"message": "..."}}
        - {"event": "thinking_step", "data": {"step": 1, "type": "...", ...}}
        - {"event": "plan_ready", "data": {"route": "...", "confidence": ...}}
        - {"event": "execution_start", "data": {"message": "...", "route": "..."}}
        - {"event": "execution_complete", "data": {"success": ..., "context_for_llm": ..., "time_ms": ...}}
        """
        # Yield thinking start event
        yield {
            "event": "thinking_start",
            "data": {"message": "Analizando consulta..."}
        }

        plan: Optional[TOONPlan] = None
        thinking_steps: List[ThinkingStep] = []

        # Stream planning phase
        async for item in self.plan_stream(query, tenant_id, session_id):
            if isinstance(item, ThinkingStep):
                thinking_steps.append(item)
                yield {
                    "event": "thinking_step",
                    "data": {
                        "step": item.step_number,
                        "type": item.step_type.value,
                        "content": item.content,
                        "entities": item.entities_found,
                        "confidence": item.confidence
                    }
                }
            elif isinstance(item, TOONPlan):
                plan = item
                yield {
                    "event": "plan_ready",
                    "data": {
                        "route": plan.route.value,
                        "confidence": plan.confidence,
                        "entities_count": len(plan.entities),
                        "reasoning": plan.reasoning
                    }
                }

        if not plan:
            yield {
                "event": "error",
                "data": {"error": "Failed to generate plan"}
            }
            return

        # Handle ASK_CLARIFY without execution
        if plan.route == TOONRoute.ASK_CLARIFY:
            yield {
                "event": "execution_complete",
                "data": {
                    "success": True,
                    "clarification_question": plan.clarify.question,
                    "clarification_options": plan.clarify.options,
                    "time_ms": 0
                }
            }
            return

        # Yield execution start event
        yield {
            "event": "execution_start",
            "data": {
                "message": f"Ejecutando en {plan.route.value.lower().replace('_', ' ')}...",
                "route": plan.route.value
            }
        }

        # Execute the plan
        start_time = time.time()
        result = await self.execute(plan)
        execution_time_ms = (time.time() - start_time) * 1000

        # Store in history (async, don't wait)
        if session_id:
            task = asyncio.create_task(
                self._store_in_history(session_id, tenant_id, query, plan, result)
            )
            task.add_done_callback(self._handle_background_task_error)

        # Yield execution complete event
        yield {
            "event": "execution_complete",
            "data": {
                "success": result.success,
                "context_for_llm": result.context_for_llm,
                "graph_result": result.graph_result,
                "graph_row_count": result.graph_row_count,
                "vector_result_count": result.vector_result_count,
                "time_ms": execution_time_ms,
                "error": result.error
            }
        }

    def _create_continuation_plan(
        self,
        query: str,
        reference_resolution: Dict[str, Any],
        tenant_id: str,
        session_id: str
    ) -> Optional[TOONPlan]:
        """
        Create a plan for a continuation/reference query.

        Uses history context to create a plan without SLM.
        """
        resolved_entities = reference_resolution.get("resolved_entities", [])
        suggested_operation = reference_resolution.get("suggested_operation")
        suggested_limit = reference_resolution.get("suggested_limit", 50)

        if not resolved_entities:
            return None

        builder = TOONPlanBuilder()\
            .with_route(TOONRoute.GRAPH_ONLY, confidence=0.85)\
            .with_context(
                original_query=query,
                tenant_id=tenant_id,
                session_id=session_id,
                reasoning="Continuation from previous turn"
            )

        # Add resolved entities
        for entity in resolved_entities:
            builder.with_entity(
                name=entity.get("name", ""),
                entity_type=entity.get("type", ""),
                graph_label=entity.get("graph_label"),
                source=EntitySource.HISTORY
            )

        # Configure graph query
        operation = GraphOperation(suggested_operation) if suggested_operation else GraphOperation.LIST

        # Build Cypher template based on entity type
        primary_entity = resolved_entities[0] if resolved_entities else {}
        entity_type = primary_entity.get("type", "client")
        entity_name = primary_entity.get("name", "")

        if entity_type == "client":
            cypher = """
                MATCH (c:Entity {name: $entity_name, type: 'client'})
                -[:HAS_DOCUMENT]->(d:structural_document)
                RETURN d.document_id as id, d.title as title, d.semantic_type as type
                LIMIT $limit
            """
        else:
            cypher = """
                MATCH (d:structural_document)
                WHERE d.tenant_id = $tenant_id
                RETURN d.document_id as id, d.title as title, d.semantic_type as type
                LIMIT $limit
            """

        builder.with_graph_query(
            operation=operation,
            cypher_template=cypher,
            params={"entity_name": entity_name, "tenant_id": tenant_id, "limit": suggested_limit},
            limit=suggested_limit
        )

        return builder.build()

    def _augment_with_history_entities(
        self,
        plan: TOONPlan,
        reference_resolution: Dict[str, Any]
    ) -> TOONPlan:
        """Augment plan with entities resolved from history."""
        resolved_entities = reference_resolution.get("resolved_entities", [])

        # Don't duplicate entities already in plan
        existing_names = {e.name.lower() for e in plan.entities}

        for entity_dict in resolved_entities:
            name = entity_dict.get("name", "")
            if name.lower() not in existing_names:
                plan.entities.append(ExtractedEntity(
                    name=name,
                    type=entity_dict.get("type", "unknown"),
                    graph_label=entity_dict.get("graph_label"),
                    source=EntitySource.HISTORY,
                    confidence=0.8
                ))

        return plan

    async def _store_in_history(
        self,
        session_id: str,
        tenant_id: str,
        query: str,
        plan: TOONPlan,
        result: TOONExecutionResult
    ):
        """Store the turn in conversation history."""
        try:
            # Create result summary
            if plan.route == TOONRoute.GRAPH_ONLY and result.graph_result:
                if "count" in result.graph_result:
                    result_summary = f"count={result.graph_result['count']}"
                elif "items" in result.graph_result:
                    result_summary = f"found {len(result.graph_result['items'])} items"
                else:
                    result_summary = f"rows={result.graph_row_count}"
            elif plan.route == TOONRoute.VECTOR_ONLY:
                result_summary = f"found {result.vector_result_count} docs"
            elif plan.route == TOONRoute.HYBRID:
                result_summary = f"graph={result.graph_row_count}, vector={result.vector_result_count}"
            else:
                result_summary = ""

            await self._history_manager.add_turn(
                session_id=session_id,
                tenant_id=tenant_id,
                query=query,
                plan=plan,
                result_summary=result_summary
            )
        except Exception as e:
            logger.warning(f"Failed to store in history: {e}")

    async def _collect_training_example(
        self,
        query: str,
        plan: TOONPlan,
        result: TOONExecutionResult
    ):
        """
        Collect training example for future fine-tuning.

        Stores successful query→route mappings in Redis for later export.
        Only collects when execution was successful (good signal).
        """
        # Only collect successful examples (good training signal)
        if not result.success:
            return

        try:
            # Create training example
            example = {
                "query": query,
                "route": plan.route.value,
                "confidence": plan.confidence,
                "entities": [e.model_dump() for e in plan.entities] if plan.entities else [],
                "tenant_id": plan.tenant_id,
                "timestamp": time.time(),
                "execution_success": result.success,
                "execution_time_ms": result.total_execution_time_ms
            }

            # Store in Redis list for batch export
            # Key: slm:training:{tenant_id}
            redis_key = f"slm:training:{plan.tenant_id or 'global'}"

            if self._history_manager and self._history_manager._redis:
                await self._history_manager._redis.lpush(
                    redis_key,
                    json.dumps(example)
                )
                # Keep max 10000 examples per tenant
                await self._history_manager._redis.ltrim(redis_key, 0, 9999)

                logger.debug(f"Collected training example: {query[:50]}... → {plan.route.value}")
        except Exception as e:
            logger.warning(f"Failed to collect training example: {e}")

    def _handle_background_task_error(self, task: asyncio.Task):
        """
        Handle errors from background tasks (history storage, training collection).

        This callback prevents silent failures in fire-and-forget tasks by logging
        any exceptions that occur during execution.
        """
        try:
            if task.exception():
                logger.error(f"Background task failed: {task.exception()}")
        except asyncio.CancelledError:
            pass  # Task was cancelled, not an error
        except asyncio.InvalidStateError:
            pass  # Task not done yet (shouldn't happen in callback)

    def _update_plan_metrics(self, start_time: float):
        """Update planning metrics."""
        elapsed = (time.time() - start_time) * 1000
        n = self._metrics["plans_generated"]
        if n == 0:
            self._metrics["average_plan_time_ms"] = elapsed
        else:
            # Running average
            self._metrics["average_plan_time_ms"] = (
                self._metrics["average_plan_time_ms"] * n + elapsed
            ) / (n + 1)

    def _update_execution_metrics(self, elapsed_ms: float):
        """Update execution metrics."""
        n = self._metrics["executions_completed"]
        if n == 0:
            self._metrics["average_execution_time_ms"] = elapsed_ms
        else:
            self._metrics["average_execution_time_ms"] = (
                self._metrics["average_execution_time_ms"] * n + elapsed_ms
            ) / (n + 1)

    async def health_check(self) -> Dict[str, Any]:
        """Get health status of the router."""
        slm_health = await self._slm_client.health_check() if self._slm_client else {"status": "not_initialized"}
        executor_health = await self._executor.health_check() if self._executor else {"status": "not_initialized"}

        return {
            "initialized": self._initialized,
            "enabled": self.config.enabled,
            "slm": slm_health,
            "executor": executor_health,
            "metrics": self._metrics
        }

    async def close(self):
        """Close all resources."""
        if self._slm_client:
            await self._slm_client.close()
        if self._schema_provider:
            await self._schema_provider.close()
        if self._history_manager:
            await self._history_manager.close()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_slm_router: Optional[SLMRouter] = None


def get_slm_router() -> SLMRouter:
    """Get the singleton SLM router instance."""
    global _slm_router
    if _slm_router is None:
        _slm_router = SLMRouter()
    return _slm_router


async def initialize_slm_router(config: Optional[SLMRouterConfig] = None) -> SLMRouter:
    """Initialize the singleton SLM router."""
    global _slm_router
    _slm_router = SLMRouter(config)
    await _slm_router.initialize()
    return _slm_router
