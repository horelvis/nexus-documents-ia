"""
Handoff Workflow - Native Microsoft Agent Framework Implementation

Agents explicitly delegate tasks to other agents using handoffs.
A coordinator agent analyzes incoming requests and routes to specialists.

Use when: You need explicit control over agent delegation,
or when a central router should distribute work.

FRAMEWORK: Microsoft Agent Framework
Uses HandoffBuilder for handoff-based multi-agent orchestration.

Reference: https://github.com/microsoft/agent-framework
"""

import logging
from typing import List, Any, AsyncIterator
from dataclasses import dataclass

from agent_framework import ChatAgent, HandoffBuilder

logger = logging.getLogger(__name__)


@dataclass
class SwarmResult:
    """Result from a handoff workflow execution."""
    answer: str
    messages: List[Any]
    agents_used: List[str]
    handoffs: List[str]  # Track the delegation path
    turns_taken: int
    completed: bool


class SwarmWorkflow:
    """
    Handoff workflow with explicit handoffs between agents.

    In a Handoff workflow, agents use handoffs to explicitly delegate control
    to other agents. The coordinator analyzes requests and routes to specialists.

    Typical pattern:
    1. Coordinator receives request
    2. Coordinator analyzes and hands off to specialist
    3. Specialist works and may hand off to another or back to coordinator

    FRAMEWORK: Microsoft Agent Framework (HandoffBuilder)
    """

    def __init__(
        self,
        agents: List[ChatAgent],
        max_turns: int = 15,
        termination_text: str = "TASK_COMPLETE",
        enable_return_to_previous: bool = True,
    ):
        """
        Initialize handoff workflow.

        Args:
            agents: List of agents (first is the coordinator/triage agent)
            max_turns: Maximum turns before stopping
            termination_text: Text that signals completion
            enable_return_to_previous: Allow returning to previous agent
        """
        self.agents = agents
        self.max_turns = max_turns
        self.termination_text = termination_text
        self.coordinator = agents[0]
        self.specialists = agents[1:] if len(agents) > 1 else []

        # Build the handoff workflow using HandoffBuilder
        builder = (
            HandoffBuilder(
                name="document_analysis_workflow",
                participants=agents
            )
            .set_coordinator(self.coordinator)
            .max_turns(max_turns)
            .termination_text(termination_text)
        )

        # Coordinator can hand off to any specialist
        if self.specialists:
            builder.add_handoff(self.coordinator, self.specialists)

            # Each specialist can hand off to other specialists
            for specialist in self.specialists:
                other_specialists = [s for s in self.specialists if s != specialist]
                if other_specialists:
                    builder.add_handoff(specialist, other_specialists)

        # Enable return to previous agent for continuity
        if enable_return_to_previous:
            builder.enable_return_to_previous(True)

        self.workflow = builder.build()

        logger.debug(
            f"Created HandoffWorkflow with {len(agents)} agents: "
            f"coordinator={self.coordinator.name}, "
            f"specialists={[a.name for a in self.specialists]}"
        )

    async def run(self, task: str) -> SwarmResult:
        """
        Execute the handoff workflow.

        The coordinator receives the task and decides
        how to delegate it to specialists.

        Args:
            task: Task description with context

        Returns:
            SwarmResult with answer, delegation path, and metadata
        """
        logger.info(f"Starting handoff workflow: task='{task[:50]}...'")

        try:
            messages = []
            agents_used = set()
            handoffs = []
            answer = ""
            last_agent = None

            async for event in self.workflow.run_stream(task):
                if hasattr(event, 'content'):
                    messages.append(event)
                    answer = event.content

                    # Track which agent produced this message
                    current_agent = getattr(event, 'source', None)
                    if current_agent:
                        agents_used.add(current_agent)

                        # Track handoffs (agent changes)
                        if last_agent and current_agent != last_agent:
                            handoffs.append(f"{last_agent} -> {current_agent}")
                        last_agent = current_agent

            completed = self.termination_text in answer if answer else False

            return SwarmResult(
                answer=answer,
                messages=messages,
                agents_used=list(agents_used),
                handoffs=handoffs,
                turns_taken=len(messages),
                completed=completed,
            )

        except Exception as e:
            logger.exception(f"Handoff workflow error: {e}")
            return SwarmResult(
                answer=f"Error: {e}",
                messages=[],
                agents_used=[],
                handoffs=[],
                turns_taken=0,
                completed=False,
            )

    async def run_stream(self, task: str) -> AsyncIterator[Any]:
        """Execute with streaming."""
        logger.info("Starting streaming handoff workflow")

        try:
            async for event in self.workflow.run_stream(task):
                yield event
        except Exception as e:
            logger.exception(f"Streaming error: {e}")
            yield {"error": str(e)}


def create_document_swarm(
    chat_client: Any,
    max_turns: int = 20,
) -> SwarmWorkflow:
    """
    Create a pre-configured document analysis handoff workflow.

    Structure:
    - TriageAgent (Coordinator): Analyzes request and routes to specialist
    - SearchAgent: Handles search queries
    - ContractAgent: Handles commercial contracts
    - LaborAgent: Handles labor contracts, payroll, sick leaves
    - LegalAgent: Handles general legal/judicial documents
    - ComplianceAgent: Handles compliance questions
    - TaxDeclarationAgent: Handles income tax declarations (IRPF)
    - SummarizerAgent: Creates final summaries

    Flow example:
    Triage -> ContractAgent -> SummarizerAgent
    Triage -> LaborAgent -> SummarizerAgent
    Triage -> LegalAgent -> SummarizerAgent
    Triage -> TaxDeclarationAgent -> SummarizerAgent

    Args:
        chat_client: Agent Framework chat client
        max_turns: Maximum turns

    Returns:
        Configured SwarmWorkflow (using HandoffBuilder internally)
    """
    from ..agents import (
        create_search_agent,
        create_contract_agent,
        create_labor_agent,
        create_legal_agent,
        create_compliance_agent,
        create_tax_declaration_agent,
        create_summarizer_agent,
        create_triage_agent,
    )

    # Create agents
    triage = create_triage_agent(chat_client)
    search = create_search_agent(chat_client)
    contract = create_contract_agent(chat_client)
    labor = create_labor_agent(chat_client)
    legal = create_legal_agent(chat_client)
    compliance = create_compliance_agent(chat_client)
    tax_declaration = create_tax_declaration_agent(chat_client)
    summarizer = create_summarizer_agent(chat_client)

    # Order matters: first agent is the coordinator
    return SwarmWorkflow(
        agents=[triage, search, contract, labor, legal, compliance, tax_declaration, summarizer],
        max_turns=max_turns,
    )


def create_simple_swarm(
    chat_client: Any,
    max_turns: int = 10,
) -> SwarmWorkflow:
    """
    Create a simple search -> summarize handoff workflow.

    Lightweight workflow with just triage, search, and summarizer.
    Good for quick document lookup tasks.

    Args:
        chat_client: Agent Framework chat client
        max_turns: Maximum turns

    Returns:
        Configured SwarmWorkflow
    """
    from ..agents import (
        create_search_agent,
        create_summarizer_agent,
        create_triage_agent,
    )

    triage = create_triage_agent(chat_client)
    search = create_search_agent(chat_client)
    summarizer = create_summarizer_agent(chat_client)

    return SwarmWorkflow(
        agents=[triage, search, summarizer],
        max_turns=max_turns,
    )
