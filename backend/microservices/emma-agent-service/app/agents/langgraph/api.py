"""
LangGraph ReAct Agent API Integration

API layer for executing LangGraph-based ReAct agent queries.
LangGraph is the single orchestration engine — no feature flags needed.

Usage:
    from app.agents.langgraph.api import execute_langgraph_query

    result = await execute_langgraph_query(query, tenant_id, user_id)
"""

import asyncio
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.execution_context import set_execution_context, clear_execution_context
from .graph import execute_react_query
# get_react_graph is now async — import at call site
from .state import ReActState, ExecutionConfig, create_initial_react_state

logger = logging.getLogger(__name__)


# Backwards-compatible stubs — always returns True.
# These will be removed in a future cleanup pass.
def is_langgraph_enabled() -> bool:
    """LangGraph is always enabled — it's the core orchestration engine."""
    return True

def is_langgraph_enabled_for_tenant(tenant_id: str) -> bool:
    """LangGraph is always enabled for all tenants."""
    return True


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

        # Extract tool names from reasoning steps for frontend detection
        reasoning = result.get("reasoning_steps", [])
        tools_used = list(dict.fromkeys(
            step["content"].split("(")[0]
            for step in reasoning
            if step.get("type") == "tool_call" and "(" in step.get("content", "")
        ))

        return LangGraphQueryResponse(
            success=result.get("success", False),
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            thread_id=result.get("thread_id", thread_id),
            agents_used=tools_used,
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
    enable_thinking: Optional[bool] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Stream a ReAct agent query execution.

    Yields events as the ReAct loop iterates, providing real-time
    visibility into the agent's Think-Act-Observe cycle.

    Conversation continuity is handled by the PostgresSaver checkpointer
    (Phase 1b).  Previous messages are restored from the checkpoint when
    ``graph.astream()`` is called with the same ``thread_id``.  The
    ``conversation_history`` parameter is kept for backwards-compatibility
    but ignored when the checkpointer is active.

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
        conversation_history: Previous messages (ignored when checkpointer active)
        context: Request context
        enable_thinking: Per-request thinking override (UI deep_reasoning toggle)

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

    try:
        try:
            from app.services.upload_context_service import upload_context_service
            hydrated_context = upload_context_service.hydrate_context(context or {})
        except Exception:
            hydrated_context = context or {}

        # conversation_history conversion kept for backwards-compatibility
        # (non-checkpointed callers). create_initial_react_state() decides
        # whether to include it based on checkpointer availability.
        langchain_history = None
        if conversation_history:
            from langchain_core.messages import HumanMessage as HM, AIMessage as AM
            langchain_history = []
            for msg in conversation_history:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if role == "user":
                    langchain_history.append(HM(content=content))
                elif role == "assistant":
                    langchain_history.append(AM(content=content))

        initial_state = await create_initial_react_state(
            query=query,
            tenant_id=tenant_id,
            user_id=user_id,
            user_role_ids=user_role_ids,
            is_admin=is_admin,
            thread_id=thread_id,
            conversation_history=langchain_history,
            request_context=hydrated_context,
            enable_thinking=enable_thinking,
        )

        from .graph import get_react_graph
        graph = await get_react_graph()

        # LangGraph config with thread_id for checkpointer scoping
        langgraph_config = {"configurable": {"thread_id": thread_id}}

        # When checkpointer is active, the checkpoint may contain
        # reasoning_steps from previous turns (merge_lists accumulates).
        # Offset the dedup counter so we only emit NEW steps from this turn.
        emitted_step_count = 0
        try:
            checkpoint_state = await graph.aget_state(langgraph_config)
            if checkpoint_state and checkpoint_state.values:
                emitted_step_count = len(
                    checkpoint_state.values.get("reasoning_steps", [])
                )
        except Exception:
            pass  # No checkpoint yet (first turn) — start at 0

        # Dual stream mode:
        # - "values": State snapshots after each node (reasoning_steps, final_answer)
        # - "custom": Real-time events from get_stream_writer() in nodes
        #   (swarm worker_started/worker_complete, synthesis tokens)
        last_values_event = None

        async for mode, event in graph.astream(
            initial_state, config=langgraph_config, stream_mode=["values", "custom"]
        ):
            if mode == "custom":
                # Real-time events from nodes via get_stream_writer()
                evt_type = event.get("type", "custom_event")
                evt_data = event.get("data", {})

                if evt_type == "token":
                    yield {"type": "token", "data": evt_data}
                else:
                    # Swarm events: worker_started, worker_complete, swarm_synthesizing
                    yield {"type": evt_type, "data": evt_data}

                continue

            # mode == "values": State snapshot after a node completed
            last_values_event = event

            # Emit reasoning steps incrementally (index-based dedup)
            reasoning_steps = event.get("reasoning_steps", [])
            for step in reasoning_steps[emitted_step_count:]:
                emitted_step_count += 1

                step_type = step.get("type", "reasoning")

                # Map step types to SSE event types
                # summary (optional): pre-humanized label for frontend ActivityTimeline
                summary = step.get("summary")
                if step_type == "thinking":
                    yield {
                        "type": "thinking",
                        "data": {"content": step.get("content", ""), **({"summary": summary} if summary else {})},
                    }
                elif step_type == "tool_call":
                    yield {
                        "type": "tool_call",
                        "data": {"content": step.get("content", ""), **({"summary": summary} if summary else {})},
                    }
                elif step_type == "observation":
                    yield {
                        "type": "tool_result",
                        "data": {
                            "content": step.get("content", ""),
                            "source": step.get("source", ""),
                            **({"summary": summary} if summary else {}),
                        },
                    }
                else:
                    yield {
                        "type": "reasoning_step",
                        "data": {
                            "step_type": step_type,
                            "content": step.get("content", ""),
                            **({"summary": summary} if summary else {}),
                        },
                    }

            # Check for final answer
            if event.get("final_answer") and event.get("is_complete"):
                # If explain is enabled, wait for the explanation field
                from app.core.config import settings as app_settings
                if app_settings.explain_enabled and not event.get("fast_path_used"):
                    if event.get("explanation") is None:
                        continue  # Not yet — explain node hasn't run

                latency_ms = (time.time() - start_time) * 1000
                final_answer = event["final_answer"]
                event_metadata = event.get("metadata", {})

                # Extract unique tool names from tool_calls_history
                agents_used = list(dict.fromkeys(
                    tc.get("name", "") for tc in event.get("tool_calls_history", [])
                    if tc.get("name") and tc.get("name") != "terminate"
                ))

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
                        "metadata": event_metadata,
                        "guardrail_metadata": event.get("guardrail_metadata"),
                        "explanation": event.get("explanation"),
                        "agents_used": agents_used,
                    },
                }
                break

    except Exception as e:
        # Check if this is a GraphInterrupt (HITL — clarification, approval, etc.)
        if type(e).__name__ == "GraphInterrupt":
            # Extract interrupt payload from the exception
            interrupt_value = None
            if hasattr(e, "interrupts") and e.interrupts:
                interrupt_value = e.interrupts[0].value if hasattr(e.interrupts[0], "value") else None
            elif hasattr(e, "args") and e.args:
                interrupt_value = e.args[0] if e.args else None

            logger.info(f"ReAct graph interrupted (HITL/exception) for thread_id={thread_id}")
            # Dispatch SSE event type based on the interrupt value's type field
            interrupt_type = "clarification"  # default for legacy interrupts
            if isinstance(interrupt_value, dict):
                interrupt_type = interrupt_value.get("type", "clarification")
            yield {
                "type": interrupt_type,
                "data": {
                    "thread_id": thread_id,
                    **(interrupt_value if isinstance(interrupt_value, dict) else {"message": str(interrupt_value)}),
                },
            }
        else:
            logger.error(f"ReAct stream error: {e}", exc_info=True)
            yield {"type": "error", "data": {"error": str(e), "thread_id": thread_id}}

    finally:
        clear_execution_context()

    # ─── Post-stream interrupt detection ──────────────────────────────
    # In LangGraph >=1.0, interrupt() with astream() does NOT raise
    # GraphInterrupt. The stream simply ends after the interrupted node.
    # Detect this by checking the checkpoint for pending interrupts.
    if last_values_event and not last_values_event.get("is_complete"):
        try:
            state_snapshot = await graph.aget_state(langgraph_config)
            if hasattr(state_snapshot, "tasks") and state_snapshot.tasks:
                for task in state_snapshot.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        interrupt_value = task.interrupts[0].value if hasattr(task.interrupts[0], "value") else None
                        logger.info(f"ReAct graph interrupted (HITL/post-stream) for thread_id={thread_id}")
                        # Dispatch SSE event type based on the interrupt value's type field
                        interrupt_type = "clarification"  # default for legacy interrupts
                        if isinstance(interrupt_value, dict):
                            interrupt_type = interrupt_value.get("type", "clarification")
                        yield {
                            "type": interrupt_type,
                            "data": {
                                "thread_id": thread_id,
                                **(interrupt_value if isinstance(interrupt_value, dict) else {"message": str(interrupt_value)}),
                            },
                        }
                        break
        except Exception as check_err:
            logger.debug(f"Post-stream interrupt check failed: {check_err}")


