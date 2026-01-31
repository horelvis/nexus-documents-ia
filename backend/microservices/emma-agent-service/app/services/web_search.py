"""
Web Search Client using DuckDuckGo.

Provides async web search capabilities for LangGraph agents
and verified generation evidence gathering.

Uses duckduckgo-search library (no API key required).
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# Singleton instance
_client: Optional["WebSearchClient"] = None


@dataclass
class WebSearchResult:
    """A single web search result."""
    title: str
    url: str
    snippet: str


class WebSearchClient:
    """
    Async web search client using DuckDuckGo.

    Gracefully returns empty results when disabled or on errors.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_results: int = 5,
        region: str = "es-es",
    ):
        self.enabled = enabled
        self.default_max_results = max_results
        self.region = region

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> List[WebSearchResult]:
        """
        Search the web using DuckDuckGo.

        Args:
            query: Search query string.
            max_results: Override default max results.

        Returns:
            List of WebSearchResult (empty if disabled or on error).
        """
        if not self.enabled:
            logger.debug("Web search disabled, returning empty results")
            return []

        if not query or not query.strip():
            return []

        limit = max_results or self.default_max_results

        try:
            from duckduckgo_search import DDGS

            # v8+ uses sync DDGS only (AsyncDDGS removed)
            # Run in thread to avoid blocking the event loop
            import asyncio
            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(
                None,
                lambda: DDGS().text(query, max_results=limit, region=self.region),
            )

            results = []
            for r in raw_results:
                results.append(WebSearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                ))

            logger.info(f"🌐 Web search: '{query[:60]}' → {len(results)} results")
            return results

        except ImportError:
            logger.warning("duckduckgo-search not installed, web search unavailable")
            return []
        except Exception as e:
            logger.error(f"Web search failed for '{query[:60]}': {e}")
            return []


def get_web_search_client() -> WebSearchClient:
    """Get or create the singleton WebSearchClient."""
    global _client
    if _client is None:
        _client = WebSearchClient(
            enabled=settings.web_search_enabled,
            max_results=settings.web_search_max_results,
            region=settings.web_search_region,
        )
    return _client
