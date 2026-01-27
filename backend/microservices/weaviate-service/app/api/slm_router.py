"""
SLM Router API Endpoints

REST API for the SLM Router system, providing:
- Query routing with TOON plans
- Plan generation (planning only, no execution)
- Health and metrics endpoints
- History management

Usage:
    POST /slm/route - Full route (plan + execute)
    POST /slm/plan - Plan only
    GET /slm/health - Health check
    DELETE /slm/history/{session_id} - Clear session history

Version 1.0 - January 2026
"""

import logging
import json
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..core.config import settings
from ..core.security import verify_api_key
from ..services.slm_router import (
    get_slm_router,
    TOONPlan,
    TOONRoute,
    TOONExecutionResult,
    SLMRouterConfig,
    SLMConfig
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/slm", tags=["SLM Router"])


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class RouteRequest(BaseModel):
    """Request for query routing."""
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    session_id: str = Field(default="", description="Session ID for conversation history")


class PlanRequest(BaseModel):
    """Request for plan generation only."""
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    session_id: str = Field(default="", description="Session ID for conversation history")


class StreamRouteRequest(BaseModel):
    """Request for streaming query routing with chain-of-thought."""
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    session_id: str = Field(default="", description="Session ID for conversation history")


class RouteResponse(BaseModel):
    """Response from route endpoint."""
    success: bool
    route: str = Field(description="TOON route used: GRAPH_ONLY, VECTOR_ONLY, HYBRID, ASK_CLARIFY")
    confidence: float = Field(description="Confidence in routing decision (0-1)")

    # For regular routes
    context_for_llm: str = Field(default="", description="Formatted context for LLM consumption")
    graph_result: Optional[Dict[str, Any]] = Field(default=None, description="Graph query result")
    vector_results: List[Dict[str, Any]] = Field(default_factory=list, description="Vector search results")

    # For ASK_CLARIFY route
    clarification_question: Optional[str] = Field(default=None, description="Clarification question")
    clarification_options: List[str] = Field(default_factory=list, description="Suggested options")

    # Metadata
    execution_time_ms: float = Field(description="Total execution time in milliseconds")
    plan_summary: Dict[str, Any] = Field(default_factory=dict, description="TOON plan summary")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class PlanResponse(BaseModel):
    """Response from plan endpoint."""
    success: bool
    plan: Dict[str, Any] = Field(description="Full TOON plan as JSON")
    route: str = Field(description="Selected route")
    confidence: float = Field(description="Confidence in routing decision")
    entities: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted entities")
    reasoning: str = Field(default="", description="Explanation of routing decision")


class HealthResponse(BaseModel):
    """Response from health endpoint."""
    status: str
    initialized: bool
    enabled: bool
    slm: Dict[str, Any]
    executor: Dict[str, Any]
    metrics: Dict[str, Any]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/route", response_model=RouteResponse)
async def route_query(
    request: RouteRequest,
    _: str = Depends(verify_api_key)
) -> RouteResponse:
    """
    Route a query through the SLM Router.

    This endpoint:
    1. Generates a TOON plan using the SLM
    2. Executes the plan against appropriate data sources
    3. Returns formatted context for LLM consumption

    The response includes the execution results formatted for direct
    use in an LLM prompt, along with metadata about the routing decision.
    """
    if not settings.slm_router_enabled:
        raise HTTPException(
            status_code=503,
            detail="SLM Router is disabled"
        )

    try:
        slm_router = get_slm_router()

        # Ensure initialized
        if not slm_router._initialized:
            await slm_router.initialize()

        # Route the query
        result = await slm_router.route(
            query=request.query,
            tenant_id=request.tenant_id,
            session_id=request.session_id
        )

        return RouteResponse(
            success=result.success,
            route=result.plan.route.value,
            confidence=result.plan.confidence,
            context_for_llm=result.context_for_llm,
            graph_result=result.graph_result,
            vector_results=result.vector_results,
            clarification_question=result.clarification_question,
            clarification_options=result.clarification_options,
            execution_time_ms=result.total_execution_time_ms,
            plan_summary=result.plan.get_execution_summary(),
            error=result.error
        )

    except Exception as e:
        logger.error(f"SLM route error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Routing failed: {str(e)}"
        )


@router.post("/route/stream")
async def route_query_stream(
    request: StreamRouteRequest,
    _: str = Depends(verify_api_key)
) -> StreamingResponse:
    """
    Route a query with streaming chain-of-thought reasoning.

    This endpoint uses Server-Sent Events (SSE) to stream:
    1. Thinking steps as the SLM reasons about the query
    2. The final TOON plan when reasoning is complete
    3. Execution progress and results

    Events:
    - thinking_start: Reasoning has begun
    - thinking_step: A reasoning step (entities, intent, route decision)
    - plan_ready: TOON plan is ready with route and confidence
    - execution_start: Execution has begun
    - execution_complete: Final result with context for LLM

    This enables the UI to show visible chain-of-thought reasoning,
    similar to how coding agents show their thinking process.
    """
    if not settings.slm_router_enabled:
        raise HTTPException(
            status_code=503,
            detail="SLM Router is disabled"
        )

    # Check if streaming is enabled (feature flag)
    slm_streaming_enabled = getattr(settings, 'slm_streaming_enabled', True)
    if not slm_streaming_enabled:
        raise HTTPException(
            status_code=503,
            detail="SLM Router streaming is disabled"
        )

    async def generate_events():
        """Generate SSE events from the router stream."""
        try:
            slm_router = get_slm_router()

            if not slm_router._initialized:
                await slm_router.initialize()

            async for event in slm_router.route_stream(
                query=request.query,
                tenant_id=request.tenant_id,
                session_id=request.session_id
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", {})

                # Format as SSE
                yield f"event: {event_type}\n"
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            yield f"event: error\n"
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.post("/plan", response_model=PlanResponse)
async def generate_plan(
    request: PlanRequest,
    _: str = Depends(verify_api_key)
) -> PlanResponse:
    """
    Generate a TOON plan without executing it.

    This endpoint is useful for:
    - Debugging routing decisions
    - Understanding how queries are interpreted
    - Testing plan generation separately from execution

    Returns the full TOON plan with routing decision and extracted entities.
    """
    if not settings.slm_router_enabled:
        raise HTTPException(
            status_code=503,
            detail="SLM Router is disabled"
        )

    try:
        slm_router = get_slm_router()

        if not slm_router._initialized:
            await slm_router.initialize()

        # Generate plan only
        plan = await slm_router.plan(
            query=request.query,
            tenant_id=request.tenant_id,
            session_id=request.session_id
        )

        return PlanResponse(
            success=True,
            plan=plan.model_dump(exclude_none=True),
            route=plan.route.value,
            confidence=plan.confidence,
            entities=[
                {"name": e.name, "type": e.type, "graph_label": e.graph_label, "source": e.source.value}
                for e in plan.entities
            ],
            reasoning=plan.reasoning
        )

    except Exception as e:
        logger.error(f"SLM plan error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Plan generation failed: {str(e)}"
        )


@router.get("/health", response_model=HealthResponse)
async def health_check(
    _: str = Depends(verify_api_key)
) -> HealthResponse:
    """
    Check SLM Router health status.

    Returns detailed health information including:
    - Initialization status
    - SLM client status
    - Executor status (graph and vector backends)
    - Metrics (request counts, timing)
    """
    try:
        slm_router = get_slm_router()
        health = await slm_router.health_check()

        return HealthResponse(
            status="healthy" if health.get("initialized") else "not_initialized",
            initialized=health.get("initialized", False),
            enabled=health.get("enabled", settings.slm_router_enabled),
            slm=health.get("slm", {}),
            executor=health.get("executor", {}),
            metrics=health.get("metrics", {})
        )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="error",
            initialized=False,
            enabled=settings.slm_router_enabled,
            slm={"error": str(e)},
            executor={},
            metrics={}
        )


@router.delete("/history/{session_id}")
async def clear_history(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
    _: str = Depends(verify_api_key)
) -> Dict[str, str]:
    """
    Clear conversation history for a session.

    This removes all stored context for the session,
    starting fresh for subsequent queries.
    """
    try:
        from ..services.slm_router import get_history_manager

        history_manager = get_history_manager()
        await history_manager.clear_session(session_id)

        return {"status": "cleared", "session_id": session_id, "tenant_id": tenant_id}

    except Exception as e:
        logger.error(f"Clear history error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear history: {str(e)}"
        )


@router.get("/schema/{tenant_id}")
async def get_tenant_schema(
    tenant_id: str,
    _: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Get the extracted schema for a tenant.

    Returns the tenant's document types, folder types,
    known entities, and other metadata used for routing.

    Useful for debugging and understanding tenant context.
    """
    try:
        from ..services.slm_router import get_schema_provider

        schema_provider = get_schema_provider()
        schema = await schema_provider.get_schema(tenant_id)

        return {
            "tenant_id": schema.tenant_id,
            "document_types": schema.document_types,
            "folder_types": schema.folder_types,
            "known_clients": schema.known_clients,
            "domains": schema.domains,
            "total_documents": schema.total_documents,
            "total_folders": schema.total_folders,
            "graph_labels": schema.graph_labels,
            "terminology": schema.terminology,
            "extracted_at": schema.extracted_at.isoformat(),
            "expires_at": schema.expires_at.isoformat() if schema.expires_at else None
        }

    except Exception as e:
        logger.error(f"Get schema error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get schema: {str(e)}"
        )


@router.post("/schema/{tenant_id}/invalidate")
async def invalidate_tenant_schema(
    tenant_id: str,
    _: str = Depends(verify_api_key)
) -> Dict[str, str]:
    """
    Invalidate cached schema for a tenant.

    Forces re-extraction of schema on next query.
    Useful when tenant data changes significantly.
    """
    try:
        from ..services.slm_router import get_schema_provider

        schema_provider = get_schema_provider()
        await schema_provider.invalidate(tenant_id)

        return {"status": "invalidated", "tenant_id": tenant_id}

    except Exception as e:
        logger.error(f"Invalidate schema error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to invalidate schema: {str(e)}"
        )


# =============================================================================
# TRAINING DATA ENDPOINTS
# =============================================================================

class TrainingExportResponse(BaseModel):
    """Response for training data export."""
    tenant_id: str
    count: int
    examples: List[Dict[str, Any]]


@router.get("/training/{tenant_id}", response_model=TrainingExportResponse)
async def export_training_data(
    tenant_id: str,
    limit: int = Query(default=1000, ge=1, le=10000, description="Max examples to export"),
    _: str = Depends(verify_api_key)
) -> TrainingExportResponse:
    """
    Export collected training data for fine-tuning.

    Training examples are collected during normal operation when:
    - Queries are successfully executed
    - Routes produce correct results

    Use this data to fine-tune the SLM for better routing accuracy.

    Returns examples in format suitable for LoRA fine-tuning:
    - query: Original user query
    - route: Correct routing decision (GRAPH_ONLY, VECTOR_ONLY, etc.)
    - confidence: Model confidence in the decision
    - entities: Extracted entities
    """
    try:
        import json
        import redis.asyncio as redis

        redis_url = settings.redis_url or "redis://redis:6379"
        redis_client = redis.from_url(redis_url)

        redis_key = f"slm:training:{tenant_id}"
        raw_examples = await redis_client.lrange(redis_key, 0, limit - 1)

        examples = []
        for raw in raw_examples:
            try:
                example = json.loads(raw)
                examples.append(example)
            except json.JSONDecodeError:
                continue

        await redis_client.aclose()

        return TrainingExportResponse(
            tenant_id=tenant_id,
            count=len(examples),
            examples=examples
        )

    except Exception as e:
        logger.error(f"Export training data error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export training data: {str(e)}"
        )


@router.delete("/training/{tenant_id}")
async def clear_training_data(
    tenant_id: str,
    _: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Clear collected training data for a tenant.

    Use after exporting data for fine-tuning.
    """
    try:
        import redis.asyncio as redis

        redis_url = settings.redis_url or "redis://redis:6379"
        redis_client = redis.from_url(redis_url)

        redis_key = f"slm:training:{tenant_id}"
        deleted = await redis_client.delete(redis_key)

        await redis_client.aclose()

        return {
            "status": "cleared",
            "tenant_id": tenant_id,
            "keys_deleted": deleted
        }

    except Exception as e:
        logger.error(f"Clear training data error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear training data: {str(e)}"
        )


# =============================================================================
# CONTINUOUS LEARNING ENDPOINTS
# =============================================================================

@router.get("/learning/status")
async def get_learning_status(
    _: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Get status of the continuous learning system.

    Shows:
    - Current state (collecting, ready, training)
    - Examples collected vs needed
    - Success rate of collected data
    - Training history
    - Next maintenance window

    The system automatically improves the SLM model
    based on usage patterns - no manual intervention needed.
    """
    try:
        from ..services.slm_router.continuous_learning import get_learning_service

        service = get_learning_service()
        status = await service.get_status()

        return {
            "continuous_learning": status,
            "description": "El sistema mejora automáticamente con el uso. "
                          f"Se necesitan {status['examples_needed']} ejemplos para entrenar. "
                          f"Actualmente hay {status['examples_collected']}."
        }

    except Exception as e:
        logger.error(f"Get learning status error: {e}")
        return {
            "continuous_learning": {
                "enabled": False,
                "error": str(e)
            }
        }


@router.post("/learning/trigger")
async def trigger_training(
    _: str = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Manually trigger a training cycle (Admin maintenance action).

    This endpoint allows administrators to force a fine-tuning cycle
    without waiting for the automatic maintenance window.

    Requirements:
    - Sufficient training examples (check /learning/status first)
    - Minimum success rate threshold met
    - No training currently in progress

    The training runs in background and may take 30-60 minutes.
    Check /learning/status to monitor progress.
    """
    try:
        from ..services.slm_router.continuous_learning import get_learning_service, LearningState

        service = get_learning_service()
        status = await service.get_status()

        # Validate conditions
        if status["state"] == LearningState.TRAINING.value:
            return {
                "success": False,
                "error": "Training already in progress",
                "state": status["state"]
            }

        if status["examples_collected"] < status["examples_needed"]:
            return {
                "success": False,
                "error": f"Insufficient examples: {status['examples_collected']}/{status['examples_needed']}",
                "examples_collected": status["examples_collected"],
                "examples_needed": status["examples_needed"]
            }

        if status["success_rate"] < service.config.min_success_rate:
            return {
                "success": False,
                "error": f"Success rate too low: {status['success_rate']:.2%} (need {service.config.min_success_rate:.2%})",
                "success_rate": status["success_rate"]
            }

        # Get training stats and trigger
        stats = await service._get_training_stats()

        # Run training in background task
        import asyncio
        asyncio.create_task(service._run_training_pipeline(stats))

        return {
            "success": True,
            "message": "Training cycle initiated",
            "examples_used": stats["total_examples"],
            "success_rate": stats["success_rate"],
            "note": "Training runs in background. Check /learning/status for progress."
        }

    except Exception as e:
        logger.error(f"Trigger training error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger training: {str(e)}"
        )
