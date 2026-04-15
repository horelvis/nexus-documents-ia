"""
LangGraph Server Protocol Endpoints

Implements a subset of the LangGraph Server API that the @langchain/langgraph-sdk
useStream hook expects. This allows the frontend to migrate from custom SSE
handling to the standard LangGraph SDK without changing the backend agent logic.

Endpoints:
    GET  /api/info                              Server metadata
    POST /api/threads                           Create a new thread
    GET  /api/threads                           List threads (placeholder)
    GET  /api/threads/{thread_id}               Thread details
    GET  /api/threads/{thread_id}/state         Current state from checkpointer
    POST /api/threads/{thread_id}/history       Checkpoint history
    POST /api/threads/{thread_id}/runs/stream   Execute run with SSE streaming

Auth: X-API-Key header (verify_api_key dependency) + X-Tenant-ID header.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import verify_api_key_or_bearer as verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["langgraph-protocol"])


# =============================================================================
# HITL Decision Formatting
# =============================================================================

def _format_hitl_decision(resume_value: Any) -> Optional[str]:
    """Convert a raw HITL decision dict into a human-friendly label.

    When a user approves/edits/rejects via the HITLReviewCard, the SDK sends
    the decision as Command(resume={type: 'approve'|'edit'|'reject', ...}).
    LangGraph persists this as a HumanMessage with the raw dict as content.
    This helper generates a clean label to show in chat instead.

    Returns None if the value is not a recognized HITL decision.
    """
    if not isinstance(resume_value, dict):
        return None

    decision_type = resume_value.get("type")
    if decision_type == "approve":
        return "Aprobado"
    elif decision_type == "edit":
        return "Editado y enviado"
    elif decision_type == "reject":
        message = resume_value.get("message", "")
        return f"Rechazado: {message}" if message else "Rechazado"

    return None


def _sanitize_checkpoint_message(content: str) -> Optional[str]:
    """Detect a raw HITL decision dict in a HumanMessage content string
    and return a friendly label. Returns None if not a decision.

    LangGraph persists Command(resume=value) as HumanMessage(content=str(value)).
    This produces Python dict repr like "{'type': 'edit', 'edited_args': {...}}".
    """
    import re
    trimmed = content.strip()
    if not re.match(r"""^[{'"]\s*['"]?type['"]?\s*:\s*['"]?(approve|edit|reject)""", trimmed):
        return None

    if "'approve'" in trimmed or '"approve"' in trimmed:
        return "Aprobado"
    elif "'edit'" in trimmed or '"edit"' in trimmed:
        return "Editado y enviado"
    elif "'reject'" in trimmed or '"reject"' in trimmed:
        msg_match = re.search(r"""['"]message['"]:\s*['"]([^'"]+)['"]""", trimmed)
        return f"Rechazado: {msg_match.group(1)}" if msg_match else "Rechazado"

    return None


# =============================================================================
# Request / Response Models
# =============================================================================

class RunInput(BaseModel):
    """Input for POST /threads/{thread_id}/runs/stream.

    Follows the LangGraph Server schema:
    - input: initial state (must contain messages list)
    - command: resume payload for HITL interrupts
    - config: LangGraph config overrides
    - checkpoint: checkpoint_id for branch/regenerate
    """
    input: Optional[Dict[str, Any]] = Field(None, description="Initial state with messages")
    command: Optional[Dict[str, Any]] = Field(None, description="Resume command (e.g., {resume: value})")
    config: Optional[Dict[str, Any]] = Field(None, description="LangGraph config overrides")
    checkpoint: Optional[Dict[str, Any]] = Field(None, description="Checkpoint for regeneration")
    assistant_id: Optional[str] = Field(None, description="Assistant ID (unused, for SDK compat)")
    stream_mode: Optional[List[str]] = Field(
        default=None,
        description="Stream modes (values, updates, etc.)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "input": {
                    "messages": [{"type": "human", "content": "Hola"}],
                },
            },
        }


class ThreadCreateRequest(BaseModel):
    """Request to create a new thread."""
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class ThreadResponse(BaseModel):
    """Thread metadata response."""
    thread_id: str
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ServerInfo(BaseModel):
    """Server metadata for useStream SDK."""
    version: str = "1.0.0"
    name: str = "emma-agent-service"
    description: str = "Emma LangGraph Agent — LangGraph protocol adapter"


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/info", response_model=ServerInfo)
async def get_info():
    """Server metadata — used by LangGraph SDK for capability detection."""
    return ServerInfo()


