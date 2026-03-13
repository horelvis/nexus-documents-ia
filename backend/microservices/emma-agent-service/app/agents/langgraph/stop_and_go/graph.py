"""
Stop-and-Go StateGraph definition.

Graph structure (HITL enabled):
    START → initialize → extract_item → search_and_evaluate → decide
                              ↑                                  |
                              └──── (continue) ─────────────────┘
                                                                 |
                                                          (complete)
                                                                 ↓
                                                             review ─── interrupt() ──→ [SSE closes]
                                                                 |
                                                        Command(resume=decisions)
                                                                 ↓
                                                           synthesize → END

When HITL is disabled (or predictive mode), the review node is a
transparent pass-through — zero behavioral change.

Dual compilation:
- get_stop_and_go_graph()        → simple graph (no checkpointer)
- get_stop_and_go_graph_hitl()   → compiled with AsyncPostgresSaver
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
    review_node,
    synthesize_node,
)

logger = logging.getLogger(__name__)


def _route_from_initialize(state: StopAndGoState) -> str:
    """Skip to synthesize if initialization failed (no source document)."""
    if state.get("is_complete", False):
        return "synthesize"
    return "extract_item"


def _route_from_decide(state: StopAndGoState) -> str:
    """Conditional edge: continue extracting or go to review."""
    if state.get("is_complete", False):
        return "review"
    return "extract_item"


def _build_graph() -> StateGraph:
    """
    Build the stop-and-go StateGraph (uncompiled).

    Topology:
        initialize → [extract_item → search_and_evaluate → decide] ⟲
                                                            ↓
                                                          review → synthesize
    """
    builder = StateGraph(StopAndGoState)

    # Add nodes
    builder.add_node("initialize", initialize_node)
    builder.add_node("extract_item", extract_item_node)
    builder.add_node("search_and_evaluate", search_and_evaluate_node)
    builder.add_node("decide", decide_node)
    builder.add_node("review", review_node)
    builder.add_node("synthesize", synthesize_node)

    # Edges
    builder.add_edge(START, "initialize")
    builder.add_conditional_edges(
        "initialize",
        _route_from_initialize,
        {"extract_item": "extract_item", "synthesize": "synthesize"},
    )
    builder.add_edge("extract_item", "search_and_evaluate")
    builder.add_edge("search_and_evaluate", "decide")
    builder.add_conditional_edges(
        "decide",
        _route_from_decide,
        {"extract_item": "extract_item", "review": "review"},
    )
    builder.add_edge("review", "synthesize")
    builder.add_edge("synthesize", END)

    return builder


def create_stop_and_go_graph():
    """
    Build and compile the stop-and-go StateGraph (no checkpointer).

    Used for predictive analysis and verified generation without HITL.
    Returns a compiled graph ready for `.astream()`.
    """
    return _build_graph().compile()


# Singleton compiled graph (simple, no checkpointer)
_compiled_graph = None


def get_stop_and_go_graph():
    """Get the singleton compiled stop-and-go graph (no checkpointer)."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = create_stop_and_go_graph()
        logger.info("Stop-and-Go graph compiled (simple)")
    return _compiled_graph


# Singleton HITL graph (compiled with checkpointer)
_compiled_graph_hitl = None


async def get_stop_and_go_graph_hitl():
    """
    Get the singleton HITL-enabled stop-and-go graph.

    Compiled with AsyncPostgresSaver checkpointer to support
    interrupt()/Command(resume=...) for human-in-the-loop review.

    Returns None if checkpointer is disabled.
    """
    global _compiled_graph_hitl
    if _compiled_graph_hitl is not None:
        return _compiled_graph_hitl

    from app.core.checkpointer import get_checkpointer

    checkpointer = await get_checkpointer()
    if checkpointer is None:
        logger.warning(
            "HITL graph requested but checkpointer is disabled — "
            "falling back to simple graph"
        )
        return get_stop_and_go_graph()

    _compiled_graph_hitl = _build_graph().compile(checkpointer=checkpointer)
    logger.info("Stop-and-Go HITL graph compiled (with checkpointer)")
    return _compiled_graph_hitl
