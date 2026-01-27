"""
Emma v2 API Endpoints

New API endpoints for Emma v2 that run in parallel with v1 during migration.

Endpoints:
- POST /emma/v2/query - Execute query (non-streaming)
- POST /emma/v2/query/stream - Execute query with SSE streaming
- GET /emma/v2/tools - List available tools
- GET /emma/v2/health - Health check

Feature flag: EMMA_V2_ENABLED (default: true)

Migration path:
1. Both v1 and v2 run in parallel
2. Frontend can choose which to use
3. Gradually route traffic to v2
4. Eventually deprecate v1
"""

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.langfuse_config import (
    flush_langfuse,
    langfuse_context,
    score_emma_result,
    trace_context,
    trace_emma_query,
)
from app.core.security import verify_api_key
from app.agents.emma_v2 import (
    EmmaV2,
    EmmaV2Config,
    EmmaV2Result,
    ExecutionContext,
    get_emma_v2,
)
from app.agents.emma_v2_tools import EMMA_V2_TOOLS, get_emma_v2_tools
from app.services.emma_persistence_service import get_emma_persistence_service
from app.schemas.emma import (
    EmmaSessionListResponse,
    EmmaSessionResponse,
    EmmaSessionUpdate,
    EmmaContinueSessionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2", tags=["Emma v2"])


# =============================================================================
# Request/Response Models
# =============================================================================

class EmmaV2Query(BaseModel):
    """Query request for Emma v2."""
    query: str = Field(..., description="User's natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID for history")
    session_id: Optional[str] = Field(None, description="Session ID (alias for thread_id)")
    enable_sil: bool = Field(True, description="Enable SIL fast path for structural queries")
    enable_domain_routing: bool = Field(True, description="Enable domain-specific prompts")
    enable_streaming: bool = Field(False, description="Enable streaming (use /stream endpoint instead)")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "¿Cuántos contratos laborales tengo?",
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "thread_id": "thread-789",
                "enable_sil": True,
            }
        }


class EmmaV2Response(BaseModel):
    """Response from Emma v2."""
    success: bool
    answer: str
    domain: str = "general"
    tools_called: List[str] = Field(default_factory=list)
    iterations: int = 0
    sil_answered: bool = False
    tokens_saved: int = 0
    latency_ms: float = 0.0
    thread_id: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "Tienes 5 contratos laborales.",
                "domain": "labor",
                "tools_called": [],
                "iterations": 0,
                "sil_answered": True,
                "tokens_saved": 2500,
                "latency_ms": 45.2,
                "thread_id": "thread-789",
            }
        }


class ToolInfo(BaseModel):
    """Information about a tool."""
    name: str
    description: str
    parameters: Dict[str, Any]


class ToolsResponse(BaseModel):
    """Response listing available tools."""
    tools: List[ToolInfo]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "2.0"
    llm_connected: bool
    sil_enabled: bool
    features: Dict[str, bool]


# =============================================================================
# Feature Flag
# =============================================================================

def is_emma_v2_enabled() -> bool:
    """Check if Emma v2 is enabled."""
    # Can be controlled via environment variable
    import os
    return os.getenv("EMMA_V2_ENABLED", "true").lower() == "true"


# =============================================================================
# Endpoints
# =============================================================================

