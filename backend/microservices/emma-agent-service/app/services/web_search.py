"""
Web Search Client with Tavily (primary) and DuckDuckGo (fallback).

Provides async web search capabilities for LangGraph agents
and verified generation evidence gathering.

Strategy:
1. If TAVILY_API_KEY is set → Use Tavily (optimized for LLMs/RAG)
2. Else → Fall back to DuckDuckGo (no API key, but lower quality)
"""

import logging
from abc import ABC, abstractmethod
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
    # Extended fields for Tavily
    content: Optional[str] = None  # Full extracted content (Tavily only)
    score: Optional[float] = None  # Relevance score (Tavily only)


class BaseSearchProvider(ABC):
    """Abstract base for search providers."""

    @abstractmethod
    async def search(self, query: str, max_results: int) -> List[WebSearchResult]:
        """Execute search and return results."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass


class TavilySearchProvider(BaseSearchProvider):
    """
    Tavily search provider - optimized for LLM/RAG use cases.

    Features:
    - Extracts relevant content automatically
    - Returns relevance scores
    - Designed specifically for AI agents
    """

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None

    @property
    def name(self) -> str:
        return "Tavily"

    def _get_client(self):
        """Lazy initialization of Tavily client."""
        if self._client is None:
            from tavily import TavilyClient
            self._client = TavilyClient(api_key=self.api_key)
        return self._client

    async def search(self, query: str, max_results: int) -> List[WebSearchResult]:
        """Search using Tavily API."""
        import asyncio

        try:
            client = self._get_client()

            # Tavily is sync, run in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    max_results=max_results,
                    include_answer=False,  # We'll use our own LLM
                    include_raw_content=False,  # Snippets are enough
                    search_depth="basic",  # "basic" is faster, "advanced" for deeper
                ),
            )

            results = []
            for r in response.get("results", []):
                results.append(WebSearchResult(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", "")[:500],  # Tavily returns longer content
                    content=r.get("content"),
                    score=r.get("score"),
                ))

            logger.info(f"🔍 Tavily search: '{query[:50]}' → {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            raise  # Let caller handle fallback


class DuckDuckGoSearchProvider(BaseSearchProvider):
    """
    DuckDuckGo search provider - free, no API key required.

    Used as fallback when Tavily is not configured.
    """

    def __init__(self, region: str = "es-es"):
        self.region = region

    @property
    def name(self) -> str:
        return "DuckDuckGo"

    async def search(self, query: str, max_results: int) -> List[WebSearchResult]:
        """Search using DuckDuckGo."""
        import asyncio

        try:
            from duckduckgo_search import DDGS

            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(
                None,
                lambda: DDGS().text(query, max_results=max_results, region=self.region),
            )

            results = []
            for r in raw_results:
                results.append(WebSearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("link", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                ))

            logger.info(f"🦆 DuckDuckGo search: '{query[:50]}' → {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            raise


class WebSearchClient:
    """
    Unified web search client with provider fallback.

    Priority:
    1. Tavily (if API key configured) - best for LLM/RAG
    2. DuckDuckGo (fallback) - free but lower quality
    """

    def __init__(
        self,
        enabled: bool = True,
        max_results: int = 5,
        region: str = "es-es",
        tavily_api_key: Optional[str] = None,
    ):
        self.enabled = enabled
        self.default_max_results = max_results
        self.region = region

        # Initialize providers based on configuration
        self.providers: List[BaseSearchProvider] = []

        if tavily_api_key:
            try:
                self.providers.append(TavilySearchProvider(api_key=tavily_api_key))
                logger.info("✅ Tavily search provider configured (primary)")
            except Exception as e:
                logger.warning(f"Failed to initialize Tavily: {e}")

        # DuckDuckGo as fallback (always available)
        self.providers.append(DuckDuckGoSearchProvider(region=region))
        logger.info(f"🔍 Web search initialized with {len(self.providers)} provider(s)")

    async def search(
        self,
        query: str,
        max_results: Optional[int] = None,
    ) -> List[WebSearchResult]:
        """
        Search the web using available providers with fallback.

        Args:
            query: Search query string.
            max_results: Override default max results.

        Returns:
            List of WebSearchResult (empty if disabled or all providers fail).
        """
        if not self.enabled:
            logger.debug("Web search disabled, returning empty results")
            return []

        if not query or not query.strip():
            return []

        limit = max_results or self.default_max_results

        # Try each provider in order (Tavily first, then DuckDuckGo)
        for provider in self.providers:
            try:
                results = await provider.search(query, limit)
                if results:
                    return results
                logger.warning(f"{provider.name} returned no results, trying next provider")
            except Exception as e:
                logger.warning(f"{provider.name} failed: {e}, trying next provider")
                continue

        logger.error(f"All search providers failed for query: '{query[:60]}'")
        return []

    @property
    def active_provider(self) -> str:
        """Return the name of the primary (first) provider."""
        return self.providers[0].name if self.providers else "None"


def get_web_search_client() -> WebSearchClient:
    """Get or create the singleton WebSearchClient."""
    global _client
    if _client is None:
        _client = WebSearchClient(
            enabled=settings.web_search_enabled,
            max_results=settings.web_search_max_results,
            region=settings.web_search_region,
            tavily_api_key=settings.tavily_api_key or None,
        )
    return _client
