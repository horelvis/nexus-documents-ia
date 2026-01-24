"""Client for Weaviate microservice"""
import logging
from typing import List, Dict, Any, Optional, AsyncGenerator
from contextlib import asynccontextmanager

import httpx

from app.core.config import settings
from app.clients.base import BaseHTTPClient
from app.clients.exceptions import HTTPClientError

logger = logging.getLogger(__name__)


class WeaviateClient(BaseHTTPClient):
    """Client for communicating with Weaviate microservice"""
    
    def __init__(self):
        base_url = getattr(settings, "WEAVIATE_SERVICE_URL", "http://weaviate-service:8007").rstrip("/")
        super().__init__(
            service_name="weaviate",
            base_url=base_url,
            timeout_type="ai",
        )
        logger.info("WeaviateClient initialized | base_url=%s", base_url)

    @staticmethod
    def _extract_context_headers(payload: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
        tenant_id = None
        user_id = None
        request_id = None
        if isinstance(payload, dict):
            tenant_id = payload.get("tenant_id")
            user_id = payload.get("user_id")
            request_id = payload.get("request_id") or payload.get("requestId")
        return {
            "tenant_id": str(tenant_id) if tenant_id else None,
            "user_id": str(user_id) if user_id else None,
            "request_id": str(request_id) if request_id else None,
        }
        
    async def health_check(self) -> Dict[str, Any]:
        """Check Weaviate service health"""
        try:
            logger.debug("Checking Weaviate health | base_url=%s", self.base_url)
            return await self.get_json("/health")
        except HTTPClientError as exc:
            logger.exception("❌ Weaviate health check failed | base_url=%s error=%s", self.base_url, exc)
            return {"status": "unhealthy", "error": exc.message}
        except Exception as exc:
            logger.exception("❌ Weaviate health check failed | base_url=%s error=%s", self.base_url, exc)
            return {"status": "unhealthy", "error": str(exc)}
    
    # Weaviate operations
    async def create_collection(self, collection_name: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new collection in Weaviate"""
        try:
            payload = {"schema": schema} if schema else {}
            logger.debug(
                "Creating Weaviate collection | collection=%s payload_keys=%s",
                collection_name,
                list(payload.keys()),
            )
            return await self.post_json(f"/weaviate/collections/{collection_name}/create", json=payload)
        except Exception as e:
            logger.exception(
                "❌ Failed to create collection | url=%s collection=%s error=%s",
                f"{self.base_url}/weaviate/collections/{collection_name}/create",
                collection_name,
                e,
            )
            raise
    
    async def add_document(self, collection_name: str, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a document to Weaviate collection"""
        try:
            logger.debug(
                "Adding document to Weaviate | collection=%s document_keys=%s",
                collection_name,
                list(document_data.keys()),
            )
            return await self.post_json(f"/weaviate/collections/{collection_name}/documents", json=document_data)
        except Exception as e:
            logger.exception(
                "❌ Failed to add document | url=%s collection=%s error=%s",
                f"{self.base_url}/weaviate/collections/{collection_name}/documents",
                collection_name,
                e,
            )
            raise
    
    async def search_documents(self, collection_name: str, search_request: Dict[str, Any]) -> Dict[str, Any]:
        """Search documents in Weaviate collection"""
        try:
            logger.debug(
                "Searching Weaviate | collection=%s payload_keys=%s",
                collection_name,
                list(search_request.keys()),
            )
            ctx = self._extract_context_headers(search_request)
            return await self.post_json(
                f"/weaviate/collections/{collection_name}/search",
                json=search_request,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
                timeout=30.0,
            )
        except Exception as e:
            logger.exception(
                "❌ Weaviate search failed | url=%s collection=%s error=%s",
                f"{self.base_url}/weaviate/collections/{collection_name}/search",
                collection_name,
                e,
            )
            raise
    
    async def batch_add_documents(self, collection_name: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Batch add multiple documents"""
        try:
            logger.debug(
                "Batch adding to Weaviate | collection=%s batch_size=%d",
                collection_name,
                len(documents),
            )
            return await self.post_json(
                f"/weaviate/collections/{collection_name}/batch",
                json=documents,
                timeout=60.0,
            )
        except Exception as e:
            logger.exception(
                "❌ Batch add failed | url=%s collection=%s batch_size=%d error=%s",
                f"{self.base_url}/weaviate/collections/{collection_name}/batch",
                collection_name,
                len(documents),
                e,
            )
            raise
    
    async def list_collections(self) -> List[str]:
        """List all Weaviate collections"""
        try:
            logger.debug("Listing Weaviate collections | base_url=%s", self.base_url)
            data = await self.get_json("/weaviate/collections")
            return data.get("collections", [])
        except Exception as e:
            logger.exception(
                "❌ Failed to list Weaviate collections | base_url=%s error=%s",
                self.base_url,
                e,
            )
            raise
    
    # Elysia operations
    async def elysia_query(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Elysia agentic query"""
        try:
            logger.debug("Calling Elysia query | payload_keys=%s", list(query_data.keys()))
            ctx = self._extract_context_headers(query_data)
            return await self.post_json(
                "/elysia/query",
                json=query_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
                timeout=120.0,
            )
        except Exception as e:
            logger.exception(
                "❌ Elysia query failed | url=%s error=%s",
                f"{self.base_url}/elysia/query",
                e,
            )
            raise
    
    async def execute_tool(self, tool_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute specific Elysia tool"""
        try:
            logger.debug("Executing Elysia tool | payload_keys=%s", list(tool_data.keys()))
            ctx = self._extract_context_headers(tool_data)
            return await self.post_json(
                "/elysia/tools/execute",
                json=tool_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
                timeout=60.0,
            )
        except Exception as e:
            logger.exception(
                "❌ Elysia tool execution failed | url=%s error=%s",
                f"{self.base_url}/elysia/tools/execute",
                e,
            )
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available Elysia tools"""
        try:
            logger.debug("Listing Elysia tools")
            data = await self.get_json("/elysia/tools")
            return data.get("tools", [])
        except Exception as e:
            logger.exception(
                "❌ Failed to list Elysia tools | url=%s error=%s",
                f"{self.base_url}/elysia/tools",
                e,
            )
            raise
    
    async def create_visualization(self, viz_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create dynamic visualization"""
        try:
            logger.debug("Creating Elysia visualization | payload_keys=%s", list(viz_data.keys()))
            ctx = self._extract_context_headers(viz_data)
            return await self.post_json(
                "/elysia/visualize",
                json=viz_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
            )
        except Exception as e:
            logger.exception(
                "❌ Visualization creation failed | url=%s error=%s",
                f"{self.base_url}/elysia/visualize",
                e,
            )
            raise
    
    async def submit_feedback(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit feedback for learning"""
        try:
            logger.debug("Submitting Elysia feedback | payload_keys=%s", list(feedback_data.keys()))
            ctx = self._extract_context_headers(feedback_data)
            return await self.post_json(
                "/elysia/feedback",
                json=feedback_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
            )
        except Exception as e:
            logger.exception(
                "❌ Feedback submission failed | url=%s error=%s",
                f"{self.base_url}/elysia/feedback",
                e,
            )
            raise
    
    async def migrate_from_qdrant(self, migration_data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate data from Qdrant to Weaviate"""
        try:
            logger.debug("Migrating from Qdrant | payload_keys=%s", list(migration_data.keys()))
            return await self.post_json("/elysia/migrate-from-qdrant", json=migration_data, timeout=300.0)
        except Exception as e:
            logger.exception(
                "❌ Elysia migration failed | url=%s error=%s",
                f"{self.base_url}/elysia/migrate-from-qdrant",
                e,
            )
            raise

    async def delete_document(self, collection_name: str, doc_id: str) -> bool:
        """Delete a document from Weaviate collection"""
        try:
            logger.debug("Deleting document from Weaviate | collection=%s doc_id=%s", collection_name, doc_id)
            response = await self.delete(f"/weaviate/collections/{collection_name}/documents/{doc_id}")
            return response.status_code < 400
        except Exception as e:
            logger.exception("❌ Failed to delete document | collection=%s doc_id=%s error=%s", collection_name, doc_id, e)
            return False

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Get information about a Weaviate collection"""
        try:
            return await self.get_json(f"/weaviate/collections/{collection_name}/info")
        except Exception as e:
            logger.exception("❌ Failed to get collection info | collection=%s error=%s", collection_name, e)
            return {"error": str(e)}

    async def search_similar(self, collection_name: str, query: str, limit: int = 5, tenant_id: str = None) -> List[Dict[str, Any]]:
        """Search for similar documents using Weaviate semantic search"""
        search_request = {
            "query": query,
            "limit": limit,
            "tenant_id": tenant_id,
            "search_type": "hybrid"
        }
        result = await self.search_documents(collection_name, search_request)
        return result.get("results", [])

    async def search_by_document_ids(self, collection_name: str, doc_ids: List[str], query: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Search within specific documents by their IDs"""
        search_request = {
            "query": query or "",
            "limit": limit,
            "doc_ids": doc_ids,
            "search_type": "keyword" if not query else "hybrid"
        }
        result = await self.search_documents(collection_name, search_request)
        return result.get("results", [])

    # =========================================================================
    # EMMA AI OPERATIONS
    # =========================================================================

    async def emma_query(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Emma AI query"""
        try:
            logger.debug("Calling Emma query | payload_keys=%s", list(query_data.keys()))
            ctx = self._extract_context_headers(query_data)
            return await self.post_json(
                "/emma/query",
                json=query_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
            )
        except Exception as e:
            logger.exception("❌ Emma query failed | error=%s", e)
            raise

    async def emma_v2_query(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Emma v2 AI query with SIL integration"""
        try:
            logger.debug("Calling Emma v2 query | payload_keys=%s", list(query_data.keys()))
            ctx = self._extract_context_headers(query_data)
            return await self.post_json(
                "/emma/v2/query",
                json=query_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
            )
        except Exception as e:
            logger.exception("❌ Emma v2 query failed | error=%s", e)
            raise

    async def emma_health(self) -> Dict[str, Any]:
        """Check Emma AI service health"""
        try:
            return await self.get_json("/emma/health")
        except HTTPClientError as exc:
            return {"status": "unhealthy", "service": "emma", "error": exc.message}
        except Exception as exc:
            return {"status": "unhealthy", "service": "emma", "error": str(exc)}

    async def emma_list_tools(self) -> Dict[str, Any]:
        """List available Emma AI tools"""
        try:
            return await self.get_json("/emma/tools")
        except Exception as e:
            logger.exception("❌ Failed to list Emma tools | error=%s", e)
            raise

    async def emma_feedback(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit feedback to Emma AI"""
        try:
            ctx = self._extract_context_headers(feedback_data)
            return await self.post_json(
                "/emma/feedback",
                json=feedback_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
            )
        except Exception as e:
            logger.exception("❌ Emma feedback failed | error=%s", e)
            raise

    async def emma_get_analysis(self, job_id: str) -> Dict[str, Any]:
        """Get stored analysis result by job ID"""
        try:
            return await self.get_json(f"/emma/analysis/{job_id}")
        except Exception as e:
            logger.exception("❌ Failed to get Emma analysis | job_id=%s error=%s", job_id, e)
            raise

    async def emma_document_markdown(
        self,
        document_id: str,
        file_content: bytes,
        filename: str,
        content_type: str = "application/pdf"
    ) -> Dict[str, Any]:
        """Convert PDF document to Markdown format"""
        try:
            files = {"pdf_file": (filename, file_content, content_type)}
            data = {"document_id": document_id}

            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                response = await client.post(
                    f"{self.base_url}/emma/document/markdown",
                    data=data,
                    files=files,
                    headers={"X-API-Key": self.api_key}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.exception("❌ Emma document/markdown failed | error=%s", e)
            raise

    async def emma_analyze_with_annotations(
        self,
        document_id: str,
        tenant_id: str,
        analysis_type: str = "legal",
        file_content: Optional[bytes] = None,
        filename: Optional[str] = None,
        content_type: str = "application/pdf"
    ) -> Dict[str, Any]:
        """Analyze document and return annotated PDF with highlights"""
        try:
            data = {
                "document_id": document_id,
                "tenant_id": tenant_id,
                "analysis_type": analysis_type,
            }
            files = {}
            if file_content and filename:
                files["file"] = (filename, file_content, content_type)

            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
                response = await client.post(
                    f"{self.base_url}/emma/analyze-with-annotations",
                    data=data,
                    files=files if files else None,
                    headers={"X-API-Key": self.api_key}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.exception("❌ Emma analyze-with-annotations failed | error=%s", e)
            raise

    def get_stream_headers(self) -> Dict[str, str]:
        """Get headers for streaming requests"""
        return {
            "X-API-Key": self.api_key,
            "Accept": "text/event-stream",
        }

    @asynccontextmanager
    async def stream_client(self, timeout: float = 300.0):
        """Get an async client configured for streaming requests"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            yield client

    # =========================================================================
    # PUBLIC KNOWLEDGE BASE OPERATIONS
    # =========================================================================

    async def public_knowledge_health(self) -> Dict[str, Any]:
        """Check public knowledge base health"""
        try:
            return await self.get_json("/public-knowledge/health")
        except HTTPClientError as exc:
            return {"status": "unhealthy", "error": exc.message}
        except Exception as exc:
            return {"status": "unhealthy", "error": str(exc)}

    async def public_knowledge_stats(self) -> Dict[str, Any]:
        """Get public knowledge base statistics"""
        try:
            return await self.get_json("/public-knowledge/stats")
        except Exception as e:
            logger.exception("❌ Public knowledge stats failed | error=%s", e)
            raise

    async def public_knowledge_categories(self) -> Dict[str, Any]:
        """Get available categories"""
        try:
            return await self.get_json("/public-knowledge/categories")
        except Exception as e:
            logger.exception("❌ Public knowledge categories failed | error=%s", e)
            raise

    async def public_knowledge_jurisdictions(self) -> Dict[str, Any]:
        """Get available jurisdictions"""
        try:
            return await self.get_json("/public-knowledge/jurisdictions")
        except Exception as e:
            logger.exception("❌ Public knowledge jurisdictions failed | error=%s", e)
            raise

    async def public_knowledge_search(self, search_data: Dict[str, Any]) -> Dict[str, Any]:
        """Search public knowledge base"""
        try:
            return await self.post_json("/public-knowledge/search", json=search_data)
        except Exception as e:
            logger.exception("❌ Public knowledge search failed | error=%s", e)
            raise

    async def public_knowledge_get_document(self, doc_id: str) -> Dict[str, Any]:
        """Get a specific document from public knowledge base"""
        try:
            return await self.get_json(f"/public-knowledge/documents/{doc_id}")
        except Exception as e:
            logger.exception("❌ Public knowledge get document failed | doc_id=%s error=%s", doc_id, e)
            raise

    async def public_knowledge_extract_entities(
        self,
        limit: int = 100,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract knowledge entities from public documents into Knowledge Graph.

        Processes existing public documents (legislation, etc.) and extracts
        entities for semantic search and entity-based queries.
        """
        try:
            params = {"limit": limit}
            if category:
                params["category"] = category
            logger.info("🧠 Extracting knowledge from public documents | limit=%s", limit)
            return await self.post_json(
                "/public-knowledge/extract-knowledge",
                params=params,
                timeout=600.0  # Can take a while for many documents
            )
        except Exception as e:
            logger.exception("❌ Public knowledge extraction failed | error=%s", e)
            raise

    # =========================================================================
    # ACL & CACHE SECURITY OPERATIONS
    # =========================================================================

    async def update_document_acl(
        self,
        document_id: str,
        collection_name: str,
        acl_user_ids: List[str],
        acl_role_ids: List[str],
        acl_everyone: bool
    ) -> Dict[str, Any]:
        """
        Update document ACL properties in Weaviate.

        Called when ACL changes in PostgreSQL to sync to Weaviate for filtering.
        """
        try:
            payload = {
                "collection_name": collection_name,
                "acl_user_ids": acl_user_ids,
                "acl_role_ids": acl_role_ids,
                "acl_everyone": acl_everyone
            }
            logger.debug(
                "Updating document ACL in Weaviate | document_id=%s collection=%s",
                document_id, collection_name
            )
            return await self.put_json(f"/weaviate/documents/{document_id}/acl", json=payload)
        except Exception as e:
            logger.exception(
                "❌ Failed to update document ACL | document_id=%s error=%s",
                document_id, e
            )
            raise

    async def invalidate_cache_by_document(
        self,
        tenant_id: str,
        document_id: str
    ) -> Dict[str, Any]:
        """
        Invalidate semantic cache entries that reference a specific document.

        SECURITY: Must be called when document ACL changes to prevent stale
        cached responses from being returned to users who lost access.

        Args:
            tenant_id: Tenant identifier
            document_id: Document whose ACL changed

        Returns:
            Dict with status and entries_invalidated count
        """
        try:
            payload = {
                "tenant_id": tenant_id,
                "document_id": document_id
            }
            logger.info(
                "🔄 Invalidating cache for document | tenant=%s document=%s",
                tenant_id, document_id
            )
            return await self.post_json("/weaviate/cache/invalidate-by-document", json=payload)
        except Exception as e:
            logger.exception(
                "❌ Failed to invalidate cache | tenant=%s document=%s error=%s",
                tenant_id, document_id, e
            )
            # Don't raise - cache invalidation failure shouldn't block ACL updates
            return {"status": "error", "error": str(e), "entries_invalidated": 0}


    # =========================================================================
    # KNOWLEDGE GRAPH OPERATIONS
    # =========================================================================

    async def knowledge_search(self, search_data: Dict[str, Any]) -> Dict[str, Any]:
        """Search knowledge entities semantically"""
        try:
            ctx = self._extract_context_headers(search_data)
            logger.debug("Searching knowledge entities | query=%s", search_data.get("query", "")[:50])
            return await self.post_json(
                "/knowledge/search",
                json=search_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
            )
        except Exception as e:
            logger.exception("❌ Knowledge search failed | error=%s", e)
            raise

    async def knowledge_list_entities(
        self,
        tenant_id: str,
        entity_type: Optional[str] = None,
        domain: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """List knowledge entities for a tenant"""
        try:
            params = {
                "tenant_id": tenant_id,
                "limit": limit
            }
            if entity_type:
                params["entity_type"] = entity_type
            if domain:
                params["domain"] = domain

            logger.debug("Listing knowledge entities | tenant=%s type=%s", tenant_id, entity_type)
            return await self.get_json("/knowledge/entities", params=params)
        except Exception as e:
            logger.exception("❌ Failed to list knowledge entities | error=%s", e)
            raise

    async def knowledge_get_entity(self, entity_id: str, tenant_id: str) -> Dict[str, Any]:
        """Get a specific knowledge entity"""
        try:
            params = {"tenant_id": tenant_id}
            return await self.get_json(f"/knowledge/entities/{entity_id}", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get knowledge entity | entity_id=%s error=%s", entity_id, e)
            raise

    async def knowledge_delete_entity(self, entity_id: str, tenant_id: str) -> Dict[str, Any]:
        """Delete a knowledge entity"""
        try:
            params = {"tenant_id": tenant_id}
            response = await self.delete(f"/knowledge/entities/{entity_id}", params=params)
            if response.status_code < 400:
                return {"status": "deleted", "entity_id": entity_id}
            return {"status": "error", "entity_id": entity_id}
        except Exception as e:
            logger.exception("❌ Failed to delete knowledge entity | entity_id=%s error=%s", entity_id, e)
            raise

    async def knowledge_delete_by_document(self, document_id: str, tenant_id: str) -> Dict[str, Any]:
        """Delete all knowledge entities from a document"""
        try:
            params = {"tenant_id": tenant_id}
            return await self.delete_json(f"/knowledge/documents/{document_id}/knowledge", params=params)
        except Exception as e:
            logger.exception("❌ Failed to delete document knowledge | document_id=%s error=%s", document_id, e)
            raise

    async def knowledge_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get knowledge graph statistics"""
        try:
            params = {"tenant_id": tenant_id}
            return await self.get_json("/knowledge/stats", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get knowledge stats | error=%s", e)
            raise

    # =========================================================================
    # USER LEARNING OPERATIONS
    # =========================================================================

    async def learning_get_profile(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Get user learning profile"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            logger.debug("Getting learning profile | user=%s", user_id[:8] if user_id else "None")
            return await self.get_json("/learning/profile", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get learning profile | error=%s", e)
            raise

    async def learning_update_profile(
        self,
        tenant_id: str,
        user_id: str,
        profile_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update user learning profile preferences"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            logger.debug("Updating learning profile | user=%s", user_id[:8] if user_id else "None")
            return await self.put_json("/learning/profile", json=profile_data, params=params)
        except Exception as e:
            logger.exception("❌ Failed to update learning profile | error=%s", e)
            raise

    async def learning_record_feedback(
        self,
        tenant_id: str,
        user_id: str,
        feedback_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Record user feedback for learning"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            logger.debug("Recording feedback | user=%s rating=%s", user_id[:8] if user_id else "None", feedback_data.get("rating"))
            return await self.post_json("/learning/feedback", json=feedback_data, params=params)
        except Exception as e:
            logger.exception("❌ Failed to record feedback | error=%s", e)
            raise

    async def learning_record_document_view(
        self,
        tenant_id: str,
        user_id: str,
        view_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Record document view for learning"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            logger.debug("Recording document view | user=%s document=%s", user_id[:8] if user_id else "None", view_data.get("document_id"))
            return await self.post_json("/learning/document-view", json=view_data, params=params)
        except Exception as e:
            logger.exception("❌ Failed to record document view | error=%s", e)
            raise

    async def learning_get_stats(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Get learning statistics for a user"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            return await self.get_json("/learning/stats", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get learning stats | error=%s", e)
            raise

    async def learning_get_context(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Get full user context for Emma"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            return await self.get_json("/learning/context", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get user context | error=%s", e)
            raise

    async def learning_get_ranking_weights(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Get personalized ranking weights"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            return await self.get_json("/learning/ranking-weights", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get ranking weights | error=%s", e)
            raise

    async def learning_flush(self, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """Flush pending learning data"""
        try:
            params = {"tenant_id": tenant_id, "user_id": user_id}
            return await self.post_json("/learning/flush", json={}, params=params)
        except Exception as e:
            logger.exception("❌ Failed to flush learning data | error=%s", e)
            raise

    # =========================================================================
    # STRUCTURAL INTELLIGENCE LAYER (SIL) OPERATIONS
    # =========================================================================

    async def sil_query(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute SIL structural query"""
        try:
            logger.debug("Calling SIL query | query=%s", query_data.get("query", "")[:50])
            ctx = self._extract_context_headers(query_data)
            return await self.post_json(
                "/sil/query",
                json=query_data,
                tenant_id=ctx["tenant_id"],
                user_id=ctx["user_id"],
                request_id=ctx["request_id"],
                timeout=60.0,
            )
        except Exception as e:
            logger.exception("❌ SIL query failed | error=%s", e)
            raise

    async def sil_index_structural(self, index_data: Dict[str, Any]) -> Dict[str, Any]:
        """Index structural metadata for a document"""
        try:
            logger.debug("Indexing structural metadata | document_id=%s", index_data.get("document_id"))
            return await self.post_json("/sil/index-structural", json=index_data, timeout=30.0)
        except Exception as e:
            logger.exception("❌ SIL index structural failed | error=%s", e)
            raise

    async def sil_get_structure(self, document_id: str, tenant_id: str) -> Dict[str, Any]:
        """Get structural metadata for a document"""
        try:
            params = {"tenant_id": tenant_id}
            logger.debug("Getting structural metadata | document_id=%s", document_id)
            return await self.get_json(f"/sil/structure/{document_id}", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get structural metadata | document_id=%s error=%s", document_id, e)
            raise

    async def sil_graph_stats(self, tenant_id: str) -> Dict[str, Any]:
        """Get SIL graph statistics"""
        try:
            params = {"tenant_id": tenant_id}
            logger.debug("Getting SIL graph stats | tenant_id=%s", tenant_id)
            return await self.get_json("/sil/graph/stats", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get SIL graph stats | error=%s", e)
            raise

    async def sil_search_structural(
        self,
        query: str,
        tenant_id: str,
        limit: int = 10,
        semantic_type: Optional[str] = None,
        domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search structural documents by semantic similarity"""
        try:
            params = {
                "query": query,
                "tenant_id": tenant_id,
                "limit": limit,
            }
            if semantic_type:
                params["semantic_type"] = semantic_type
            if domain:
                params["domain"] = domain

            logger.debug("Searching structural documents | query=%s", query[:50])
            return await self.post_json("/sil/search-structural", params=params)
        except Exception as e:
            logger.exception("❌ SIL structural search failed | error=%s", e)
            raise

    async def sil_get_folder_contents(
        self,
        folder_path: str,
        tenant_id: str,
        include_subfolders: bool = False
    ) -> Dict[str, Any]:
        """Get contents of a structural folder"""
        try:
            params = {
                "tenant_id": tenant_id,
                "include_subfolders": str(include_subfolders).lower(),
            }
            logger.debug("Getting folder contents | path=%s", folder_path)
            return await self.get_json(f"/sil/folder/{folder_path}", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get folder contents | folder=%s error=%s", folder_path, e)
            raise

    async def sil_get_related_documents(
        self,
        document_id: str,
        tenant_id: str,
        relationship_type: Optional[str] = None,
        max_depth: int = 2
    ) -> Dict[str, Any]:
        """Get documents related to a given document"""
        try:
            params = {
                "tenant_id": tenant_id,
                "max_depth": max_depth,
            }
            if relationship_type:
                params["relationship_type"] = relationship_type

            logger.debug("Getting related documents | document_id=%s", document_id)
            return await self.get_json(f"/sil/related/{document_id}", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get related documents | document_id=%s error=%s", document_id, e)
            raise

    async def sil_mark_document_removed(self, document_id: str, tenant_id: str) -> Dict[str, Any]:
        """Mark a document as removed in the structural graph"""
        try:
            params = {"tenant_id": tenant_id}
            logger.debug("Marking document as removed | document_id=%s", document_id)
            response = await self.delete(f"/sil/structure/{document_id}", params=params)
            if response.status_code < 400:
                return await response.json()
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.exception("❌ Failed to mark document removed | document_id=%s error=%s", document_id, e)
            raise

    async def sil_clear_graph(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """Clear the structural graph"""
        try:
            params = {}
            if tenant_id:
                params["tenant_id"] = tenant_id
            logger.info("🔄 Clearing SIL graph | tenant_id=%s", tenant_id or "ALL")
            response = await self.delete("/sil/graph/clear", params=params)
            if response.status_code < 400:
                return await response.json()
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.exception("❌ Failed to clear SIL graph | error=%s", e)
            raise

    async def sil_get_document_ids(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 10000
    ) -> Dict[str, Any]:
        """Get list of document IDs already indexed in the graph"""
        try:
            params = {"limit": limit}
            if tenant_id:
                params["tenant_id"] = tenant_id
            logger.debug("Getting indexed document IDs | tenant_id=%s", tenant_id)
            return await self.get_json("/sil/graph/document-ids", params=params)
        except Exception as e:
            logger.exception("❌ Failed to get document IDs | error=%s", e)
            raise

    async def sil_reindex(self, reindex_data: Dict[str, Any]) -> Dict[str, Any]:
        """Re-index documents to the structural graph"""
        try:
            logger.info(
                "🔄 Starting SIL reindex | tenant_id=%s full_reindex=%s",
                reindex_data.get("tenant_id"),
                reindex_data.get("full_reindex", False)
            )
            return await self.post_json("/sil/reindex", json=reindex_data, timeout=300.0)
        except Exception as e:
            logger.exception("❌ SIL reindex failed | error=%s", e)
            raise

    # =========================================================================
    # BOE LEGISLATION OPERATIONS (Public Knowledge Indexing)
    # =========================================================================

    async def boe_list_presets(self) -> List[Dict[str, Any]]:
        """List available BOE legislation presets"""
        try:
            logger.debug("Listing BOE presets")
            return await self.get_json("/boe/presets")
        except Exception as e:
            logger.exception("❌ Failed to list BOE presets | error=%s", e)
            raise

    async def boe_get_preset(self, preset_name: str) -> Dict[str, Any]:
        """Get details of a specific preset"""
        try:
            logger.debug("Getting BOE preset | preset=%s", preset_name)
            return await self.get_json(f"/boe/presets/{preset_name}")
        except Exception as e:
            logger.exception("❌ Failed to get BOE preset | preset=%s error=%s", preset_name, e)
            raise

    async def boe_download_legislation(self, boe_id: str, index: bool = True) -> Dict[str, Any]:
        """Download and index a specific BOE legislation"""
        try:
            logger.info("📥 Downloading BOE legislation | boe_id=%s", boe_id)
            return await self.post_json(
                "/boe/download",
                json={"boe_id": boe_id, "index_to_weaviate": index},
                timeout=120.0
            )
        except Exception as e:
            logger.exception("❌ BOE download failed | boe_id=%s error=%s", boe_id, e)
            raise

    async def boe_download_preset(self, preset_name: str, index: bool = True) -> List[Dict[str, Any]]:
        """Download all legislation in a preset"""
        try:
            logger.info("📥 Downloading BOE preset | preset=%s", preset_name)
            return await self.post_json(
                "/boe/download/preset",
                json={"preset": preset_name, "index_to_weaviate": index},
                timeout=600.0  # Can take a while for large presets
            )
        except Exception as e:
            logger.exception("❌ BOE preset download failed | preset=%s error=%s", preset_name, e)
            raise

    async def boe_search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search BOE for legislation"""
        try:
            params = {"query": query, "limit": limit}
            return await self.get_json("/boe/search", params=params)
        except Exception as e:
            logger.exception("❌ BOE search failed | error=%s", e)
            raise

    async def boe_get_legislation_info(self, boe_id: str) -> Dict[str, Any]:
        """Get information about a BOE legislation document"""
        try:
            return await self.get_json(f"/boe/legislation/{boe_id}")
        except Exception as e:
            logger.exception("❌ Failed to get BOE legislation info | boe_id=%s error=%s", boe_id, e)
            raise

    async def boe_sync_legislation(self, boe_id: str, force: bool = False) -> Dict[str, Any]:
        """Sync a specific legislation with BOE and detect changes"""
        try:
            params = {"force": str(force).lower()}
            logger.info("🔄 Syncing BOE legislation | boe_id=%s", boe_id)
            return await self.post_json(f"/boe/sync/{boe_id}", params=params, timeout=120.0)
        except Exception as e:
            logger.exception("❌ BOE sync failed | boe_id=%s error=%s", boe_id, e)
            raise

    async def boe_sync_all(self) -> List[Dict[str, Any]]:
        """Sync all tracked legislation and detect changes"""
        try:
            logger.info("🔄 Syncing all BOE legislation")
            return await self.post_json("/boe/sync/all", timeout=600.0)
        except Exception as e:
            logger.exception("❌ BOE sync all failed | error=%s", e)
            raise

    async def boe_get_all_legislation_ids(self) -> Dict[str, Any]:
        """Get all BOE IDs across all presets"""
        try:
            return await self.get_json("/boe/all-legislation-ids")
        except Exception as e:
            logger.exception("❌ Failed to get all BOE legislation IDs | error=%s", e)
            raise

    async def boe_get_pending_updates(self) -> List[Dict[str, Any]]:
        """Get list of legislation with pending updates"""
        try:
            return await self.get_json("/boe/updates")
        except Exception as e:
            logger.exception("❌ Failed to get pending BOE updates | error=%s", e)
            raise


# Global client instance
weaviate_client = WeaviateClient()
