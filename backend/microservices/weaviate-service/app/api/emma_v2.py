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
from app.core.security import verify_api_key
from app.agents.emma_v2 import (
    EmmaV2,
    EmmaV2Config,
    EmmaV2Result,
    ExecutionContext,
    get_emma_v2,
)
from app.agents.emma_v2_tools import EMMA_V2_TOOLS, get_emma_v2_tools

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

    try:
        emma = await get_emma_v2()

        # Build context
        thread_id = query.thread_id or query.session_id or str(uuid.uuid4())
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
        try:
            emma = await get_emma_v2()

            thread_id = query.thread_id or query.session_id or str(uuid.uuid4())
            context = ExecutionContext(
                tenant_id=query.tenant_id,
                user_id=query.user_id,
                thread_id=thread_id,
            )

            emma.config.enable_sil_fast_path = query.enable_sil
            emma.config.enable_domain_routing = query.enable_domain_routing

            async for event in emma.execute_stream(query.query, context):
                event_type = event.get("type", "message")
                event_data = {k: v for k, v in event.items() if k != "type"}

                sse_message = f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                yield sse_message

                # Force immediate flush
                await asyncio.sleep(0)

        except Exception as e:
            logger.error(f"Emma v2 stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

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