@router.post("/query", response_model=EmmaV2Response)
async def emma_v2_query(
    query: EmmaV2Query,
    _: bool = Depends(verify_api_key),
):
    """
    Execute a query with Emma v2.

    This endpoint uses the new Emma v2 architecture:
    1. SIL fast path for structural queries (70-90% token savings)
    2. Domain-specific dynamic prompts
    3. Native async LLM client
    4. Consolidated tool set (6 tools)

    Use thread_id to maintain conversation context across requests.
    """
    if not is_emma_v2_enabled():
        raise HTTPException(
            status_code=503,
            detail="Emma v2 is not enabled. Set EMMA_V2_ENABLED=true",
        )

    # Build context
    thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

    # Create Langfuse trace for this query
    with trace_context(
        name="emma.query",
        session_id=thread_id,
        user_id=query.user_id,
        metadata={
            "tenant_id": query.tenant_id,
            "sil_enabled": query.enable_sil,
            "domain_routing_enabled": query.enable_domain_routing,
        },
        input={"query": query.query},
        tags=["emma-v2", "api"],
    ) as trace:
        try:
            emma = await get_emma_v2()

            context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=query.user_id,
                thread_id=thread_id,
            )

            # Configure Emma based on request
            emma.config.enable_sil_fast_path = query.enable_sil
            emma.config.enable_domain_routing = query.enable_domain_routing

            # Execute query
            result = await emma.execute(query.query, context)

            # Update trace with output
            if trace:
                trace.update(
                    output={
                        "answer": result.answer[:500] + "..." if len(result.answer) > 500 else result.answer,
                        "domain": result.domain.value,
                        "sil_answered": result.sil_answered,
                    }
                )

            return EmmaV2Response(
                success=result.success,
                answer=result.answer,
                domain=result.domain.value,
                tools_called=result.tools_called,
                iterations=result.iterations,
                sil_answered=result.sil_answered,
                tokens_saved=result.tokens_saved,
                latency_ms=result.latency_ms,
                thread_id=result.thread_id,
                metadata=result.metadata,
            )

        except Exception as e:
            logger.error(f"Emma v2 query error: {e}", exc_info=True)
            if trace:
                trace.update(level="ERROR", status_message=str(e))
            raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def emma_v2_query_stream(
    query: EmmaV2Query,
    _: bool = Depends(verify_api_key),
):
    """
    Execute a query with Emma v2 using Server-Sent Events (SSE) streaming.

    Events:
    - `thinking`: LLM reasoning process (if thinking mode enabled)
    - `content`: Response text chunks
    - `tool_call`: Tool invocation with name and arguments
    - `tool_result`: Result from tool execution
    - `done`: Final result with full metadata
    - `error`: Error message

    Example SSE stream:
    ```
    event: content
    data: {"content": "Analizando tu consulta..."}

    event: tool_call
    data: {"name": "search", "arguments": {"query": "contratos laborales"}}

    event: tool_result
    data: {"name": "search", "result": {"count": 5}}

    event: content
    data: {"content": "Encontré 5 contratos laborales."}

    event: done
    data: {"success": true, "answer": "...", "latency_ms": 1234.5}
    ```
    """
    if not is_emma_v2_enabled():
        raise HTTPException(
            status_code=503,
            detail="Emma v2 is not enabled. Set EMMA_V2_ENABLED=true",
        )

    async def generate_sse() -> AsyncGenerator[str, None]:
        """
        Generate SSE events, transforming Emma v2 internal events to frontend format.

        Emma v2 internal → Frontend expected:
        - content → token (with text field)
        - thinking → progress (with stage='thinking')
        - tool_call → delegation (with tool field)
        - tool_result → step_complete
        - done → complete (with answer, success, tools_used)
        - error → error
        """
        thread_id = query.thread_id or query.session_id or str(uuid.uuid4())

        # Create Langfuse trace for this streaming query
        trace = trace_emma_query(
            query=query.query,
            tenant_id=query.tenant_id,
            user_id=query.user_id,
            thread_id=thread_id,
        )
        if trace:
            trace.update(metadata={"streaming": True})
            langfuse_context.push_observation(trace)

        try:
            logger.info(f"[Emma v2 Stream] Starting for tenant={query.tenant_id}, query={query.query[:50]}...")

            # Send start event
            yield f"event: start\ndata: {json.dumps({'message': 'Iniciando análisis...', 'progress': 0})}\n\n"
            await asyncio.sleep(0)

            try:
                emma = await get_emma_v2()
                logger.info("[Emma v2 Stream] Emma instance created")
            except Exception as init_err:
                logger.error(f"[Emma v2 Stream] Failed to create Emma instance: {init_err}")
                yield f"event: error\ndata: {json.dumps({'error': f'Error inicializando Emma: {str(init_err)}'})}\n\n"
                return

            yield f"event: progress\ndata: {json.dumps({'message': 'Emma inicializada...', 'stage': 'init', 'progress': 5})}\n\n"
            await asyncio.sleep(0)

            context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=query.user_id,
                thread_id=thread_id,
            )

            emma.config.enable_sil_fast_path = query.enable_sil
            emma.config.enable_domain_routing = query.enable_domain_routing

            # Send progress event
            yield f"event: progress\ndata: {json.dumps({'message': 'Procesando consulta...', 'stage': 'context_preparation', 'progress': 10})}\n\n"
            await asyncio.sleep(0)

            logger.info(f"[Emma v2 Stream] Starting execute_stream loop (SIL={query.enable_sil})")
            event_count = 0
            has_complete = False

            try:
                async for event in emma.execute_stream(query.query, context):
                    event_count += 1
                    event_type = event.get("type", "message")
                    logger.debug(f"[Emma v2 Stream] Event {event_count}: {event_type}")

                    # Transform events to frontend expected format
                    if event_type == "content":
                        # content → token (text streaming)
                        frontend_data = {
                            "text": event.get("content", ""),
                            "token": event.get("content", ""),
                        }
                        yield f"event: token\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "thinking":
                        # thinking → progress with stage
                        frontend_data = {
                            "message": "Razonando...",
                            "stage": "thinking",
                            "text": event.get("content", ""),
                        }
                        yield f"event: progress\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    # SLM Router chain-of-thought events
                    elif event_type == "slm_thinking_start":
                        # SLM started reasoning
                        frontend_data = {
                            "message": event.get("content", "Analizando consulta..."),
                            "stage": "slm_reasoning",
                            "slmIsThinking": True,
                            "slmThinkingSteps": [],
                        }
                        yield f"event: progress\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "slm_thinking_step":
                        # SLM reasoning step (entity, intent, route)
                        frontend_data = {
                            "message": event.get("content", ""),
                            "stage": "slm_reasoning",
                            "slmIsThinking": True,
                            "slmThinkingStep": {
                                "step": event.get("step"),
                                "type": event.get("step_type"),
                                "content": event.get("content"),
                                "entities": event.get("entities", []),
                                "confidence": event.get("confidence", 1.0),
                            },
                        }
                        yield f"event: slm_thinking\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "slm_plan_ready":
                        # SLM plan generated
                        frontend_data = {
                            "message": f"Plan: {event.get('route', 'N/A')} ({event.get('confidence', 0)*100:.0f}% confianza)",
                            "stage": "slm_plan_ready",
                            "slmIsThinking": False,
                            "slmPlan": {
                                "route": event.get("route"),
                                "confidence": event.get("confidence", 0),
                                "entities_count": event.get("entities_count", 0),
                                "reasoning": event.get("reasoning"),
                            },
                        }
                        yield f"event: slm_plan\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "slm_execution_start":
                        # SLM starting execution
                        frontend_data = {
                            "message": event.get("message", "Ejecutando plan..."),
                            "stage": "slm_executing",
                            "slmIsExecuting": True,
                            "route": event.get("route"),
                        }
                        yield f"event: progress\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "tool_call":
                        # tool_call → delegation
                        tool_name = event.get("name", "unknown")
                        frontend_data = {
                            "tool": tool_name,
                            "message": f"Ejecutando {tool_name}...",
                            "stage": "searching" if "search" in tool_name.lower() else "analyzing",
                            "process_info": event.get("process_info", {}),
                        }
                        yield f"event: delegation\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "tool_result":
                        # tool_result → step_complete
                        tool_name = event.get("name", "unknown")
                        frontend_data = {
                            "tool": tool_name,
                            "message": f"{tool_name} completado",
                            "process_info": event.get("process_info", {}),
                        }
                        yield f"event: step_complete\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "done":
                        # done → complete
                        has_complete = True
                        result = event.get("result", {})
                        frontend_data = {
                            "success": result.get("success", True),
                            "answer": result.get("answer", ""),
                            "tools_used": result.get("tools_called", []),
                            "execution_time_ms": result.get("latency_ms", 0),
                            "session_id": result.get("thread_id", thread_id),
                            "process_info": result.get("process_info", {}),
                            "final_result": result,
                        }
                        yield f"event: complete\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    elif event_type == "error":
                        # error stays as error
                        frontend_data = {"error": event.get("error", "Unknown error")}
                        yield f"event: error\ndata: {json.dumps(frontend_data, ensure_ascii=False)}\n\n"

                    else:
                        # Unknown event types → progress
                        event_data = {k: v for k, v in event.items() if k != "type"}
                        event_data["message"] = event_data.get("message", f"Procesando ({event_type})...")
                        yield f"event: progress\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

                    # Force immediate flush after each event
                    await asyncio.sleep(0)

                # After loop: Check if we got events
                logger.info(f"[Emma v2 Stream] Loop finished with {event_count} events, has_complete={has_complete}")
                if event_count == 0:
                    logger.warning("[Emma v2 Stream] No events received from execute_stream!")
                    if trace:
                        trace.update(level="WARNING", status_message="No events received")
                    yield f"event: error\ndata: {json.dumps({'error': 'No se recibieron eventos del procesamiento'})}\n\n"
                elif not has_complete:
                    logger.warning("[Emma v2 Stream] Stream ended without 'done' event")

                # Finalize trace on success
                if trace and has_complete:
                    trace.update(
                        output={"event_count": event_count, "completed": has_complete}
                    )

            except Exception as stream_err:
                import traceback
                error_details = traceback.format_exc()
                logger.error(f"[Emma v2 Stream] Error in execute_stream: {stream_err}\n{error_details}")
                if trace:
                    trace.update(level="ERROR", status_message=str(stream_err))
                yield f"event: error\ndata: {json.dumps({'error': f'Error en procesamiento: {str(stream_err)}'})}\n\n"

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            logger.error(f"Emma v2 stream error: {e}\n{error_details}")
            if trace:
                trace.update(level="ERROR", status_message=str(e))
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'details': error_details[:500]})}\n\n"
        finally:
            # Cleanup: pop trace from context and flush
            if trace:
                langfuse_context.pop_observation()
                flush_langfuse()

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/tools", response_model=ToolsResponse)
async def list_tools(_: bool = Depends(verify_api_key)):
    """
    List all available Emma v2 tools.

    Emma v2 uses a consolidated set of 6 tools:
    - search: Semantic/keyword/hybrid document search
    - read_document: Get full document content
    - analyze: Deep RAG-based document analysis
    - sil_query: Structural queries via SIL/Cypher
    - ask_user: Human-in-the-loop clarification
    - legal_search: Public legal knowledge search
    """
    tools = get_emma_v2_tools()

    return ToolsResponse(
        tools=[
            ToolInfo(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in tools
        ],
        count=len(tools),
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Check Emma v2 health status.

    Returns:
    - LLM connection status
    - SIL availability
    - Enabled features
    """
    try:
        emma = await get_emma_v2()

        # Check LLM connection
        llm_connected, llm_msg = await emma._llm_client.validate_connection()

        return HealthResponse(
            status="healthy" if llm_connected else "degraded",
            version="2.0",
            llm_connected=llm_connected,
            sil_enabled=emma.config.enable_sil_fast_path and emma._sil is not None,
            features={
                "sil_fast_path": emma.config.enable_sil_fast_path,
                "domain_routing": emma.config.enable_domain_routing,
                "streaming": emma.config.enable_streaming,
                "emma_v2_enabled": is_emma_v2_enabled(),
            },
        )

    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthResponse(
            status="unhealthy",
            version="2.0",
            llm_connected=False,
            sil_enabled=False,
            features={"error": str(e)},
        )


@router.get("/compare")
async def compare_v1_v2(
    query: str = Query(..., description="Query to compare"),
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Compare Emma v1 and v2 responses for the same query.

    Useful for A/B testing during migration.
    Returns both responses with timing information.
    """
    import time
    from app.services.emma_service import emma_service
    from app.schemas.emma import EmmaQuery

    results = {}

    # Execute v1
    try:
        v1_start = time.time()
        v1_query = EmmaQuery(
            query=query,
            tenant_id=tenant_id,
        )
        v1_response = await emma_service.execute_query(v1_query)
        v1_latency = (time.time() - v1_start) * 1000

        results["v1"] = {
            "success": v1_response.success,
            "answer": v1_response.answer[:500] + "..." if len(v1_response.answer) > 500 else v1_response.answer,
            "latency_ms": v1_latency,
        }
    except Exception as e:
        results["v1"] = {"error": str(e)}

    # Execute v2
    try:
        emma = await get_emma_v2()
        v2_start = time.time()
        context = ExecutionContext(tenant_id=tenant_id)
        v2_result = await emma.execute(query, context)
        v2_latency = (time.time() - v2_start) * 1000

        results["v2"] = {
            "success": v2_result.success,
            "answer": v2_result.answer[:500] + "..." if len(v2_result.answer) > 500 else v2_result.answer,
            "latency_ms": v2_latency,
            "sil_answered": v2_result.sil_answered,
            "tokens_saved": v2_result.tokens_saved,
            "domain": v2_result.domain.value,
        }
    except Exception as e:
        results["v2"] = {"error": str(e)}

    # Calculate comparison
    if "latency_ms" in results.get("v1", {}) and "latency_ms" in results.get("v2", {}):
        v1_lat = results["v1"]["latency_ms"]
        v2_lat = results["v2"]["latency_ms"]
        results["comparison"] = {
            "latency_improvement_pct": round((v1_lat - v2_lat) / v1_lat * 100, 1) if v1_lat > 0 else 0,
            "v2_sil_fast_path": results["v2"].get("sil_answered", False),
            "v2_tokens_saved": results["v2"].get("tokens_saved", 0),
        }

    return results


# =============================================================================
# Session Persistence Endpoints
# =============================================================================

@router.get("/sessions", response_model=EmmaSessionListResponse)
async def list_sessions(
    user_id: str = Query(..., description="User ID"),
    tenant_id: str = Query(..., description="Tenant ID"),
    include_archived: bool = Query(False, description="Include archived sessions"),
    limit: int = Query(50, ge=1, le=100, description="Max sessions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    _: bool = Depends(verify_api_key),
):
    """
    List Emma chat sessions for a user.

    Returns paginated list of sessions with previews of first/last messages.
    Sessions are ordered by:
    1. Pinned sessions first
    2. Then by last_message_at (most recent first)

    Use this to build a conversation history sidebar.
    """
    persistence = get_emma_persistence_service()

    result = await persistence.get_user_sessions(
        user_id=user_id,
        tenant_id=tenant_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )

    return EmmaSessionListResponse(**result)


@router.get("/sessions/{session_id}", response_model=EmmaSessionResponse)
async def get_session(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Get a full Emma session with all messages.

    Returns the complete conversation history including:
    - All messages (user and assistant)
    - Sources cited in responses
    - Tools used
    - Metadata

    Use this when the user opens an old conversation.
    """
    persistence = get_emma_persistence_service()

    session = await persistence.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify tenant access
    if session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    return EmmaSessionResponse(**session)


@router.post("/sessions/{session_id}/continue", response_model=EmmaContinueSessionResponse)
async def continue_session(
    session_id: str,
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Continue an old Emma session.

    This endpoint:
    1. Loads the session from PostgreSQL
    2. Restores it to Redis (hot cache)
    3. Returns confirmation

    After calling this, use the regular /query or /query/stream endpoints
    with the same session_id to continue the conversation.
    The LLM will have access to the full conversation history.
    """
    persistence = get_emma_persistence_service()

    # Check if session exists
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify tenant access
    if session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Check if already in Redis
    in_redis = await persistence.session_exists_in_redis(session_id)

    if in_redis:
        return EmmaContinueSessionResponse(
            success=True,
            session_id=session_id,
            message_count=session["message_count"],
            loaded_to_redis=False,  # Already there
            message="Session already active in cache",
        )

    # Load to Redis
    loaded = await persistence.load_session_to_redis(session_id)

    if not loaded:
        raise HTTPException(
            status_code=500,
            detail="Failed to load session to cache. Please try again.",
        )

    return EmmaContinueSessionResponse(
        success=True,
        session_id=session_id,
        message_count=session["message_count"],
        loaded_to_redis=True,
        message=f"Session restored with {session['message_count']} messages",
    )


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    update: EmmaSessionUpdate,
    user_id: str = Query(..., description="User ID"),
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Update session properties.

    Allows updating:
    - title: Custom session title
    - is_archived: Archive/unarchive session
    - is_pinned: Pin/unpin session
    """
    persistence = get_emma_persistence_service()

    # Verify session exists
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify ownership
    if session["user_id"] != user_id or session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Update
    updated = await persistence.update_session(
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
        title=update.title,
        is_archived=update.is_archived,
        is_pinned=update.is_pinned,
    )

    if not updated:
        raise HTTPException(status_code=500, detail="Failed to update session")

    return {"success": True, "message": "Session updated"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Query(..., description="User ID"),
    tenant_id: str = Query(..., description="Tenant ID"),
    _: bool = Depends(verify_api_key),
):
    """
    Permanently delete an Emma session.

    This action:
    - Removes the session from PostgreSQL
    - Clears it from Redis if present
    - Cannot be undone

    Consider archiving instead for recoverable deletion.
    """
    persistence = get_emma_persistence_service()

    # Verify session exists
    session = await persistence.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    # Verify ownership
    if session["user_id"] != user_id or session["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this session")

    # Delete
    deleted = await persistence.delete_session(
        session_id=session_id,
        user_id=user_id,
        tenant_id=tenant_id,
    )

    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete session")

    return {"success": True, "message": "Session deleted"}
