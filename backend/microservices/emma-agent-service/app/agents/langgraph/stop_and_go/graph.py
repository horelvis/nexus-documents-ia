"""
Stop-and-Go StateGraph definition.

Graph structure:
    START → initialize → extract_item → search_and_evaluate → decide
                              ↑                                  |
                              └──── (continue) ─────────────────┘
                                                                 |
                                                          (complete)
                                                                 ↓
                                                           synthesize → END
"""

from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, START, StateGraph

from .state import StopAndGoState
from .nodes import (
    initialize_node,
    extract_item_node,
    search_and_evaluate_node,
    decide_node,
    synthesize_node,
)

logger = logging.getLogger(__name__)


def _route_from_decide(state: StopAndGoState) -> str:
    """Conditional edge: continue extracting or synthesize."""
    if state.get("is_complete", False):
        return "synthesize"
    return "extract_item"


def create_stop_and_go_graph() -> StateGraph:
    """
    Build and compile the stop-and-go StateGraph.

    Returns a compiled graph ready for `.astream()`.
    """
    builder = StateGraph(StopAndGoState)

    # Add nodes
    builder.add_node("initialize", initialize_node)
    builder.add_node("extract_item", extract_item_node)
    builder.add_node("search_and_evaluate", search_and_evaluate_node)
    builder.add_node("decide", decide_node)
    builder.add_node("synthesize", synthesize_node)

    # Edges
    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "extract_item")
    builder.add_edge("extract_item", "search_and_evaluate")
    builder.add_edge("search_and_evaluate", "decide")
    builder.add_conditional_edges("decide", _route_from_decide)
    builder.add_edge("synthesize", END)

    return builder.compile()


# Singleton compiled graph
_compiled_graph = None


def get_stop_and_go_graph():
    """Get the singleton compiled stop-and-go graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = create_stop_and_go_graph()
        logger.info("Stop-and-Go graph compiled")
    return _compiled_graph
