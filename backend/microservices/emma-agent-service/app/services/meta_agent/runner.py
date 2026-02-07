"""
Meta Agent Runner — Execute strategies against test sets via sandbox.

Takes a StrategyCandidate and a list of TestCases, runs each in the sandbox,
and returns structured CaseResults for evaluation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from app.core.config import settings
from .sandbox import AgentContext, CodeExecutor, SecurityError, ResourceLimitError
from .schemas import CaseResult, RunResult, StrategyCandidate, TestCase

logger = logging.getLogger(__name__)


class StrategyRunner:
    """Runs strategies against test cases in the sandbox."""

    def __init__(self, executor: Optional[CodeExecutor] = None):
        self._executor = executor or CodeExecutor()

    async def run_test_set(
        self,
        strategy: StrategyCandidate,
        test_cases: List[TestCase],
    ) -> RunResult:
        """Execute strategy against all test cases.

        Args:
            strategy: The strategy to evaluate
            test_cases: Test cases to run against

        Returns:
            RunResult with individual case results
        """
        results = []
        for case in test_cases:
            result = await self._run_single(strategy, case)
            results.append(result)

        return RunResult(
            strategy_id=strategy.id,
            case_results=results,
        )

    async def _run_single(
        self,
        strategy: StrategyCandidate,
        case: TestCase,
    ) -> CaseResult:
        """Run a strategy against a single test case."""
        start = time.time()

        try:
            # Build context from test case
            ctx = await self._build_context(case)

            # Execute in sandbox
            result = await self._executor.execute(
                code=strategy.code,
                query=case.query,
                ctx=ctx,
                timeout=settings.meta_agent_execution_timeout,
            )

            latency = time.time() - start

            return CaseResult(
                success=True,
                answer=result.answer,
                sources=result.sources,
                llm_calls=ctx.llm._call_count,
                tool_calls=ctx.tools._call_count,
                latency_s=latency,
                reasoning_steps=ctx._reasoning_steps,
            )

        except SecurityError as e:
            logger.warning(f"Security violation in strategy {strategy.id[:8]}...: {e}")
            return CaseResult(
                success=False,
                error=f"SecurityError: {e}",
                latency_s=time.time() - start,
            )

        except ResourceLimitError as e:
            logger.warning(f"Resource limit in strategy {strategy.id[:8]}...: {e}")
            return CaseResult(
                success=False,
                error=f"ResourceLimitError: {e}",
                latency_s=time.time() - start,
            )

        except asyncio.TimeoutError:
            logger.warning(
                f"Strategy {strategy.id[:8]}... timed out "
                f"after {settings.meta_agent_execution_timeout}s"
            )
            return CaseResult(
                success=False,
                error=f"TimeoutError: exceeded {settings.meta_agent_execution_timeout}s",
                latency_s=time.time() - start,
            )

        except Exception as e:
            logger.error(f"Unexpected error in strategy {strategy.id[:8]}...: {e}")
            return CaseResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                latency_s=time.time() - start,
            )

    async def _build_context(self, case: TestCase) -> AgentContext:
        """Build an AgentContext for a test case.

        Enables all feature-gated tools (CENDOJ, web search, connectors) so
        generated strategies can discover multi-source approaches.
        """
        from app.agents.langgraph.state import create_initial_react_state
        from app.agents.langgraph.tools.registry import get_tool_registry
        from app.agents.llm_router import get_llm_router

        state = create_initial_react_state(
            query=case.query,
            tenant_id=settings.meta_agent_test_tenant_id,
            request_context={
                "web_search_enabled": True,
                "connectors_enabled": True,
            },
        )

        # Enable all feature-gated tools for strategy discovery
        state_dict = dict(state)
        state_dict["features"] = {
            **state_dict.get("features", {}),
            "cendoj_enabled": settings.cendoj_enabled,
            "web_search_enabled": True,
            "connectors_enabled": True,
        }

        registry = get_tool_registry()
        router = await get_llm_router()

        return AgentContext(
            state=state_dict,
            registry=registry,
            router=router,
            max_llm_calls=settings.meta_agent_max_llm_calls,
            max_tool_calls=settings.meta_agent_max_tool_calls,
        )
