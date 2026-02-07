"""
Synthesize node — delegates to strategy.synthesize().

Called when decide determines the loop is complete.
Emits a final completion event and stores the result.
"""

from __future__ import annotations

import logging

from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)


async def synthesize_node(state: dict) -> dict:
    """Run final synthesis via strategy, emit completion event."""
    strategy = get_strategy(state["mode"])

    try:
        result = await strategy.synthesize(state)
    except Exception as e:
        logger.error(f"Synthesis failed: {e}")
        return {
            "result": {"error": str(e)},
            "pending_events": [{
                "event_type": "error",
                "data": {"error": f"Synthesis failed: {str(e)}"},
            }],
        }

    return {
        "result": result,
        "pending_events": [{
            "event_type": f"{state['mode']}_complete",
            "data": result,
            "progress_percent": 100,
        }],
    }
