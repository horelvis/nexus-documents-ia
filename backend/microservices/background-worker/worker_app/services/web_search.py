"""
Web Search for Background Worker (Verified Generation).

Simplified DuckDuckGo client for claim verification evidence gathering.
Returns evidence in the same format as Weaviate search results.
"""

import hashlib
import logging
import os
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))
WEB_SEARCH_REGION = os.getenv("WEB_SEARCH_REGION", "es-es")


async def search_web_evidence(
    claim_text: str,
    max_results: int = WEB_SEARCH_MAX_RESULTS,
) -> List[Dict[str, Any]]:
    """
    Search web for evidence supporting or refuting a claim.

    Returns evidence in the same format as Weaviate search results
    so it can be merged seamlessly.

    Args:
        claim_text: The claim to find evidence for.
        max_results: Maximum number of web results.

    Returns:
        List of evidence dicts compatible with Weaviate evidence format.
    """
    if not WEB_SEARCH_ENABLED:
        return []

    if not claim_text or not claim_text.strip():
        return []

    try:
        from duckduckgo_search import AsyncDDGS

        async with AsyncDDGS() as ddgs:
            raw_results = await ddgs.atext(
                claim_text,
                max_results=max_results,
                region=WEB_SEARCH_REGION,
            )

        evidence = []
        for r in raw_results:
            url = r.get("href", r.get("link", ""))
            url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
            evidence.append({
                "document_id": f"web:{url_hash}",
                "document_title": r.get("title", ""),
                "chunk_id": None,
                "text_excerpt": r.get("body", r.get("snippet", ""))[:500],
                "similarity_score": 0.70,  # Fixed score (no embedding comparison)
                "source": "web",
                "url": url,
            })

        logger.info(f"🌐 Web evidence search: '{claim_text[:60]}' → {len(evidence)} results")
        return evidence

    except ImportError:
        logger.warning("duckduckgo-search not installed, web evidence unavailable")
        return []
    except Exception as e:
        logger.error(f"Web evidence search failed: {e}")
        return []