# =============================================================================
# Resume after interrupt (HITL — clarification, approval, etc.)
# =============================================================================

async def resume_react_query(
    thread_id: str,
    resume_value: Any,
    tenant_id: str,
    user_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Resume a paused ReAct graph after a HITL interrupt.

    Uses Command(resume=value) to continue the graph from where it paused.
    The resumed node re-executes from the beginning, but interrupt() returns
    the resume_value instead of pausing again.

    Args:
        thread_id: The thread ID of the paused graph
        resume_value: The value to pass back to interrupt() (e.g., user's selected option)
        tenant_id: Tenant ID
        user_id: Optional user ID
    """
    from langgraph.types import Command
    from .graph import get_react_graph

    start_time = time.time()

    set_execution_context(tenant_id=tenant_id, user_id=user_id)

    # Format a human-friendly label for the resume value (HITL decision)
    resume_label = str(resume_value)
    if isinstance(resume_value, dict):
        dtype = resume_value.get("type", "")
        if dtype == "approve":
            resume_label = "Aprobado"
        elif dtype == "edit":
            resume_label = "Editado y enviado"
        elif dtype == "reject":
            resume_label = f"Rechazado{': ' + resume_value.get('message', '') if resume_value.get('message') else ''}"

    yield {
        "type": "started",
        "data": {"thread_id": thread_id, "query": resume_label, "graph_type": "react_resume"},
    }

    try:
        graph = await get_react_graph()
        langgraph_config = {"configurable": {"thread_id": thread_id}}

        # Get event offset from checkpoint to skip pre-interrupt events
        emitted_step_count = 0
        try:
            checkpoint_state = await graph.aget_state(langgraph_config)
            if checkpoint_state and checkpoint_state.values:
                emitted_step_count = len(
                    checkpoint_state.values.get("reasoning_steps", [])
                )
        except Exception:
            pass

        received_real_tokens = False

        # Resume with Command(resume=value)
        async for mode, event in graph.astream(
            Command(resume=resume_value),
            config=langgraph_config,
            stream_mode=["values", "custom"],
        ):
            if mode == "custom":
                evt_type = event.get("type", "custom_event")
                evt_data = event.get("data", {})
                if evt_type == "token":
                    received_real_tokens = True
                    yield {"type": "token", "data": evt_data}
                else:
                    yield {"type": evt_type, "data": evt_data}
                continue

            # mode == "values"
            reasoning_steps = event.get("reasoning_steps", [])
            for step in reasoning_steps[emitted_step_count:]:
                emitted_step_count += 1
                step_type = step.get("type", "reasoning")
                if step_type == "thinking":
                    yield {"type": "thinking", "data": {"content": step.get("content", "")}}
                elif step_type == "tool_call":
                    yield {"type": "tool_call", "data": {"content": step.get("content", "")}}
                elif step_type == "observation":
                    yield {"type": "tool_result", "data": {"content": step.get("content", ""), "source": step.get("source", "")}}
                else:
                    yield {"type": "reasoning_step", "data": {"step_type": step_type, "content": step.get("content", "")}}

            if event.get("final_answer") and event.get("is_complete"):
                # If explain is enabled, wait for the explanation field
                from app.core.config import settings as app_settings
                if app_settings.explain_enabled and not event.get("fast_path_used"):
                    if event.get("explanation") is None:
                        continue  # Not yet — explain node hasn't run

                latency_ms = (time.time() - start_time) * 1000
                final_answer = event["final_answer"]

                if not received_real_tokens:
                    words = final_answer.split(' ')
                    for i, word in enumerate(words):
                        token = f" {word}" if i > 0 else word
                        yield {"type": "token", "data": {"text": token, "token": token}}
                        await asyncio.sleep(0)

                yield {
                    "type": "complete",
                    "data": {
                        "success": event.get("success", True),
                        "answer": final_answer,
                        "sources": event.get("sources", []),
                        "thread_id": thread_id,
                        "latency_ms": latency_ms,
                        "total_steps": event.get("current_step", 0),
                        "graph_type": "react_resume",
                        "metadata": event.get("metadata", {}),
                        "guardrail_metadata": event.get("guardrail_metadata"),
                        "explanation": event.get("explanation"),
                    },
                }
                break

    except Exception as e:
        if type(e).__name__ == "GraphInterrupt":
            logger.info(f"ReAct resume: another interrupt at thread_id={thread_id}")
            interrupt_value = None
            if hasattr(e, "interrupts") and e.interrupts:
                interrupt_value = e.interrupts[0].value if hasattr(e.interrupts[0], "value") else None
            # Dispatch SSE event type based on the interrupt value's type field
            interrupt_type = "clarification"  # default for legacy interrupts
            if isinstance(interrupt_value, dict):
                interrupt_type = interrupt_value.get("type", "clarification")
            yield {
                "type": interrupt_type,
                "data": {
                    "thread_id": thread_id,
                    **(interrupt_value if isinstance(interrupt_value, dict) else {"message": str(interrupt_value)}),
                },
            }
        else:
            logger.error(f"ReAct resume error: {e}", exc_info=True)
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
    """Execute a LangGraph query. Always returns a result (LangGraph is always enabled).

    Kept for backwards compatibility with callers that check for None.
    """
    return await execute_langgraph_query(
        query=query,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=thread_id,
        **kwargs,
    )
