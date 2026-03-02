"""
LangGraph ReAct Agent Architecture

This module implements a LangGraph-based ReAct agent system with:
- ReActState (TypedDict) for explicit state management
- Conditional routing (fast-path, react loop, swarm decomposition)
- Swarm parallel execution for complex queries
- Built-in memory/checkpointing

Architecture:
    START -> classify -> [fast_path -> END]
                       -> react_loop <-> synthesize -> END       (simple)
                       -> decompose -> [swarm_worker x N] ->     (complex)
                         synthesize_swarm -> END

Usage:
    from app.agents.langgraph import execute_langgraph_query, is_langgraph_enabled

    if is_langgraph_enabled():
        result = await execute_langgraph_query(
            query="What GDPR documents do I have?",
            tenant_id="tenant-123",
            user_id="user-456",
        )
        print(result.answer)

Feature Flags:
    - LANGGRAPH_RAG_ENABLED: Enable LangGraph for all tenants (uses ReAct agent)
    - LANGGRAPH_TENANTS: Comma-separated list of tenant IDs to enable
"""

from .state import RAGState, ReActState, ExecutionConfig, create_initial_state, create_initial_react_state
from .graph import create_react_graph, get_react_graph, execute_react_query
from .api import (
    execute_langgraph_query,
    stream_react_query,
    is_langgraph_enabled,
    is_langgraph_enabled_for_tenant,
    maybe_use_langgraph,
    LangGraphQueryRequest,
    LangGraphQueryResponse,
)

__all__ = [
    # State (RAGState kept for stop_and_go/verified_generation compatibility)
    "RAGState",
    "ReActState",
    "ExecutionConfig",
    "create_initial_state",
    "create_initial_react_state",
    # ReAct Graph
    "create_react_graph",
    "get_react_graph",
    "execute_react_query",
    # API
    "execute_langgraph_query",
    "stream_react_query",
    "is_langgraph_enabled",
    "is_langgraph_enabled_for_tenant",
    "maybe_use_langgraph",
    "LangGraphQueryRequest",
    "LangGraphQueryResponse",
]
