"""
LangChain-based Embedding Service
"""
import logging
from typing import List, Dict, Any
from langchain.schema import Document

from app.core.config import settings
from app.core.langchain_config import LangChainManager
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Servicio para la generación y gestión de embeddings usando LangChain"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.embeddings = LangChainManager.get_embeddings()
        self.text_splitter = LangChainManager.get_text_splitter()
        
        # Mantener vector service para retrocompatibilidad
        self.vector_service = VectorService(tenant_id)
        
        logger.info(f"EmbeddingService initialized for tenant: {self.tenant_id}")
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para una lista de textos usando LangChain.
        
        Args:
            texts: Lista de textos para generar embeddings
            
        Returns:
            Lista de vectores de embeddings
        """
        try:
            logger.debug(f"Generating embeddings for {len(texts)} texts")
            embeddings = self.embeddings.embed_documents(texts)
            logger.debug(f"Generated {len(embeddings)} embeddings successfully")
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    def get_embedding(self, text: str) -> List[float]:
        """
        Genera embedding para un solo texto.
        
        Args:
            text: Texto para generar embedding
            
        Returns:
            Vector de embedding
        """
        try:
            logger.debug(f"Generating embedding for text of length: {len(text)}")
            embedding = self.embeddings.embed_query(text)
            logger.debug("Embedding generated successfully")
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Divide texto en chunks usando LangChain.
        
        Args:
            text: Texto a dividir
            
        Returns:
            Lista de diccionarios con chunks de texto
        """
        try:
            logger.debug(f"Chunking text of length: {len(text)}")
            chunks = self.text_splitter.split_text(text)
            
            chunked_data = []
            for i, chunk in enumerate(chunks):
                chunked_data.append({
                    "text": chunk,
                    "chunk_index": i,
                    "chunk_size": len(chunk)
                })
            
            logger.debug(f"Text split into {len(chunked_data)} chunks")
            return chunked_data
            
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise
    
    def create_documents(self, texts: List[str], metadatas: List[Dict] = None) -> List[Document]:
        """
        Crea documentos LangChain con metadatos.
        
        Args:
            texts: Lista de textos
            metadatas: Lista opcional de metadatos
            
        Returns:
            Lista de documentos LangChain
        """
        if metadatas is None:
            metadatas = [{}] * len(texts)
        
        documents = []
        for text, metadata in zip(texts, metadatas):
            # Agregar información del tenant a los metadatos
            metadata = metadata.copy()
            metadata["tenant_id"] = self.tenant_id
            
            doc = Document(page_content=text, metadata=metadata)
            documents.append(doc)
        
        logger.debug(f"Created {len(documents)} LangChain documents")
        return documents
    
    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> bool:
        """
        Procesa y añade un documento al vector store.
        
        Args:
            doc_id: ID único del documento
            text: Contenido del texto
            metadata: Metadatos adicionales
            
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            # Chunking del texto
            chunks_data = self.chunk_text(text)
            
            # Preparar textos y metadatos para vectorización
            chunk_texts = [chunk["text"] for chunk in chunks_data]
            chunk_metadatas = []
            
            for i, chunk in enumerate(chunks_data):
                chunk_metadata = {
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "tenant_id": self.tenant_id,
                    **chunk
                }
                if metadata:
                    chunk_metadata.update(metadata)
                chunk_metadatas.append(chunk_metadata)
            
            # Usar vector service para añadir al vectorstore
            success = self.vector_service.add_documents(chunk_texts, chunk_metadatas)
            
            if success:
                logger.info(f"Document {doc_id} processed and added successfully with {len(chunk_texts)} chunks")
            else:
                logger.error(f"Failed to add document {doc_id} to vector store")
                
            return success
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {str(e)}")
            return False
    
    def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Busca documentos similares usando el query.
        
        Args:
            query: Consulta de búsqueda
            limit: Número máximo de resultados
            
        Returns:
            Lista de documentos similares con scores
        """
        try:
            logger.debug(f"Searching for similar documents with query: {query[:100]}...")
            
            # Usar vector service para búsqueda
            results = self.vector_service.search_similar(query, limit)
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar documents: {str(e)}")
            return []