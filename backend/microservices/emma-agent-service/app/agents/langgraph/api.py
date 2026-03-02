"""
LangGraph ReAct Agent API Integration

API layer for executing LangGraph-based ReAct agent queries.
Integrated into Emma endpoints via feature flag.

Usage:
    from app.agents.langgraph.api import execute_langgraph_query, is_langgraph_enabled

    if is_langgraph_enabled():
        result = await execute_langgraph_query(query, tenant_id, user_id)
    else:
        result = await emma.execute(query, context)

Feature Flag: LANGGRAPH_RAG_ENABLED (default: false)
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.execution_context import set_execution_context, clear_execution_context
from .graph import execute_react_query, get_react_graph
from .state import ReActState, ExecutionConfig, create_initial_react_state

logger = logging.getLogger(__name__)


# =============================================================================
# Feature Flags
# =============================================================================

def is_langgraph_enabled() -> bool:
    """
    Check if LangGraph RAG is enabled.

    Controlled via environment variable LANGGRAPH_RAG_ENABLED.
    Defaults to false for backward compatibility.
    """
    return os.getenv("LANGGRAPH_RAG_ENABLED", "false").lower() == "true"


def get_langgraph_tenants() -> List[str]:
    """
    Get list of tenant IDs with LangGraph enabled.

    For gradual rollout, specific tenants can be whitelisted.
    Set LANGGRAPH_TENANTS="tenant-1,tenant-2" to enable for specific tenants.
    Set LANGGRAPH_TENANTS="*" to enable for all tenants (same as LANGGRAPH_RAG_ENABLED=true).
    """
    tenants = os.getenv("LANGGRAPH_TENANTS", "")
    if not tenants or tenants == "*":
        return []  # Empty means check global flag
    return [t.strip() for t in tenants.split(",") if t.strip()]


def is_langgraph_enabled_for_tenant(tenant_id: str) -> bool:
    """
    Check if LangGraph is enabled for a specific tenant.

    Allows gradual rollout by tenant.
    """
    # Check global flag first
    if is_langgraph_enabled():
        return True

    # Check tenant-specific whitelist
    whitelisted = get_langgraph_tenants()
    if whitelisted and tenant_id in whitelisted:
        return True

    return False


# =============================================================================
# Request/Response Models
# =============================================================================

class LangGraphQueryRequest(BaseModel):
    """Request for LangGraph RAG query."""
    query: str = Field(..., description="User's natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: Optional[str] = Field(None, description="User identifier for ACL")
    user_role_ids: Optional[List[str]] = Field(None, description="User role IDs for ACL")
    is_admin: bool = Field(False, description="Admin bypass for ACL")
    thread_id: Optional[str] = Field(None, description="Conversation thread ID")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Request context (document_id, attachments, etc.)")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "¿Qué documentos sobre RGPD tengo?",
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "thread_id": "thread-789",
            }
        }


class LangGraphQueryResponse(BaseModel):
    """Response from LangGraph RAG query."""
    success: bool
    answer: str
    sources: List[Dict[str, Any]] = Field(default_factory=list)
    thread_id: str
    agents_used: List[str] = Field(default_factory=list)
    domains: List[str] = Field(default_factory=list)
    fast_path: bool = False
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "answer": "Encontré 3 documentos relacionados con RGPD...",
                "sources": [{"title": "Política RGPD", "id": "doc-123"}],
                "thread_id": "thread-789",
                "agents_used": ["privacy_agent"],
                "domains": ["privacy"],
                "fast_path": False,
                "latency_ms": 1250.5,
            }
        }


# =============================================================================
# API Functions
# =============================================================================

async def execute_langgraph_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    config: Optional[ExecutionConfig] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> LangGraphQueryResponse:
    """
    Execute a RAG query using LangGraph.

    This is the main API function for executing queries.
    Can be called directly or integrated into Emma v2 endpoints.

    Args:
        query: User's natural language query
        tenant_id: Tenant ID for ACL isolation
        user_id: Optional user ID for fine-grained ACL
        user_role_ids: Optional role IDs for permission checks
        is_admin: Admin bypass flag
        thread_id: Optional conversation thread ID
        config: Optional execution configuration

    Returns:
        LangGraphQueryResponse with answer, sources, and metadata

    Example:
        >>> response = await execute_langgraph_query(
        ...     query="¿Qué contratos tienen cláusula RGPD?",
        ...     tenant_id="tenant-123",
        ...     user_id="user-456",
        ... )
        >>> print(response.answer)
    """
    start_time = time.time()

    # Generate thread ID if not provided
    if not thread_id:
        thread_id = str(uuid.uuid4())

    logger.info(
        f"🚀 LangGraph query: tenant={tenant_id}, "
        f"thread={thread_id[:8]}..., query='{query[:50]}...'"
    )

    # Set execution context for tools
    document_id = (context or {}).get("document_id")
    set_execution_context(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids,
        is_admin=is_admin,
        document_id=document_id,
    )

    try:
        # Execute via ReAct graph (default behavior)
        result = await execute_react_query(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            thread_id=thread_id,
            conversation_history=conversation_history,
            context=context,
        )

        latency_ms = (time.time() - start_time) * 1000

        logger.info(
            f"✅ ReAct query completed: success={result.get('success')}, "
            f"steps={result.get('metadata', {}).get('total_steps', 0)}, latency={latency_ms:.1f}ms"
        )

        return LangGraphQueryResponse(
            success=result.get("success", False),
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            thread_id=result.get("thread_id", thread_id),
            agents_used=[],
            domains=[],
            fast_path=result.get("fast_path", False),
            latency_ms=latency_ms,
            metadata=result.get("metadata", {}),
        )

    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"❌ ReAct query failed: {e}")

        return LangGraphQueryResponse(
            success=False,
            answer=f"Error processing query: {str(e)}",
            sources=[],
            thread_id=thread_id,
            agents_used=[],
            domains=[],
            fast_path=False,
            latency_ms=latency_ms,
            metadata={"error": str(e)},
        )

    finally:
        clear_execution_context()


# =============================================================================
# ReAct Agent Streaming
# =============================================================================

async def stream_react_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream a ReAct agent query execution.

    Yields events as the ReAct loop iterates, providing real-time
    visibility into the agent's Think-Act-Observe cycle.

    Event Types:
        - started: Query execution started
        - thinking: Agent's reasoning before an action
        - tool_call: Agent decided to use a tool
        - tool_result: Tool execution completed with results
        - reasoning_step: Generic reasoning step (routing, validation, etc.)
        - token: Streaming token from the final answer
        - complete: Final answer ready
        - error: Error occurred

    Args:
        query: User's query
        tenant_id: Tenant ID
        user_id: Optional user ID
        user_role_ids: Optional role IDs
        is_admin: Admin flag
        thread_id: Optional thread ID
        conversation_history: Previous messages
        context: Request context

    Yields:
        Event dicts with type and data
    """
    start_time = time.time()
    thread_id = thread_id or str(uuid.uuid4())

    if not tenant_id or not tenant_id.strip():
        yield {"type": "error", "data": {"error": "tenant_id is required", "thread_id": thread_id}}
        return

    document_id = (context or {}).get("document_id")
    set_execution_context(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids,
        is_admin=is_admin,
        document_id=document_id,
    )

    yield {
        "type": "started",
        "data": {"thread_id": thread_id, "query": query, "graph_type": "react"},
    }

    # Track emitted events for deduplication (index-based)
    emitted_step_count = 0
    emitted_swarm_event_count = 0

    try:
        from langchain_core.messages import HumanMessage, AIMessage

        langchain_history = None
        if conversation_history:
            langchain_history = []
            for msg in conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    langchain_history.append(HumanMessage(content=content))
                elif role == "assistant":
                    langchain_history.append(AIMessage(content=content))

        try:
            from app.services.upload_context_service import upload_context_service
            hydrated_context = upload_context_service.hydrate_context(context or {})
        except Exception:
            hydrated_context = context or {}

        initial_state = await create_initial_react_state(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            thread_id=thread_id,
            conversation_history=langchain_history,
            request_context=hydrated_context,
        )

        graph = get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}

        # Stream graph execution — each node output is yielded
        async for event in graph.astream(initial_state, config, stream_mode="values"):

            # Emit reasoning steps incrementally (index-based dedup)
            reasoning_steps = event.get("reasoning_steps", [])
            for step in reasoning_steps[emitted_step_count:]:
                emitted_step_count += 1

                step_type = step.get("type", "reasoning")

                # Map step types to SSE event types
                if step_type == "thinking":
                    yield {
                        "type": "thinking",
                        "data": {"content": step.get("content", "")},
                    }
                elif step_type == "tool_call":
                    yield {
                        "type": "tool_call",
                        "data": {"content": step.get("content", "")},
                    }
                elif step_type == "observation":
                    yield {
                        "type": "tool_result",
                        "data": {
                            "content": step.get("content", ""),
                            "source": step.get("source", ""),
                        },
                    }
                else:
                    yield {
                        "type": "reasoning_step",
                        "data": {
                            "step_type": step_type,
                            "content": step.get("content", ""),
                        },
                    }

            # Drain swarm pending events incrementally (same pattern as reasoning_steps)
            swarm_events = event.get("swarm_pending_events", [])
            for swarm_evt in swarm_events[emitted_swarm_event_count:]:
                emitted_swarm_event_count += 1
                evt_type = swarm_evt.get("type", "swarm_event")
                evt_data = swarm_evt.get("data", {})
                yield {"type": evt_type, "data": evt_data}

            # Check for final answer
            if event.get("final_answer") and event.get("is_complete"):
                latency_ms = (time.time() - start_time) * 1000
                final_answer = event["final_answer"]

                # Stream answer as tokens (with event loop yield for HTTP flush)
                words = final_answer.split(' ')
                for i, word in enumerate(words):
                    token = f" {word}" if i > 0 else word
                    yield {"type": "token", "data": {"text": token, "token": token}}
                    await asyncio.sleep(0)

                # Emit complete
                yield {
                    "type": "complete",
                    "data": {
                        "success": event.get("success", True),
                        "answer": final_answer,
                        "sources": event.get("sources", []),
                        "thread_id": thread_id,
                        "fast_path": event.get("fast_path_used", False),
                        "latency_ms": latency_ms,
                        "total_steps": event.get("current_step", 0),
                        "graph_type": "react",
                    },
                }
                break

    except Exception as e:
        logger.error(f"ReAct stream error: {e}", exc_info=True)
        yield {"type": "error", "data": {"error": str(e), "thread_id": thread_id}}

    finally:
        clear_execution_context()


# =============================================================================
# Integration Helper
# =============================================================================

async def maybe_use_langgraph(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    **kwargs,
) -> Optional[LangGraphQueryResponse]:
    """
    Try to use LangGraph if enabled, otherwise return None.

    This helper allows gradual migration from Emma to LangGraph.
    If LangGraph is not enabled for this tenant, returns None
    so the caller can fall back to Emma.

    When enabled, routes through the ReAct agent graph.

    Args:
        query: User's query
        tenant_id: Tenant ID
        user_id: Optional user ID
        thread_id: Optional thread ID
        **kwargs: Additional arguments passed to execute_langgraph_query

    Returns:
        LangGraphQueryResponse if LangGraph is enabled, None otherwise
    """
    if not is_langgraph_enabled_for_tenant(tenant_id):
        return None

    return await execute_langgraph_query(
        query=query,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=thread_id,
        **kwargs,
    )
