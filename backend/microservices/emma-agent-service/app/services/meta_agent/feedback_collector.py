"""
Meta Agent Feedback Collector — Production signal recording.

Records production usage data (latency, thumbs up/down, success/failure)
back into the archive to update strategy scores over time.
"""

from __future__ import annotations

import logging
from typing import Optional

from .archive import StrategyArchive, get_strategy_archive

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """Collect production feedback and update archive entries."""

    def __init__(self, archive: Optional[StrategyArchive] = None):
        self._archive = archive or get_strategy_archive()

    async def record_feedback(
        self,
        strategy_id: str,
        latency_s: float = 0.0,
        thumbs_up: bool = False,
        thumbs_down: bool = False,
    ) -> None:
        """Record production feedback for a strategy."""
        try:
            await self._archive.record_production_use(
                strategy_id=strategy_id,
                latency_s=latency_s,
                thumbs_up=thumbs_up,
                thumbs_down=thumbs_down,
            )
            logger.debug(
                f"Recorded feedback for strategy {strategy_id[:8]}... "
                f"(latency={latency_s:.2f}s, up={thumbs_up}, down={thumbs_down})"
            )
        except Exception as e:
            logger.warning(f"Failed to record feedback: {e}")


# Singleton
_collector: Optional[FeedbackCollector] = None


def get_feedback_collector() -> FeedbackCollector:
    """Get the singleton FeedbackCollector."""
    global _collector
    if _collector is None:
        _collector = FeedbackCollector()
    return _collector
