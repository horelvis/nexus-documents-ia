"""
Review node — HITL batch review before document synthesis.

When HITL is enabled for verified mode:
1. Reads all verified claims from Redis cache
2. Flags claims below confidence_threshold as needs_review
3. If no claims need review → pass-through (emit review_skipped)
4. Calls interrupt(payload) — graph pauses, SSE closes
5. On resume: interrupt() returns the human review decisions
6. Applies decisions to Redis cache (reject/edit)
7. Emits review_submitted event, continues to synthesize

Idempotency: Code before interrupt() only reads from Redis.
On resume it re-reads — same result. No side effects before interrupt.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from langgraph.types import interrupt

from app.core.config import settings

logger = logging.getLogger(__name__)


async def review_node(state: dict) -> dict:
    """
    Batch human review of verified claims before synthesis.

    Pass-through when:
    - mode != "verified"
    - hitl_enabled == False
    - No claims below confidence threshold
    """
    mode = state.get("mode", "")
    hitl_enabled = state.get("hitl_enabled", False)

    # Pass-through for non-verified or non-HITL sessions
    if mode != "verified" or not hitl_enabled:
        return {}

    session_id = state.get("session_id", "")
    tenant_id = state.get("tenant_id", "")
    threshold = settings.verified_hitl_confidence_threshold

    # Read claims from Redis cache (idempotent read — safe for re-runs)
    claims = await _read_claims_from_cache(tenant_id, session_id)

    if not claims:
        logger.info(f"[review] No claims found in cache for {session_id[:16]}")
        return {}

    # Flag claims that need human review
    claims_for_review = []
    auto_approved_count = 0
    for claim in claims:
        confidence = claim.get("confidence", 0.0)
        status = claim.get("status", "")
        needs_review = confidence < threshold and status not in ("rejected",)

        claim_entry = {
            "claim_id": claim["id"],
            "claim_text": claim["text"],
            "confidence": confidence,
            "status": status,
            "verification_type": claim.get("verification_type"),
            "verification_reason": claim.get("verification_reason"),
            "needs_review": needs_review,
        }
        claims_for_review.append(claim_entry)

        if not needs_review:
            auto_approved_count += 1

    needs_review_count = sum(1 for c in claims_for_review if c["needs_review"])

    # If no claims need review, skip the interrupt
    if needs_review_count == 0:
        logger.info(
            f"[review] All {len(claims)} claims above threshold "
            f"({threshold}) — skipping review"
        )
        return {
            "pending_events": [{
                "event_type": "review_skipped",
                "data": {
                    "total_claims": len(claims),
                    "auto_approved": auto_approved_count,
                    "message": "All claims above confidence threshold — review skipped.",
                },
            }],
        }

    logger.info(
        f"[review] {needs_review_count}/{len(claims)} claims need review "
        f"(threshold={threshold}). Interrupting for human review."
    )

    # Build the review payload
    review_payload = {
        "session_id": session_id,
        "tenant_id": tenant_id,
        "claims": claims_for_review,
        "needs_review_count": needs_review_count,
        "auto_approved_count": auto_approved_count,
        "confidence_threshold": threshold,
    }

    # Emit review_requested event BEFORE interrupt
    # (This event will be yielded by the runner before SSE closes)
    pre_interrupt_events = [{
        "event_type": "review_requested",
        "data": review_payload,
    }]

    # ─── INTERRUPT ───────────────────────────────────────────────
    # Graph pauses here. SSE closes. Frontend shows review UI.
    # When the user submits their review, the graph resumes with
    # Command(resume=decisions_dict) and interrupt() returns it.
    # ─────────────────────────────────────────────────────────────
    human_response = interrupt(review_payload)

    # ─── RESUMED ─────────────────────────────────────────────────
    logger.info(f"[review] Resumed with human decisions for {session_id[:16]}")

    # Apply review decisions to Redis cache
    decisions = human_response.get("decisions", [])
    approved, rejected, edited = 0, 0, 0

    for decision in decisions:
        claim_id = decision.get("claim_id", "")
        action = decision.get("action", "approve")

        if action == "reject":
            await _remove_claim_from_cache(tenant_id, session_id, claim_id)
            rejected += 1
        elif action == "edit":
            new_text = decision.get("edited_text", "")
            if new_text:
                await _update_claim_in_cache(
                    tenant_id, session_id, claim_id, new_text
                )
                edited += 1
            else:
                approved += 1  # Empty edit = approve
        else:
            approved += 1

    logger.info(
        f"[review] Decisions applied: "
        f"approved={approved}, rejected={rejected}, edited={edited}"
    )

    return {
        "review_response": human_response,
        "pending_events": pre_interrupt_events + [{
            "event_type": "review_submitted",
            "data": {
                "approved": approved + auto_approved_count,
                "rejected": rejected,
                "edited": edited,
            },
        }],
    }


# =============================================================================
# Redis Cache Helpers (thin wrappers around VerifiedContextCache)
# =============================================================================


async def _read_claims_from_cache(
    tenant_id: str, session_id: str
) -> list[dict]:
    """Read all claims from Redis as dicts."""
    from app.services.verified_generation.verified_cache import get_verified_cache

    cache = get_verified_cache()
    await cache.connect()
    claims = await cache.get_verified_claims(tenant_id, session_id)
    return [c.to_dict() for c in claims]


async def _remove_claim_from_cache(
    tenant_id: str, session_id: str, claim_id: str
) -> None:
    """Remove a single claim from Redis by ID."""
    from app.services.verified_generation.verified_cache import get_verified_cache

    cache = get_verified_cache()
    await cache.connect()
    await cache.remove_claim(tenant_id, session_id, claim_id)


async def _update_claim_in_cache(
    tenant_id: str, session_id: str, claim_id: str, new_text: str
) -> None:
    """Update a claim's text in Redis and set status to 'corrected'."""
    from app.services.verified_generation.verified_cache import get_verified_cache

    cache = get_verified_cache()
    await cache.connect()
    await cache.update_claim_text(tenant_id, session_id, claim_id, new_text)
