"""
Extract Item node — delegates to strategy.extract_item().

Increments items_extracted, checks for duplicates, and emits
an SSE event for the extracted item. If the item is a duplicate,
it increments duplicate_streak and skips to decide.
"""

from __future__ import annotations

import logging

from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)


async def extract_item_node(state: dict) -> dict:
    """Extract next item via strategy, check duplicates."""
    strategy = get_strategy(state["mode"])
    source_context = state.get("source_context", "")

    try:
        item = await strategy.extract_item(state, source_context)
    except Exception as e:
        logger.error(f"Item extraction failed: {e}")
        return {
            "is_complete": True,
            "pending_events": [{
                "event_type": "error",
                "data": {"error": f"Extraction failed: {str(e)}"},
            }],
        }

    items_extracted = state.get("items_extracted", 0) + 1

    # Deduplication check
    if strategy.is_duplicate(item, state):
        logger.info(f"Skipping duplicate item #{items_extracted}: {item.get('text', '')[:60]}...")
        new_streak = state.get("duplicate_streak", 0) + 1
        # Don't add to all_extracted_items — it's a dup
        return {
            "current_item": None,
            "items_extracted": items_extracted,
            "duplicate_streak": new_streak,
            # If 2+ consecutive dups, signal completion
            "is_complete": new_streak >= 2,
        }

    # Progress percent: 10% base + up to 70% for items
    max_items = state.get("max_items", 10)
    progress = min(80, 10 + (items_extracted * 70 // max_items))

    return {
        "current_item": item,
        "items_extracted": items_extracted,
        "duplicate_streak": 0,
        "pending_events": [{
            "event_type": f"{state['mode']}_item_extracted",
            "item_id": item.get("id"),
            "data": item.get("event_data", {}),
            "progress_percent": progress,
        }],
    }
