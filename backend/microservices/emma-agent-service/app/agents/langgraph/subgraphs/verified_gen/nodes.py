"""
Verified Generation sub-graph nodes.

Thin wrappers around the existing business logic in:
- stop_and_go/strategies/verified.py (VerifiedStrategy)
- stop_and_go/nodes/initialize.py (source hydration, DOI, CENDOJ)
- stop_and_go/nodes/search_and_evaluate.py (evidence search)

The strategy pattern indirection (get_strategy(mode)) is replaced by
direct instantiation of VerifiedStrategy. Node functions take
VerifiedGenState and return partial update dicts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from app.core.config import settings

logger = logging.getLogger(__name__)

# Lazy-init strategy singleton
_strategy = None


def _get_strategy():
    """Get or create the VerifiedStrategy singleton."""
    global _strategy
    if _strategy is None:
        from app.agents.langgraph.stop_and_go.strategies.verified import VerifiedStrategy
        _strategy = VerifiedStrategy()
    return _strategy


async def initialize_node(state: dict) -> dict:
    """Hydrate source texts, split into sections, pre-validate DOIs, fetch jurisprudence.

    Reuses the shared initialize logic from stop_and_go/nodes/initialize.py.
    """
    from app.agents.langgraph.subgraphs.evidence import (
        get_source_context,
        chunk_source_into_sections,
        validate_source_dois,
        search_cendoj_jurisprudence,
        is_cendoj_enabled,
    )

    strategy = _get_strategy()
    await strategy.initialize(state)

    source_context, source_document_ids = await get_source_context(
        query=state["query"],
        tenant_id=state["tenant_id"],
        document_ids=state.get("context_document_ids"),
        collections=state.get("collections"),
        uploaded_texts=state.get("uploaded_texts"),
    )

    if not source_context.strip():
        logger.error("No source context — aborting verified generation")
        return {
            "source_context": "",
            "source_sections": [""],
            "current_section_index": 0,
            "section_claims_count": [0],
            "is_complete": True,
            "pending_events": [{
                "event_type": "error",
                "data": {
                    "message": "No se pudo obtener el contenido del documento. "
                               "Asegúrese de subir un archivo antes de generar.",
                    "session_id": state["session_id"],
                },
            }],
        }

    source_filenames = [
        t.get("filename", "Documento") for t in (state.get("uploaded_texts") or [])
        if t.get("text")
    ]

    sections = chunk_source_into_sections(source_context)
    logger.info(
        f"Source loaded: {len(source_context)} chars, "
        f"{len(sections)} section(s), {len(source_document_ids)} source doc(s)"
    )

    updates: Dict[str, Any] = {
        "source_context": source_context,
        "source_document_ids": source_document_ids,
        "source_filenames": source_filenames,
        "source_sections": sections,
        "current_section_index": 0,
        "section_claims_count": [0] * len(sections),
        "pending_events": [{
            "event_type": "progress",
            "data": {
                "message": "Context retrieved, starting claim generation...",
                "session_id": state["session_id"],
                "total_sections": len(sections),
            },
            "progress_percent": 10,
        }],
    }

    # DOI pre-validation from uploaded documents
    if state.get("uploaded_texts"):
        doi_validations = await validate_source_dois(state["uploaded_texts"])
        if doi_validations:
            updates["source_doi_validations"] = doi_validations
            valid = sum(1 for d in doi_validations if d.get("valid"))
            logger.info(f"DOI pre-validation: {len(doi_validations)} DOIs ({valid} valid)")

    # CENDOJ jurisprudence (legal sector only)
    verification_sources = state.get("mode_config", {}).get("verification_sources", [])
    sector = state.get("mode_config", {}).get("sector", "")
    if sector == "legal" and ("jurisprudence" in verification_sources or "public_knowledge" in verification_sources):
        if await is_cendoj_enabled():
            jurisprudence = await search_cendoj_jurisprudence(
                query=state["query"],
                with_content=settings.cendoj_max_content,
            )
            if jurisprudence:
                updates["jurisprudence_evidence"] = jurisprudence

    return updates


async def generate_claim_node(state: dict) -> dict:
    """Generate one factual claim from the current section.

    Delegates to VerifiedStrategy.extract_item(), handles dedup and section windowing.
    """
    strategy = _get_strategy()

    # Current section (windowed) or full source
    sections = state.get("source_sections", [])
    section_idx = state.get("current_section_index", 0)
    if sections and section_idx < len(sections):
        source_context = sections[section_idx]
    else:
        source_context = state.get("source_context", "")

    try:
        item = await strategy.extract_item(state, source_context)
    except Exception as e:
        logger.error(f"Claim generation failed: {e}")
        return {
            "is_complete": True,
            "pending_events": [{
                "event_type": "error",
                "data": {"error": f"Claim generation failed: {str(e)}"},
            }],
        }

    items_extracted = state.get("items_extracted", 0) + 1

    # Dedup check
    if strategy.is_duplicate(item, state):
        logger.info(f"Skipping duplicate claim #{items_extracted}")
        new_streak = state.get("duplicate_streak", 0) + 1
        return {
            "current_item": None,
            "items_extracted": items_extracted,
            "duplicate_streak": new_streak,
            "is_complete": new_streak >= 2,
        }

    max_claims = state.get("max_claims", 20)
    progress = min(80, 10 + (items_extracted * 70 // max_claims))

    return {
        "current_item": item,
        "items_extracted": items_extracted,
        "duplicate_streak": 0,
        "pending_events": [{
            "event_type": "claim_generated",
            "item_id": item.get("id"),
            "data": item.get("event_data", {}),
            "progress_percent": progress,
        }],
    }


async def verify_claim_node(state: dict) -> dict:
    """Two-tier verification: faithfulness (NLI) + external corroboration.

    Delegates to shared _search_evidence() for evidence, then
    VerifiedStrategy.evaluate_item() for LLM-based verification.
    """
    from app.agents.langgraph.subgraphs.evidence import search_evidence

    strategy = _get_strategy()
    item = state.get("current_item")

    if item is None:
        return {}

    verification_event = {
        "event_type": "verified_verification_started",
        "item_id": item.get("id"),
        "data": {"message": "Verifying claim against evidence..."},
    }

    try:
        evidence_by_tier = await search_evidence(
            query_text=item.get("text", ""),
            tenant_id=state["tenant_id"],
            collections=state.get("collections", []),
            uploaded_texts=state.get("uploaded_texts", []),
            mode_config=state.get("mode_config", {}),
            jurisprudence_evidence=state.get("jurisprudence_evidence", []),
            source_document_ids=state.get("source_document_ids", []),
            source_doi_validations=state.get("source_doi_validations", []),
        )

        all_evidence = evidence_by_tier.get("source", []) + evidence_by_tier.get("external", [])

        evaluation = await strategy.evaluate_item(item, evidence_by_tier, state)
        status = evaluation.get("status", "rejected")

        events = [verification_event]
        all_items = list(state.get("all_extracted_items", []))
        all_items.append(item)

        updates: Dict[str, Any] = {"all_extracted_items": all_items}

        if status in ("accepted", "corrected"):
            event_data = await strategy.on_accepted(item, evaluation, state)
            if status == "corrected":
                updates["items_corrected"] = state.get("items_corrected", 0) + 1
            else:
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
                source_entry = {
                    "id": src_id,
                    "title": e.get("document_title", ""),
                    "source": src_type,
                    "url": e.get("url", ""),
                }
                if src_type == "jurisprudence":
                    source_entry.update({
                        "roj": e.get("roj", ""),
                        "ecli": e.get("ecli", ""),
                    })
                sources_map[src_id] = source_entry
        updates["sources_map"] = sources_map
        updates["pending_events"] = events
        return updates

    except Exception as e:
        import traceback
        logger.error(f"Claim verification failed: {e}\n{traceback.format_exc()}")
        return {
            "all_extracted_items": list(state.get("all_extracted_items", [])) + [item],
            "items_rejected": state.get("items_rejected", 0) + 1,
            "pending_events": [verification_event, {
                "event_type": "error",
                "item_id": item.get("id"),
                "data": {"error": f"Verification failed: {str(e)}"},
            }],
        }


async def decide_node(state: dict) -> dict:
    """Check completion: more claims needed, advance section, or synthesize.

    Handles max claims, duplicate streaks, rejection thresholds, section
    advancement, and LLM completion check.
    """
    strategy = _get_strategy()
    step = state.get("current_step", 0) + 1

    sections = state.get("source_sections", [])
    section_idx = state.get("current_section_index", 0)
    total_sections = len(sections)
    has_more_sections = total_sections > 1 and section_idx < total_sections - 1

    # Max claims reached
    if state.get("items_extracted", 0) >= state.get("max_claims", 20):
        logger.info(f"Max claims reached ({state.get('items_extracted', 0)})")
        return {"is_complete": True, "current_step": step}

    # Already complete (e.g., duplicate streak)
    if state.get("is_complete", False):
        if has_more_sections:
            return _advance_section(state, section_idx, step, reason="duplicate_streak")
        return {"current_step": step}

    # Early exit: 3+ rejections, 0 accepted
    items_rejected = state.get("items_rejected", 0)
    items_accepted = state.get("items_accepted", 0)
    if items_rejected >= 3 and items_accepted == 0:
        if has_more_sections:
            return _advance_section(state, section_idx, step, reason="no_evidence")
        logger.info(f"Stopping: {items_rejected} rejections with 0 accepted")
        return {"is_complete": True, "current_step": step}

    # LLM completion check (after 3+ accepted)
    if items_accepted >= 3:
        if sections and section_idx < len(sections):
            source_context = sections[section_idx]
        else:
            source_context = state.get("source_context", "")
        try:
            is_done = await strategy.check_completion(state, source_context)
            if is_done:
                if has_more_sections:
                    return _advance_section(state, section_idx, step, reason="section_complete")
                logger.info(f"LLM completion: done at {items_accepted} accepted claims")
                return {"is_complete": True, "current_step": step}
        except Exception as e:
            logger.warning(f"Completion check failed (continuing): {e}")

    return {"is_complete": False, "current_step": step}


def _advance_section(state: dict, current_idx: int, step: int, reason: str) -> dict:
    """Advance to the next source section."""
    next_idx = current_idx + 1
    sections = state.get("source_sections", [])

    section_claims = list(state.get("section_claims_count", [0] * len(sections)))
    if current_idx < len(section_claims):
        section_claims[current_idx] = state.get("items_accepted", 0) - sum(
            section_claims[i] for i in range(current_idx)
        )

    logger.info(f"Advancing to section {next_idx + 1}/{len(sections)} (reason={reason})")

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
            },
        }],
    }


async def synthesize_on_complete(state: dict) -> dict:
    """Run final synthesis — assemble document from verified claims.

    Called as an END hook (after decide returns is_complete=True).
    Delegates to VerifiedStrategy.synthesize().
    """
    if not state.get("is_complete", False):
        return {}

    strategy = _get_strategy()

    try:
        result = await strategy.synthesize(state)
    except Exception as e:
        logger.error(f"Document synthesis failed: {e}")
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
            "event_type": "document_complete",
            "data": result,
            "progress_percent": 100,
        }],
    }
