"""
LangChain Client Service - Interface para comunicarse con el microservicio LangChain
NOTA: Esta es una implementación simplificada para mantener compatibilidad con servicios existentes.
Para agentes avanzados, usar LangroidClient en su lugar.
"""
import asyncio
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class LangChainClient:
    """Cliente simplificado para el microservicio LangChain"""
    
    def __init__(self):
        self.base_url = settings.LANGCHAIN_SERVICE_URL
        self.timeout = 30.0
        self.http_client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.http_client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.http_client:
            await self.http_client.aclose()
    
    async def get_embeddings(self, texts: List[str], tenant_id: str = None) -> List[List[float]]:
        """Generar embeddings usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "texts": texts,
                "tenant_id": tenant_id or settings.DEFAULT_TENANT
            }
            
            response = await self.http_client.post(
                "/embeddings/generate",
                json=payload
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("embeddings", [])
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error generating embeddings: {str(e)}")
            # Fallback: return dummy embeddings for compatibility
            return [[0.0] * 384 for _ in texts]  # nomic-embed-text dimension
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            return [[0.0] * 384 for _ in texts]
    
    async def generate_response(
        self,
        query: str,
        tenant_id: str = None,
        max_tokens: int = 1000,
        temperature: float = 0.1
    ) -> Dict[str, Any]:
        """Generar respuesta usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "query": query,
                "tenant_id": tenant_id or settings.DEFAULT_TENANT,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            response = await self.http_client.post(
                "/chat/generate",
                json=payload
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error generating response: {str(e)}")
            return {
                "answer": "Lo siento, no pude procesar tu solicitud en este momento.",
                "sources": [],
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return {
                "answer": "Error interno del servicio.",
                "sources": [],
                "error": str(e)
            }
    
    async def search_similar(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Búsqueda semántica usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "query": query,
                "tenant_id": tenant_id,
                "limit": limit,
                "threshold": threshold
            }
            
            response = await self.http_client.post(
                "/search/similar",
                json=payload
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("documents", [])
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in semantic search: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            return []
    
    async def store_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        tenant_id: str = None
    ) -> str:
        """Almacenar documento en vector store usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            payload = {
                "content": content,
                "metadata": metadata,
                "tenant_id": tenant_id or settings.DEFAULT_TENANT
            }
            
            response = await self.http_client.post(
                "/documents/store",
                json=payload
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("document_id", "")
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error storing document: {str(e)}")
            return ""
        except Exception as e:
            logger.error(f"Error storing document: {str(e)}")
            return ""
    
    async def health_check(self) -> Dict[str, Any]:
        """Verificar estado del LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            response = await self.http_client.get("/health")
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"LangChain health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }