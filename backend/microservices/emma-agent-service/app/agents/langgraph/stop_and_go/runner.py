"""
SSE Bridge — drains pending_events from LangGraph state snapshots.

LangGraph nodes can't yield events directly. Instead:
1. Each node appends events to state["pending_events"]
2. The merge_lists reducer accumulates them across snapshots
3. This runner uses graph.astream(stream_mode="values") to get snapshots
4. After each snapshot, it yields only NEW events (events we haven't seen)
5. This keeps the existing SSE contract intact

HITL support:
- When thread_id is provided, it's added to config["configurable"]
- When resume_value is provided, graph is invoked with Command(resume=value)
  and events_offset skips pre-interrupt events
- GraphInterrupt exceptions are caught and surfaced as a special
  "__interrupt__" event so the service layer can close the SSE cleanly

The frontend receives the same event types as before — zero changes needed
(except for the new review_requested/review_submitted events).
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, Optional

from .state import StopAndGoState

logger = logging.getLogger(__name__)


async def stream_stop_and_go(
    graph,
    initial_state: StopAndGoState,
    *,
    thread_id: Optional[str] = None,
    resume_value: Optional[dict] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Bridge between LangGraph state snapshots and SSE events.

    Yields event dicts as they accumulate in pending_events.
    The caller maps these to PredictiveEvent or VerificationEvent.

    Args:
        graph: Compiled StopAndGoGraph
        initial_state: Initial state dict (ignored when resuming)
        thread_id: Thread ID for checkpointed graphs (required for HITL)
        resume_value: Human review decisions (set when resuming after review)

    Yields:
        Event dicts with at least 'event_type' and 'data'
    """
    config: Dict[str, Any] = {"recursion_limit": 100}

    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    # Determine input and event offset
    if resume_value is not None:
        # Resuming after HITL interrupt — use Command(resume=...)
        from langgraph.types import Command

        graph_input = Command(resume=resume_value)

        # Skip pre-interrupt events by reading offset from checkpoint metadata
        events_offset = await _get_events_offset(graph, config)
        seen_events = events_offset
        logger.info(
            f"[runner] Resuming with events_offset={events_offset}, "
            f"thread_id={thread_id}"
        )
    else:
        graph_input = initial_state
        seen_events = 0

    try:
        async for snapshot in graph.astream(
            graph_input, config, stream_mode="values"
        ):
            events = snapshot.get("pending_events", [])

            # Only yield NEW events (merge_lists accumulates, so list grows)
            new_events = events[seen_events:]
            seen_events = len(events)

            for event in new_events:
                yield event

    except Exception as exc:
        # Check if this is a GraphInterrupt (HITL pause)
        exc_type = type(exc).__name__
        if exc_type == "GraphInterrupt":
            # The review_requested event was already emitted by review_node
            # and yielded above before the interrupt. We just need to signal
            # the service layer that the graph is paused.
            logger.info(
                f"[runner] Graph interrupted for HITL review "
                f"(thread_id={thread_id})"
            )
            yield {
                "event_type": "__interrupt__",
                "data": {"thread_id": thread_id},
            }
        else:
            logger.error(f"[runner] Unexpected error: {exc}")
            yield {
                "event_type": "error",
                "data": {"error": str(exc)},
            }


async def _get_events_offset(graph, config: dict) -> int:
    """
    Read the number of pending_events from the last checkpoint.

    This tells us how many events were emitted before the interrupt,
    so we can skip them when resuming.
    """
    try:
        state = await graph.aget_state(config)
        if state and state.values:
            events = state.values.get("pending_events", [])
            return len(events)
    except Exception as e:
        logger.warning(f"[runner] Could not read events offset: {e}")
    return 0
