"""
Sequential Workflow - Ordered Agent Execution

Agents take turns in a fixed order. Each agent sees all previous
messages and builds on the work of previous agents.

Typical use case: Search -> Analyze -> Summarize pipeline

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework SequentialBuilder pattern
- Now uses Qwen-Agent's Assistant class with our SequentialOrchestration
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
class WorkflowResult:
    """Result from a workflow execution."""
    answer: str
    messages: List[Any]
    agents_used: List[str]
    turns_taken: int
    completed: bool


async def _run_qwen_agent(agent: "Assistant", prompt: str) -> tuple[str, list]:
    """
    Execute a Qwen-Agent Assistant and extract the response.

    Args:
        agent: Qwen-Agent Assistant instance
        prompt: User query/prompt

    Returns:
        Tuple of (answer_text, tools_called)
    """
    messages = [{'role': 'user', 'content': prompt}]
    all_responses = []
    tools_called = []

    try:
        for response_messages in agent.run(messages):
            all_responses.extend(response_messages)
            for msg in response_messages:
                if isinstance(msg, dict) and msg.get('function_call'):
                    tools_called.append(msg['function_call'].get('name', 'unknown'))
    except Exception as e:
        logger.error(f"Error running Qwen agent: {e}")
        raise

    answer = ""
    for msg in all_responses:
        if isinstance(msg, dict):
            content = msg.get('content', '')
            role = msg.get('role', '')
            if role == 'assistant' and content:
                answer = content

    if "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()

    return answer, tools_called


class SequentialWorkflow:
    """
    Sequential workflow where agents process in fixed order.

    Each agent sees all previous messages from the conversation.
    This enables building up context through the pipeline.

    Example flow: SearchAgent -> AnalystAgent -> SummarizerAgent
    """

    def __init__(
        self,
        agents: List["Assistant"],
        max_turns: int = 15,
        termination_text: str = "TASK_COMPLETE",
    ):
        """
        Initialize sequential workflow.

        Args:
            agents: List of Qwen-Agent Assistant instances in execution order
            max_turns: Maximum total turns before stopping
            termination_text: Text that signals task completion
        """
        self.agents = agents
        self.max_turns = max_turns
        self.termination_text = termination_text

        # Create orchestration config
        self.config = SequentialConfig(
            continue_on_error=True,
            agent_timeout_ms=60000,
            accumulate_context=True,
        )

        logger.debug(
            f"Created SequentialWorkflow with {len(agents)} agents: "
            f"{[a.name for a in agents if hasattr(a, 'name')]}"
        )

    async def run(self, task: str, tenant_id: str = "default", session_id: str = "default") -> WorkflowResult:
        """
        Execute the workflow with the given task.

        Args:
            task: Task description including any required context
            tenant_id: Tenant identifier for data isolation
            session_id: Session identifier for context

        Returns:
            WorkflowResult with the final answer and execution metadata
        """
        logger.info(f"Starting sequential workflow: task='{task[:50]}...'")

        try:
            orchestration = get_sequential_orchestration(self.config)
            result = await orchestration.execute(
                task=task,
                tenant_id=tenant_id,
                session_id=session_id,
                agents=self.agents,
            )

            completed = self.termination_text in result.answer if result.answer else False

            return WorkflowResult(
                answer=result.answer,
                messages=[r.answer for r in result.intermediate_results],
                agents_used=result.agents_executed,
                turns_taken=len(result.intermediate_results),
                completed=completed or result.success,
            )

        except Exception as e:
            logger.exception(f"Sequential workflow error: {e}")
            return WorkflowResult(
                answer=f"Error executing workflow: {e}",
                messages=[],
                agents_used=[],
                turns_taken=0,
                completed=False,
            )

    async def run_stream(self, task: str, tenant_id: str = "default", session_id: str = "default") -> AsyncIterator[Any]:
        """
        Execute workflow with streaming of messages.

        Yields messages as they are generated by each agent.

        Args:
            task: Task description
            tenant_id: Tenant identifier
            session_id: Session identifier

        Yields:
            Messages as they are produced
        """
        logger.info(f"Starting streaming sequential workflow")

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


def create_analysis_pipeline(
    llm_cfg: dict,
    max_turns: int = 15,
) -> SequentialWorkflow:
    """
    Create a pre-configured Search -> Analyze -> Summarize pipeline.

    This is the default sequential workflow for document analysis.
    The agents process in order:
    1. SearchAgent: Finds relevant documents
    2. AnalystAgent: Performs deep analysis
    3. SummarizerAgent: Creates executive summary

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        max_turns: Maximum workflow turns

    Returns:
        Configured SequentialWorkflow
    """
    from ..agents import (
        create_search_agent,
        create_analyst_agent,
        create_summarizer_agent,
    )

    search = create_search_agent(llm_cfg)
    analyst = create_analyst_agent(llm_cfg)
    summarizer = create_summarizer_agent(llm_cfg)

    return SequentialWorkflow(
        agents=[search, analyst, summarizer],
        max_turns=max_turns,
    )


def create_contract_review_pipeline(
    llm_cfg: dict,
    max_turns: int = 20,
) -> SequentialWorkflow:
    """
    Create a pipeline for contract review.

    Flow: Search -> Contract Analysis -> Compliance Check -> Summary

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        max_turns: Maximum turns

    Returns:
        Configured SequentialWorkflow for contract review
    """
    from ..agents import (
        create_search_agent,
        create_contract_agent,
        create_compliance_agent,
        create_summarizer_agent,
    )

    search = create_search_agent(llm_cfg)
    contract = create_contract_agent(llm_cfg)
    compliance = create_compliance_agent(llm_cfg)
    summarizer = create_summarizer_agent(llm_cfg)

    return SequentialWorkflow(
        agents=[search, contract, compliance, summarizer],
        max_turns=max_turns,
    )
