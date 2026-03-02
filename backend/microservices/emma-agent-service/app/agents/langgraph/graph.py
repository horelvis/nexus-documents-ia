"""
LangGraph ReAct Agent StateGraph Assembly

Main graph construction for the ReAct agent with optional Swarm
parallel execution for complex multi-faceted queries.

Graph Structure:
    START -> classify -> [fast_path -> END]
                       -> react_loop <-> (continue) -> synthesize -> END     (simple)
                       -> decompose -> Send[swarm_worker x N] ->             (complex)
                         synthesize_swarm -> END

The swarm path is activated when classify detects a complex multi-faceted
query and SWARM_ENABLED=true. LangGraph's Send() API spawns N parallel
workers, each running a focused mini-ReAct loop.

Design Decisions:
1. Use StateGraph for explicit state management
2. MemorySaver for conversation persistence
3. Conditional edges for dynamic routing
4. Send() fan-out for parallel swarm workers
5. Graceful error handling with timeouts

References:
- https://langchain-ai.github.io/langgraph/concepts/low_level/
- https://langchain-ai.github.io/langgraph/tutorials/multi_agent/
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Send

from .state import ReActState

logger = logging.getLogger(__name__)


# =============================================================================
# ReAct Agent Graph
# =============================================================================

_react_graph: Optional[StateGraph] = None


def create_react_graph(enable_checkpointing: bool = True) -> StateGraph:
    """Create the ReAct agent StateGraph.

    Graph with 6 nodes — two execution paths through the same graph:

        START -> classify -> [fast_path -> END]
                           -> react_loop <-> -> synthesize -> END              (simple queries)
                           -> decompose -> Send[swarm_worker x N] ->          (complex queries)
                             synthesize_swarm -> END

    The swarm path is activated when classify detects a complex multi-faceted
    query and SWARM_ENABLED=true. LangGraph's Send() API spawns N parallel
    workers, each running a focused mini-ReAct loop.

    Args:
        enable_checkpointing: Whether to enable MemorySaver for conversation persistence

    Returns:
        Compiled StateGraph
    """
    from .nodes.classify import classify_node
    from .nodes.react_loop import react_loop_node
    from .nodes.synthesize_react import synthesize_react_node
    from .nodes.decompose import decompose_node
    from .nodes.swarm_worker import swarm_worker_node
    from .nodes.synthesize_swarm import synthesize_swarm_node

    logger.info("Creating ReAct Agent StateGraph")

    workflow = StateGraph(ReActState)

    # Core nodes (3 original)
    workflow.add_node("classify", classify_node)
    workflow.add_node("react_loop", react_loop_node)
    workflow.add_node("synthesize", synthesize_react_node)

    # Swarm nodes (+3)
    workflow.add_node("decompose", decompose_node)
    workflow.add_node("swarm_worker", swarm_worker_node)
    workflow.add_node("synthesize_swarm", synthesize_swarm_node)

    # Entry point
    workflow.set_entry_point("classify")

    # classify -> fast_path END | react_loop | decompose
    workflow.add_conditional_edges(
        "classify",
        _route_from_classify,
        {
            "react": "react_loop",
            "decompose": "decompose",
            "end": END,
        },
    )

    # decompose -> Send[swarm_worker x N] (dynamic fan-out)
    # OR fallback to react_loop if decomposition fails
    workflow.add_conditional_edges(
        "decompose",
        _route_from_decompose,
    )

    # react_loop -> react_loop (continue) | synthesize (terminate)
    workflow.add_conditional_edges(
        "react_loop",
        _route_from_react,
        {
            "continue": "react_loop",
            "synthesize": "synthesize",
        },
    )

    # All swarm workers converge at synthesize_swarm
    workflow.add_edge("swarm_worker", "synthesize_swarm")

    # Both synthesize paths -> END
    workflow.add_edge("synthesize", END)
    workflow.add_edge("synthesize_swarm", END)

    # Compile
    if enable_checkpointing:
        memory = MemorySaver()
        compiled = workflow.compile(checkpointer=memory)
        logger.info("ReAct graph compiled with checkpointing (swarm-enabled)")
    else:
        compiled = workflow.compile()
        logger.info("ReAct graph compiled without checkpointing (swarm-enabled)")

    return compiled


def _route_from_classify(state: ReActState) -> str:
    """Route from classify node: fast-path, swarm decompose, or react loop."""
    if state.get("fast_path_used") or state.get("is_complete"):
        return "end"
    if state.get("use_swarm"):
        return "decompose"
    return "react"


def _route_from_decompose(state: ReActState):
    """Route from decompose node: dynamic fan-out via Send() or fallback.

    If decompose set use_swarm=False (parse failure, empty result), fall back
    to react_loop. Otherwise, spawn N parallel swarm workers via Send().

    Returns:
        list[Send] for parallel workers, or str for fallback routing
    """
    # Decomposition failed or returned empty -> fall back to react_loop
    if not state.get("use_swarm", True):
        return [Send("react_loop", state)]

    sub_tasks = state.get("swarm_sub_tasks", [])
    if not sub_tasks:
        return [Send("react_loop", state)]

    # Dynamic fan-out: spawn N parallel workers
    return [
        Send("swarm_worker", {
            **state,
            "swarm_current_task": task,
            "swarm_worker_id": i,
        })
        for i, task in enumerate(sub_tasks)
    ]


def _route_from_react(state: ReActState) -> str:
    """Route from react_loop: continue iterating or synthesize."""
    if state.get("is_complete"):
        return "synthesize"
    return "continue"


def get_react_graph(force_new: bool = False) -> StateGraph:
    """Get or create the global ReAct graph instance (singleton)."""
    global _react_graph
    if _react_graph is None or force_new:
        _react_graph = create_react_graph()
    return _react_graph


async def execute_react_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[list] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    conversation_history: Optional[list] = None,
    context: Optional[Dict[str, Any]] = None,
    max_steps: int = 10,
) -> Dict[str, Any]:
    """Execute a query using the ReAct agent graph.

    High-level API for executing queries through the ReAct graph.

    Args:
        query: User's query
        tenant_id: Tenant ID for ACL
        user_id: Optional user ID
        user_role_ids: Optional role IDs
        is_admin: Admin bypass flag
        thread_id: Optional conversation thread ID
        conversation_history: Previous conversation messages
        context: Request context (document_id, social_channel_mode, etc.)
        max_steps: Maximum ReAct iterations (default: 10)

    Returns:
        Dict with success, answer, sources, thread_id, metadata
    """
    if not tenant_id or not tenant_id.strip():
        return {
            "success": False,
            "answer": "Error: tenant_id is required",
            "sources": [],
            "thread_id": thread_id or "",
            "fast_path": False,
            "latency_ms": 0,
            "metadata": {"error": "tenant_id_required"},
        }

    from .state import create_initial_react_state
    from langchain_core.messages import HumanMessage, AIMessage

    start_time = time.time()

    # Convert conversation history
    langchain_history = None
    if conversation_history:
        langchain_history = []
        for msg in conversation_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                langchain_history.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_history.append(AIMessage(content=content))

    # Hydrate upload context
    try:
        from app.services.upload_context_service import upload_context_service
        hydrated_context = upload_context_service.hydrate_context(context or {})
    except Exception:
        hydrated_context = context or {}

    # Create initial state (async — loads user memory from DB/Redis)
    initial_state = await create_initial_react_state(
        query=query,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids,
        is_admin=is_admin,
        thread_id=thread_id,
        conversation_history=langchain_history,
        request_context=hydrated_context,
        max_steps=max_steps,
    )

    # Get graph
    graph = get_react_graph()

    # Execute
    config_dict = {"configurable": {"thread_id": thread_id or initial_state["thread_id"]}}

    try:
        from app.core.config import settings as _settings
        result = await asyncio.wait_for(
            graph.ainvoke(initial_state, config_dict),
            timeout=_settings.react_global_timeout_seconds,
        )

        latency_ms = (time.time() - start_time) * 1000

        return {
            "success": result.get("success", False),
            "answer": result.get("final_answer", ""),
            "sources": result.get("sources", []),
            "thread_id": result.get("thread_id", ""),
            "fast_path": result.get("fast_path_used", False),
            "latency_ms": latency_ms,
            "metadata": {
                **(result.get("metadata") or {}),
                "graph_type": "react",
                "total_steps": result.get("current_step", 0),
                "reasoning_steps": result.get("reasoning_steps", []),
            },
        }

    except asyncio.TimeoutError:
        latency_ms = (time.time() - start_time) * 1000
        logger.error(f"ReAct query timed out after {_settings.react_global_timeout_seconds}s")
        return {
            "success": False,
            "answer": "La consulta ha excedido el tiempo máximo. Intenta con una pregunta más específica.",
            "sources": [],
            "thread_id": initial_state["thread_id"],
            "metadata": {"graph_type": "react", "timeout": True},
        }

    except Exception as e:
        logger.error(f"ReAct query execution failed: {e}", exc_info=True)

        return {
            "success": False,
            "answer": f"Error processing query: {str(e)}",
            "sources": [],
            "thread_id": initial_state["thread_id"],
            "error": str(e),
            "metadata": {"graph_type": "react"},
        }
