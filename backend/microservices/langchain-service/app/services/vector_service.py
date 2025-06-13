"""
LangChain-based Vector Service using Qdrant
"""
import logging
from typing import List, Dict, Any, Optional
from uuid import uuid4

from langchain_community.vectorstores import Qdrant
from langchain_core.documents import Document
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.config import settings
from app.core.langchain_config import LangChainManager

logger = logging.getLogger(__name__)


class VectorService:
    """Servicio para gestión de vectores usando LangChain y Qdrant"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.collection_name = f"documents_{self.tenant_id}"
        
        # Inicializar componentes LangChain
        self.client = LangChainManager.get_qdrant_client()
        self.embeddings = LangChainManager.get_embeddings()
        
        # Inicializar colección
        self._ensure_collection_exists()
        
        logger.info(f"VectorService initialized for tenant: {self.tenant_id}")
    
    def _ensure_collection_exists(self):
        """Asegura que la colección existe en Qdrant con las dimensiones correctas"""
        try:
            # Verificar y recrear colección si hay conflicto de dimensiones
            collection_ok = self._recreate_collection_if_needed()
            
            if not collection_ok:
                raise Exception("Failed to ensure collection has correct dimensions")
            
            # Verificar si necesitamos crear la colección
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                # Crear nueva colección con dimensiones dinámicas
                embedding_dimensions = self._get_embedding_dimensions()
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=embedding_dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info(f"Colección Qdrant '{self.collection_name}' creada exitosamente con {embedding_dimensions} dimensiones")
            else:
                logger.debug(f"Colección Qdrant '{self.collection_name}' ya existe con dimensiones correctas")
                
        except Exception as e:
            logger.error(f"Error al verificar/crear colección {self.collection_name}: {str(e)}")
            raise
    
    def get_vectorstore(self) -> Qdrant:
        """Obtiene instancia del vectorstore LangChain"""
        return LangChainManager.create_vectorstore(self.collection_name)
    
    def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> bool:
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
            
            # Crear vectorstore
            vectorstore = self.get_vectorstore()
            
            # Generar IDs únicos para cada documento
            ids = [str(uuid4()) for _ in texts]
            
            # Añadir documentos al vectorstore
            vectorstore.add_texts(
                texts=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Successfully added {len(texts)} documents to vector store")
            return True
            
        except Exception as e:
            logger.error(f"Error adding documents to vector store: {str(e)}")
            return False
    
    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> bool:
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
            
            vectorstore = self.get_vectorstore()
            vectorstore.add_texts(
                texts=[text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            
            logger.info(f"Successfully added document {doc_id} to vector store")
            return True
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {str(e)}")
            return False
    
    def search_similar(self, query: str, limit: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """
        Busca documentos similares al query.
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            filter_dict: Filtros adicionales para los metadatos
            
        Returns:
            Lista de documentos similares con scores
        """
        try:
            logger.debug(f"Searching for similar documents with query: {query[:100]}...")
            
            vectorstore = self.get_vectorstore()
            
            # Realizar búsqueda de similitud
            if filter_dict:
                # Búsqueda con filtros
                docs = vectorstore.similarity_search_with_score(
                    query=query,
                    k=limit,
                    filter=filter_dict
                )
            else:
                # Búsqueda sin filtros
                docs = vectorstore.similarity_search_with_score(
                    query=query,
                    k=limit
                )
            
            # Formatear resultados
            results = []
            for doc, score in docs:
                result = {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score)
                }
                results.append(result)
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error searching similar documents: {error_msg}")
            
            # Check for dimension mismatch and try to fix it
            if "dimension error" in error_msg.lower() or "expected dim" in error_msg.lower():
                logger.warning("Detected vector dimension mismatch. Attempting to recreate collection...")
                try:
                    collection_recreated = self._recreate_collection_if_needed()
                    if collection_recreated:
                        logger.info("Collection recreated successfully. Please try your search again.")
                    else:
                        logger.error("Failed to recreate collection with correct dimensions")
                except Exception as recreate_error:
                    logger.error(f"Error recreating collection: {str(recreate_error)}")
            
            return []
    
    def search_by_document_ids(self, doc_ids: List[str], query: str, limit: int = 5) -> List[Dict[str, Any]]:
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
            # Filtrar por documentos específicos
            filter_dict = {
                "doc_id": {"$in": doc_ids}
            }
            
            return self.search_similar(query, limit, filter_dict)
            
        except Exception as e:
            logger.error(f"Error searching by document IDs: {str(e)}")
            return []
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Elimina un documento del vector store.
        
        Args:
            doc_id: ID del documento a eliminar
            
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            logger.debug(f"Deleting document {doc_id} from vector store")
            
            # Buscar y eliminar puntos con el doc_id específico
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="metadata.doc_id",
                                match=models.MatchValue(value=doc_id)
                            )
                        ]
                    )
                )
            )
            
            logger.info(f"Successfully deleted document {doc_id} from vector store")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {str(e)}")
            return False
    
    def get_collection_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre la colección.
        
        Returns:
            Diccionario con información de la colección
        """
        try:
            collection_info = self.client.get_collection(self.collection_name)
            
            return {
                "name": self.collection_name,
                "vectors_count": collection_info.vectors_count,
                "indexed_vectors_count": collection_info.indexed_vectors_count,
                "status": collection_info.status
            }
            
        except Exception as e:
            logger.error(f"Error getting collection info: {str(e)}")
            return {}
    
    def clear_collection(self) -> bool:
        """
        Limpia todos los documentos de la colección.
        
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            logger.warning(f"Clearing all documents from collection {self.collection_name}")
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="metadata.tenant_id",
                                match=models.MatchValue(value=self.tenant_id)
                            )
                        ]
                    )
                )
            )
            
            logger.info(f"Successfully cleared collection {self.collection_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error clearing collection: {str(e)}")
            return False
    
    def _get_embedding_dimensions(self) -> int:
        """
        Determina las dimensiones del modelo de embeddings actual.
        
        Returns:
            Número de dimensiones del vector de embeddings
        """
        try:
            # Generar un embedding de prueba para determinar dimensiones
            test_embedding = self.embeddings.embed_query("test")
            dimensions = len(test_embedding)
            logger.info(f"Detected embedding dimensions: {dimensions}")
            return dimensions
        except Exception as e:
            logger.error(f"Error detecting embedding dimensions: {str(e)}")
            # Fallback para nomic-embed-text
            return 768
    
    def _recreate_collection_if_needed(self) -> bool:
        """
        Recrea la colección si hay conflicto de dimensiones.
        
        Returns:
            True si la colección fue recreada o está OK, False en caso de error
        """
        try:
            # Verificar si la colección existe
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                logger.info(f"Collection {self.collection_name} does not exist, will be created")
                return True
            
            # Obtener info de la colección existente
            collection_info = self.client.get_collection(self.collection_name)
            existing_dimensions = collection_info.config.params.vectors.size
            required_dimensions = self._get_embedding_dimensions()
            
            if existing_dimensions != required_dimensions:
                logger.warning(f"Dimension mismatch: existing={existing_dimensions}, required={required_dimensions}")
                logger.warning(f"Recreating collection {self.collection_name}")
                
                # Eliminar colección existente
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted collection {self.collection_name}")
                
                # Crear nueva colección con dimensiones correctas
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=required_dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
                logger.info(f"Recreated collection {self.collection_name} with {required_dimensions} dimensions")
                return True
            else:
                logger.debug(f"Collection {self.collection_name} has correct dimensions: {existing_dimensions}")
                return True
                
        except Exception as e:
            logger.error(f"Error recreating collection: {str(e)}")
            return False