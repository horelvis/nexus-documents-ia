"""
LangGraph RAG StateGraph Assembly

Main graph construction that wires together all nodes with
conditional routing for multi-agent execution.

Graph Structure:
    START → retrieve → plan → route_to_agents → [agents] → synthesize → END
                                    ↓
                         ┌─────────┴─────────┐
                         ↓                   ↓
                   privacy_agent      general_agent
                         ↓                   ↓
                         └─────────┬─────────┘
                                   ↓
                            check_more_agents
                                   ↓
                         ┌─────────┴─────────┐
                         ↓                   ↓
                    next_agent          synthesize
                                             ↓
                                           END

Design Decisions:
1. Use StateGraph for explicit state management
2. MemorySaver for conversation persistence
3. Conditional edges for dynamic routing
4. Support sequential multi-agent execution
5. Graceful error handling with retries

References:
- https://langchain-ai.github.io/langgraph/concepts/low_level/
- https://langchain-ai.github.io/langgraph/tutorials/multi_agent/
"""

import logging
from typing import Any, Dict, Literal, Optional, Union

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from .state import RAGState, ExecutionConfig
from .nodes.context_tree import context_tree_node
from .nodes.retrieve import retrieve_node
from .nodes.coordinator import coordinator_node
from .nodes.plan import plan_node
from .nodes.synthesize import synthesize_node
from .nodes.router import (
    route_to_agents,
    check_remaining_agents,
    get_next_agent,
    should_retry,
)
from .nodes.specialists import privacy_node, legal_node, general_node

logger = logging.getLogger(__name__)

# Global graph instance (singleton)
_rag_graph: Optional[StateGraph] = None


