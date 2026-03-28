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


@dataclass
class StructuralQueryResult:
    """Result from SIL structural query"""
    route: str  # GRAPH_ONLY, VECTOR_ONLY, HYBRID
    data: dict[str, Any]
    context: str
    confidence: float


class WeaviateClient(BaseHTTPClient):
    """
    HTTP client for weaviate-service.

    Provides async methods for:
    - Vector search (semantic similarity)
    - RAG pipeline execution
    - Document content retrieval
    - Structural queries (knowledge graph)

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
        filters: Optional[dict[str, Any]] = None,
        person_filter: Optional[str] = None,
        domain_filter: Optional[str] = None,
        semantic_type_filter: Optional[str] = None,
        min_quality: Optional[float] = None,
        folder_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Hybrid search combining vector and keyword search.

        Args:
            tenant_id: Tenant identifier
            query: Search query text
            limit: Maximum results
            alpha: Balance between vector (1.0) and keyword (0.0)
            filters: Optional metadata filters
            person_filter: Filter by associated person name
            domain_filter: Filter by business domain
            semantic_type_filter: Filter by semantic document type
            min_quality: Minimum quality score threshold
            folder_filter: Filter by folder path

        Returns:
            List of SearchResult
        """
        payload: dict[str, Any] = {
            "query": query,
            "tenant_id": tenant_id,
            "limit": limit,
            "alpha": alpha,
        }
        if filters:
            payload["filters"] = filters
        if person_filter:
            payload["person_filter"] = person_filter
        if domain_filter:
            payload["domain_filter"] = domain_filter
        if semantic_type_filter:
            payload["semantic_type_filter"] = semantic_type_filter
        if min_quality is not None:
            payload["min_quality"] = min_quality
        if folder_filter:
            payload["filters"] = payload.get("filters") or {}
            payload["filters"]["folder_path"] = folder_filter
        if date_from:
            payload["date_from"] = date_from
        if date_to:
            payload["date_to"] = date_to

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
                        "domain": item.get("domain", ""),
                        "semantic_type": item.get("semantic_type", ""),
                        "quality_score": item.get("quality_score"),
                        "associated_person": item.get("associated_person", ""),
                        "chunk_index": item.get("chunk_index"),
                        "page_number": item.get("page_number"),
                        "document_id": item.get("document_id", ""),
                        **item.get("metadata", {})
                    }
                ))
            return results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    # =========================================================================
    # Public Knowledge Search
    # =========================================================================

    async def search_public_knowledge(
        self,
        query: str,
        limit: int = 5,
        domain: str = "",
        boe_ids: list[str] | None = None,
    ) -> list[SearchResult]:
        """
        Search public knowledge base (BOE, legislation).

        Uses the public-knowledge service endpoint which supports
        hybrid search over indexed legislation with filtering by
        topics, categories, jurisdictions, and legal status.

        Args:
            query: Search query text
            limit: Maximum results to return
            domain: Optional domain/topic filter (e.g., "labor", "fiscal")
            boe_ids: Optional list of BOE identifiers to filter by (e.g., ["BOE-A-2006-7899"])

        Returns:
            List of SearchResult from public knowledge
        """
        payload: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "search_type": "hybrid",
            "current_version_only": True,
        }
        # If specific BOE IDs are provided, add them as keywords to the query
        # This ensures the search prioritizes documents with those identifiers
        if boe_ids:
            boe_keywords = " ".join(boe_ids)
            payload["query"] = f"{query} {boe_keywords}"
        elif domain:
            payload["topics"] = [domain]

        try:
            response = await self.post_json(
                "/public-knowledge/search",
                json=payload,
                headers=self._headers(),
            )

            results = []
            for item in response.get("results", []):
                results.append(SearchResult(
                    document_id=item.get("id", ""),
                    chunk_id=None,
                    content=item.get("content", ""),
                    score=item.get("similarity_score") or 0.0,
                    metadata={
                        "title": item.get("title", ""),
                        "source": "public_knowledge",
                        "category": item.get("category", ""),
                        "legal_reference": item.get("legal_reference", ""),
                        "legal_status": item.get("legal_status", ""),
                        "jurisdiction": item.get("jurisdiction", ""),
                        "boe_id": item.get("boe_id", ""),
                        "topics": item.get("topics", []),
                    },
                ))
            return results

        except Exception as e:
            logger.warning(f"Public knowledge search failed: {e}")
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
    # Structural Queries (Knowledge Graph)
    # =========================================================================

    async def structural_query(
        self,
        tenant_id: str,
        query: str,
        max_results: int = 20
    ) -> StructuralQueryResult:
        """
        Execute structural query via weaviate-service.

        For structural queries (count, list, filter), this endpoint
        attempts to use the knowledge graph when available,
        falling back to hybrid vector search.

        Structural queries are queries like:
        - "How many contracts does ACME have?"
        - "Show documents from last month"
        - "List all invoices over $10,000"

        The routing determines:
        - GRAPH_ONLY: Pure structural (counting, filtering)
        - VECTOR_ONLY: Semantic content search
        - HYBRID: Combination of both

        Args:
            tenant_id: Tenant identifier
            query: Natural language query
            max_results: Maximum results

        Returns:
            StructuralQueryResult with route and data
        """
        payload = {
            "tenant_id": tenant_id,
            "query": query,
            "max_results": max_results
        }

        try:
            # Call weaviate-service structural endpoint
            response = await self.post_json(
                "/weaviate/structural/query",
                json=payload,
                headers=self._headers()
            )

            route = response.get("route", "VECTOR_ONLY")
            confidence = response.get("confidence", 0.5)
            context = response.get("context", "")
            data = response.get("data", {})

            # Include document results if present
            if "documents" in response:
                data["documents"] = response["documents"]
            if "count" in response:
                data["count"] = response["count"]

            return StructuralQueryResult(
                route=route,
                data=data,
                context=context,
                confidence=confidence
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Structural query failed: {error_msg}")

            # Return error result - let the caller handle the fallback
            return StructuralQueryResult(
                route="ERROR",
                data={"error": error_msg},
                context="",
                confidence=0.0
            )

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

        Uses knowledge graph traversal for:
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
                f"/weaviate/collections/{tenant_id}/stats",
                headers=self._headers()
            )
        except Exception as e:
            logger.warning(f"Get tenant stats failed: {e}")
            return {"document_count": 0, "error": str(e)}

    async def count_by_semantic_type(
        self, tenant_id: str, semantic_type: str | None = None
    ) -> dict[str, Any]:
        """Count documents by semantic_type via Weaviate aggregate."""
        try:
            params = {}
            if semantic_type:
                params["semantic_type"] = semantic_type
            return await self.get_json(
                f"/weaviate/tenants/{tenant_id}/count-by-type",
                params=params,
                headers=self._headers(),
            )
        except Exception as e:
            logger.warning(f"count_by_semantic_type failed: {e}")
            return {"count": 0, "error": str(e)}

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
