"""Client for Weaviate microservice"""
import httpx
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class WeaviateClient:
    """Client for communicating with Weaviate microservice"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'WEAVIATE_SERVICE_URL', 'http://weaviate-service:8007')
        self.api_key = settings.MICROSERVICES_API_KEY
        self.headers = {
            'X-API-Key': self.api_key,
            'Content-Type': 'application/json'
        }
        logger.info("WeaviateClient initialized | base_url=%s", self.base_url)
        
    async def health_check(self) -> Dict[str, Any]:
        """Check Weaviate service health"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/health"
                logger.debug("Checking Weaviate health | url=%s", url)
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.exception("❌ Weaviate health check failed | base_url=%s error=%s", self.base_url, e)
            return {"status": "unhealthy", "error": str(e)}
    
    # Weaviate operations
    async def create_collection(self, collection_name: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new collection in Weaviate"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/create"
                payload = {"schema": schema} if schema else {}
                logger.debug(
                    "Creating Weaviate collection | url=%s collection=%s payload_keys=%s",
                    url,
                    collection_name,
                    list(payload.keys()),
                )
                
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/documents"
                logger.debug(
                    "Adding document to Weaviate | url=%s collection=%s document_keys=%s",
                    url,
                    collection_name,
                    list(document_data.keys()),
                )
                
                response = await client.post(url, json=document_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/search"
                logger.debug(
                    "Searching Weaviate | url=%s collection=%s payload_keys=%s",
                    url,
                    collection_name,
                    list(search_request.keys()),
                )
                
                response = await client.post(url, json=search_request, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/batch"
                logger.debug(
                    "Batch adding to Weaviate | url=%s collection=%s batch_size=%d",
                    url,
                    collection_name,
                    len(documents),
                )
                
                response = await client.post(url, json=documents, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections"
                logger.debug("Listing Weaviate collections | url=%s", url)
                
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
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
            async with httpx.AsyncClient(timeout=120.0) as client:
                url = f"{self.base_url}/elysia/query"
                logger.debug("Calling Elysia query | url=%s payload_keys=%s", url, list(query_data.keys()))
                
                response = await client.post(url, json=query_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self.base_url}/elysia/tools/execute"
                logger.debug("Executing Elysia tool | url=%s payload_keys=%s", url, list(tool_data.keys()))
                
                response = await client.post(url, json=tool_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/elysia/tools"
                logger.debug("Listing Elysia tools | url=%s", url)
                
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
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
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/elysia/visualize"
                logger.debug("Creating Elysia visualization | url=%s payload_keys=%s", url, list(viz_data.keys()))
                
                response = await client.post(url, json=viz_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/elysia/feedback"
                logger.debug("Submitting Elysia feedback | url=%s payload_keys=%s", url, list(feedback_data.keys()))
                
                response = await client.post(url, json=feedback_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout for migration
                url = f"{self.base_url}/elysia/migrate-from-qdrant"
                logger.debug(
                    "Migrating from Qdrant | url=%s payload_keys=%s",
                    url,
                    list(migration_data.keys()),
                )

                response = await client.post(url, json=migration_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
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
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/documents/{doc_id}"
                logger.debug("Deleting document from Weaviate | url=%s", url)
                response = await client.delete(url, headers=self.headers)
                response.raise_for_status()
                return True
        except Exception as e:
            logger.exception("❌ Failed to delete document | collection=%s doc_id=%s error=%s", collection_name, doc_id, e)
            return False

    async def get_collection_info(self, collection_name: str) -> Dict[str, Any]:
        """Get information about a Weaviate collection"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/info"
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json()
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


# Global client instance
weaviate_client = WeaviateClient()