def create_rag_graph(
    config: Optional[ExecutionConfig] = None,
    enable_checkpointing: bool = True,
) -> StateGraph:
    """
    Create the main RAG StateGraph.

    This assembles all nodes and edges into a complete graph
    for multi-agent RAG execution.

    Args:
        config: Optional execution configuration
        enable_checkpointing: Whether to enable memory checkpointing

    Returns:
        Compiled StateGraph ready for execution
    """
    config = config or ExecutionConfig()

    logger.info("🔧 Creating LangGraph RAG StateGraph")

    # Create graph with RAGState
    workflow = StateGraph(RAGState)

    # =========================================================================
    # Add Nodes
    # =========================================================================

    # Core pipeline nodes
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("context_tree", context_tree_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("synthesize", synthesize_node)

    # Specialist agent nodes (Privacy, Legal, General implemented)
    workflow.add_node("privacy_agent", privacy_node)
    workflow.add_node("legal_agent", legal_node)
    workflow.add_node("general_agent", general_node)

    # Placeholder nodes for future specialists
    # These redirect to general_agent for now
    workflow.add_node("labor_agent", _placeholder_agent("labor_agent"))
    workflow.add_node("fiscal_agent", _placeholder_agent("fiscal_agent"))
    workflow.add_node("contract_agent", _placeholder_agent("contract_agent"))
    workflow.add_node("compliance_agent", _placeholder_agent("compliance_agent"))
    workflow.add_node("realestate_agent", _placeholder_agent("realestate_agent"))
    workflow.add_node("education_agent", _placeholder_agent("education_agent"))

    # Router node for sequential agent execution
    workflow.add_node("agent_router", _agent_router_node)

    # =========================================================================
    # Define Edges
    # =========================================================================

    # Entry point
    workflow.set_entry_point("coordinator")

    # coordinator → retrieve (conditional)
    workflow.add_conditional_edges(
        "coordinator",
        _route_from_coordinator,
        {
            "retrieve": "context_tree",
            "plan": "plan",
            "end": END,
        },
    )

    # context_tree → retrieve
    workflow.add_edge("context_tree", "retrieve")

    # retrieve → plan
    workflow.add_edge("retrieve", "plan")

    # plan → route_to_agents (conditional)
    workflow.add_conditional_edges(
        "plan",
        _route_from_plan,
        {
            "privacy_agent": "privacy_agent",
            "general_agent": "general_agent",
            "labor_agent": "labor_agent",
            "fiscal_agent": "fiscal_agent",
            "contract_agent": "contract_agent",
            "compliance_agent": "compliance_agent",
            "realestate_agent": "realestate_agent",
            "education_agent": "education_agent",
            "legal_agent": "legal_agent",
            "synthesize": "synthesize",
            "end": END,
        },
    )

    # All agents → agent_router (to check for more agents)
    for agent in [
        "privacy_agent", "general_agent", "labor_agent", "fiscal_agent",
        "contract_agent", "compliance_agent", "realestate_agent",
        "education_agent", "legal_agent",
    ]:
        workflow.add_edge(agent, "agent_router")

    # agent_router → next agent or synthesize (conditional)
    workflow.add_conditional_edges(
        "agent_router",
        _route_after_agent,
        {
            "privacy_agent": "privacy_agent",
            "general_agent": "general_agent",
            "labor_agent": "labor_agent",
            "fiscal_agent": "fiscal_agent",
            "contract_agent": "contract_agent",
            "compliance_agent": "compliance_agent",
            "realestate_agent": "realestate_agent",
            "education_agent": "education_agent",
            "legal_agent": "legal_agent",
            "synthesize": "synthesize",
        },
    )

    # synthesize → END
    workflow.add_edge("synthesize", END)

    # =========================================================================
    # Compile Graph
    # =========================================================================

    if enable_checkpointing:
        # Use MemorySaver for conversation persistence
        memory = MemorySaver()
        compiled = workflow.compile(checkpointer=memory)
        logger.info("✅ Graph compiled with checkpointing enabled")
    else:
        compiled = workflow.compile()
        logger.info("✅ Graph compiled without checkpointing")

    return compiled


def _route_from_plan(state: RAGState) -> str:
    """
    Route from plan node to first agent.

    Determines which agent should execute first based on
    the execution plan created by the plan node.
    """
    # Check if SLM fast-path already provided answer
    if state.get("slm_fast_path_used"):
        logger.info("⚡ SLM fast-path: skipping to end")
        return "end"

    execution_plan = state.get("execution_plan", [])

    if not execution_plan:
        logger.info("📋 Empty plan: going to synthesize")
        return "synthesize"

    first_agent = execution_plan[0]
    logger.info(f"🚀 First agent: {first_agent}")

    # Validate agent exists
    valid_agents = [
        "privacy_agent", "general_agent", "labor_agent", "fiscal_agent",
        "contract_agent", "compliance_agent", "realestate_agent",
        "education_agent", "legal_agent",
    ]

    if first_agent not in valid_agents:
        logger.warning(f"Unknown agent {first_agent}, using general_agent")
        return "general_agent"

    return first_agent


def _route_from_coordinator(state: RAGState) -> str:
    """
    Route from coordinator to the next step.

    Uses coordinator_route metadata to decide if we should end early
    (e.g., empty query) or proceed to retrieval.
    """
    route = state.get("metadata", {}).get("coordinator_route", "retrieve")
    if route == "end":
        logger.info("🧭 Coordinator requested early end")
        return "end"
    if route == "plan":
        logger.info("🧭 Coordinator skipping retrieval")
        return "plan"
    return "retrieve"


def _route_after_agent(state: RAGState) -> str:
    """
    Route after an agent completes.

    Checks if there are more agents to run, or proceeds
    to synthesis.
    """
    execution_plan = state.get("execution_plan", [])
    current_index = state.get("current_agent_index", 0)

    # Check if there are more agents
    if current_index < len(execution_plan):
        next_agent = execution_plan[current_index]
        logger.info(f"🔄 Next agent: {next_agent} (index {current_index})")

        valid_agents = [
            "privacy_agent", "general_agent", "labor_agent", "fiscal_agent",
            "contract_agent", "compliance_agent", "realestate_agent",
            "education_agent", "legal_agent",
        ]

        if next_agent in valid_agents:
            return next_agent

    logger.info("✅ All agents done: going to synthesize")
    return "synthesize"


async def _agent_router_node(state: RAGState) -> Dict[str, Any]:
    """
    Router node that just passes state through.

    This node exists to provide a consistent routing point
    after each agent completes.
    """
    # Just return empty dict - state flows through unchanged
    return {}


def _placeholder_agent(agent_name: str):
    """
    Create a placeholder for unimplemented agents.

    These agents forward to general_agent while logging
    that the specific agent isn't implemented yet.
    """
    async def placeholder_node(state: RAGState) -> Dict[str, Any]:
        logger.warning(
            f"⚠️ {agent_name} not implemented, using general_agent behavior"
        )
        # Import here to avoid circular imports
        from .nodes.specialists import general_node
        return await general_node(state)

    return placeholder_node


def get_rag_graph(
    config: Optional[ExecutionConfig] = None,
    force_new: bool = False,
) -> StateGraph:
    """
    Get or create the global RAG graph instance.

    Uses singleton pattern for efficiency.

    Args:
        config: Optional execution configuration
        force_new: Force creation of new graph

    Returns:
        Compiled StateGraph
    """
    global _rag_graph

    if _rag_graph is None or force_new:
        _rag_graph = create_rag_graph(config)

    return _rag_graph


async def execute_rag_query(
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[list] = None,
    is_admin: bool = False,
    thread_id: Optional[str] = None,
    config: Optional[ExecutionConfig] = None,
    conversation_history: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Execute a RAG query using the LangGraph.

    High-level API for executing queries without directly
    managing state.

    Args:
        query: User's query
        tenant_id: Tenant ID for ACL
        user_id: Optional user ID
        user_role_ids: Optional role IDs
        is_admin: Admin bypass flag
        thread_id: Optional conversation thread ID
        config: Optional execution config
        conversation_history: Previous conversation messages for context

    Returns:
        Dict with final_answer, sources, success, and metadata
    """
    # Validate tenant_id to prevent Weaviate schema errors
    if not tenant_id or not tenant_id.strip():
        logger.error("❌ tenant_id is required for RAG query execution")
        return {
            "success": False,
            "answer": "Error: tenant_id is required",
            "sources": [],
            "thread_id": thread_id or "",
            "agents_used": [],
            "domains": [],
            "slm_fast_path": False,
            "latency_ms": 0,
            "metadata": {"error": "tenant_id_required"},
        }

    from .state import create_initial_state
    from langchain_core.messages import HumanMessage, AIMessage

    # Convert conversation history to LangChain messages
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
        logger.debug(f"📜 Converted {len(langchain_history)} messages to LangChain format")

    # Create initial state
    initial_state = create_initial_state(
        query=query,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids,
        is_admin=is_admin,
        thread_id=thread_id,
        conversation_history=langchain_history,
    )

    # Get graph
    graph = get_rag_graph(config)

    # Execute
    config_dict = {"configurable": {"thread_id": thread_id or initial_state["thread_id"]}}

    try:
        result = await graph.ainvoke(initial_state, config_dict)

        return {
            "success": result.get("success", False),
            "answer": result.get("final_answer", ""),
            "sources": result.get("sources", []),
            "thread_id": result.get("thread_id", ""),
            "agents_used": list(result.get("agent_results", {}).keys()),
            "domains": result.get("detected_domains", []),
            "slm_fast_path": result.get("slm_fast_path_used", False),
            "latency_ms": result.get("total_latency_ms", 0),
            "metadata": result.get("metadata", {}),
        }

    except Exception as e:
        logger.error(f"RAG query execution failed: {e}")
        return {
            "success": False,
            "answer": f"Error processing query: {str(e)}",
            "sources": [],
            "thread_id": initial_state["thread_id"],
            "error": str(e),
        }
