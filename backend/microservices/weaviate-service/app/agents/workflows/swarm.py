"""
Swarm Workflow - Handoff-Based Agent Coordination

Agents explicitly delegate tasks to other agents using handoffs.
A coordinator agent analyzes incoming requests and routes to specialists.

Use when: You need explicit control over agent delegation,
or when a central router should distribute work.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework HandoffBuilder pattern
- Now uses Qwen-Agent's Assistant class with our SequentialOrchestration
- Handoffs are simulated by routing through coordinator
"""

import logging
from typing import List, Any, AsyncIterator, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from qwen_agent.agents import Assistant

from ..orchestration import (
    SequentialOrchestration,
    SequentialConfig,
    get_sequential_orchestration,
)

logger = logging.getLogger(__name__)


@dataclass
class SwarmResult:
    """Result from a swarm workflow execution."""
    answer: str
    messages: List[Any]
    agents_used: List[str]
    handoffs: List[str]  # Track the delegation path
    turns_taken: int
    completed: bool


class SwarmWorkflow:
    """
    Swarm workflow with coordinator-based handoffs.

    In this workflow, a coordinator (triage) agent analyzes requests
    and routes to the appropriate specialists. The execution follows
    a sequential pattern where each agent's output feeds into the next.

    Typical pattern:
    1. Coordinator receives request
    2. Coordinator analyzes and routes to specialist
    3. Specialist works and produces output
    4. Summarizer creates final summary
    """

    def __init__(
        self,
        agents: List["Assistant"],
        max_turns: int = 15,
        termination_text: str = "TASK_COMPLETE",
        enable_return_to_previous: bool = True,
    ):
        """
        Initialize swarm workflow.

        Args:
            agents: List of agents (first is the coordinator/triage agent)
            max_turns: Maximum turns before stopping
            termination_text: Text that signals completion
            enable_return_to_previous: Allow returning to previous agent
        """
        self.agents = agents
        self.max_turns = max_turns
        self.termination_text = termination_text
        self.coordinator = agents[0] if agents else None
        self.specialists = agents[1:] if len(agents) > 1 else []

        # Create orchestration config
        self.config = SequentialConfig(
            continue_on_error=True,
            agent_timeout_ms=60000,
            accumulate_context=True,
        )

        logger.debug(
            f"Created SwarmWorkflow with {len(agents)} agents: "
            f"coordinator={self.coordinator.name if self.coordinator and hasattr(self.coordinator, 'name') else 'None'}, "
            f"specialists={[a.name for a in self.specialists if hasattr(a, 'name')]}"
        )

    async def run(self, task: str, tenant_id: str = "default", session_id: str = "default") -> SwarmResult:
        """
        Execute the swarm workflow.

        The coordinator receives the task and the pipeline executes
        through all configured agents.

        Args:
            task: Task description with context
            tenant_id: Tenant identifier
            session_id: Session identifier

        Returns:
            SwarmResult with answer, delegation path, and metadata
        """
        logger.info(f"Starting swarm workflow: task='{task[:50]}...'")

        try:
            orchestration = get_sequential_orchestration(self.config)
            result = await orchestration.execute(
                task=task,
                tenant_id=tenant_id,
                session_id=session_id,
                agents=self.agents,
            )

            # Build handoffs list from execution order
            handoffs = []
            agents_executed = result.agents_executed
            for i in range(len(agents_executed) - 1):
                handoffs.append(f"{agents_executed[i]} -> {agents_executed[i+1]}")

            completed = self.termination_text in result.answer if result.answer else False

            return SwarmResult(
                answer=result.answer,
                messages=[r.answer for r in result.intermediate_results],
                agents_used=result.agents_executed,
                handoffs=handoffs,
                turns_taken=len(result.intermediate_results),
                completed=completed or result.success,
            )

        except Exception as e:
            logger.exception(f"Swarm workflow error: {e}")
            return SwarmResult(
                answer=f"Error: {e}",
                messages=[],
                agents_used=[],
                handoffs=[],
                turns_taken=0,
                completed=False,
            )

    async def run_stream(self, task: str, tenant_id: str = "default", session_id: str = "default") -> AsyncIterator[Any]:
        """Execute with streaming."""
        logger.info("Starting streaming swarm workflow")

        try:
            orchestration = get_sequential_orchestration(self.config)
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


def create_document_swarm(
    llm_cfg: dict,
    max_turns: int = 20,
) -> SwarmWorkflow:
    """
    Create a pre-configured document analysis swarm workflow.

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
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        max_turns: Maximum turns

    Returns:
        Configured SwarmWorkflow
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
    triage = create_triage_agent(llm_cfg)
    search = create_search_agent(llm_cfg)
    contract = create_contract_agent(llm_cfg)
    labor = create_labor_agent(llm_cfg)
    legal = create_legal_agent(llm_cfg)
    compliance = create_compliance_agent(llm_cfg)
    tax_declaration = create_tax_declaration_agent(llm_cfg)
    summarizer = create_summarizer_agent(llm_cfg)

    # Order matters: first agent is the coordinator
    return SwarmWorkflow(
        agents=[triage, search, contract, labor, legal, compliance, tax_declaration, summarizer],
        max_turns=max_turns,
    )


def create_simple_swarm(
    llm_cfg: dict,
    max_turns: int = 10,
) -> SwarmWorkflow:
    """
    Create a simple search -> summarize swarm workflow.

    Lightweight workflow with just triage, search, and summarizer.
    Good for quick document lookup tasks.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        max_turns: Maximum turns

    Returns:
        Configured SwarmWorkflow
    """
    from ..agents import (
        create_search_agent,
        create_summarizer_agent,
        create_triage_agent,
    )

    triage = create_triage_agent(llm_cfg)
    search = create_search_agent(llm_cfg)
    summarizer = create_summarizer_agent(llm_cfg)

    return SwarmWorkflow(
        agents=[triage, search, summarizer],
        max_turns=max_turns,
    )
