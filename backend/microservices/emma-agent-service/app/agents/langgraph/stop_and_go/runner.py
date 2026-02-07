"""
SSE Bridge — drains pending_events from LangGraph state snapshots.

LangGraph nodes can't yield events directly. Instead:
1. Each node appends events to state["pending_events"]
2. The merge_lists reducer accumulates them across snapshots
3. This runner uses graph.astream(stream_mode="values") to get snapshots
4. After each snapshot, it yields only NEW events (events we haven't seen)
5. This keeps the existing SSE contract intact

The frontend receives the same event types as before — zero changes needed.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict

from .state import StopAndGoState

logger = logging.getLogger(__name__)


async def stream_stop_and_go(
    graph,
    initial_state: StopAndGoState,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Bridge between LangGraph state snapshots and SSE events.

    Yields event dicts as they accumulate in pending_events.
    The caller maps these to PredictiveEvent or VerificationEvent.

    Args:
        graph: Compiled StopAndGoGraph
        initial_state: Initial state dict

    Yields:
        Event dicts with at least 'event_type' and 'data'
    """
    seen_events = 0  # Track how many events we've already yielded

    config = {"recursion_limit": 100}  # Safety limit for the loop

    async for snapshot in graph.astream(initial_state, config, stream_mode="values"):
        events = snapshot.get("pending_events", [])

        # Only yield NEW events (merge_lists accumulates, so list grows)
        new_events = events[seen_events:]
        seen_events = len(events)

        for event in new_events:
            yield event
