"""
LangGraph Server Protocol SSE Adapter

Translates Emma's internal SSE events (from stream_react_query / resume_react_query)
into the LangGraph Server wire protocol that @langchain/langgraph-sdk useStream expects.

LangGraph protocol SSE event types:
    - event: metadata     {"run_id": "..."}
    - event: values       {"messages": [...], ...state}  (primary data source for useStream)
    - event: updates      {"node_name": {...}}  (node-level output)
    - event: end          null

Emma internal event types:
    started, thinking, tool_call, tool_result, reasoning_step,
    token, complete, error,
    swarm_started, worker_started, worker_complete, swarm_synthesizing,
    clarification, confirmation, hitl_review
"""

import json
import logging
import uuid
from typing import Any, AsyncGenerator, Dict, List

logger = logging.getLogger(__name__)


def _sse_line(event: str, data: Any) -> str:
    """Format a single SSE event line."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _make_ai_message(
    content: str,
    msg_id: str | None = None,
    tool_calls: List[Dict] | None = None,
) -> Dict:
    """Create a serialized AIMessage dict compatible with useStream.

    Args:
        content: Message text (may be partial during token streaming).
        msg_id: Stable message ID — MUST be consistent across all values
            events within a single run so the SDK's message reducer can
            identify it as the same message being updated (streaming).
        tool_calls: Optional tool call metadata.
    """
    msg = {
        "type": "ai",
        "content": content,
        "id": msg_id or str(uuid.uuid4()),
    }
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _make_human_message(content: str) -> Dict:
    """Create a serialized HumanMessage dict."""
    return {
        "type": "human",
        "content": content,
        "id": str(uuid.uuid4()),
    }


async def translate_to_langgraph_sse(
    emma_event_generator: AsyncGenerator[Dict[str, Any], None],
    thread_id: str,
    prior_messages: List[Dict] | None = None,
) -> AsyncGenerator[str, None]:
    """Translate Emma SSE events into LangGraph Server protocol SSE format.

    This is the core adapter that allows @langchain/langgraph-sdk's useStream
    hook to consume Emma's existing streaming pipeline without modifying any
    of the LangGraph nodes.

    The translation accumulates state (messages, sources, metadata) and emits
    `event: values` snapshots that useStream uses to render the UI.

    Args:
        emma_event_generator: Async generator from stream_react_query() or
            resume_react_query() yielding {"type": str, "data": dict}.
        thread_id: The conversation thread ID.
        prior_messages: Conversation history from checkpointer to include
            in every values snapshot (multi-turn continuity).

    Yields:
        SSE-formatted strings in LangGraph Server protocol.
    """
    run_id = str(uuid.uuid4())
    # Stable AI message ID for this run — the SDK's message reducer uses
    # the id to identify "the same message being updated" across values
    # events, enabling progressive token streaming in the UI.
    ai_msg_id = str(uuid.uuid4())

    # Accumulated state for values snapshots — seed with prior conversation
    messages: List[Dict] = list(prior_messages) if prior_messages else []
    accumulated_text = ""
    sources: List[Dict] = []
    reasoning_steps: List[Dict] = []

    # Emit metadata event (first event useStream expects)
    yield _sse_line("metadata", {"run_id": run_id, "thread_id": thread_id})

    try:
        async for event in emma_event_generator:
            event_type = event.get("type", "")
            data = event.get("data", {})

            if event_type == "started":
                # Emit initial values with the user query as first message
                query = data.get("query", "")
                if query:
                    messages.append(_make_human_message(query))
                yield _sse_line("values", {
                    "messages": list(messages),
                    "reasoning_steps": list(reasoning_steps),
                    "thread_id": data.get("thread_id", thread_id),

                })

            elif event_type == "thinking":
                content = data.get("content", "")
                if content:
                    reasoning_steps.append({"type": "thinking", "content": content})
                    # Emit both updates (for SDK internals) and values (for UI)
                    yield _sse_line("updates", {
                        "classify": {"type": "thinking", "content": content},
                    })
                    yield _sse_line("values", {
                        "messages": list(messages) + (
                            [_make_ai_message(accumulated_text, msg_id=ai_msg_id)] if accumulated_text else []
                        ),
                        "reasoning_steps": list(reasoning_steps),
    
                    })

            elif event_type == "tool_call":
                content = data.get("content", "")
                if content:
                    step = {"type": "tool_call", "content": content}
                    if data.get("summary"):
                        step["summary"] = data["summary"]
                    reasoning_steps.append(step)
                    yield _sse_line("updates", {
                        "react_loop": {"type": "tool_call", "content": content},
                    })
                    yield _sse_line("values", {
                        "messages": list(messages) + (
                            [_make_ai_message(accumulated_text, msg_id=ai_msg_id)] if accumulated_text else []
                        ),
                        "reasoning_steps": list(reasoning_steps),
    
                    })

            elif event_type == "tool_result":
                content = data.get("content", "")
                source = data.get("source", "")
                if content:
                    step = {"type": "tool_result", "content": content, "source": source}
                    if data.get("summary"):
                        step["summary"] = data["summary"]
                    reasoning_steps.append(step)
                    yield _sse_line("updates", {
                        "react_loop": {
                            "type": "tool_result",
                            "content": content,
                            "source": source,
                        },
                    })
                    yield _sse_line("values", {
                        "messages": list(messages) + (
                            [_make_ai_message(accumulated_text, msg_id=ai_msg_id)] if accumulated_text else []
                        ),
                        "reasoning_steps": list(reasoning_steps),
    
                    })

            elif event_type == "reasoning_step":
                step_type = data.get("step_type", "reasoning")
                content = data.get("content", "")
                if content:
                    step = {"type": step_type, "content": content}
                    if data.get("summary"):
                        step["summary"] = data["summary"]
                    reasoning_steps.append(step)
                    yield _sse_line("updates", {
                        "react_loop": {"type": step_type, "content": content},
                    })
                    yield _sse_line("values", {
                        "messages": list(messages) + (
                            [_make_ai_message(accumulated_text, msg_id=ai_msg_id)] if accumulated_text else []
                        ),
                        "reasoning_steps": list(reasoning_steps),
    
                    })

            elif event_type == "token":
                # Emit individual token chunks via event: messages.
                # The SDK's MessageTupleManager uses BaseMessageChunk.concat()
                # to accumulate chunks by ID — enabling progressive streaming
                # without full state replacement on each token.
                token_text = data.get("text", data.get("token", ""))
                if token_text:
                    accumulated_text += token_text
                    yield _sse_line("messages", [
                        {"type": "ai", "content": token_text, "id": ai_msg_id},
                        {},  # metadata (empty — no subgraph namespace)
                    ])

            # Swarm events
            elif event_type == "swarm_started":
                yield _sse_line("updates", {
                    "decompose": {
                        "type": "swarm_started",
                        "num_workers": data.get("num_workers", 0),
                        "sub_tasks": data.get("sub_tasks", []),
                    },
                })

            elif event_type == "worker_started":
                yield _sse_line("updates", {
                    "swarm_worker": {
                        "type": "worker_started",
                        "worker_id": data.get("worker_id", 0),
                        "sub_task": data.get("sub_task", ""),
                    },
                })

            elif event_type == "worker_complete":
                yield _sse_line("updates", {
                    "swarm_worker": {
                        "type": "worker_complete",
                        "worker_id": data.get("worker_id", 0),
                        "latency_ms": data.get("latency_ms", 0),
                    },
                })

            elif event_type == "swarm_synthesizing":
                yield _sse_line("updates", {
                    "synthesize_swarm": {
                        "type": "swarm_synthesizing",
                        "successful_workers": data.get("successful_workers", 0),
                    },
                })

            # HITL interrupts
            elif event_type in ("clarification", "confirmation", "hitl_review"):
                interrupt_data = data if isinstance(data, dict) else {"message": str(data)}
                # Emit as values with __interrupt__ marker for useStream detection
                yield _sse_line("values", {
                    "messages": list(messages),
                    "__interrupt__": [{
                        "value": interrupt_data,
                        "resumable": True,
                    }],
                    "thread_id": interrupt_data.get("thread_id", thread_id),

                })
                # Also emit as update for immediate frontend detection
                yield _sse_line("updates", {
                    "classify": {
                        "type": event_type,
                        **interrupt_data,
                    },
                })

            elif event_type == "complete":


                final_answer = data.get("answer", "")
                sources = data.get("sources", [])
                metadata = data.get("metadata", {})

                # Build final AI message
                ai_msg = _make_ai_message(final_answer or accumulated_text, msg_id=ai_msg_id)

                # Final messages list
                final_messages = list(messages) + [ai_msg]

                # Emit final values snapshot with full state
                yield _sse_line("values", {
                    "messages": final_messages,
                    "sources": sources,
                    "thread_id": data.get("thread_id", thread_id),
                    "success": data.get("success", True),
                    "fast_path": data.get("fast_path", False),
                    "latency_ms": data.get("latency_ms", 0),
                    "reasoning_steps": reasoning_steps,
                    "metadata": metadata,
                    "guardrail_metadata": data.get("guardrail_metadata"),
                    "explanation": data.get("explanation"),

                })

            elif event_type == "error":
                error_msg = data.get("error", "Unknown error")
                yield _sse_line("error", {
                    "error": error_msg,
                    "thread_id": data.get("thread_id", thread_id),
                })

    except Exception as e:
        logger.error(f"LangGraph adapter translation error: {e}", exc_info=True)
        yield _sse_line("error", {"error": str(e)})

    # Always emit end event
    yield _sse_line("end", None)
