"""
Decide node — checks completion, dedup streaks, early exit conditions.

Routes to either:
  - extract_item (continue loop)
  - synthesize (done)

This logic is shared between modes, with the LLM completion check
delegated to the strategy.
"""

from __future__ import annotations

import logging

from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)


async def decide_node(state: dict) -> dict:
    """Check whether to continue extracting or synthesize."""
    step = state.get("current_step", 0) + 1

    # Already marked complete (e.g., by extract_item on duplicate streak)
    if state.get("is_complete", False):
        return {"current_step": step}

    # Max items reached
    if state.get("items_extracted", 0) >= state.get("max_items", 10):
        logger.info(f"Max items reached ({state.get('items_extracted', 0)})")
        return {"is_complete": True, "current_step": step}

    # Early exit: 3+ rejections with 0 accepted
    items_rejected = state.get("items_rejected", 0)
    items_accepted = state.get("items_accepted", 0)
    if items_rejected >= 3 and items_accepted == 0:
        logger.info(
            f"Stopping: {items_rejected} rejections with 0 accepted — "
            "insufficient evidence"
        )
        return {"is_complete": True, "current_step": step}

    # LLM completion check (only after 3+ accepted items)
    if items_accepted >= 3:
        strategy = get_strategy(state["mode"])
        source_context = state.get("source_context", "")
        try:
            is_done = await strategy.check_completion(state, source_context)
            if is_done:
                logger.info(f"LLM completion check: done at {items_accepted} accepted items")
                return {"is_complete": True, "current_step": step}
        except Exception as e:
            logger.warning(f"Completion check failed (continuing): {e}")

    return {"is_complete": False, "current_step": step}
