"""
Embedding Service using LangChain microservice HTTP client
"""
import asyncio
import logging
from typing import List, Dict, Any
from app.core.config import settings
from app.services.langchain_client import LangChainClient

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Servicio para la generación y gestión de embeddings usando el microservicio LangChain"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        logger.info(f"EmbeddingService initialized for tenant: {self.tenant_id}")
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para una lista de textos usando el microservicio LangChain.
        
        Args:
            texts: Lista de textos para generar embeddings
            
        Returns:
            Lista de vectores de embeddings
        """
        try:
            logger.debug(f"Generating embeddings for {len(texts)} texts")
            async with LangChainClient() as client:
                embeddings = await client.generate_embeddings(texts)
            logger.debug(f"Generated {len(embeddings)} embeddings successfully")
            return embeddings
        except Exception as e:
            logger.error(f"Error generating embeddings: {str(e)}")
            raise
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Genera embedding para un solo texto.
        
        Args:
            text: Texto para generar embedding
            
        Returns:
            Vector de embedding
        """
        try:
            logger.debug(f"Generating embedding for text of length: {len(text)}")
            async with LangChainClient() as client:
                embedding = await client.generate_embedding(text)
            logger.debug("Embedding generated successfully")
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    async def chunk_text_async(self, text: str) -> List[Dict[str, Any]]:
        """
        Divide texto en chunks usando el microservicio LangChain.
        
        Args:
            text: Texto a dividir
            
        Returns:
            Lista de diccionarios con chunks de texto
        """
        try:
            logger.debug(f"Chunking text of length: {len(text)}")
            async with LangChainClient() as client:
                chunks = await client.chunk_text(text)
            logger.debug(f"Text split into {len(chunks)} chunks")
            return chunks
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise
    
    async def add_document_async(self, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> bool:
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
            chunks_data = await self.chunk_text_async(text)
            
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
            
            # Usar cliente HTTP para añadir al vectorstore
            async with LangChainClient() as client:
                success = await client.add_documents(self.tenant_id, chunk_texts, chunk_metadatas)
            
            if success:
                logger.info(f"Document {doc_id} processed and added successfully with {len(chunk_texts)} chunks")
            else:
                logger.error(f"Failed to add document {doc_id} to vector store")
                
            return success
            
        except Exception as e:
            logger.error(f"Error adding document {doc_id}: {str(e)}")
            return False
    
    async def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
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
            
            # Usar cliente HTTP para búsqueda
            async with LangChainClient() as client:
                results = await client.search_similar(self.tenant_id, query, limit)
            
            logger.debug(f"Found {len(results)} similar documents")
            return results
            
        except Exception as e:
            logger.error(f"Error searching similar documents: {str(e)}")
            return []
    
    async def delete_document_async(self, doc_id: str) -> bool:
        """
        Elimina un documento del vector store.
        
        Args:
            doc_id: ID del documento a eliminar
            
        Returns:
            True si fue exitoso, False en caso contrario
        """
        try:
            logger.debug(f"Deleting document {doc_id} from vector store")
            
            async with LangChainClient() as client:
                success = await client.delete_document(self.tenant_id, doc_id)
            
            if success:
                logger.info(f"Document {doc_id} deleted successfully from vector store")
            else:
                logger.error(f"Failed to delete document {doc_id} from vector store")
                
            return success
            
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {str(e)}")
            return False
    
    # Métodos síncronos para compatibilidad con DocumentService
    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """Versión síncrona de chunk_text"""
        try:
            return asyncio.run(self.chunk_text_async(text))
        except Exception as e:
            logger.error(f"Error in sync chunk_text: {str(e)}")
            return []
    
    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None) -> bool:
        """Versión síncrona de add_document"""
        try:
            return asyncio.run(self.add_document_async(doc_id, text, metadata))
        except Exception as e:
            logger.error(f"Error in sync add_document: {str(e)}")
            return False
    
    def delete_document(self, doc_id: str) -> bool:
        """Versión síncrona de delete_document"""
        try:
            return asyncio.run(self.delete_document_async(doc_id))
        except Exception as e:
            logger.error(f"Error in sync delete_document: {str(e)}")
            return False