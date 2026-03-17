"""
Predictive Analysis StateGraph — factor extraction + outcome evaluation.

Graph structure:
    START → initialize → extract_factor → evaluate_outcome → decide ──→ synthesize → END
                               ↑                               │
                               └────────── more_factors ────────┘
"""

from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, START, StateGraph

from .state import PredictiveState
from .nodes import (
    initialize_node,
    extract_factor_node,
    evaluate_outcome_node,
    decide_node,
    synthesize_on_complete,
)

logger = logging.getLogger(__name__)

_graph = None


def _route_from_decide(state: PredictiveState) -> str:
    if state.get("is_complete", False):
        return "synthesize"
    return "extract_factor"


def create_predictive_graph():
    """Build and compile the predictive analysis StateGraph."""
    builder = StateGraph(PredictiveState)

    builder.add_node("initialize", initialize_node)
    builder.add_node("extract_factor", extract_factor_node)
    builder.add_node("evaluate_outcome", evaluate_outcome_node)
    builder.add_node("decide", decide_node)
    builder.add_node("synthesize", synthesize_on_complete)

    builder.add_edge(START, "initialize")
    builder.add_edge("initialize", "extract_factor")
    builder.add_edge("extract_factor", "evaluate_outcome")
    builder.add_edge("evaluate_outcome", "decide")
    builder.add_conditional_edges(
        "decide",
        _route_from_decide,
        ["extract_factor", "synthesize"],
    )
    builder.add_edge("synthesize", END)

    return builder.compile(checkpointer=False)


def get_predictive_graph():
    """Get the singleton compiled predictive analysis graph."""
    global _graph
    if _graph is None:
        _graph = create_predictive_graph()
        logger.info("Predictive Analysis sub-graph compiled")
    return _graph
