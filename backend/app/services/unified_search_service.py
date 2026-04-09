"""
Unified Search Service for NouxCubeIA.

This service provides a unified interface for document search that can use
either Elasticsearch (when enabled) or Weaviate's native hybrid search
(BM25 + vector) when Elasticsearch is disabled.

For on-premise Emma-centric deployments, Elasticsearch is disabled and
Weaviate handles all search operations natively.

Usage:
    from app.services.unified_search_service import UnifiedSearchService

    service = UnifiedSearchService()
    results = await service.search(query="...", search_type="hybrid")
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

from app.core.features import Feature, FeatureFlags
from app.services.weaviate_client import weaviate_client

logger = logging.getLogger(__name__)


@dataclass
class SearchUserContext:
    """User context for ACL-based search filtering."""
    user_id: str
    role_ids: List[str]
    is_admin: bool = False


@dataclass
class SearchResult:
    """Normalized search result from any backend."""
    document_id: str
    title: str
    filename: str
    description: Optional[str]
    content_snippet: Optional[str]
    score: float
    file_type: Optional[str]
    file_size: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    tags: List[str]
    matches: List[Dict[str, Any]]
    source: str  # "weaviate" or "elasticsearch"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "document": {
                "id": self.document_id,
                "title": self.title,
                "filename": self.filename,
                "description": self.description or "",
                "file_type": self.file_type or "",
                "file_size": self.file_size or 0,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None,
                "tags": self.tags,
            },
            "score": self.score,
            "content_snippet": self.content_snippet,
            "matches": self.matches,
            "source": self.source,
        }


class UnifiedSearchService:
    """
    Unified search service that abstracts the search backend.

    Uses Elasticsearch when Feature.ELASTICSEARCH_SEARCH is enabled,
    otherwise uses Weaviate's native hybrid search (BM25 + vector).
    """

    def __init__(self):
        self._use_elasticsearch = FeatureFlags.is_enabled(
            Feature.ELASTICSEARCH_SEARCH,
        )

        if self._use_elasticsearch:
            logger.debug("UnifiedSearchService using Elasticsearch")
        else:
            logger.debug("UnifiedSearchService using Weaviate hybrid")

    async def search(
        self,
        query: str,
        limit: int = 10,
        search_type: str = "hybrid",
        filters: Optional[Dict[str, Any]] = None,
        user_context: Optional[SearchUserContext] = None,
        alpha: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search documents using the configured backend.

        Args:
            query: Search query text
            limit: Maximum number of results
            search_type: Type of search ("hybrid", "semantic", "keyword")
            filters: Additional filters (tags, dates, etc.)
            user_context: User context for ACL filtering
            alpha: Balance between semantic (1.0) and keyword (0.0) for hybrid search

        Returns:
            List of search results as dictionaries
        """
        if self._use_elasticsearch:
            return await self._search_elasticsearch(
                query=query,
                limit=limit,
                search_type=search_type,
                filters=filters,
                user_context=user_context,
            )
        else:
            return await self._search_weaviate(
                query=query,
                limit=limit,
                search_type=search_type,
                filters=filters,
                user_context=user_context,
                alpha=alpha,
            )

    async def _search_elasticsearch(
        self,
        query: str,
        limit: int,
        search_type: str,
        filters: Optional[Dict[str, Any]],
        user_context: Optional[SearchUserContext],
    ) -> List[Dict[str, Any]]:
        """
        Search using Elasticsearch microservice.

        This is the original search path when ES is enabled.
        """
        try:
            from app.services.elasticsearch_client import (
                elasticsearch_client,
                SearchUserContext as ESUserContext,
            )

            # Convert user context if provided
            es_user_context = None
            if user_context:
                es_user_context = ESUserContext(
                    user_id=user_context.user_id,
                    role_ids=user_context.role_ids,
                    is_admin=user_context.is_admin,
                )

            results = await elasticsearch_client.hybrid_search(
                query=query,
                limit=limit,
                filters=filters or {},
                user_context=es_user_context,
            )

            # Results are already in the expected format from ES
            return results if isinstance(results, list) else []

        except Exception as e:
            logger.error(f"Elasticsearch search failed: {e}")
            # Fallback to Weaviate if ES fails
            logger.info("Falling back to Weaviate search")
            return await self._search_weaviate(
                query=query,
                limit=limit,
                search_type=search_type,
                filters=filters,
                user_context=user_context,
            )

    async def _search_weaviate(
        self,
        query: str,
        limit: int,
        search_type: str,
        filters: Optional[Dict[str, Any]],
        user_context: Optional[SearchUserContext],
        alpha: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """
        Search using Weaviate's native hybrid search.

        Weaviate v4+ supports hybrid search combining:
        - BM25 (keyword/lexical search)
        - Vector similarity (semantic search)

        The alpha parameter controls the balance:
        - alpha=0.0: Pure BM25 (keyword)
        - alpha=0.5: Balanced hybrid
        - alpha=1.0: Pure vector (semantic)
        """
        try:
            # Determine alpha based on search_type
            if search_type == "keyword":
                search_alpha = 0.0
            elif search_type == "semantic":
                search_alpha = 1.0
            else:  # hybrid
                search_alpha = alpha

            # Build search request for Weaviate service
            search_request = {
                "query": query,
                "limit": limit,
                "search_type": "hybrid",
                "alpha": search_alpha,
            }

            # Add filters if provided
            if filters:
                if filters.get("tags"):
                    search_request["tags"] = filters["tags"]
                if filters.get("date_from"):
                    search_request["date_from"] = filters["date_from"]
                if filters.get("date_to"):
                    search_request["date_to"] = filters["date_to"]
                if filters.get("file_types"):
                    search_request["file_types"] = filters["file_types"]

            # Add ACL context if provided
            if user_context:
                search_request["user_id"] = user_context.user_id
                search_request["role_ids"] = user_context.role_ids
                search_request["is_admin"] = user_context.is_admin

            # Get collection name (single-tenant: fixed)
            collection_name = self._get_collection_name()

            # Execute search via Weaviate client
            response = await weaviate_client.search_documents(
                collection_name=collection_name,
                search_request=search_request,
            )

            # Normalize results to expected format
            results = response.get("results", [])
            return self._normalize_weaviate_results(results)

        except Exception as e:
            logger.error(f"Weaviate search failed: {e}")
            return []

    def _get_collection_name(self) -> str:
        """Get the Weaviate collection name (single-tenant default)."""
        return "documents_default"

    def _normalize_weaviate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Normalize Weaviate results to match the expected API format.

        The format matches what Elasticsearch returns for API compatibility.
        """
        normalized = []

        for item in results:
            try:
                # Extract document data from Weaviate result
                properties = item.get("properties", item)

                normalized.append({
                    "document": {
                        "id": properties.get("document_id") or item.get("id", ""),
                        "title": properties.get("title", ""),
                        "filename": properties.get("filename", ""),
                        "description": properties.get("description", ""),
                        "file_type": properties.get("file_type", ""),
                        "file_size": properties.get("file_size", 0),
                        "mime_type": properties.get("mime_type", ""),
                        "created_at": properties.get("created_at"),
                        "updated_at": properties.get("updated_at"),
                        "indexed": "true",
                        "tags": properties.get("tags", []),
                    },
                    "score": item.get("score", item.get("_additional", {}).get("score", 0.0)),
                    "content_snippet": properties.get("content", "")[:500] if properties.get("content") else "",
                    "matches": [],
                    "source": "weaviate",
                })
            except Exception as e:
                logger.warning(f"Error normalizing Weaviate result: {e}")
                continue

        return normalized

    async def suggest_search_type(self, query: str) -> str:
        """
        Suggest the optimal search type based on query characteristics.

        Args:
            query: The search query to analyze

        Returns:
            Suggested search type: "semantic", "hybrid", or "keyword"
        """
        # Short exact terms → keyword
        if len(query.split()) <= 2 and not any(c in query for c in "?¿"):
            return "keyword"

        # Questions or natural language → semantic
        question_indicators = ["?", "¿", "cómo", "qué", "cuál", "dónde", "quién", "why", "what", "how", "where", "who"]
        if any(indicator in query.lower() for indicator in question_indicators):
            return "semantic"

        # Default → hybrid
        return "hybrid"

    async def get_search_stats(self) -> Dict[str, Any]:
        """
        Get search system statistics.

        Returns:
            Dictionary with search backend info and stats
        """
        backend = "elasticsearch" if self._use_elasticsearch else "weaviate"

        stats = {
            "backend": backend,
            "features": {
                "hybrid_search": True,
                "semantic_search": True,
                "keyword_search": True,
                "acl_filtering": True,
            },
        }

        if backend == "weaviate":
            stats["capabilities"] = {
                "bm25": True,
                "vector_similarity": True,
                "hybrid_alpha_control": True,
            }

        return stats


# Convenience function for quick searches
async def unified_search(
    query: str,
    limit: int = 10,
    search_type: str = "hybrid",
    filters: Optional[Dict[str, Any]] = None,
    user_context: Optional[SearchUserContext] = None,
) -> List[Dict[str, Any]]:
    """
    Quick search function without instantiating the service.

    Usage:
        from app.services.unified_search_service import unified_search

        results = await unified_search(
            query="contract terms",
            search_type="hybrid"
        )
    """
    service = UnifiedSearchService()
    return await service.search(
        query=query,
        limit=limit,
        search_type=search_type,
        filters=filters,
        user_context=user_context,
    )
