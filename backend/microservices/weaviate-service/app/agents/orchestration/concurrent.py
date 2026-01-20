"""
Concurrent Orchestration Pattern

Executes multiple agents in parallel and aggregates their results.

ARCHITECTURE:
```
              ┌─→ Contract Agent ──┐
              │                    │
User Query ───┼─→ Fiscal Agent ────┼──→ Aggregator → Final Answer
              │                    │
              └─→ Labor Agent ─────┘
```

USE CASES:
- "Analiza este documento desde perspectiva legal, fiscal y laboral"
- Multi-domain compliance checks (GDPR + LOPDGDD + sector)
- Parallel searches across different document types
- Ensemble analysis for comprehensive reports

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
class ConcurrentConfig:
    """Configuration for concurrent orchestration."""
    # Global timeout for all parallel executions (ms)
    global_timeout_ms: int = 120000
    # Minimum agents that must succeed
    min_successful_agents: int = 1
    # Whether to use an aggregator agent to combine results
    use_aggregator: bool = True
    # Custom aggregation prompt template
    aggregation_prompt: str = """Combina los siguientes análisis de diferentes perspectivas en una respuesta coherente y estructurada.

{analyses}

Proporciona una síntesis que:
1. Integre los puntos clave de cada perspectiva
2. Identifique coincidencias y diferencias
3. Ofrezca una conclusión general

Responde en español de forma clara y estructurada."""


class ConcurrentOrchestration(BaseOrchestration):
    """
    Concurrent orchestration pattern - parallel execution with aggregation.

    All agents execute simultaneously on the same query, then results
    are optionally combined by an aggregator agent.
    """

    def __init__(
        self,
        aggregator: Optional["Assistant"] = None,
        config: Optional[ConcurrentConfig] = None,
        name: str = "ConcurrentOrchestration"
    ):
        super().__init__(name=name)
        self._pattern = OrchestrationPattern.CONCURRENT
        self.aggregator = aggregator
        self.config = config or ConcurrentConfig()

    def set_aggregator(self, aggregator: "Assistant") -> None:
        """Set the aggregator agent."""
        self.aggregator = aggregator

    async def execute(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        agents: List["Assistant"],
        **kwargs
    ) -> OrchestrationResult:
        """
        Execute all agents in parallel and aggregate results.

        Args:
            task: User query to send to all agents
            tenant_id: Tenant identifier
            session_id: Session for context
            agents: List of Qwen-Agent Assistant instances to execute in parallel

        Returns:
            OrchestrationResult with aggregated answer
        """
        start_time = time.perf_counter()

        if not agents:
            return self._create_result(
                success=False,
                answer="No agents provided for concurrent execution",
                agents_executed=[],
                start_time=start_time,
                metadata={"error": "no_agents"}
            )

        logger.info(f"🔀 Starting Concurrent orchestration with {len(agents)} agents")

        # Execute all agents in parallel
        tasks = []
        for agent in agents:
            tasks.append(self._execute_single_agent(agent, task))

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.global_timeout_ms / 1000
            )
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Concurrent orchestration global timeout ({self.config.global_timeout_ms}ms)")
            return self._create_result(
                success=False,
                answer="La ejecución paralela excedió el tiempo límite.",
                agents_executed=[a.name for a in agents],
                start_time=start_time,
                metadata={"error": "global_timeout"}
            )

        # Process results
        intermediate_results: List[AgentResult] = []
        agents_executed: List[str] = []
        successful_results: List[AgentResult] = []

        for agent, result in zip(agents, results):
            agent_name = agent.name if hasattr(agent, 'name') else "Unknown"
            agents_executed.append(agent_name)

            if isinstance(result, Exception):
                agent_result = AgentResult(
                    agent_name=agent_name,
                    success=False,
                    answer=f"Error: {str(result)}",
                    execution_time_ms=0,
                    metadata={"error": str(result)}
                )
            else:
                agent_result = result
                if result.success:
                    successful_results.append(result)

            intermediate_results.append(agent_result)

        logger.info(f"📊 Parallel execution: {len(successful_results)}/{len(agents)} succeeded")

        # Check minimum successful agents
        if len(successful_results) < self.config.min_successful_agents:
            return self._create_result(
                success=False,
                answer=f"Solo {len(successful_results)} de {len(agents)} agentes completaron exitosamente.",
                agents_executed=agents_executed,
                start_time=start_time,
                intermediate_results=intermediate_results,
                metadata={"error": "insufficient_successful_agents"}
            )

        # Aggregate results
        if self.config.use_aggregator and self.aggregator and len(successful_results) > 1:
            final_answer = await self._aggregate_results(successful_results, task)
        else:
            final_answer = self._format_results(successful_results)

        return self._create_result(
            success=True,
            answer=final_answer,
            agents_executed=agents_executed,
            start_time=start_time,
            intermediate_results=intermediate_results,
            metadata={
                "total_agents": len(agents),
                "successful_agents": len(successful_results),
                "aggregated": self.config.use_aggregator and self.aggregator is not None
            }
        )

    async def _execute_single_agent(
        self,
        agent: "Assistant",
        task: str
    ) -> AgentResult:
        """Execute a single agent and return its result."""
        agent_name = agent.name if hasattr(agent, 'name') else "Unknown"
        start_time = time.perf_counter()

        try:
            answer, tools_called = await _run_qwen_agent(agent, task)
            execution_time = (time.perf_counter() - start_time) * 1000

            logger.info(f"  ✓ {agent_name} completed in {execution_time:.0f}ms")

            return AgentResult(
                agent_name=agent_name,
                success=True,
                answer=answer,
                execution_time_ms=execution_time,
                tools_called=tools_called
            )

        except Exception as e:
            execution_time = (time.perf_counter() - start_time) * 1000
            logger.error(f"  ❌ {agent_name} failed: {e}")

            return AgentResult(
                agent_name=agent_name,
                success=False,
                answer=f"Error: {str(e)}",
                execution_time_ms=execution_time,
                metadata={"error": str(e)}
            )

    async def _aggregate_results(
        self,
        results: List[AgentResult],
        original_task: str
    ) -> str:
        """Use aggregator agent to combine results."""
        if not self.aggregator:
            return self._format_results(results)

        logger.info("🔄 Aggregating results with aggregator agent...")

        # Build analysis summary
        analyses = []
        for r in results:
            analyses.append(f"**{r.agent_name}:**\n{r.answer}")

        prompt = self.config.aggregation_prompt.format(
            analyses="\n\n---\n\n".join(analyses)
        )

        try:
            answer, _ = await _run_qwen_agent(self.aggregator, prompt)
            logger.info("✅ Aggregation complete")
            return answer

        except Exception as e:
            logger.warning(f"⚠️ Aggregation failed, using formatted results: {e}")
            return self._format_results(results)

    def _format_results(self, results: List[AgentResult]) -> str:
        """Format results without aggregation."""
        sections = []
        for r in results:
            sections.append(f"## {r.agent_name}\n\n{r.answer}")

        return "\n\n---\n\n".join(sections)

    async def execute_stream(
        self,
        task: str,
        tenant_id: str,
        session_id: str,
        agents: List["Assistant"],
        **kwargs
    ):
        """
        Execute agents concurrently with streaming progress.

        Yields events as each agent completes for real-time UI feedback.
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
                "message": f"Iniciando análisis paralelo con {len(agents)} perspectivas...",
                "total_agents": len(agents),
                "pattern": "concurrent"
            }
        }

        # Start all agents
        for agent in agents:
            agent_name = agent.name if hasattr(agent, 'name') else "Unknown"
            yield {
                "event": "agent_start",
                "data": {
                    "agent": agent_name,
                    "message": f"Iniciando {agent_name}..."
                }
            }

        # Execute in parallel
        tasks = [self._execute_single_agent(agent, task) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_results = []
        for agent, result in zip(agents, results):
            agent_name = agent.name if hasattr(agent, 'name') else "Unknown"

            if isinstance(result, Exception):
                yield {
                    "event": "agent_complete",
                    "data": {
                        "agent": agent_name,
                        "success": False,
                        "error": str(result)
                    }
                }
            else:
                yield {
                    "event": "agent_complete",
                    "data": {
                        "agent": agent_name,
                        "success": result.success,
                        "answer_preview": result.answer[:200] + "..." if len(result.answer) > 200 else result.answer
                    }
                }
                if result.success:
                    successful_results.append(result)

        # Aggregate and stream final answer
        if successful_results:
            if self.config.use_aggregator and self.aggregator and len(successful_results) > 1:
                yield {
                    "event": "aggregating",
                    "data": {"message": "Combinando resultados..."}
                }
                final_answer = await self._aggregate_results(successful_results, task)
            else:
                final_answer = self._format_results(successful_results)

            yield {
                "event": "token",
                "data": {"text": final_answer}
            }

            yield {
                "event": "complete",
                "data": {
                    "success": True,
                    "total_agents": len(agents),
                    "successful_agents": len(successful_results)
                }
            }
        else:
            yield {
                "event": "error",
                "data": {
                    "error": "No agents succeeded",
                    "message": "Ningún agente completó exitosamente"
                }
            }


# Singleton instance
_concurrent_orchestration: Optional[ConcurrentOrchestration] = None


def get_concurrent_orchestration(
    config: Optional[ConcurrentConfig] = None
) -> ConcurrentOrchestration:
    """Get or create the ConcurrentOrchestration instance."""
    global _concurrent_orchestration
    if _concurrent_orchestration is None:
        _concurrent_orchestration = ConcurrentOrchestration(config=config)
    return _concurrent_orchestration
