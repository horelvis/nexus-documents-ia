"""
Vector Service using LangChain microservice HTTP client
"""
import logging
from typing import List, Dict, Any, Optional
from app.core.config import settings
from app.services.langchain_client import LangChainClient

logger = logging.getLogger(__name__)


class VectorService:
    """Servicio para gestión de vectores usando el microservicio LangChain"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
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
            async with LangChainClient() as client:
                success = await client.add_documents(self.tenant_id, texts, metadatas)
            
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
            async with LangChainClient() as client:
                success = await client.add_document(self.tenant_id, doc_id, text, metadata)
            
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
            async with LangChainClient() as client:
                results = await client.search_similar(self.tenant_id, query, limit)
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar documents: {str(e)}")
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
            async with LangChainClient() as client:
                results = await client.search_similar(self.tenant_id, query, limit, doc_ids)
            
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
            async with LangChainClient() as client:
                success = await client.delete_document(self.tenant_id, doc_id)
            
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
            async with LangChainClient() as client:
                info = await client.get_collection_info(self.tenant_id)
            
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