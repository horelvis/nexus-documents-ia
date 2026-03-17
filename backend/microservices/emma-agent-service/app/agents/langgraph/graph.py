"""
LangGraph ReAct Agent StateGraph Assembly

Main graph construction for the ReAct agent with optional Swarm
parallel execution for complex multi-faceted queries.

Graph Structure:
    START -> classify -> [fast_path -> END]
                       -> rewrite -> memory_recall -> react_loop <-> -> synthesize -> END     (simple)
                       -> rewrite -> memory_recall -> decompose -> Send[swarm_worker x N] ->  (complex)
                         synthesize_swarm -> END

The rewrite node contextualizes follow-up queries using conversation history
(ConversationalRetrievalChain / Self-RAG pattern), preventing hallucination
from ambiguous references like "cuales son?" or "si".

The swarm path is activated when classify detects a complex multi-faceted
query and SWARM_ENABLED=true. LangGraph's Send() API spawns N parallel
workers, each running a focused mini-ReAct loop.

Design Decisions:
1. Use StateGraph for explicit state management
2. PostgresSaver checkpointer for conversation continuity, time travel, and HITL.
   Thread-scoped state accumulates across invocations via add_messages reducer.
   emma_persistence_service remains for UI metadata (titles, archive, pin).
3. Conditional edges for dynamic routing
4. Send() fan-out for parallel swarm workers with slim state (only fields
   the worker actually reads, not the full ~30-field state)
5. Graceful error handling with timeouts + RetryPolicy for transient LLM failures
6. Query rewrite node for conversational context resolution

References:
- https://langchain-ai.github.io/langgraph/concepts/low_level/
- https://langchain-ai.github.io/langgraph/tutorials/multi_agent/
- https://python.langchain.com/docs/use_cases/question_answering/conversational_retrieval/
- https://arxiv.org/abs/2310.11511 (Self-RAG)
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from .state import ReActState

logger = logging.getLogger(__name__)


# =============================================================================
# ReAct Agent Graph
# =============================================================================

_react_graph: Optional[StateGraph] = None


def create_react_graph() -> StateGraph:
    """Create the ReAct agent StateGraph.

    Graph with 8 nodes — two execution paths through the same graph:

        START -> classify -> [fast_path -> END]
                           -> rewrite -> memory_recall -> react_loop <-> -> synthesize -> END     (simple)
                           -> rewrite -> memory_recall -> decompose -> Send[swarm_worker x N] ->  (complex)
                             synthesize_swarm -> END

    The rewrite node contextualizes follow-up queries using conversation
    history (ConversationalRetrievalChain pattern). It runs a fast PLANNER
    LLM call (~100-200ms) that rewrites ambiguous queries like "cuales son?"
    into self-contained queries like "¿Cuáles son los contratos caducados?".
    Passes through transparently when no history or no rewrite needed.

    The swarm path is activated when classify detects a complex multi-faceted
    query and SWARM_ENABLED=true. LangGraph's Send() API spawns N parallel
    workers, each running a focused mini-ReAct loop.

    Retry policy: Nodes that make LLM calls get RetryPolicy(max_attempts=2)
    to handle transient failures (network timeouts, vLLM cold starts).
    Non-LLM nodes (synthesize) don't need retries.

    Returns:
        Compiled StateGraph
    """
    from .nodes.classify import classify_node
    from .nodes.rewrite import rewrite_node
    from .nodes.memory_recall import memory_recall_node
    from .nodes.react_loop import react_loop_node
    from .nodes.synthesize_react import synthesize_react_node
    from .nodes.decompose import decompose_node
    from .nodes.swarm_worker import swarm_worker_node
    from .nodes.synthesize_swarm import synthesize_swarm_node
    from .nodes.explain import explain_node

    logger.info("Creating ReAct Agent StateGraph")

    workflow = StateGraph(ReActState)

    # Retry policy for nodes that call LLMs — handles transient failures
    # (network timeouts, vLLM/SGLang cold starts, OpenRouter rate limits).
    # 2 attempts with 1s backoff is enough for transient issues without
    # adding excessive latency on permanent failures.
    llm_retry = RetryPolicy(max_attempts=2, initial_interval=1.0, backoff_factor=2.0)

    # Core nodes (5: classify + rewrite + memory_recall + react_loop + synthesize)
    workflow.add_node("classify", classify_node, retry_policy=llm_retry)
    workflow.add_node("rewrite", rewrite_node, retry_policy=llm_retry)
    workflow.add_node("memory_recall", memory_recall_node, retry_policy=llm_retry)
    workflow.add_node("react_loop", react_loop_node)  # Has internal retry logic
    workflow.add_node("synthesize", synthesize_react_node)  # No LLM call, no retry

    # Swarm nodes (+3)
    workflow.add_node("decompose", decompose_node, retry_policy=llm_retry)
    workflow.add_node("swarm_worker", swarm_worker_node)  # Has internal timeout
    workflow.add_node("synthesize_swarm", synthesize_swarm_node, retry_policy=llm_retry)

    # Explain node — humanized query trace after synthesis
    workflow.add_node("explain", explain_node)

    # Entry point
    workflow.set_entry_point("classify")

    # classify -> fast_path END | rewrite (for non-fast-path queries)
    workflow.add_conditional_edges(
        "classify",
        _route_from_classify,
        {
            "rewrite": "rewrite",
            "end": END,
        },
    )

    # rewrite -> memory_recall (always, rewrite is a pass-through when no history)
    workflow.add_edge("rewrite", "memory_recall")

    # memory_recall -> react_loop | decompose (based on use_swarm flag from classify)
    workflow.add_conditional_edges(
        "memory_recall",
        _route_from_memory_recall,
        {
            "react": "react_loop",
            "decompose": "decompose",
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

    # Both synthesize paths -> explain -> END
    workflow.add_edge("synthesize", "explain")
    workflow.add_edge("synthesize_swarm", "explain")
    workflow.add_edge("explain", END)

    # Compilation deferred to get_react_graph() which injects the checkpointer.
    # We return the uncompiled workflow here.
    return workflow


def _route_from_classify(state: ReActState) -> str:
    """Route from classify node: fast-path END or rewrite (always)."""
    if state.get("fast_path_used") or state.get("is_complete"):
        return "end"
    return "rewrite"


def _route_from_memory_recall(state: ReActState) -> str:
    """Route from memory_recall: swarm decompose or react loop."""
    if state.get("use_swarm"):
        return "decompose"
    return "react"


def _route_from_decompose(state: ReActState):
    """Route from decompose node: dynamic fan-out via Send() or fallback.

    If decompose set use_swarm=False (parse failure, empty result), fall back
    to react_loop. Otherwise, spawn N parallel swarm workers via Send().

    Send() receives a slim state with only the fields the worker actually
    reads (11 fields), instead of copying the full ~30-field state. This
    reduces memory when spawning N workers in parallel.

    Worker reads: swarm_current_task, swarm_worker_id, query, tenant_id,
    sector, sector_config, features, user_id, user_role_ids, is_admin,
    thread_id, metadata.

    Returns:
        list[Send] for parallel workers, or str for fallback routing
    """
    # Decomposition failed or returned empty -> fall back to react_loop
    if not state.get("use_swarm", True):
        return [Send("react_loop", state)]

    sub_tasks = state.get("swarm_sub_tasks", [])
    if not sub_tasks:
        return [Send("react_loop", state)]

    # Slim state: only fields swarm_worker_node actually reads.
    # merge_lists fields must be initialized as empty lists so reducers
    # can accumulate results from parallel workers correctly.
    worker_base = {
        # Fields the worker reads
        "query": state.get("query", ""),
        "tenant_id": state.get("tenant_id", ""),
        "user_id": state.get("user_id"),
        "user_role_ids": state.get("user_role_ids"),
        "is_admin": state.get("is_admin", False),
        "sector": state.get("sector"),
        "sector_config": state.get("sector_config"),
        "features": state.get("features", {}),
        "thread_id": state.get("thread_id", ""),
        "metadata": state.get("metadata", {}),
        # merge_lists accumulator fields (initialized empty)
        "swarm_worker_results": [],
        "swarm_pending_events": [],
        "reasoning_steps": [],
    }

    # Dynamic fan-out: spawn N parallel workers
    return [
        Send("swarm_worker", {
            **worker_base,
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


async def get_react_graph(force_new: bool = False):
    """Get or create the global compiled ReAct graph instance (singleton).

    Async because checkpointer initialization requires awaiting PostgresSaver.setup().
    Falls back to no-checkpointer compilation if disabled or unavailable.
    """
    global _react_graph
    if _react_graph is None or force_new:
        workflow = create_react_graph()

        # Try to get PostgresSaver checkpointer + Store
        checkpointer = None
        store = None
        try:
            from app.core.checkpointer import get_checkpointer, get_store
            checkpointer = await get_checkpointer()
            store = await get_store()
        except Exception as e:
            logger.warning(f"Checkpointer/Store unavailable, compiling without: {e}")

        _react_graph = workflow.compile(checkpointer=checkpointer, store=store)
        parts = []
        if checkpointer:
            parts.append("PostgresSaver")
        if store:
            parts.append("Store")
        mode = f"with {' + '.join(parts)}" if parts else "without persistence"
        logger.info(f"ReAct graph compiled (swarm-enabled, {mode})")
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

    # Get graph (async — initializes checkpointer on first call)
    graph = await get_react_graph()

    # LangGraph config with thread_id for checkpointer scoping.
    # Each thread_id maintains its own checkpoint sequence (conversation).
    langgraph_config = {"configurable": {"thread_id": thread_id or "ephemeral"}}

    try:
        from app.core.config import settings as _settings
        result = await asyncio.wait_for(
            graph.ainvoke(initial_state, config=langgraph_config),
            timeout=_settings.react_global_timeout_seconds,
        )

        latency_ms = (time.time() - start_time) * 1000

        # Strip checkpoint-accumulated items from reasoning_steps —
        # only return steps from the current turn.
        all_steps = result.get("reasoning_steps", [])
        offsets = (result.get("metadata") or {}).get("_checkpoint_offsets", {})
        step_offset = offsets.get("reasoning_steps", 0)
        current_turn_steps = all_steps[step_offset:]

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
                "reasoning_steps": current_turn_steps,
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
