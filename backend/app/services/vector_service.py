"""
Vector Service using LangChain microservice HTTP client
"""
import logging
import httpx # Added httpx import
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.langchain_client import LangChainClient

logger = logging.getLogger(__name__)


class VectorService:
    """Servicio para gestión de vectores usando el microservicio LangChain"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.user_id = user_id
        logger.info(f"VectorService initialized for tenant: {self.tenant_id}")
    
    async def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        """
        Añade documentos al vector store.
        
        Args:
            texts: Lista de textos a vectorizar
            metadatas: Lista de metadatos correspondientes
            
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            if len(texts) != len(metadatas):
                raise ValueError("Texts and metadatas must have the same length")
            
            logger.debug(f"Adding {len(texts)} documents to vector store")
            
            # Usar cliente HTTP para añadir documentos
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client, tenant_id=self.tenant_id, user_id=self.user_id)
                success = await lc_client.add_documents(tenant_id=self.tenant_id, texts=texts, metadatas=metadatas)
            
            if success:
                logger.info(f"Successfully added {len(texts)} documents to vector store")
            else:
                logger.error("Failed to add documents to vector store")
                
            return success
            
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {str(e)}")
            return False
    
    async def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> bool:
        """
        Añade un solo documento al vector store.
        
        Args:
            doc_id: ID único del documento
            text: Contenido del texto
            metadata: Metadatos del documento
            
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            logger.debug(f"Adding single document {doc_id} to vector store")
            
            # Agregar tenant_id a metadatos
            metadata = metadata.copy()
            metadata["tenant_id"] = self.tenant_id
            metadata["doc_id"] = doc_id
            
            # Usar cliente HTTP para añadir documento
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client, tenant_id=self.tenant_id, user_id=self.user_id)
                # Call updated LangChainClient.store_document signature:
                # store_document(self, doc_id: str, text: str, metadata: Dict[str, Any], tenant_id: str) -> bool
                success = await lc_client.store_document(doc_id=doc_id, text=text, metadata=metadata, tenant_id=self.tenant_id)
            
            if success:
                logger.info(f"Successfully added document {doc_id} to vector store")
            else:
                logger.error(f"Failed to add document {doc_id} to vector store")
                
            return success
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {str(e)}")
            return False
    
    async def search_similar(self, query: str, limit: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Busca documentos similares al query.
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            filter_dict: Filtros adicionales para los metadatos (no implementado en HTTP client)
            
        Returns:
            Lista de documentos similares con scores
        """
        try:
            logger.debug(f"Searching for similar documents with query: {query[:100]}...")
            
            # Usar cliente HTTP para búsqueda
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                results = await lc_client.search_similar(tenant_id=self.tenant_id, query=query, limit=limit)
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error searching similar documents: {error_msg}")
            
            # Check if the error is related to missing embedding model
            if "model" in error_msg.lower() and ("not found" in error_msg.lower() or "404" in error_msg):
                logger.warning("Detected missing embedding model. Attempting to auto-fix...")
                await self._ensure_embedding_model()
                
            return []
    
    async def search_by_document_ids(self, doc_ids: List[str], query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Busca dentro de documentos específicos.
        
        Args:
            doc_ids: Lista de IDs de documentos donde buscar
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            
        Returns:
            Lista de resultados filtrados por documento
        """
        try:
            # Usar cliente HTTP para búsqueda con filtro de documentos
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                # LangChainClient.search_similar does not support doc_ids filter directly
                logger.warning("LangChainClient.search_similar does not support doc_ids filter. Calling without it.")
                results = await lc_client.search_similar(tenant_id=self.tenant_id, query=query, limit=limit)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching by document IDs: {str(e)}")
            return []
    
    async def delete_document(self, doc_id: str) -> bool:
        """
        Elimina un documento del vector store.
        
        Args:
            doc_id: ID del documento a eliminar
            
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            logger.debug(f"Deleting document {doc_id} from vector store")
            
            # Usar cliente HTTP para eliminar documento
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                success = await lc_client.delete_document(tenant_id=self.tenant_id, doc_id=doc_id)
            
            if success:
                logger.info(f"Successfully deleted document {doc_id} from vector store")
            else:
                logger.error(f"Failed to delete document {doc_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {str(e)}")
            return False
    
    async def get_collection_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre la colección.
        
        Returns:
            Diccionario con información de la colección
        """
        try:
            # Usar cliente HTTP para obtener información de colección
            # Usar cliente HTTP para obtener información de colección
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                info = await lc_client.get_collection_info(tenant_id=self.tenant_id)
            
            return info
            
        except Exception as e:
            logger.error(f"Error getting collection info: {str(e)}")
            return {}
    
    async def clear_collection(self) -> bool:
        """
        Limpia todos los documentos de la colección.
        
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            logger.warning(f"Clearing all documents from collection for tenant {self.tenant_id}")
            
            # NOTE: Esta funcionalidad requeriría un endpoint específico en el microservicio
            # Por ahora, retornamos False como no implementado
            logger.error("clear_collection not implemented in microservice client")
            return False
            
        except Exception as e:
            logger.error(f"Error clearing collection: {str(e)}")
            return False
    
    async def _ensure_embedding_model(self) -> bool:
        """
        Ensures the embedding model is available in Ollama.
        Calls the Ollama service to automatically pull the model if missing.
        
        Returns:
            True if model is available, False otherwise
        """
        try:
            logger.info("Checking and ensuring embedding model is available...")
            
            ollama_url = settings.OLLAMA_BASE_URL.replace("ollama-service:11434", "localhost:8004")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # First check if model is available
                check_response = await client.get(f"{ollama_url}/api/v1/models/check-embedding")
                
                if check_response.status_code == 200:
                    data = check_response.json()
                    if data.get("available", False):
                        logger.info("Embedding model is already available")
                        return True
                
                # Model not available, try to ensure required models
                logger.info("Embedding model not available. Triggering auto-download...")
                ensure_response = await client.post(f"{ollama_url}/api/v1/models/ensure-required")
                
                if ensure_response.status_code == 200:
                    result_data = ensure_response.json()
                    embedding_result = result_data.get("results", {}).get(settings.EMBEDDING_MODEL)
                    
                    if embedding_result == "available":
                        logger.info("Successfully ensured embedding model is available")
                        return True
                    else:
                        logger.error(f"Failed to ensure embedding model: {embedding_result}")
                        return False
                else:
                    logger.error(f"Failed to trigger model download: {ensure_response.status_code}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error ensuring embedding model: {str(e)}")
            return False
    
    async def check_system_health(self) -> Dict[str, Any]:
        """
        Performs a comprehensive health check of the vector system.
        
        Returns:
            Dictionary with health status information
        """
        try:
            health_info = {
                "vector_service": "healthy",
                "langchain_service": "unknown",
                "ollama_service": "unknown",
                "embedding_model": "unknown",
                "issues": []
            }
            
            # Check LangChain service
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    lc_client = LangChainClient(http_client=client)
                    collection_info = await lc_client.get_collection_info(tenant_id=self.tenant_id)
                    health_info["langchain_service"] = "healthy"
            except Exception as e:
                health_info["langchain_service"] = "unhealthy"
                health_info["issues"].append(f"LangChain service error: {str(e)}")
            
            # Check Ollama service and embedding model
            try:
                ollama_url = settings.OLLAMA_BASE_URL.replace("ollama-service:11434", "localhost:8004")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    # Check service status
                    status_response = await client.get(f"{ollama_url}/api/v1/status")
                    if status_response.status_code == 200:
                        health_info["ollama_service"] = "healthy"
                        
                        # Check embedding model
                        embedding_response = await client.get(f"{ollama_url}/api/v1/models/check-embedding")
                        if embedding_response.status_code == 200:
                            embedding_data = embedding_response.json()
                            health_info["embedding_model"] = "available" if embedding_data.get("available") else "missing"
                            if not embedding_data.get("available"):
                                health_info["issues"].append(f"Embedding model '{settings.EMBEDDING_MODEL}' is not available")
                        else:
                            health_info["embedding_model"] = "check_failed"
                            health_info["issues"].append("Could not check embedding model status")
                    else:
                        health_info["ollama_service"] = "unhealthy"
                        health_info["issues"].append("Ollama service is not responding")
            except Exception as e:
                health_info["ollama_service"] = "unreachable"
                health_info["issues"].append(f"Cannot reach Ollama service: {str(e)}")
            
            # Overall health assessment
            if len(health_info["issues"]) == 0:
                health_info["overall_status"] = "healthy"
            elif health_info["embedding_model"] == "missing":
                health_info["overall_status"] = "degraded"
                health_info["auto_fix_available"] = True
            else:
                health_info["overall_status"] = "unhealthy"
            
            return health_info
            
        except Exception as e:
            logger.error(f"Error checking system health: {str(e)}")
            return {
                "overall_status": "error",
                "vector_service": "error",
                "error": str(e)
            }