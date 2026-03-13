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

    # Section-windowed state
    sections = state.get("source_sections", [])
    section_idx = state.get("current_section_index", 0)
    total_sections = len(sections)
    has_more_sections = total_sections > 1 and section_idx < total_sections - 1

    # Max items reached (global ceiling across all sections)
    if state.get("items_extracted", 0) >= state.get("max_items", 10):
        logger.info(f"Max items reached ({state.get('items_extracted', 0)})")
        return {"is_complete": True, "current_step": step}

    # Already marked complete (e.g., by extract_item on duplicate streak)
    if state.get("is_complete", False):
        if has_more_sections:
            # Duplicate streak exhausted this section — advance to next
            return _advance_section(state, section_idx, step, reason="duplicate_streak")
        return {"current_step": step}

    # Early exit: 3+ rejections with 0 accepted
    items_rejected = state.get("items_rejected", 0)
    items_accepted = state.get("items_accepted", 0)
    if items_rejected >= 3 and items_accepted == 0:
        if has_more_sections:
            # Poor evidence in this section — try next one
            return _advance_section(state, section_idx, step, reason="no_evidence")
        logger.info(
            f"Stopping: {items_rejected} rejections with 0 accepted — "
            "insufficient evidence"
        )
        return {"is_complete": True, "current_step": step}

    # LLM completion check (only after 3+ accepted items)
    if items_accepted >= 3:
        strategy = get_strategy(state["mode"])
        # Pass current section to completion check (not full document)
        if sections and section_idx < len(sections):
            source_context = sections[section_idx]
        else:
            source_context = state.get("source_context", "")
        try:
            is_done = await strategy.check_completion(state, source_context)
            if is_done:
                if has_more_sections:
                    # LLM says done for this section — advance
                    return _advance_section(state, section_idx, step, reason="section_complete")
                logger.info(f"LLM completion check: done at {items_accepted} accepted items")
                return {"is_complete": True, "current_step": step}
        except Exception as e:
            logger.warning(f"Completion check failed (continuing): {e}")

    return {"is_complete": False, "current_step": step}


def _advance_section(state: dict, current_idx: int, step: int, reason: str) -> dict:
    """Advance to the next source section, resetting per-section counters."""
    next_idx = current_idx + 1
    sections = state.get("source_sections", [])

    # Track claims generated in the section we're leaving
    section_claims = list(state.get("section_claims_count", [0] * len(sections)))
    if current_idx < len(section_claims):
        section_claims[current_idx] = state.get("items_accepted", 0) - sum(
            section_claims[i] for i in range(current_idx)
        )

    logger.info(
        f"Advancing to section {next_idx + 1}/{len(sections)} "
        f"(reason={reason}, claims_so_far={state.get('items_accepted', 0)})"
    )

    return {
        "current_section_index": next_idx,
        "section_claims_count": section_claims,
        "duplicate_streak": 0,
        "is_complete": False,
        "current_step": step,
        "pending_events": [{
            "event_type": "section_advanced",
            "data": {
                "section": next_idx + 1,
                "total_sections": len(sections),
                "reason": reason,
                "message": f"Processing section {next_idx + 1} of {len(sections)}...",
            },
        }],
    }
