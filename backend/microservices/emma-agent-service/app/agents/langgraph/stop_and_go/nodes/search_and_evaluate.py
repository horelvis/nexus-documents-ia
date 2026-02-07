"""
Search & Evaluate node — shared evidence search + strategy-specific evaluation.

This node:
1. Searches for evidence (Weaviate + uploads + web) — shared logic
2. Calls strategy.evaluate_item() — mode-specific evaluation
3. Routes accepted/rejected/corrected items via strategy callbacks
4. Collects source references for the final result

The _search_evidence() function is extracted from the identical code
previously duplicated in both services.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings
from app.agents.langgraph.stop_and_go.strategy import get_strategy

logger = logging.getLogger(__name__)


async def search_and_evaluate_node(state: dict) -> dict:
    """Search for evidence, evaluate item, route to accept/reject."""
    strategy = get_strategy(state["mode"])
    item = state.get("current_item")

    # If current_item is None (e.g., duplicate was skipped), pass through
    if item is None:
        return {}

    # Emit verification-started event
    verification_event = {
        "event_type": f"{state['mode']}_verification_started",
        "item_id": item.get("id"),
        "data": {"message": "Searching for supporting documents..."},
    }

    try:
        # Shared: search for evidence
        evidence = await _search_evidence(
            query_text=item.get("text", ""),
            tenant_id=state["tenant_id"],
            collections=state.get("collections", []),
            uploaded_texts=state.get("uploaded_texts", []),
            mode_config=state.get("mode_config", {}),
            jurisprudence_evidence=state.get("jurisprudence_evidence", []),
        )

        # Strategy-specific: evaluate item against evidence
        evaluation = await strategy.evaluate_item(item, evidence, state)
        status = evaluation.get("status", "rejected")

        events = [verification_event]
        all_items = list(state.get("all_extracted_items", []))
        all_items.append(item)

        updates: Dict[str, Any] = {"all_extracted_items": all_items}

        if status == "accepted":
            event_data = await strategy.on_accepted(item, evaluation, state)
            updates["items_accepted"] = state.get("items_accepted", 0) + 1
            events.append(event_data)
        elif status == "corrected":
            event_data = await strategy.on_accepted(item, evaluation, state)
            updates["items_corrected"] = state.get("items_corrected", 0) + 1
            events.append(event_data)
        else:
            event_data = await strategy.on_rejected(item, evaluation, state)
            updates["items_rejected"] = state.get("items_rejected", 0) + 1
            events.append(event_data)

        # Collect sources for final result
        sources_map = dict(state.get("sources_map", {}))
        for e in evidence:
            src_id = e.get("document_id", "")
            if src_id and src_id not in sources_map:
                source_entry = {
                    "id": src_id,
                    "title": e.get("document_title", ""),
                    "source": e.get("source", "internal"),
                    "url": e.get("url", ""),
                }
                # Include CENDOJ metadata for jurisprudence sources
                if e.get("source") == "jurisprudence":
                    source_entry.update({
                        "roj": e.get("roj", ""),
                        "ecli": e.get("ecli", ""),
                        "date": e.get("date", ""),
                        "resolution_type": e.get("resolution_type", ""),
                        "ponente": e.get("ponente", ""),
                    })
                sources_map[src_id] = source_entry
        updates["sources_map"] = sources_map
        updates["pending_events"] = events
        return updates

    except asyncio.TimeoutError:
        logger.warning(f"Verification timeout for item {item.get('id')}")
        return {
            "all_extracted_items": list(state.get("all_extracted_items", [])) + [item],
            "pending_events": [verification_event, {
                "event_type": f"{state['mode']}_verification_timeout",
                "item_id": item.get("id"),
                "data": {"message": "Verification timed out, skipping item"},
            }],
        }

    except Exception as e:
        import traceback
        logger.error(f"Verification failed: {e}\n{traceback.format_exc()}")
        return {
            "all_extracted_items": list(state.get("all_extracted_items", [])) + [item],
            "items_rejected": state.get("items_rejected", 0) + 1,
            "pending_events": [verification_event, {
                "event_type": "error",
                "item_id": item.get("id"),
                "data": {"error": f"Verification failed: {str(e)}"},
            }],
        }


async def _search_evidence(
    query_text: str,
    tenant_id: str,
    collections: List[str],
    uploaded_texts: List[Dict],
    mode_config: Dict[str, Any],
    jurisprudence_evidence: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    Unified evidence search: Weaviate -> uploads (RLM) -> jurisprudence -> web.

    This was previously duplicated between PredictiveAnalysisService._search_evidence
    and VerifiedDocumentService._verify_claim (Steps 1a + 1a-bis + 1b).

    Jurisprudence evidence (from CENDOJ) is cached in state during initialization
    and injected here to avoid repeated Docker container launches.
    """
    similarity_threshold = settings.predictive_similarity_threshold
    evidence: List[Dict] = []

    # --- Weaviate search ---
    sanitized_tenant = tenant_id.replace("-", "_")
    safe_tenant = ''.join(c for c in tenant_id if c.isalnum())[:32]
    candidate_collections = (
        [collections[0]] if collections
        else [
            f"Nouxcube_{sanitized_tenant}_documents",
            f"Nouxcube_{safe_tenant}_knowledge",
        ]
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for collection_name in candidate_collections:
                response = await client.post(
                    f"{settings.weaviate_service_url}/weaviate/collections/{collection_name}/search",
                    headers={
                        "Content-Type": "application/json",
                        "X-API-Key": settings.MICROSERVICES_API_KEY,
                    },
                    json={
                        "query": query_text,
                        "tenant_id": tenant_id,
                        "limit": 5,
                        "search_type": "hybrid",
                        "is_admin": True,
                    },
                )
                if response.status_code == 200:
                    results = response.json().get("results", [])
                    for r in results:
                        distance = r.get("distance", 1.0)
                        similarity = 1.0 - min(distance, 1.0)
                        if similarity >= similarity_threshold:
                            evidence.append({
                                "document_id": r.get("document_id", ""),
                                "document_title": r.get("title", ""),
                                "chunk_id": r.get("chunk_id"),
                                "text_excerpt": r.get("content", "")[:settings.predictive_evidence_excerpt_limit],
                                "similarity_score": round(similarity, 3),
                                "source": "internal",
                            })
                    if evidence:
                        break
    except Exception as e:
        logger.error(f"Weaviate evidence search failed: {e}")

    # --- Uploaded documents (RLM-powered filtering) ---
    if not evidence and uploaded_texts:
        try:
            from app.services.verified_generation.service import _rlm_filter_evidence
            evidence = await _rlm_filter_evidence(
                query_text, uploaded_texts, max_evidence=5
            )
        except Exception as e:
            logger.warning(f"RLM evidence filtering failed: {e}")

    # --- Jurisprudence (CENDOJ, cached from initialization) ---
    if jurisprudence_evidence and len(evidence) < 5:
        for jur in jurisprudence_evidence:
            evidence.append({
                "document_id": jur.get("document_id", ""),
                "document_title": jur.get("document_title", ""),
                "chunk_id": jur.get("chunk_id"),
                "text_excerpt": jur.get("text_excerpt", "")[:settings.predictive_evidence_excerpt_limit],
                "similarity_score": jur.get("similarity_score", 0.80),
                "source": "jurisprudence",
                "url": jur.get("url", ""),
                "roj": jur.get("roj", ""),
                "ecli": jur.get("ecli", ""),
                "date": jur.get("date", ""),
                "resolution_type": jur.get("resolution_type", ""),
                "ponente": jur.get("ponente", ""),
            })
        logger.info(f"Added {len(jurisprudence_evidence)} jurisprudence evidence items")

    # --- Web search (supplementary) ---
    verification_sources = mode_config.get("verification_sources", [])
    web_enabled = settings.web_search_enabled or "web" in verification_sources
    if web_enabled and len(evidence) < 5:
        try:
            from app.services.web_search import get_web_search_client
            web_client = get_web_search_client()
            web_results = await asyncio.wait_for(
                web_client.search(query_text, max_results=3),
                timeout=10.0,
            )
            for wr in web_results:
                url_hash = hashlib.md5(wr.url.encode()).hexdigest()[:12]
                evidence.append({
                    "document_id": f"web:{url_hash}",
                    "document_title": wr.title,
                    "chunk_id": None,
                    "text_excerpt": wr.snippet[:settings.predictive_evidence_excerpt_limit],
                    "similarity_score": 0.65,
                    "source": "web",
                    "url": wr.url,
                })
        except asyncio.TimeoutError:
            logger.warning("Web search timed out")
        except Exception as e:
            logger.warning(f"Web search failed (non-fatal): {e}")

    logger.info(f"Found {len(evidence)} evidence items for query: {query_text[:60]}...")
    return evidence
