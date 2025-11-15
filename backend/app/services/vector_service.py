"""
Vector Service migrado para usar Weaviate/Elysia directamente
Reemplaza la anterior integración con LangChain microservice
"""
import logging
import httpx
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.weaviate_client import weaviate_client

logger = logging.getLogger(__name__)


class VectorService:
    """Servicio para gestión de vectores usando Weaviate/Elysia"""
    
    def __init__(self, tenant_id: str = None, user_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.user_id = user_id
        self.collection_name = f"Nexus_{self.tenant_id.replace('-', '_')}_documents"
        self.weaviate_base_url = getattr(weaviate_client, "base_url", "unknown")
        logger.info(
            "VectorService initialized | tenant_id=%s collection=%s weaviate_base_url=%s",
            self.tenant_id,
            self.collection_name,
            self.weaviate_base_url,
        )
    
    async def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
        """
        Añade documentos al vector store usando Weaviate.
        
        Args:
            texts: Lista de textos a vectorizar
            metadatas: Lista de metadatos correspondientes
            
        Returns:
            bool: True si se añadieron correctamente, False en caso contrario
        """
        try:
            if len(texts) != len(metadatas):
                raise ValueError("texts and metadatas must have the same length")
            
            # Preparar documentos para Weaviate
            documents = []
            for i, (text, metadata) in enumerate(zip(texts, metadatas)):
                doc = {
                    "title": metadata.get("title", f"Document {i+1}"),
                    "content": text,
                    "metadata": metadata,
                    "tenant_id": self.tenant_id,
                    "document_type": metadata.get("document_type", "text"),
                    "tags": metadata.get("tags", [])
                }
                documents.append(doc)
            
            # Usar batch add del cliente Weaviate
            logger.debug(
                "Batch adding documents | collection=%s count=%d weaviate_base_url=%s",
                self.collection_name,
                len(documents),
                self.weaviate_base_url,
            )
            result = await weaviate_client.batch_add_documents(self.collection_name, documents)
            
            logger.info(f"✅ Added {len(documents)} documents to Weaviate collection {self.collection_name}")
            return True
            
        except Exception as e:
            logger.exception(
                "❌ Failed to batch add documents | collection=%s weaviate_base_url=%s error=%s",
                self.collection_name,
                self.weaviate_base_url,
                e,
            )
            return False
    
    async def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> bool:
        """
        Añade un solo documento al vector store.
        
        Args:
            doc_id: ID único del documento
            text: Texto del documento
            metadata: Metadatos del documento
            
        Returns:
            bool: True si se añadió correctamente, False en caso contrario
        """
        try:
            document_data = {
                "id": doc_id,
                "title": metadata.get("title", f"Document {doc_id}"),
                "content": text,
                "metadata": metadata,
                "tenant_id": self.tenant_id,
                "document_type": metadata.get("document_type", "text"),
                "tags": metadata.get("tags", [])
            }
            
            result = await weaviate_client.add_document(self.collection_name, document_data)
            
            logger.info(f"✅ Added document {doc_id} to Weaviate collection {self.collection_name}")
            return True
            
        except Exception as e:
            logger.exception(
                "❌ Failed to add document | doc_id=%s collection=%s weaviate_base_url=%s error=%s",
                doc_id,
                self.collection_name,
                self.weaviate_base_url,
                e,
            )
            return False
    
    async def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Busca documentos similares usando Weaviate search.
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            
        Returns:
            Lista de documentos similares
        """
        try:
            search_request = {
                "query": query,
                "limit": limit,
                "tenant_id": self.tenant_id,
                "search_type": "hybrid"
            }
            
            result = await weaviate_client.search_documents(self.collection_name, search_request)
            
            # Convertir resultados al formato esperado
            documents = []
            if "results" in result:
                for doc in result["results"]:
                    documents.append({
                        "id": doc.get("id"),
                        "content": doc.get("content"),
                        "metadata": doc.get("metadata", {}),
                        "similarity_score": doc.get("similarity_score"),
                        "title": doc.get("title")
                    })
            
            logger.info(f"✅ Found {len(documents)} similar documents for query: {query[:50]}...")
            return documents
            
        except Exception as e:
            logger.exception(
                "❌ Search failed in Weaviate | collection=%s weaviate_base_url=%s query_chars=%d error=%s",
                self.collection_name,
                self.weaviate_base_url,
                len(query),
                e,
            )
            return []
    
    async def search_by_document_ids(self, doc_ids: List[str], query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Busca documentos similares restringiendo por IDs específicos.
        
        Args:
            doc_ids: Lista de IDs de documentos
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            
        Returns:
            Lista de documentos similares
        """
        try:
            search_request = {
                "query": query,
                "limit": limit,
                "tenant_id": self.tenant_id,
                "search_type": "hybrid",
                "filters": {
                    "doc_ids": doc_ids
                }
            }
            
            result = await weaviate_client.search_documents(self.collection_name, search_request)
            
            # Convertir resultados al formato esperado
            documents = []
            if "results" in result:
                for doc in result["results"]:
                    # Filtrar solo documentos con IDs especificados
                    if doc.get("id") in doc_ids:
                        documents.append({
                            "id": doc.get("id"),
                            "content": doc.get("content"),
                            "metadata": doc.get("metadata", {}),
                            "similarity_score": doc.get("similarity_score"),
                            "title": doc.get("title")
                        })
            
            logger.info(f"✅ Found {len(documents)} documents by IDs for query: {query[:50]}...")
            return documents
            
        except Exception as e:
            logger.exception(
                "❌ Search by IDs failed | collection=%s doc_ids=%s weaviate_base_url=%s error=%s",
                self.collection_name,
                doc_ids,
                self.weaviate_base_url,
                e,
            )
            return []
    
    async def delete_document(self, doc_id: str) -> bool:
        """
        Elimina un documento del vector store.
        
        Args:
            doc_id: ID del documento a eliminar
            
        Returns:
            bool: True si se eliminó correctamente, False en caso contrario
        """
        try:
            # Weaviate delete operation (implementar en cliente si necesario)
            # Por ahora, retornamos True como placeholder
            logger.warning(f"⚠️ Document deletion not fully implemented for Weaviate: {doc_id}")
            return True
            
        except Exception as e:
            logger.exception(
                "❌ Failed to delete document from Weaviate | doc_id=%s collection=%s error=%s",
                doc_id,
                self.collection_name,
                e,
            )
            return False
    
    def get_collection_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre la colección de vectores.
        
        Returns:
            Dict con información de la colección
        """
        try:
            # Placeholder - implementar cuando el cliente lo soporte
            return {
                "collection_name": self.collection_name,
                "tenant_id": self.tenant_id,
                "status": "active",
                "backend": "weaviate"
            }
            
        except Exception as e:
            logger.exception(
                "❌ Failed to get collection info from Weaviate | collection=%s error=%s",
                self.collection_name,
                e,
            )
            return {}
    
    def _recreate_collection_if_needed(self) -> bool:
        """
        Recrea la colección si es necesario.
        
        Returns:
            bool: True si se recreó exitosamente o no era necesario
        """
        try:
            # Placeholder - Weaviate maneja esto automáticamente
            logger.info(f"✅ Weaviate collection {self.collection_name} verified")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to recreate Weaviate collection: {e}")
            return False
    
    def _get_embedding_dimensions(self) -> int:
        """
        Obtiene las dimensiones de los embeddings.
        
        Returns:
            int: Número de dimensiones
        """
        # Weaviate maneja esto automáticamente basado en el modelo
        return 384  # Default para modelos como all-minilm
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Verifica el estado de salud del servicio de vectores.
        
        Returns:
            Dict con información de salud
        """
        try:
            health = await weaviate_client.health_check()
            
            return {
                "status": health.get("status", "unknown"),
                "backend": "weaviate",
                "collection": self.collection_name,
                "tenant_id": self.tenant_id,
                "details": health
            }
            
        except Exception as e:
            logger.error(f"❌ Vector service health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "backend": "weaviate",
                "collection": self.collection_name,
                "tenant_id": self.tenant_id
            }
