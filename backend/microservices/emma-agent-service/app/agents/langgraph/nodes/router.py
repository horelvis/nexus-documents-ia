"""
Router Functions for LangGraph Conditional Edges

These functions determine how the graph routes between nodes
based on the current state.

Routing Logic:
    PLAN → route_to_agents → {labor_agent, fiscal_agent, ..., general_agent}
    AGENT → check_remaining_agents → {next_agent OR synthesize}

Design Decisions:
1. Support sequential multi-agent execution
2. Track progress via current_agent_index
3. Handle errors gracefully (continue with remaining agents)
"""

import logging
from typing import Literal, Union

from ..state import RAGState

logger = logging.getLogger(__name__)

# Type for routing decisions
AgentRoute = Literal[
    "labor_agent",
    "fiscal_agent",
    "privacy_agent",
    "realestate_agent",
    "contract_agent",
    "compliance_agent",
    "education_agent",
    "legal_agent",
    "general_agent",
    "synthesize",
    "end",
]


def route_to_agents(state: RAGState) -> AgentRoute:
    """
    Route from PLAN to first specialist agent.

    This is called after the plan node to determine
    which agent should execute first.

    Args:
        state: Current RAG state with execution_plan

    Returns:
        Name of first agent to invoke, or "synthesize" if no plan
    """
    # Check if fast-path already provided answer
    if state.get("fast_path_used"):
        logger.info("⚡ Fast-path used, skipping to end")
        return "end"

    execution_plan = state.get("execution_plan", [])

    if not execution_plan:
        logger.info("📋 Empty execution plan, going to synthesize")
        return "synthesize"

    first_agent = execution_plan[0]
    logger.info(f"🚀 Routing to first agent: {first_agent}")

    # Validate agent name
    valid_agents = [
        "labor_agent", "fiscal_agent", "privacy_agent",
        "realestate_agent", "contract_agent", "compliance_agent",
        "education_agent", "legal_agent", "general_agent",
    ]

    if first_agent not in valid_agents:
        logger.warning(f"Unknown agent {first_agent}, using general_agent")
        return "general_agent"

    return first_agent


def check_remaining_agents(state: RAGState) -> Literal["next_agent", "synthesize"]:
    """
    Check if more agents need to run.

    Called after each agent completes to determine
    whether to run another agent or proceed to synthesis.

    Args:
        state: Current RAG state with agent_results and execution_plan

    Returns:
        "next_agent" if more agents, "synthesize" if done
    """
    execution_plan = state.get("execution_plan", [])
    current_index = state.get("current_agent_index", 0)
    agent_results = state.get("agent_results", {})
    agent_errors = state.get("agent_errors", {})

    # Count completed agents (results + errors)
    completed = len(agent_results) + len(agent_errors)

    logger.debug(
        f"check_remaining: plan={execution_plan}, "
        f"current_index={current_index}, completed={completed}"
    )

    # Check if there are more agents to run
    if current_index + 1 < len(execution_plan):
        next_agent = execution_plan[current_index + 1]
        logger.info(f"🔄 More agents to run: next={next_agent}")
        return "next_agent"

    logger.info("✅ All agents completed, proceeding to synthesize")
    return "synthesize"


def get_next_agent(state: RAGState) -> AgentRoute:
    """
    Get the next agent to run from execution plan.

    Called when check_remaining_agents returns "next_agent".

    Args:
        state: Current RAG state

    Returns:
        Name of next agent to invoke
    """
    execution_plan = state.get("execution_plan", [])
    current_index = state.get("current_agent_index", 0)

    next_index = current_index + 1

    if next_index >= len(execution_plan):
        logger.warning("get_next_agent called but no more agents")
        return "synthesize"

    next_agent = execution_plan[next_index]

    valid_agents = [
        "labor_agent", "fiscal_agent", "privacy_agent",
        "realestate_agent", "contract_agent", "compliance_agent",
        "education_agent", "legal_agent", "general_agent",
    ]

    if next_agent not in valid_agents:
        logger.warning(f"Unknown agent {next_agent}, using general_agent")
        return "general_agent"

    logger.info(f"🔄 Next agent: {next_agent} (index {next_index})")
    return next_agent


def should_retry(state: RAGState) -> Literal["retry", "synthesize"]:
    """
    Determine if we should retry failed agents.

    Called when all planned agents have errors.

    Args:
        state: Current RAG state with errors

    Returns:
        "retry" to retry with general_agent, "synthesize" to give up
    """
    agent_results = state.get("agent_results", {})
    agent_errors = state.get("agent_errors", {})
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)

    # If we have some results, proceed to synthesis
    if agent_results:
        return "synthesize"

    # If all agents failed and we haven't exceeded retries
    if agent_errors and retry_count < max_retries:
        logger.info(f"🔄 All agents failed, retry {retry_count + 1}/{max_retries}")
        return "retry"

    logger.warning("❌ Max retries exceeded, proceeding to synthesize")
    return "synthesize"
