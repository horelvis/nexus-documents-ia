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
        self.api_key = settings.MICROSERVICES_API_KEY if hasattr(settings, 'MICROSERVICES_API_KEY') else 'unified-microservices-key-12345'
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
    async def health_check(self) -> Dict[str, Any]:
        """Check Weaviate service health"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/health", headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Weaviate health check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    # Weaviate operations
    async def create_collection(self, collection_name: str, schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new collection in Weaviate"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/create"
                payload = {"schema": schema} if schema else {}
                
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Failed to create collection {collection_name}: {e}")
            raise
    
    async def add_document(self, collection_name: str, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a document to Weaviate collection"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/documents"
                
                response = await client.post(url, json=document_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Failed to add document to {collection_name}: {e}")
            raise
    
    async def search_documents(self, collection_name: str, search_request: Dict[str, Any]) -> Dict[str, Any]:
        """Search documents in Weaviate collection"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/search"
                
                response = await client.post(url, json=search_request, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Search failed in {collection_name}: {e}")
            raise
    
    async def batch_add_documents(self, collection_name: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Batch add multiple documents"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self.base_url}/weaviate/collections/{collection_name}/batch"
                
                response = await client.post(url, json=documents, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Batch add failed for {collection_name}: {e}")
            raise
    
    async def list_collections(self) -> List[str]:
        """List all Weaviate collections"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/weaviate/collections"
                
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("collections", [])
        except Exception as e:
            logger.error(f"❌ Failed to list collections: {e}")
            raise
    
    # Elysia operations
    async def elysia_query(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute Elysia agentic query"""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                url = f"{self.base_url}/elysia/query"
                
                response = await client.post(url, json=query_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Elysia query failed: {e}")
            raise
    
    async def execute_tool(self, tool_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute specific Elysia tool"""
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                url = f"{self.base_url}/elysia/tools/execute"
                
                response = await client.post(url, json=tool_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Tool execution failed: {e}")
            raise
    
    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available Elysia tools"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/elysia/tools"
                
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                return data.get("tools", [])
        except Exception as e:
            logger.error(f"❌ Failed to list tools: {e}")
            raise
    
    async def create_visualization(self, viz_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create dynamic visualization"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/elysia/visualize"
                
                response = await client.post(url, json=viz_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Visualization creation failed: {e}")
            raise
    
    async def submit_feedback(self, feedback_data: Dict[str, Any]) -> Dict[str, Any]:
        """Submit feedback for learning"""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{self.base_url}/elysia/feedback"
                
                response = await client.post(url, json=feedback_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Feedback submission failed: {e}")
            raise
    
    async def migrate_from_qdrant(self, migration_data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate data from Qdrant to Weaviate"""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:  # 5 minute timeout for migration
                url = f"{self.base_url}/elysia/migrate-from-qdrant"
                
                response = await client.post(url, json=migration_data, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            raise


# Global client instance
weaviate_client = WeaviateClient()