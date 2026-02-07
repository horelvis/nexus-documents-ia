"""
Meta Agent Online Selector — Query-time strategy selection + execution.

Called from classify_node when META_AGENT_ONLINE_SELECTION is enabled.
Uses epsilon-greedy exploration to balance exploitation of the best
known strategy with exploration of alternatives.

If no strategy is found or execution fails → returns None,
and classify_node falls through to the standard react_loop.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

from app.core.config import settings
from .archive import StrategyArchive, get_strategy_archive
from .sandbox import AgentContext, CodeExecutor, SecurityError, ResourceLimitError

logger = logging.getLogger(__name__)


class OnlineSelector:
    """Select and execute discovered strategies at query time."""

    def __init__(
        self,
        archive: Optional[StrategyArchive] = None,
        executor: Optional[CodeExecutor] = None,
    ):
        self._archive = archive or get_strategy_archive()
        self._executor = executor or CodeExecutor()

    async def try_execute(
        self,
        query: str,
        state: Dict[str, Any],
        intent: str,
        sector: Optional[str],
        confidence: float,
    ) -> Optional[Dict[str, Any]]:
        """Try to execute a discovered strategy.

        Returns graph-compatible state update dict or None if:
        - Confidence too low
        - No strategy found
        - Execution fails

        On failure, classify_node uses standard react_loop.
        """
        if confidence < 0.7:
            return None

        # Epsilon-greedy selection
        if random.random() < settings.meta_agent_epsilon:
            entry = await self._archive.get_random_active(intent, sector)
        else:
            entry = await self._archive.get_best_strategy(intent, sector)

        if not entry:
            return None

        strategy = entry.strategy
        logger.info(
            f"Meta strategy selected: {strategy.name} ({strategy.id[:8]}...) "
            f"for intent={intent}, sector={sector}"
        )

        try:
            # Build context and execute
            from app.agents.langgraph.tools.registry import get_tool_registry
            from app.agents.llm_router import get_llm_router

            registry = get_tool_registry()
            router = await get_llm_router()
            ctx = AgentContext(
                state=state,
                registry=registry,
                router=router,
                max_llm_calls=settings.meta_agent_max_llm_calls,
                max_tool_calls=settings.meta_agent_max_tool_calls,
            )

            start = time.time()
            result = await self._executor.execute(
                code=strategy.code,
                query=query,
                ctx=ctx,
                timeout=settings.meta_agent_execution_timeout,
            )
            latency = time.time() - start

            # Record production use (fire-and-forget)
            if settings.meta_agent_feedback_enabled:
                try:
                    await self._archive.record_production_use(
                        strategy.id, latency_s=latency
                    )
                except Exception:
                    pass

            # Return state update compatible with graph
            return {
                "is_complete": True,
                "final_answer": result.answer,
                "sources": result.sources,
                "success": True,
                "fast_path_used": False,
                "reasoning_steps": ctx._reasoning_steps + [
                    {
                        "type": "response",
                        "content": f"Strategy: {strategy.name} ({strategy.id[:8]}...)",
                    }
                ],
                "metadata": {
                    "_meta_strategy_id": strategy.id,
                    "_meta_strategy_name": strategy.name,
                    "_meta_latency_s": latency,
                },
            }

        except (SecurityError, ResourceLimitError) as e:
            logger.warning(f"Meta strategy failed safely: {e}")
            return None

        except Exception as e:
            logger.debug(f"Meta strategy execution error: {e}")
            return None


# Singleton
_selector: Optional[OnlineSelector] = None


def get_online_selector() -> OnlineSelector:
    """Get the singleton OnlineSelector."""
    global _selector
    if _selector is None:
        _selector = OnlineSelector()
    return _selector
