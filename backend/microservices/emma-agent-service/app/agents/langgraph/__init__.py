"""
LangGraph Multi-Agent RAG Architecture

This module implements a LangGraph-based RAG system with:
- Shared state (TypedDict) for explicit state management
- Conditional routing based on execution plan
- Parallel agent execution capability
- Built-in memory/checkpointing

Architecture:
    ┌──────────────────────────────────────────────────────────────────────────────┐
    │                         LANGGRAPH STATE GRAPH                                 │
    │                                                                               │
    │  START → RETRIEVE → PLAN (Emma) → route_to_agents → [Specialist Nodes]       │
    │                                                      → SYNTHESIZE → END      │
    │                                                                               │
    │  Specialists: Privacy, General (more to be added)                            │
    └──────────────────────────────────────────────────────────────────────────────┘

Usage:
    # Option 1: High-level API
    from app.agents.langgraph import execute_langgraph_query

    result = await execute_langgraph_query(
        query="¿Qué documentos sobre RGPD tengo?",
        tenant_id="tenant-123",
        user_id="user-456",
    )
    print(result.answer)

    # Option 2: Direct graph access
    from app.agents.langgraph import create_rag_graph, create_initial_state

    graph = create_rag_graph()
    state = create_initial_state(
        query="¿Cuál es la indemnización por despido?",
        tenant_id="tenant-123",
    )
    result = await graph.ainvoke(state)

Feature Flags:
    - LANGGRAPH_RAG_ENABLED: Enable LangGraph for all tenants (uses ReAct agent)
    - LANGGRAPH_TENANTS: Comma-separated list of tenant IDs to enable
"""

from .state import RAGState, ReActState, ExecutionConfig, create_initial_state, create_initial_react_state
from .graph import (
    create_rag_graph, get_rag_graph, execute_rag_query,
    create_react_graph, get_react_graph, execute_react_query,
)
from .api import (
    execute_langgraph_query,
    stream_langgraph_query,
    stream_react_query,
    is_langgraph_enabled,
    is_langgraph_enabled_for_tenant,
    maybe_use_langgraph,
    LangGraphQueryRequest,
    LangGraphQueryResponse,
)

__all__ = [
    # State
    "RAGState",
    "ReActState",
    "ExecutionConfig",
    "create_initial_state",
    "create_initial_react_state",
    # RAG Graph (legacy)
    "create_rag_graph",
    "get_rag_graph",
    "execute_rag_query",
    # ReAct Graph
    "create_react_graph",
    "get_react_graph",
    "execute_react_query",
    # API
    "execute_langgraph_query",
    "stream_langgraph_query",
    "stream_react_query",
    "is_langgraph_enabled",
    "is_langgraph_enabled_for_tenant",
    "maybe_use_langgraph",
    "LangGraphQueryRequest",
    "LangGraphQueryResponse",
]
