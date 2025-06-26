"""
LangChain Client Service - Interface para comunicarse con el microservicio LangChain
NOTA: Esta es una implementación simplificada para mantener compatibilidad con servicios existentes.
Para agentes avanzados, usar LangroidClient en su lugar.
"""
import asyncio
import logging
import httpx
import uuid
from typing import List, Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
from app.core.config import settings

logger = logging.getLogger(__name__)


# Helper function to determine if an exception should be retried
def should_retry_exception(exception: BaseException) -> bool:
    if isinstance(exception, (httpx.NetworkError, httpx.TimeoutException)):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code >= 500  # Retry on 5xx errors
    return False


class LangChainClient:
    """Cliente simplificado para el microservicio LangChain"""

    def __init__(self, http_client: httpx.AsyncClient, tenant_id: str = None, user_id: str = None):
        self.http_client = http_client
        self.base_url = settings.LANGCHAIN_SERVICE_URL
        self.tenant_id = tenant_id
        self.user_id = user_id
        # self.timeout = 30.0 # Timeout is now managed by the passed client or per-request
    
    def _get_auth_headers(self, tenant_id: str = None, user_id: str = None) -> dict:
        """Get authentication headers for microservice requests"""
        headers = {
            "X-API-Key": settings.MICROSERVICES_API_KEY,
            "X-Tenant-ID": tenant_id or self.tenant_id or settings.DEFAULT_TENANT
        }
        
        user_id_to_use = user_id or self.user_id
        if user_id_to_use:
            headers["X-User-ID"] = user_id_to_use
            
        return headers

    # __aenter__ and __aexit__ removed as client is managed externally

    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def get_embeddings(self, texts: List[str], tenant_id: str = None) -> List[List[float]]:
        """Generar embeddings usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        
        try:
            payload = {
                "texts": texts
            }
            
            headers = self._get_auth_headers(tenant_id)
            
            response = await self.http_client.post(
                f"{self.base_url}/embeddings",
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("embeddings", [])
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error generating embeddings: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def generate_response(
        self,
        query: str,
        tenant_id: str = None,
        max_tokens: int = 1000,
        temperature: float = 0.1
    ) -> Dict[str, Any]:
        """Generar respuesta usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        
        try:
            payload = {
                "query": query,
                "tenant_id": tenant_id or settings.DEFAULT_TENANT,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/llm/generate",
                json=payload,
                headers=self._get_auth_headers(tenant_id)
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
    
    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def search_similar(
        self,
        tenant_id: str,
        query: str,
        limit: int = 10,
        threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """Búsqueda semántica usando LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        
        try:
            payload = {
                "query": query,
                "tenant_id": tenant_id,
                "limit": limit,
                "threshold": threshold
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/search",
                json=payload,
                headers=self._get_auth_headers(tenant_id)
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("results", [])
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in semantic search: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error in semantic search: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def store_document(
        self,
        doc_id: str, # Changed signature
        text: str,   # Changed signature (content -> text)
        metadata: Dict[str, Any],
        tenant_id: str # Changed signature (Optional str = None -> str)
    ) -> bool: # Changed return type
        """Almacenar un solo documento en vector store usando LangChain service."""
        
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        
        try:
            payload = {
                "doc_id": doc_id, # Added doc_id to payload
                "text": text,     # Changed content to text in payload
                "metadata": metadata,
                "tenant_id": tenant_id # No longer uses DEFAULT_TENANT fallback here, expecting explicit tenant_id
            }
            
            headers = self._get_auth_headers(tenant_id)
            
            response = await self.http_client.post(
                f"{self.base_url}/documents/add-single", # Correct endpoint
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("success", False) # Changed return logic
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error storing document {doc_id}: {str(e)}") # Added doc_id to log
            raise
        except Exception as e:
            logger.error(f"Error storing document {doc_id}: {str(e)}") # Added doc_id to log
            raise
    
    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def health_check(self) -> Dict[str, Any]:
        """Verificar estado del LangChain service"""
        
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        
        try:
            response = await self.http_client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error(f"LangChain health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }

    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def add_documents(self, tenant_id: str, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        """Añade documentos en batch al vector store."""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")

        try:
            payload = {
                "tenant_id": tenant_id or settings.DEFAULT_TENANT,
                "doc_id": str(uuid.uuid4()),  # Generate a doc_id for batch
                "texts": texts,
                "metadatas": metadatas
            }
            response = await self.http_client.post(
                f"{self.base_url}/documents/add",
                json=payload,
                headers=self._get_auth_headers(tenant_id)
            )
            response.raise_for_status()
            # Assuming success is True if no error, or based on response content
            return response.json().get("success", True)
        except httpx.HTTPError as e:
            logger.error(f"HTTP error adding documents: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error adding documents: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def delete_document(self, tenant_id: str, doc_id: str) -> bool:
        """Elimina un documento del vector store."""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")

        try:
            headers = self._get_auth_headers(tenant_id)
            response = await self.http_client.delete(
                f"{self.base_url}/documents/{tenant_id}/{doc_id}",
                headers=headers
            )
            response.raise_for_status()
            return response.json().get("success", False)
        except httpx.HTTPError as e:
            logger.error(f"HTTP error deleting document {doc_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def chunk_text(self, text: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Divide texto en chunks usando el microservicio LangChain."""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        try:
            payload = {"text": text, "tenant_id": tenant_id or settings.DEFAULT_TENANT}
            headers = self._get_auth_headers(tenant_id)
            response = await self.http_client.post(f"{self.base_url}/chunk", json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            return result.get("chunks", [{"text": text}])
        except httpx.HTTPError as e:
            logger.error(f"HTTP error chunking text: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def get_collection_info(self, tenant_id: str) -> Dict[str, Any]:
        """Obtiene información sobre la colección del vector store."""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        try:
            # Assuming tenant_id might be a query parameter for GET requests
            params = {"tenant_id": tenant_id}
            response = await self.http_client.get(f"{self.base_url}/vectorstore/info", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting collection info for tenant {tenant_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting collection info for tenant {tenant_id}: {str(e)}")
            raise

    @retry(
        stop=stop_after_attempt(settings.LANGCHAIN_CLIENT_RETRY_ATTEMPTS if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_ATTEMPTS') else 3),
        wait=wait_exponential(
            multiplier=settings.LANGCHAIN_CLIENT_RETRY_MULTIPLIER if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MULTIPLIER') else 1,
            min=settings.LANGCHAIN_CLIENT_RETRY_MIN_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MIN_WAIT') else 1,
            max=settings.LANGCHAIN_CLIENT_RETRY_MAX_WAIT if hasattr(settings, 'LANGCHAIN_CLIENT_RETRY_MAX_WAIT') else 10
        ),
        retry=retry_if_exception(should_retry_exception),
        reraise=True
    )
    async def extract_entities(self, text: str, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Extract named entities from text using LangChain service."""
        if not self.http_client:
            raise RuntimeError("HTTP client not provided to LangChainClient.")
        
        try:
            payload = {"text": text}
            headers = self._get_auth_headers(tenant_id)
            
            response = await self.http_client.post(
                f"{self.base_url}/llm/extract-entities",
                json=payload,
                headers=headers
            )
            
            response.raise_for_status()
            result = response.json()
            
            return result.get("entities", [])
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error extracting entities: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error extracting entities: {str(e)}")
            return []