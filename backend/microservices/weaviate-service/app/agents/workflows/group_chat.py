"""
GroupChat Workflow - Coordinator Pattern

An LLM coordinator dynamically selects which agent should respond based on
the conversation context. This allows for flexible, context-aware
agent selection.

Use when: Complex queries that may need different specialists
depending on how the conversation evolves.

FRAMEWORK: Microsoft Agent Framework
Uses Coordinator agent pattern for dynamic multi-agent orchestration.
"""

import logging
from typing import List, Any, AsyncIterator
from dataclasses import dataclass

from agent_framework import ChatAgent, GroupBuilder

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

    Uses Agent Framework's GroupBuilder with coordinator pattern.
    At each turn, the coordinator analyzes the conversation and
    chooses which specialist should respond.

    This is more flexible than sequential - the order is dynamic
    based on what's needed.
    """

    def __init__(
        self,
        agents: List[ChatAgent],
        coordinator_client: Any,
        max_turns: int = 15,
        termination_text: str = "TASK_COMPLETE",
    ):
        """
        Initialize group chat workflow.

        Args:
            agents: List of specialist agents (min 2)
            coordinator_client: LLM client for coordinator
            max_turns: Maximum conversation turns
            termination_text: Text that signals completion
        """
        if len(agents) < 2:
            raise ValueError("GroupChat requires at least 2 agents")

        self.agents = agents
        self.coordinator_client = coordinator_client
        self.max_turns = max_turns
        self.termination_text = termination_text

        # Build role descriptions for coordinator
        roles = "\n".join([
            f"- {a.name}: {self._get_agent_role(a)}"
            for a in agents
        ])

        coordinator_instructions = COORDINATOR_INSTRUCTIONS.replace("{roles}", roles)

        # Build the group chat workflow
        self.workflow = (
            GroupBuilder()
            .participants(agents)
            .coordinator(coordinator_client, coordinator_instructions)
            .max_turns(max_turns)
            .termination_text(termination_text)
            .build()
        )

        logger.debug(
            f"Created GroupChatWorkflow with {len(agents)} agents: "
            f"{[a.name for a in agents]}"
        )

    def _get_agent_role(self, agent: ChatAgent) -> str:
        """Extract a brief role description from agent."""
        instructions = getattr(agent, 'instructions', '')
        if instructions:
            first_line = instructions.split('\n')[0]
            return first_line[:100]
        return f"{agent.name} specialist"

    async def run(self, task: str) -> GroupChatResult:
        """
        Execute the group chat workflow.

        The coordinator will dynamically choose which agent responds
        at each turn based on the conversation context.

        Args:
            task: Task description with context

        Returns:
            GroupChatResult with answer and metadata
        """
        logger.info(f"Starting group chat workflow: task='{task[:50]}...'")

        try:
            messages = []
            agents_used = set()
            answer = ""

            async for event in self.workflow.run_stream(task):
                if hasattr(event, 'content'):
                    messages.append(event)
                    answer = event.content
                    if hasattr(event, 'source'):
                        agents_used.add(event.source)

            completed = self.termination_text in answer if answer else False

            return GroupChatResult(
                answer=answer,
                messages=messages,
                agents_used=list(agents_used),
                turns_taken=len(messages),
                completed=completed,
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

    async def run_stream(self, task: str) -> AsyncIterator[Any]:
        """Execute with streaming."""
        logger.info("Starting streaming group chat")

        try:
            async for event in self.workflow.run_stream(task):
                yield event
        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield {"error": str(e)}


def create_specialist_group(
    chat_client: Any,
    max_turns: int = 15,
) -> GroupChatWorkflow:
    """
    Create a group with all specialist agents.

    The coordinator will dynamically choose which specialist responds
    based on the query and conversation context.

    Includes: Search, Analyst, Contract, Compliance, Summarizer

    Args:
        chat_client: Agent Framework chat client
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
        create_search_agent(chat_client),
        create_analyst_agent(chat_client),
        create_contract_agent(chat_client),
        create_compliance_agent(chat_client),
        create_summarizer_agent(chat_client),
    ]

    return GroupChatWorkflow(
        agents=agents,
        coordinator_client=chat_client,
        max_turns=max_turns,
    )


def create_search_and_summarize_group(
    chat_client: Any,
    max_turns: int = 10,
) -> GroupChatWorkflow:
    """
    Create a lightweight group for search and summary tasks.

    Only includes SearchAgent and SummarizerAgent for faster
    execution on simpler queries.

    Args:
        chat_client: Agent Framework chat client
        max_turns: Maximum turns

    Returns:
        Configured GroupChatWorkflow
    """
    from ..agents import create_search_agent, create_summarizer_agent

    agents = [
        create_search_agent(chat_client),
        create_summarizer_agent(chat_client),
    ]

    return GroupChatWorkflow(
        agents=agents,
        coordinator_client=chat_client,
        max_turns=max_turns,
    )
