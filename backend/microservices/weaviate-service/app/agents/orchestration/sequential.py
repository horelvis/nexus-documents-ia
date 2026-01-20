"""
Sequential Orchestration Pattern

Executes agents in a pipeline where each agent's output becomes
the next agent's input context.

ARCHITECTURE:
```
User Query → Agent A → Agent B → Agent C → Final Answer
               ↓          ↓          ↓
           (analyze)  (enrich)   (summarize)
```

USE CASES:
- "Primero busca el contrato, después analiza las cláusulas, finalmente resume"
- Document processing pipelines (extract → validate → transform)
- Multi-stage analysis (search → analyze → risk-assess → summarize)

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework ChatAgent pattern
- Uses Assistant class with run(messages) interface
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .base import (
    BaseOrchestration,
    OrchestrationPattern,
    OrchestrationResult,
    AgentResult
)

if TYPE_CHECKING:
    from qwen_agent.agents import Assistant

logger = logging.getLogger(__name__)


async def _run_qwen_agent(agent: "Assistant", prompt: str) -> tuple[str, list]:
    """
    Execute a Qwen-Agent Assistant and extract the response.

    Qwen-Agent's run() returns a generator yielding message lists.
    This helper runs the agent and extracts the final text response.

    Args:
        agent: Qwen-Agent Assistant instance
        prompt: User query/prompt

    Returns:
        Tuple of (answer_text, tools_called)
    """
    messages = [{'role': 'user', 'content': prompt}]

    # Run agent and collect all response messages
    all_responses = []
    tools_called = []

    # Qwen-Agent's run() can be sync or async depending on LLM
    # We handle both cases
    try:
        for response_messages in agent.run(messages):
            all_responses.extend(response_messages)
            # Track tool calls
            for msg in response_messages:
                if isinstance(msg, dict):
                    if msg.get('function_call'):
                        tools_called.append(msg['function_call'].get('name', 'unknown'))
    except Exception as e:
        logger.error(f"Error running Qwen agent: {e}")
        raise

    # Extract final answer from responses
    answer = ""
    for msg in all_responses:
        if isinstance(msg, dict):
            content = msg.get('content', '')
            role = msg.get('role', '')
            if role == 'assistant' and content:
                answer = content

    # Clean Qwen thinking tags if present
    if "</think>" in answer:
        answer = answer.split("</think>")[-1].strip()

    return answer, tools_called


@dataclass
class SequentialConfig:
    """Configuration for sequential orchestration."""
    # Continue to next agent even if current one fails
    continue_on_error: bool = True
    # Maximum time per agent (ms)
    agent_timeout_ms: int = 60000
    # Whether to include intermediate results in final context
    accumulate_context: bool = True
    # Prefix for context accumulation
    context_prefix: str = "Contexto previo:\n"


class SequentialOrchestration(BaseOrchestration):
    """
    Sequential orchestration pattern - pipeline execution.

    Each agent receives the output of the previous agent as additional
    context, building up a comprehensive analysis step by step.
    """

    def __init__(
        self,
        config: Optional[SequentialConfig] = None,
        name: str = "SequentialOrchestration"
    ):
        super().__init__(name=name)
        self._pattern = OrchestrationPattern.SEQUENTIAL
        self.config = config or SequentialConfig()

    async def execute(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        agents: List["Assistant"],
        **kwargs
    ) -> OrchestrationResult:
        """
        Execute agents sequentially, passing context between them.

        Args:
            task: Original user query
            tenant_id: Tenant identifier
            session_id: Session for context
            agents: List of Qwen-Agent Assistant instances to execute in order

        Returns:
            OrchestrationResult with final answer and all intermediate results
        """
        start_time = time.perf_counter()
        intermediate_results: List[AgentResult] = []
        agents_executed: List[str] = []
        accumulated_context = ""
        last_successful_answer = ""

        if not agents:
            return self._create_result(
                success=False,
                answer="No agents provided for sequential execution",
                agents_executed=[],
                start_time=start_time,
                metadata={"error": "no_agents"}
            )

        logger.info(f"🔗 Starting Sequential orchestration with {len(agents)} agents")

        for i, agent in enumerate(agents):
            agent_name = agent.name if hasattr(agent, 'name') else f"Agent_{i}"
            agent_start = time.perf_counter()

            try:
                # Build context for this agent
                if self.config.accumulate_context and accumulated_context:
                    prompt = f"{self.config.context_prefix}{accumulated_context}\n\nTarea actual: {task}"
                else:
                    prompt = task

                logger.info(f"  → [{i+1}/{len(agents)}] Executing {agent_name}...")

                # Execute Qwen-Agent with timeout
                answer, tools_called = await asyncio.wait_for(
                    _run_qwen_agent(agent, prompt),
                    timeout=self.config.agent_timeout_ms / 1000
                )

                execution_time = (time.perf_counter() - agent_start) * 1000

                agent_result = AgentResult(
                    agent_name=agent_name,
                    success=True,
                    answer=answer,
                    execution_time_ms=execution_time,
                    tools_called=tools_called,
                    metadata={"step": i + 1, "total_steps": len(agents)}
                )
                intermediate_results.append(agent_result)
                agents_executed.append(agent_name)

                # Update accumulated context for next agent
                accumulated_context += f"\n\n**{agent_name}:**\n{answer}"
                last_successful_answer = answer

                logger.info(f"  ✓ {agent_name} completed in {execution_time:.0f}ms")

            except asyncio.TimeoutError:
                logger.warning(f"  ⏱️ {agent_name} timed out after {self.config.agent_timeout_ms}ms")
                agent_result = AgentResult(
                    agent_name=agent_name,
                    success=False,
                    answer=f"Agent timed out after {self.config.agent_timeout_ms}ms",
                    execution_time_ms=self.config.agent_timeout_ms,
                    metadata={"error": "timeout"}
                )
                intermediate_results.append(agent_result)
                agents_executed.append(agent_name)

                if not self.config.continue_on_error:
                    break

            except Exception as e:
                logger.error(f"  ❌ {agent_name} failed: {e}")
                agent_result = AgentResult(
                    agent_name=agent_name,
                    success=False,
                    answer=f"Agent failed: {str(e)}",
                    execution_time_ms=(time.perf_counter() - agent_start) * 1000,
                    metadata={"error": str(e)}
                )
                intermediate_results.append(agent_result)
                agents_executed.append(agent_name)

                if not self.config.continue_on_error:
                    break

        # Build final answer
        successful_results = [r for r in intermediate_results if r.success]

        if not successful_results:
            final_answer = "No se pudo completar ningún paso del análisis."
            success = False
        else:
            # Use last successful result as main answer
            final_answer = last_successful_answer
            success = True

        logger.info(f"✅ Sequential orchestration completed: {len(successful_results)}/{len(agents)} agents succeeded")

        return self._create_result(
            success=success,
            answer=final_answer,
            agents_executed=agents_executed,
            start_time=start_time,
            intermediate_results=intermediate_results,
            metadata={
                "total_agents": len(agents),
                "successful_agents": len(successful_results),
                "failed_agents": len(agents) - len(successful_results),
                "accumulated_context_length": len(accumulated_context)
            }
        )

    async def execute_stream(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        agents: List["Assistant"],
        **kwargs
    ):
        """
        Execute agents sequentially with streaming progress updates.

        Yields events for each agent start/complete for UI feedback.
        """
        if not agents:
            yield {
                "event": "error",
                "data": {"error": "No agents provided", "message": "No hay agentes configurados"}
            }
            return

        yield {
            "event": "start",
            "data": {
                "message": f"Iniciando análisis secuencial con {len(agents)} pasos...",
                "total_steps": len(agents),
                "pattern": "sequential"
            }
        }

        accumulated_context = ""

        for i, agent in enumerate(agents):
            agent_name = agent.name if hasattr(agent, 'name') else f"Agent_{i}"

            yield {
                "event": "step_start",
                "data": {
                    "step": i + 1,
                    "step_index": i,  # 0-indexed for frontend
                    "total_steps": len(agents),
                    "agent": agent_name,
                    "message": f"Paso {i+1}/{len(agents)}: {agent_name}..."
                }
            }

            try:
                if self.config.accumulate_context and accumulated_context:
                    prompt = f"{self.config.context_prefix}{accumulated_context}\n\nTarea actual: {task}"
                else:
                    prompt = task

                answer, tools_called = await asyncio.wait_for(
                    _run_qwen_agent(agent, prompt),
                    timeout=self.config.agent_timeout_ms / 1000
                )

                accumulated_context += f"\n\n**{agent_name}:**\n{answer}"

                yield {
                    "event": "step_complete",
                    "data": {
                        "step": i + 1,
                        "step_index": i,  # 0-indexed for frontend
                        "agent": agent_name,
                        "success": True,
                        "answer_preview": answer[:200] + "..." if len(answer) > 200 else answer
                    }
                }

                # Stream final answer if this is the last agent
                if i == len(agents) - 1:
                    yield {
                        "event": "token",
                        "data": {"text": answer, "agent": agent_name}
                    }

            except Exception as e:
                yield {
                    "event": "step_complete",
                    "data": {
                        "step": i + 1,
                        "step_index": i,  # 0-indexed for frontend
                        "agent": agent_name,
                        "success": False,
                        "error": str(e)
                    }
                }

                if not self.config.continue_on_error:
                    yield {
                        "event": "error",
                        "data": {"error": str(e), "message": f"Error en {agent_name}: {str(e)}"}
                    }
                    return

        yield {
            "event": "complete",
            "data": {
                "success": True,
                "message": "Análisis secuencial completado",
                "total_steps": len(agents)
            }
        }


# Singleton instance
_sequential_orchestration: Optional[SequentialOrchestration] = None


def get_sequential_orchestration(
    config: Optional[SequentialConfig] = None
) -> SequentialOrchestration:
    """Get or create the SequentialOrchestration instance."""
    global _sequential_orchestration
    if _sequential_orchestration is None:
        _sequential_orchestration = SequentialOrchestration(config=config)
    return _sequential_orchestration
