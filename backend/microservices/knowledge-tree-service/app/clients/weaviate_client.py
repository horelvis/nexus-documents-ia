"""
HTTP client for weaviate-service.

This client replaces direct service calls, enabling emma-agent-service
to communicate with weaviate-service over HTTP for:
- Vector search (semantic similarity)
- RAG pipeline queries
- Document content retrieval
- Structural/graph queries (SIL)
"""
import logging
from typing import Any, Optional
from dataclasses import dataclass

from .base import BaseHTTPClient, HTTPClientConfig
from app.core.config import settings

logger = logging.getLogger(__name__)


# Singleton client instance
_weaviate_client: Optional["WeaviateClient"] = None


@dataclass
class SearchResult:
    """Result from vector search"""
    document_id: str
    chunk_id: Optional[str]
    content: str
    score: float
    metadata: dict[str, Any]


@dataclass
class RAGResult:
    """Result from RAG pipeline"""
    answer: str
    sources: list[dict[str, Any]]
    confidence: float
    metadata: dict[str, Any]



class WeaviateClient(BaseHTTPClient):
    """
    HTTP client for weaviate-service.

    Provides async methods for:
    - Vector search (semantic similarity)
    - RAG pipeline execution
    - Document content retrieval
    - Structural queries (FalkorDB graph)

    Example:
        client = WeaviateClient()
        results = await client.search_documents(
            tenant_id="tenant-123",
            query="contratos laborales",
            limit=10
        )
    """

    # Collection prefix matching weaviate-service configuration
    COLLECTION_PREFIX = "Nouxcube_"

    def __init__(self):
        config = HTTPClientConfig(
            base_url=settings.weaviate_service_url,
            timeout=settings.weaviate_service_timeout,
            max_connections=100,
            max_keepalive_connections=20,
            retry_attempts=3,
            retry_delay=1.0
        )
        super().__init__(config)
        self._api_key = settings.MICROSERVICES_API_KEY

    def _headers(self) -> dict[str, str]:
        """Get headers with API key"""
        return {
            "X-API-Key": self._api_key,
            "Content-Type": "application/json"
        }

    def _get_collection_name(self, tenant_id: str, collection_type: str = "documents") -> str:
        """
        Generate tenant-specific collection name for Weaviate.

        Matches the naming convention in weaviate-service:
        Nouxcube_{tenant_id_with_underscores}_{collection_type}

        Example: Nouxcube_00000000_0000_0000_0000_000000000001_documents
        """
        tenant_normalized = tenant_id.replace("-", "_")
        return f"{self.COLLECTION_PREFIX}{tenant_normalized}_{collection_type}"

    # =========================================================================
    # Vector Search
    # =========================================================================

    async def search_documents(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        filters: Optional[dict[str, Any]] = None,
        include_content: bool = True
    ) -> list[SearchResult]:
        """
        Search documents using vector similarity.

        Args:
            tenant_id: Tenant identifier
            query: Search query text
            limit: Maximum results to return
            filters: Optional metadata filters
            include_content: Include document content in results

        Returns:
            List of SearchResult with document matches
        """
        # Generate tenant-specific collection name
        collection_name = self._get_collection_name(tenant_id, "documents")

        payload = {
            "query": query,
            "tenant_id": tenant_id,
            "limit": limit,
            "include_content": include_content
        }
        if filters:
            payload["filters"] = filters

        try:
            response = await self.post_json(
                f"/weaviate/collections/{collection_name}/search",
                json=payload,
                headers=self._headers()
            )

            results = []
            for item in response.get("results", []):
                results.append(SearchResult(
                    document_id=item.get("id", item.get("document_id", "")),
                    chunk_id=item.get("chunk_id"),
                    content=item.get("content", ""),
                    score=item.get("similarity_score", item.get("score", 0.0)),
                    metadata={
                        "title": item.get("title", ""),
                        "document_type": item.get("document_type", ""),
                        "folder_path": item.get("folder_path", ""),
                        **item.get("metadata", {})
                    }
                ))
            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def hybrid_search(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        alpha: float = 0.5,
        filters: Optional[dict[str, Any]] = None
    ) -> list[SearchResult]:
        """
        Hybrid search combining vector and keyword search.

        Args:
            tenant_id: Tenant identifier
            query: Search query text
            limit: Maximum results
            alpha: Balance between vector (1.0) and keyword (0.0)
            filters: Optional metadata filters

        Returns:
            List of SearchResult
        """
        payload = {
            "query": query,
            "tenant_id": tenant_id,
            "limit": limit,
            "alpha": alpha
        }
        if filters:
            payload["filters"] = filters

        try:
            # Use the global hybrid search endpoint
            response = await self.post_json(
                "/weaviate/collections/documents/hybrid",
                json=payload,
                headers=self._headers()
            )

            results = []
            for item in response.get("results", []):
                results.append(SearchResult(
                    document_id=item.get("id", item.get("document_id", "")),
                    chunk_id=item.get("chunk_id"),
                    content=item.get("content", ""),
                    score=item.get("similarity_score", item.get("score", 0.0)),
                    metadata={
                        "title": item.get("title", ""),
                        "document_type": item.get("document_type", ""),
                        "folder_path": item.get("folder_path", ""),
                        **item.get("metadata", {})
                    }
                ))
            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    # =========================================================================
    # RAG Pipeline
    # =========================================================================

    async def rag_query(
        self,
        tenant_id: str,
        query: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        max_tokens: int = 4096,
        include_sources: bool = True
    ) -> RAGResult:
        """
        Execute RAG pipeline query.

        This calls the full 7-layer RAG pipeline in weaviate-service:
        1. Query understanding
        2. Retrieval
        3. Reranking
        4. Context assembly
        5. Generation
        6. Validation
        7. Response formatting

        Args:
            tenant_id: Tenant identifier
            query: User query
            user_id: Optional user ID for personalization
            conversation_id: Optional conversation ID for context
            max_tokens: Maximum tokens for response
            include_sources: Include source documents

        Returns:
            RAGResult with answer and sources
        """
        payload = {
            "query": query,
            "tenant_id": tenant_id,
            "max_tokens": max_tokens,
            "include_sources": include_sources
        }
        if user_id:
            payload["user_id"] = user_id
        if conversation_id:
            payload["conversation_id"] = conversation_id

        try:
            response = await self.post_json(
                "/weaviate/rag/query",
                json=payload,
                headers=self._headers()
            )

            return RAGResult(
                answer=response.get("answer", ""),
                sources=response.get("sources", []),
                confidence=response.get("confidence", 0.0),
                metadata=response.get("metadata", {})
            )

        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            return RAGResult(
                answer=f"Error executing RAG query: {e}",
                sources=[],
                confidence=0.0,
                metadata={"error": str(e)}
            )

    # =========================================================================
    # Document Content
    # =========================================================================

    async def get_document_content(
        self,
        tenant_id: str,
        document_id: str,
        include_chunks: bool = False
    ) -> dict[str, Any]:
        """
        Get document content by ID.

        Args:
            tenant_id: Tenant identifier
            document_id: Document UUID
            include_chunks: Include individual chunks

        Returns:
            Document content and metadata
        """
        params = {"include_chunks": include_chunks}

        try:
            return await self.get_json(
                f"/weaviate/documents/{tenant_id}/{document_id}/content",
                params=params,
                headers=self._headers()
            )
        except Exception as e:
            logger.error(f"Get document content failed: {e}")
            return {"error": str(e)}

    async def get_document_chunks(
        self,
        tenant_id: str,
        document_id: str,
        offset: int = 0,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get document chunks.

        Args:
            tenant_id: Tenant identifier
            document_id: Document UUID
            offset: Pagination offset
            limit: Maximum chunks to return

        Returns:
            List of chunk dictionaries
        """
        params = {"offset": offset, "limit": limit}

        try:
            response = await self.get_json(
                f"/weaviate/documents/{tenant_id}/{document_id}/chunks",
                params=params,
                headers=self._headers()
            )
            return response.get("chunks", [])
        except Exception as e:
            logger.error(f"Get document chunks failed: {e}")
            return []

    # =========================================================================
    # Knowledge Graph
    # =========================================================================

    async def get_related_entities(
        self,
        tenant_id: str,
        entity_id: str,
        relationship_types: Optional[list[str]] = None,
        depth: int = 1,
        limit: int = 20
    ) -> list[dict[str, Any]]:
        """
        Get entities related to a given entity.

        Uses FalkorDB graph traversal for:
        - Finding related documents
        - Entity relationship exploration
        - Knowledge graph navigation

        Args:
            tenant_id: Tenant identifier
            entity_id: Starting entity ID
            relationship_types: Filter by relationship types
            depth: Traversal depth
            limit: Maximum entities

        Returns:
            List of related entities with relationships
        """
        payload = {
            "tenant_id": tenant_id,
            "entity_id": entity_id,
            "depth": depth,
            "limit": limit
        }
        if relationship_types:
            payload["relationship_types"] = relationship_types

        try:
            response = await self.post_json(
                "/weaviate/knowledge/related",
                json=payload,
                headers=self._headers()
            )
            return response.get("entities", [])
        except Exception as e:
            logger.error(f"Get related entities failed: {e}")
            return []

    # =========================================================================
    # Health & Status
    # =========================================================================

    async def health_check(self) -> dict[str, Any]:
        """Check weaviate-service health"""
        try:
            return await self.get_json("/health", headers=self._headers())
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    async def get_collection_stats(
        self,
        tenant_id: str
    ) -> dict[str, Any]:
        """Get collection statistics for tenant"""
        try:
            return await self.get_json(
                f"/weaviate/collections/{tenant_id}/stats",
                headers=self._headers()
            )
        except Exception as e:
            logger.error(f"Get collection stats failed: {e}")
            return {"error": str(e)}

    async def get_structural_summary(
        self,
        tenant_id: str,
        include_entities: bool = True,
        include_relationships: bool = False,
    ) -> dict[str, Any]:
        """
        Get structural summary for a tenant.

        Returns learned terminology and document structure information.
        """
        payload = {
            "tenant_id": tenant_id,
            "include_entities": include_entities,
            "include_relationships": include_relationships,
        }
        try:
            return await self.post_json(
                "/weaviate/structural/summary",
                json=payload,
                headers=self._headers()
            )
        except Exception as e:
            logger.warning(f"Get structural summary failed: {e}")
            return {
                "summary": "",
            }

    async def get_tenant_stats(self, tenant_id: str) -> dict[str, Any]:
        """Get tenant statistics including document count."""
        try:
            return await self.get_json(
                f"/weaviate/tenants/{tenant_id}/stats",
                headers=self._headers()
            )
        except Exception as e:
            logger.warning(f"Get tenant stats failed: {e}")
            return {"document_count": 0, "error": str(e)}

    async def get_tenant_schema(self, tenant_id: str) -> dict[str, Any]:
        """Get schema information for tenant's collections."""
        try:
            return await self.get_json(
                f"/weaviate/tenants/{tenant_id}/schema",
                headers=self._headers()
            )
        except Exception as e:
            logger.warning(f"Get tenant schema failed: {e}")
            return {"collections": [], "properties": {}}


def get_weaviate_client() -> WeaviateClient:
    """
    Get singleton WeaviateClient instance.

    Returns the same client instance across calls for connection reuse.
    """
    global _weaviate_client
    if _weaviate_client is None:
        _weaviate_client = WeaviateClient()
    return _weaviate_client


async def close_weaviate_client():
    """Close the singleton client"""
    global _weaviate_client
    if _weaviate_client is not None:
        await _weaviate_client.close()
        _weaviate_client = None
