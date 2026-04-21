"""
Predictive Analysis sub-graph nodes.

Delegates to PredictiveStrategy (from stop_and_go/strategies/predictive.py)
without the strategy registry indirection.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

_strategy = None


def _get_strategy():
    global _strategy
    if _strategy is None:
        from .strategy import PredictiveStrategy
        _strategy = PredictiveStrategy()
    return _strategy


async def initialize_node(state: dict) -> dict:
    """Hydrate source texts, fetch jurisprudence for legal sector."""
    from app.agents.langgraph.subgraphs.evidence import (
        get_source_context,
        chunk_source_into_sections,
        search_cendoj_jurisprudence,
        is_cendoj_enabled,
    )

    strategy = _get_strategy()
    await strategy.initialize(state)

    source_context, source_document_ids = await get_source_context(
        query=state["query"],
        document_ids=state.get("context_document_ids"),
        collections=state.get("collections"),
        uploaded_texts=state.get("uploaded_texts"),
    )

    if not source_context.strip():
        logger.warning("No source context — predictive analysis will use case description only")

    source_filenames = [
        t.get("filename", "Documento") for t in (state.get("uploaded_texts") or [])
        if t.get("text")
    ]

    updates: Dict[str, Any] = {
        "source_context": source_context,
        "source_document_ids": source_document_ids,
        "source_filenames": source_filenames,
        "pending_events": [{
            "event_type": "progress",
            "data": {
                "message": "Context loaded, starting factor extraction...",
                "session_id": state["session_id"],
            },
            "progress_percent": 10,
        }],
    }

    # CENDOJ for legal sector
    sector = state.get("mode_config", {}).get("sector_override", "")
    if sector == "legal":
        if await is_cendoj_enabled():
            jurisprudence = await search_cendoj_jurisprudence(
                query=state["query"],
                with_content=settings.cendoj_max_content,
            )
            if jurisprudence:
                updates["jurisprudence_evidence"] = jurisprudence

    return updates


async def extract_factor_node(state: dict) -> dict:
    """Extract one legal/business factor from source documents."""
    strategy = _get_strategy()

    source_context = state.get("source_context", "")

    try:
        item = await strategy.extract_item(state, source_context)
    except Exception as e:
        logger.error(f"Factor extraction failed: {e}")
        return {
            "is_complete": True,
            "pending_events": [{
                "event_type": "error",
                "data": {"error": f"Factor extraction failed: {str(e)}"},
            }],
        }

    items_extracted = state.get("items_extracted", 0) + 1

    if strategy.is_duplicate(item, state):
        new_streak = state.get("duplicate_streak", 0) + 1
        return {
            "current_item": None,
            "items_extracted": items_extracted,
            "duplicate_streak": new_streak,
            "is_complete": new_streak >= 2,
        }

    max_factors = state.get("max_factors", 10)
    progress = min(80, 10 + (items_extracted * 70 // max_factors))

    return {
        "current_item": item,
        "items_extracted": items_extracted,
        "duplicate_streak": 0,
        "pending_events": [{
            "event_type": "factor_extracted",
            "item_id": item.get("id"),
            "data": item.get("event_data", {}),
            "progress_percent": progress,
        }],
    }


async def evaluate_outcome_node(state: dict) -> dict:
    """Evaluate evidence for/against the current factor, assign weight."""
    from app.agents.langgraph.subgraphs.evidence import search_evidence

    strategy = _get_strategy()
    item = state.get("current_item")

    if item is None:
        return {}

    try:
        evidence_by_tier = await search_evidence(
            query_text=item.get("text", ""),
            collections=state.get("collections", []),
            uploaded_texts=state.get("uploaded_texts", []),
            mode_config=state.get("mode_config", {}),
            jurisprudence_evidence=state.get("jurisprudence_evidence", []),
            source_document_ids=state.get("source_document_ids", []),
            user_roles=state.get("user_roles", []),
        )

        all_evidence = evidence_by_tier.get("source", []) + evidence_by_tier.get("external", [])
        evaluation = await strategy.evaluate_item(item, evidence_by_tier, state)
        status = evaluation.get("status", "rejected")

        events = []
        all_items = list(state.get("all_extracted_items", []))
        all_items.append(item)

        updates: Dict[str, Any] = {"all_extracted_items": all_items}

        if status == "accepted":
            event_data = await strategy.on_accepted(item, evaluation, state)
            updates["items_accepted"] = state.get("items_accepted", 0) + 1
            events.append(event_data)
        else:
            event_data = await strategy.on_rejected(item, evaluation, state)
            updates["items_rejected"] = state.get("items_rejected", 0) + 1
            events.append(event_data)

        # Collect external sources
        sources_map = dict(state.get("sources_map", {}))
        for e in all_evidence:
            src_id = e.get("document_id", "")
            src_type = e.get("source", "internal")
            if src_id and src_id not in sources_map and src_type not in ("uploaded", "source_document"):
                sources_map[src_id] = {
                    "id": src_id,
                    "title": e.get("document_title", ""),
                    "source": src_type,
                    "url": e.get("url", ""),
                }
        updates["sources_map"] = sources_map
        updates["pending_events"] = events
        return updates

    except Exception as e:
        logger.error(f"Factor evaluation failed: {e}")
        return {
            "all_extracted_items": list(state.get("all_extracted_items", [])) + [item],
            "items_rejected": state.get("items_rejected", 0) + 1,
            "pending_events": [{
                "event_type": "error",
                "item_id": item.get("id"),
                "data": {"error": f"Evaluation failed: {str(e)}"},
            }],
        }


async def decide_node(state: dict) -> dict:
    """Check completion: more factors needed or synthesize recommendation."""
    strategy = _get_strategy()
    step = state.get("current_step", 0) + 1

    if state.get("items_extracted", 0) >= state.get("max_factors", 10):
        return {"is_complete": True, "current_step": step}

    if state.get("is_complete", False):
        return {"current_step": step}

    items_rejected = state.get("items_rejected", 0)
    items_accepted = state.get("items_accepted", 0)
    if items_rejected >= 3 and items_accepted == 0:
        return {"is_complete": True, "current_step": step}

    if items_accepted >= 3:
        source_context = state.get("source_context", "")
        try:
            is_done = await strategy.check_completion(state, source_context)
            if is_done:
                return {"is_complete": True, "current_step": step}
        except Exception as e:
            logger.warning(f"Completion check failed: {e}")

    return {"is_complete": False, "current_step": step}


async def synthesize_on_complete(state: dict) -> dict:
    """Run final synthesis — aggregate factors into prediction."""
    if not state.get("is_complete", False):
        return {}

    strategy = _get_strategy()

    try:
        result = await strategy.synthesize(state)
    except Exception as e:
        logger.error(f"Prediction synthesis failed: {e}")
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
            "event_type": "prediction_ready",
            "data": result,
            "progress_percent": 100,
        }],
    }
