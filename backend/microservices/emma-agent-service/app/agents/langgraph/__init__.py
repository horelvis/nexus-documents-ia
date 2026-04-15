"""
LangGraph ReAct Agent — Core Orchestration Engine

Architecture:
    START -> classify -> [fast_path -> END]
                       -> rewrite -> memory_recall -> react_loop <-> synthesize -> END      (simple)
                       -> rewrite -> memory_recall -> decompose -> [swarm_worker x N] ->    (complex)
                         synthesize_swarm -> END

Sub-graphs (invoked as tools from the ReAct agent):
    - VerifiedGenGraph: claim-by-claim verified document generation
    - PredictiveGraph: factor extraction + outcome evaluation + recommendation

Usage:
    from app.agents.langgraph import execute_langgraph_query

    result = await execute_langgraph_query(
        query="What GDPR documents do I have?",
        user_id="user-456",
        user_roles=["legal", "EVERYONE"],
    )
    print(result.answer)
"""

from .state import ReActState, ExecutionConfig, create_initial_react_state
from .graph import create_react_graph, get_react_graph, execute_react_query
from .api import (
    execute_langgraph_query,
    stream_react_query,
    is_langgraph_enabled,
    maybe_use_langgraph,
    LangGraphQueryRequest,
    LangGraphQueryResponse,
)

__all__ = [
    "ReActState",
    "ExecutionConfig",
    "create_initial_react_state",
    "create_react_graph",
    "get_react_graph",
    "execute_react_query",
    "execute_langgraph_query",
    "stream_react_query",
    "is_langgraph_enabled",
    "maybe_use_langgraph",
    "LangGraphQueryRequest",
    "LangGraphQueryResponse",
]
