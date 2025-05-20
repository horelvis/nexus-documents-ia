import logging
import numpy as np
import requests
import json
import os
import time
from typing import List, Dict, Any, Optional, Union

from app.core.config import settings
from app.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Servicio para la generación y gestión de embeddings de texto"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        self.embedding_dim = 1536  # Dimensión del vector de embedding
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP
        
        # Inicializar el servicio vectorial
        self.vector_service = VectorService(tenant_id)
    
    def get_embedding(self, text: str) -> np.ndarray:
        """
        Genera el embedding para un texto dado usando Ollama.
        
        Args:
            text: Texto para generar embedding
            
        Returns:
            Vector numpy con el embedding
        """
        # Endpoint para embeddings de Ollama
        api_url = f"{self.base_url}/api/embeddings"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "prompt": text,
        }
        
        try:
            start_time = time.time()
            response = requests.post(api_url, headers=headers, json=data)
            elapsed_time = time.time() - start_time
            
            if response.status_code != 200:
                logger.error(f"Embedding API error: {response.status_code} - {response.text}")
                # Devolver un vector de ceros en caso de error
                return np.zeros(self.embedding_dim)
            
            result = response.json()
            logger.debug(f"Embedding generated in {elapsed_time:.2f}s")
            
            # Extraer el vector de embedding
            embedding_vector = np.array(result["embedding"], dtype=np.float32)
            return embedding_vector
            
        except Exception as e:
            logger.exception(f"Error generating embedding: {str(e)}")
            return np.zeros(self.embedding_dim)
    
    def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Divide el texto en chunks más pequeños para procesamiento, 
        manteniendo metadatos adicionales.
        
        Args:
            text: Texto completo a dividir
            
        Returns:
            Lista de dictionaries con texto de chunk y metadatos
        """
        if not text:
            return []
        
        # Dividir el texto en párrafos
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = ""
        
        for paragraph in paragraphs:
            # Si el párrafo es más largo que el tamaño de chunk, dividirlo
            if len(paragraph) > self.chunk_size:
                # Añadir el chunk actual si existe
                if current_chunk:
                    chunks.append({
                        "text": current_chunk,
                        "metadata": {"is_paragraph_boundary": True}
                    })
                    current_chunk = ""
                
                # Dividir el párrafo largo en chunks
                words = paragraph.split()
                temp_chunk = ""
                
                for word in words:
                    if len(temp_chunk) + len(word) + 1 <= self.chunk_size:
                        if temp_chunk:
                            temp_chunk += " "
                        temp_chunk += word
                    else:
                        chunks.append({
                            "text": temp_chunk,
                            "metadata": {"is_paragraph_boundary": False}
                        })
                        # Mantener solapamiento
                        last_words = " ".join(temp_chunk.split()[-self.chunk_overlap//10:])
                        temp_chunk = last_words
                        if temp_chunk:
                            temp_chunk += " "
                        temp_chunk += word
                
                # Añadir el último chunk si existe
                if temp_chunk:
                    chunks.append({
                        "text": temp_chunk,
                        "metadata": {"is_paragraph_boundary": False}
                    })
            else:
                # Si añadir el párrafo excede el tamaño del chunk, guardar el actual y empezar uno nuevo
                if len(current_chunk) + len(paragraph) + 2 > self.chunk_size:
                    chunks.append({
                        "text": current_chunk,
                        "metadata": {"is_paragraph_boundary": True}
                    })
                    current_chunk = paragraph
                else:
                    # Añadir párrafo al chunk actual
                    if current_chunk:
                        current_chunk += "\n\n"
                    current_chunk += paragraph
        
        # Añadir el último chunk si existe
        if current_chunk:
            chunks.append({
                "text": current_chunk,
                "metadata": {"is_paragraph_boundary": True}
            })
        
        return chunks
    
    def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any]) -> bool:
        """
        Añade un documento al almacén de vectores.
        
        Args:
            doc_id: ID único del documento
            text: Texto completo del documento
            metadata: Metadatos asociados al documento
            
        Returns:
            True si se añadió correctamente, False en caso contrario
        """
        try:
            # Dividir el texto en chunks
            chunks_data = self.chunk_text(text)
            if not chunks_data:
                logger.warning(f"No chunks generated for document {doc_id}")
                return False
            
            # Generar embeddings para cada chunk
            vectors = []
            chunk_metadatas = []
            
            for i, chunk_data in enumerate(chunks_data):
                chunk_text = chunk_data["text"]
                chunk_meta = chunk_data["metadata"]
                
                embedding = self.get_embedding(chunk_text)
                vectors.append(embedding)
                
                # Crear metadatos para el chunk
                chunk_metadata = metadata.copy()
                chunk_metadata.update(chunk_meta)
                chunk_metadata.update({
                    "doc_id": doc_id,
                    "chunk_id": i,
                    "chunk_text": chunk_text,
                    "total_chunks": len(chunks_data)
                })
                chunk_metadatas.append(chunk_metadata)
            
            # Añadir al índice vectorial
            point_ids = self.vector_service.add_document_vectors(
                doc_id=doc_id,
                vectors=vectors,
                metadatas=chunk_metadatas
            )
            
            logger.info(f"Added document {doc_id} with {len(chunks_data)} chunks to vector store")
            return True
            
        except Exception as e:
            logger.exception(f"Error adding document to vector store: {str(e)}")
            return False
    
    def search(
        self, 
        query: str, 
        limit: int = 5, 
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Realiza una búsqueda semántica en el almacén de vectores.
        
        Args:
            query: Texto de consulta
            limit: Número máximo de resultados
            filters: Filtros a aplicar sobre los metadatos
            
        Returns:
            Lista de resultados con metadatos y puntuaciones
        """
        try:
            # Generar embedding para la consulta
            query_embedding = self.get_embedding(query)
            
            # Buscar en el índice vectorial
            results = self.vector_service.search_similar(
                query_vector=query_embedding,
                limit=limit,
                filter_by=filters
            )
            
            return results
            
        except Exception as e:
            logger.exception(f"Error searching vector store: {str(e)}")
            return []
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Elimina un documento del almacén de vectores.
        
        Args:
            doc_id: ID del documento
            
        Returns:
            True si se eliminó correctamente, False en caso contrario
        """
        try:
            success = self.vector_service.delete_document_vectors(doc_id)
            if success:
                logger.info(f"Deleted document {doc_id} from vector store")
            
            return success
            
        except Exception as e:
            logger.exception(f"Error deleting document from vector store: {str(e)}")
            return False