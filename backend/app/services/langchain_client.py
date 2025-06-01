"""
HTTP client for LangChain microservice
"""
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class LangChainClient:
    """HTTP client for communicating with LangChain microservice"""
    
    def __init__(self):
        self.base_url = getattr(settings, 'LANGCHAIN_SERVICE_URL', 'http://langchain-service:8001')
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    async def health_check(self) -> bool:
        """Check if LangChain service is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False
    
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        try:
            response = await self.client.post(
                f"{self.base_url}/embeddings",
                json={"texts": texts}
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        try:
            response = await self.client.post(
                f"{self.base_url}/embedding",
                json={"text": text}
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except Exception as e:
            logger.error(f"Error generating single embedding: {str(e)}")
            raise
    
    async def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """Chunk text into smaller pieces"""
        try:
            response = await self.client.post(
                f"{self.base_url}/chunk",
                json={"text": text}
            )
            response.raise_for_status()
            return response.json()["chunks"]
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise
    
    async def add_documents(self, tenant_id: str, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        """Add documents to vector store"""
        try:
            response = await self.client.post(
                f"{self.base_url}/documents/add",
                json={
                    "tenant_id": tenant_id,
                    "texts": texts,
                    "metadatas": metadatas
                }
            )
            response.raise_for_status()
            return response.json()["success"]
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}")
            return False
    
    async def add_document(self, tenant_id: str, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> bool:
        """Add single document to vector store"""
        try:
            response = await self.client.post(
                f"{self.base_url}/documents/add-single",
                json={
                    "tenant_id": tenant_id,
                    "doc_id": doc_id,
                    "text": text,
                    "metadata": metadata or {}
                }
            )
            response.raise_for_status()
            return response.json()["success"]
        except Exception as e:
            logger.error(f"Error adding single document: {str(e)}")
            return False
    
    async def search_similar(self, tenant_id: str, query: str, limit: int = 5, doc_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        try:
            response = await self.client.post(
                f"{self.base_url}/search",
                json={
                    "tenant_id": tenant_id,
                    "query": query,
                    "limit": limit,
                    "doc_ids": doc_ids
                }
            )
            response.raise_for_status()
            return response.json()["results"]
        except Exception as e:
            logger.error(f"Error searching documents: {str(e)}")
            return []
    
    async def generate_response(self, query: str, tenant_id: Optional[str] = None, doc_ids: Optional[List[str]] = None, max_tokens: int = 500) -> Dict[str, Any]:
        """Generate LLM response with optional RAG"""
        try:
            response = await self.client.post(
                f"{self.base_url}/llm/generate",
                json={
                    "query": query,
                    "tenant_id": tenant_id,
                    "doc_ids": doc_ids,
                    "max_tokens": max_tokens
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error generating LLM response: {str(e)}")
            return {
                "answer": "Lo siento, ocurrió un error al procesar tu consulta.",
                "sources": [],
                "error": str(e)
            }
    
    async def suggest_tags(self, text: str, num_tags: int = 5) -> List[str]:
        """Suggest tags for text"""
        try:
            response = await self.client.post(
                f"{self.base_url}/llm/suggest-tags",
                json={"text": text, "num_tags": num_tags}
            )
            response.raise_for_status()
            return response.json()["tags"]
        except Exception as e:
            logger.error(f"Error suggesting tags: {str(e)}")
            return ["documento", "texto", "contenido"]
    
    async def extract_metadata(self, text: str) -> Dict[str, str]:
        """Extract metadata from text"""
        try:
            response = await self.client.post(
                f"{self.base_url}/llm/extract-metadata",
                json={"text": text}
            )
            response.raise_for_status()
            return response.json()["metadata"]
        except Exception as e:
            logger.error(f"Error extracting metadata: {str(e)}")
            return {"título": "Documento", "tipo": "texto"}
    
    async def summarize_text(self, text: str, max_length: int = 200) -> str:
        """Summarize text"""
        try:
            response = await self.client.post(
                f"{self.base_url}/llm/summarize",
                json={"text": text, "max_length": max_length}
            )
            response.raise_for_status()
            return response.json()["summary"]
        except Exception as e:
            logger.error(f"Error summarizing text: {str(e)}")
            return "Resumen no disponible."
    
    async def delete_document(self, tenant_id: str, doc_id: str) -> bool:
        """Delete document from vector store"""
        try:
            response = await self.client.delete(
                f"{self.base_url}/documents/{tenant_id}/{doc_id}"
            )
            response.raise_for_status()
            return response.json()["success"]
        except Exception as e:
            logger.error(f"Error deleting document: {str(e)}")
            return False
    
    async def get_collection_info(self, tenant_id: str) -> Dict[str, Any]:
        """Get collection information"""
        try:
            response = await self.client.get(
                f"{self.base_url}/collection/{tenant_id}/info"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting collection info: {str(e)}")
            return {}