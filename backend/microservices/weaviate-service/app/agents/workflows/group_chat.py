"""
GroupChat Workflow - Coordinator Pattern

An LLM coordinator dynamically selects which agent should respond based on
the conversation context. This allows for flexible, context-aware
agent selection.

Use when: Complex queries that may need different specialists
depending on how the conversation evolves.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework GroupBuilder pattern
- Now uses Qwen-Agent's Assistant class with our ConcurrentOrchestration
"""

import logging
from typing import List, Any, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from qwen_agent.agents import Assistant

from ..orchestration import (
    ConcurrentOrchestration,
    ConcurrentConfig,
    get_concurrent_orchestration,
)

logger = logging.getLogger(__name__)


@dataclass
class GroupChatResult:
    """Result from a group chat execution."""
    answer: str
    messages: List[Any]
    agents_used: List[str]
    turns_taken: int
    completed: bool


# Prompt for the coordinator to select agents
COORDINATOR_INSTRUCTIONS = """You are a coordinator that orchestrates a team of specialist agents.

Available specialists:
{roles}

Your job:
1. Analyze what the user needs
2. Delegate to the appropriate specialist
3. Synthesize their responses
4. Continue until the task is complete

When the task is complete, respond with TASK_COMPLETE.

Always delegate to the most appropriate specialist for each subtask.
Do not try to answer questions directly - use your team."""


class GroupChatWorkflow:
    """
    Group chat where a coordinator selects which agent responds.

    At each turn, the coordinator analyzes the conversation and
    chooses which specialist should respond.

    This is more flexible than sequential - the order is dynamic
    based on what's needed.
    """

    def __init__(
        self,
        agents: List["Assistant"],
        coordinator_llm_cfg: dict,
        max_turns: int = 15,
        termination_text: str = "TASK_COMPLETE",
    ):
        """
        Initialize group chat workflow.

        Args:
            agents: List of Qwen-Agent Assistant instances (min 2)
            coordinator_llm_cfg: LLM config dict for coordinator
            max_turns: Maximum conversation turns
            termination_text: Text that signals completion
        """
        if len(agents) < 2:
            raise ValueError("GroupChat requires at least 2 agents")

        self.agents = agents
        self.coordinator_llm_cfg = coordinator_llm_cfg
        self.max_turns = max_turns
        self.termination_text = termination_text

        # Build role descriptions for coordinator
        roles = "\n".join([
            f"- {a.name}: {self._get_agent_role(a)}"
            for a in agents if hasattr(a, 'name')
        ])

        self.coordinator_instructions = COORDINATOR_INSTRUCTIONS.replace("{roles}", roles)

        # Create orchestration config
        self.config = ConcurrentConfig(
            global_timeout_ms=120000,
            min_successful_agents=1,
            use_aggregator=True,
        )

        logger.debug(
            f"Created GroupChatWorkflow with {len(agents)} agents: "
            f"{[a.name for a in agents if hasattr(a, 'name')]}"
        )

    def _get_agent_role(self, agent: "Assistant") -> str:
        """Extract a brief role description from agent."""
        system_message = getattr(agent, 'system_message', '')
        if system_message:
            first_line = system_message.split('\n')[0]
            return first_line[:100]
        name = getattr(agent, 'name', 'Unknown')
        return f"{name} specialist"

    async def run(self, task: str, tenant_id: str = "default", session_id: str = "default") -> GroupChatResult:
        """
        Execute the group chat workflow.

        The coordinator will dynamically choose which agent responds
        at each turn based on the conversation context.

        Args:
            task: Task description with context
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            GroupChatResult with answer and metadata
        """
        logger.info(f"Starting group chat workflow: task='{task[:50]}...'")

        try:
            # Create coordinator agent for aggregation
            from qwen_agent.agents import Assistant

            coordinator = Assistant(
                llm=self.coordinator_llm_cfg,
                name="Coordinator",
                system_message=self.coordinator_instructions,
                function_list=[],
            )

            orchestration = get_concurrent_orchestration(self.config)
            orchestration.set_aggregator(coordinator)

            result = await orchestration.execute(
                task=task,
                tenant_id=tenant_id,
                session_id=session_id,
                agents=self.agents,
            )

            completed = self.termination_text in result.answer if result.answer else False

            return GroupChatResult(
                answer=result.answer,
                messages=[r.answer for r in result.intermediate_results],
                agents_used=result.agents_executed,
                turns_taken=len(result.intermediate_results),
                completed=completed or result.success,
            )

        except Exception as e:
            logger.exception(f"Group chat workflow error: {e}")
            return GroupChatResult(
                answer=f"Error: {e}",
                messages=[],
                agents_used=[],
                turns_taken=0,
                completed=False,
            )

    async def run_stream(self, task: str, tenant_id: str = "default", session_id: str = "default") -> AsyncIterator[Any]:
        """Execute with streaming."""
        logger.info("Starting streaming group chat")

        try:
            # Create coordinator agent for aggregation
            from qwen_agent.agents import Assistant

            coordinator = Assistant(
                llm=self.coordinator_llm_cfg,
                name="Coordinator",
                system_message=self.coordinator_instructions,
                function_list=[],
            )

            orchestration = get_concurrent_orchestration(self.config)
            orchestration.set_aggregator(coordinator)

            async for event in orchestration.execute_stream(
                task=task,
                tenant_id=tenant_id,
                session_id=session_id,
                agents=self.agents,
            ):
                yield event
        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield {"error": str(e)}


def create_specialist_group(
    llm_cfg: dict,
    max_turns: int = 15,
) -> GroupChatWorkflow:
    """
    Create a group with all specialist agents.

    The coordinator will dynamically choose which specialist responds
    based on the query and conversation context.

    Includes: Search, Analyst, Contract, Compliance, Summarizer

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        max_turns: Maximum turns

    Returns:
        Configured GroupChatWorkflow
    """
    from ..agents import (
        create_search_agent,
        create_analyst_agent,
        create_contract_agent,
        create_compliance_agent,
        create_summarizer_agent,
    )

    agents = [
        create_search_agent(llm_cfg),
        create_analyst_agent(llm_cfg),
        create_contract_agent(llm_cfg),
        create_compliance_agent(llm_cfg),
        create_summarizer_agent(llm_cfg),
    ]

    return GroupChatWorkflow(
        agents=agents,
        coordinator_llm_cfg=llm_cfg,
        max_turns=max_turns,
    )


def create_search_and_summarize_group(
    llm_cfg: dict,
    max_turns: int = 10,
) -> GroupChatWorkflow:
    """
    Create a lightweight group for search and summary tasks.

    Only includes SearchAgent and SummarizerAgent for faster
    execution on simpler queries.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        max_turns: Maximum turns

    Returns:
        Configured GroupChatWorkflow
    """
    from ..agents import create_search_agent, create_summarizer_agent

    agents = [
        create_search_agent(llm_cfg),
        create_summarizer_agent(llm_cfg),
    ]

    return GroupChatWorkflow(
        agents=agents,
        coordinator_llm_cfg=llm_cfg,
        max_turns=max_turns,
    )
