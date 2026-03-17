"""
Verified Generation StateGraph — claim-by-claim document generation.

Graph structure:
    START → initialize → generate_claim → verify_claim → decide ──→ synthesize → END
                               ↑                           │
                               └────── more_claims ────────┘

Compiled with checkpointer=False (no multi-turn memory).
The graph runs as a single tool invocation inside the ReAct agent.

The synthesize node runs after decide when is_complete=True. It's wired
via a conditional edge from decide — if complete, go to synthesize;
otherwise loop back to generate_claim.
"""

from __future__ import annotations

import logging
from typing import Optional

from langgraph.graph import END, START, StateGraph

from .state import VerifiedGenState
from .nodes import (
    initialize_node,
    generate_claim_node,
    verify_claim_node,
    decide_node,
    synthesize_on_complete,
)

logger = logging.getLogger(__name__)

_graph = None


def _route_from_initialize(state: VerifiedGenState) -> str:
    """Skip to synthesize if initialization failed (no source document)."""
    if state.get("is_complete", False):
        return "synthesize"
    return "generate_claim"


def _route_from_decide(state: VerifiedGenState) -> str:
    """Continue extracting or synthesize."""
    if state.get("is_complete", False):
        return "synthesize"
    return "generate_claim"


def create_verified_gen_graph():
    """Build and compile the verified generation StateGraph."""
    builder = StateGraph(VerifiedGenState)

    builder.add_node("initialize", initialize_node)
    builder.add_node("generate_claim", generate_claim_node)
    builder.add_node("verify_claim", verify_claim_node)
    builder.add_node("decide", decide_node)
    builder.add_node("synthesize", synthesize_on_complete)

    builder.add_edge(START, "initialize")
    builder.add_conditional_edges(
        "initialize",
        _route_from_initialize,
        ["generate_claim", "synthesize"],
    )
    builder.add_edge("generate_claim", "verify_claim")
    builder.add_edge("verify_claim", "decide")
    builder.add_conditional_edges(
        "decide",
        _route_from_decide,
        ["generate_claim", "synthesize"],
    )
    builder.add_edge("synthesize", END)

    return builder.compile(checkpointer=False)


def get_verified_gen_graph():
    """Get the singleton compiled verified generation graph."""
    global _graph
    if _graph is None:
        _graph = create_verified_gen_graph()
        logger.info("Verified Generation sub-graph compiled")
    return _graph
