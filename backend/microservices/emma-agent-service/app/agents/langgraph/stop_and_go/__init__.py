"""
Stop-and-Go LangGraph — shared graph for Predictive Analysis + Verified Generation.

Both services share the same loop pattern:
    initialize → LOOP(extract → search_evidence → evaluate → accept/reject) → synthesize

This package provides:
- StopAndGoState: Shared TypedDict state
- StopAndGoStrategy: Protocol for mode-specific behavior
- create_stop_and_go_graph(): Compiled StateGraph
- stream_stop_and_go(): SSE bridge for streaming events

Usage (from service layer):
    from app.agents.langgraph.stop_and_go import (
        get_stop_and_go_graph,
        stream_stop_and_go,
        create_initial_state,
    )

    graph = get_stop_and_go_graph()
    state = create_initial_state(mode="predictive", ...)
    async for event in stream_stop_and_go(graph, state):
        yield PredictiveEvent(**event)
"""

from .state import StopAndGoState, create_initial_state
from .strategy import StopAndGoStrategy, register_strategy, get_strategy
from .graph import create_stop_and_go_graph, get_stop_and_go_graph
from .runner import stream_stop_and_go

# Import strategies to trigger registration
from . import strategies  # noqa: F401

__all__ = [
    "StopAndGoState",
    "StopAndGoStrategy",
    "create_initial_state",
    "create_stop_and_go_graph",
    "get_stop_and_go_graph",
    "stream_stop_and_go",
    "register_strategy",
    "get_strategy",
]