@router.post("/threads", response_model=ThreadResponse)
async def create_thread(
    body: Optional[ThreadCreateRequest] = None,
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Create a new conversation thread.

    Returns a thread_id that can be used with /runs/stream.
    The actual thread state is created lazily when the first run executes
    (the checkpointer creates it on first graph.astream call).
    """
    thread_id = str(uuid.uuid4())
    metadata = (body.metadata if body else {}) or {}
    metadata["tenant_id"] = x_tenant_id

    return ThreadResponse(
        thread_id=thread_id,
        metadata=metadata,
    )


@router.get("/threads", response_model=List[ThreadResponse])
async def list_threads(
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    limit: int = 20,
    offset: int = 0,
):
    """List threads for a tenant.

    Placeholder — returns empty list. Full implementation will query
    emma_sessions table filtered by tenant_id.
    """
    # TODO: Query emma_sessions for this tenant
    return []


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Get thread details.

    Returns thread metadata. The thread exists if the checkpointer has
    state for this thread_id.
    """
    # Try to get state from checkpointer
    try:
        from app.agents.langgraph.graph import get_react_graph
        graph = await get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        if state and state.values:
            return ThreadResponse(
                thread_id=thread_id,
                metadata=state.values.get("metadata", {}),
            )
    except Exception as e:
        logger.debug(f"Could not load thread state for {thread_id}: {e}")

    # Thread may not have state yet (created but no runs)
    return ThreadResponse(
        thread_id=thread_id,
        metadata={"tenant_id": x_tenant_id},
    )


@router.get("/threads/{thread_id}/state")
async def get_thread_state(
    thread_id: str,
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Get current state from the checkpointer.

    Returns the latest checkpoint state for this thread. Used by useStream
    for initial state hydration and interrupt detection on reconnect.
    """
    try:
        from app.agents.langgraph.graph import get_react_graph
        graph = await get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = await graph.aget_state(config)

        if not state_snapshot or not state_snapshot.values:
            raise HTTPException(status_code=404, detail="No state found for thread")

        values = state_snapshot.values

        # Convert LangChain messages to serializable dicts
        messages = []
        for msg in values.get("messages", []):
            if hasattr(msg, "model_dump"):
                msg_dict = msg.model_dump()
            elif hasattr(msg, "dict"):
                msg_dict = msg.dict()
            elif isinstance(msg, dict):
                msg_dict = msg
            else:
                msg_dict = {"type": "unknown", "content": str(msg)}

            # Sanitize HITL resume values persisted as HumanMessages
            if msg_dict.get("type") == "human" and isinstance(msg_dict.get("content"), str):
                friendly = _sanitize_checkpoint_message(msg_dict["content"])
                if friendly:
                    msg_dict = {**msg_dict, "content": friendly}

            messages.append(msg_dict)

        # Check for pending interrupts
        interrupts = []
        if hasattr(state_snapshot, "tasks") and state_snapshot.tasks:
            for task in state_snapshot.tasks:
                if hasattr(task, "interrupts") and task.interrupts:
                    for interrupt in task.interrupts:
                        value = interrupt.value if hasattr(interrupt, "value") else None
                        interrupts.append({
                            "value": value,
                            "resumable": True,
                        })

        result = {
            "values": {
                "messages": messages,
                "sources": values.get("sources", []),
                "thread_id": values.get("thread_id", thread_id),
                "success": values.get("success"),
                "is_complete": values.get("is_complete", False),
            },
            "next": [],  # Next nodes to execute (empty if complete)
        }

        if interrupts:
            result["values"]["__interrupt__"] = interrupts

        # Include checkpoint config for branch switching
        if hasattr(state_snapshot, "config"):
            result["checkpoint"] = state_snapshot.config

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get thread state: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get state: {str(e)}")


@router.post("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    limit: int = 10,
):
    """Get checkpoint history for branch switching.

    Returns a list of checkpoint snapshots for this thread, ordered by
    most recent first. Used by useStream for time-travel / branching.
    """
    try:
        from app.agents.langgraph.graph import get_react_graph
        graph = await get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}

        history = []
        count = 0
        async for state_snapshot in graph.aget_state_history(config):
            if count >= limit:
                break
            checkpoint_config = None
            if hasattr(state_snapshot, "config"):
                checkpoint_config = state_snapshot.config
            history.append({
                "checkpoint": checkpoint_config,
                "values": {
                    "thread_id": thread_id,
                    "is_complete": (state_snapshot.values or {}).get("is_complete", False),
                },
                "next": list(state_snapshot.next) if hasattr(state_snapshot, "next") else [],
            })
            count += 1

        return history

    except Exception as e:
        logger.error(f"Failed to get thread history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


@router.post("/threads/{thread_id}/runs/stream")
async def run_stream(
    thread_id: str,
    body: RunInput,
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    """Execute a run with SSE streaming in LangGraph protocol format.

    This is the main endpoint consumed by useStream. It:
    1. Parses the RunInput body
    2. Routes to stream_react_query() or resume_react_query()
    3. Wraps the generator with translate_to_langgraph_sse()
    4. Returns a StreamingResponse

    The response is a standard SSE stream with events:
    - event: metadata  (run_id, thread_id)
    - event: values    (state snapshots with messages)
    - event: updates   (node-level outputs)
    - event: error     (on failure)
    - event: end       (stream complete)
    """
    from app.services.langgraph_adapter import translate_to_langgraph_sse

    # Resolve user_id: SDK sends it in config.configurable, header is fallback
    configurable = (body.config or {}).get("configurable", {})
    user_id = configurable.get("user_id") or x_user_id

    # Load prior conversation messages from checkpointer for multi-turn continuity.
    # The adapter needs these so every `values` event includes the full history
    # (useStream SDK replaces state on each values event).
    prior_messages = []
    try:
        from app.agents.langgraph.graph import get_react_graph
        graph = await get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state_snapshot = await graph.aget_state(config)
        if state_snapshot and state_snapshot.values:
            for msg in state_snapshot.values.get("messages", []):
                if hasattr(msg, "model_dump"):
                    msg_dict = msg.model_dump()
                elif hasattr(msg, "dict"):
                    msg_dict = msg.dict()
                elif isinstance(msg, dict):
                    msg_dict = msg
                else:
                    continue

                # Sanitize HITL resume values from checkpoint history
                if msg_dict.get("type") == "human" and isinstance(msg_dict.get("content"), str):
                    friendly = _sanitize_checkpoint_message(msg_dict["content"])
                    if friendly:
                        msg_dict = {**msg_dict, "content": friendly}

                prior_messages.append(msg_dict)
    except Exception as e:
        logger.debug(f"Could not load prior messages for thread {thread_id[:8]}: {e}")

    # Determine if this is a resume (HITL interrupt response)
    if body.command and body.command.get("resume") is not None:
        resume_value = body.command["resume"]
        logger.info(f"LangGraph protocol: resuming thread {thread_id[:8]}...")

        # Inject a human-friendly message into prior_messages so the adapter
        # emits it in values snapshots instead of the raw Command(resume=...)
        # dict that LangGraph persists as a HumanMessage in the checkpoint.
        friendly_label = _format_hitl_decision(resume_value)
        if friendly_label:
            prior_messages.append({
                "type": "human",
                "content": friendly_label,
                "id": str(uuid.uuid4()),
            })

        from app.agents.langgraph.api import resume_react_query

        emma_generator = resume_react_query(
            thread_id=thread_id,
            resume_value=resume_value,
            user_id=user_id,
        )

    else:
        # New query — extract from input.messages
        input_data = body.input or {}
        messages = input_data.get("messages", [])
        if not messages:
            raise HTTPException(
                status_code=400,
                detail="input.messages is required and must contain at least one message",
            )

        # Get the last human message as the query
        last_message = messages[-1]
        if isinstance(last_message, dict):
            query = last_message.get("content", "")
        elif isinstance(last_message, str):
            query = last_message
        else:
            query = str(last_message)

        if not query.strip():
            raise HTTPException(status_code=400, detail="Empty query")

        logger.info(
            f"LangGraph protocol: new run thread={thread_id[:8]}... "
            f"query='{query[:50]}...'"
        )

        # Extract config from SDK body (user_id, deep_reasoning, etc.)
        enable_thinking = configurable.get("deep_reasoning") or input_data.get("enable_thinking")
        context = input_data.get("context", {})

        from app.agents.langgraph.api import stream_react_query

        emma_generator = stream_react_query(
            query=query,
            user_id=user_id,
            thread_id=thread_id,
            context=context,
            enable_thinking=enable_thinking,
        )

    # Wrap with the LangGraph protocol translator (prior_messages for multi-turn)
    sse_generator = translate_to_langgraph_sse(emma_generator, thread_id, prior_messages)

    return StreamingResponse(
        sse_generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
