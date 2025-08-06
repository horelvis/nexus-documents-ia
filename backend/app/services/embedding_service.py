"""
Embedding Service using CAG microservice HTTP client
"""
import asyncio
import logging
import httpx # Added httpx import
from typing import List, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Servicio para la generación y gestión de embeddings usando el microservicio LangChain"""
    
    def __init__(self, tenant_id: str = None):
        self.tenant_id = tenant_id or settings.DEFAULT_TENANT
        logger.info(f"EmbeddingService initialized for tenant: {self.tenant_id}")
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings para una lista de textos usando el microservicio CAG.
        
        Args:
            texts: Lista de textos para generar embeddings
            
        Returns:
            Lista de vectores de embeddings
        """
        try:
            logger.debug(f"Generating embeddings for {len(texts)} texts")
            # Increase timeout for large documents
            timeout = httpx.Timeout(60.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as http_client:
                headers = {
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                    "X-Tenant-ID": self.tenant_id or settings.DEFAULT_TENANT
                }
                
                response = await http_client.post(
                    f"{settings.CAG_SERVICE_URL}/api/v1/cag/embeddings",
                    json=texts,  # Send texts directly as array
                    headers=headers,
                    params={"tenant_id": self.tenant_id} if self.tenant_id else None
                )
                
                response.raise_for_status()
                result = response.json()
                embeddings = result.get("embeddings", [])
                
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
            # Use get_embeddings for a single text
            embeddings_list = await self.get_embeddings([text])
            embedding = embeddings_list[0] if embeddings_list else []
            logger.debug("Embedding generated successfully")
            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    async def generate_embeddings(self, text: str) -> List[List[float]]:
        """
        Genera embeddings para un texto.
        Alias for get_embeddings to maintain compatibility.
        
        Args:
            text: Texto para generar embeddings
            
        Returns:
            Lista de vectores de embeddings
        """
        # Split text into chunks if it's too long
        chunks = await self.chunk_text(text)
        texts = [chunk["text"] for chunk in chunks] if chunks else [text]
        return await self.get_embeddings(texts)
    
    async def chunk_text(self, text: str) -> List[Dict[str, Any]]:
        """
        Divide texto en chunks localmente.
        
        Args:
            text: Texto a dividir
            
        Returns:
            Lista de diccionarios con chunks de texto
        """
        try:
            logger.debug(f"Chunking text of length: {len(text)}")
            
            # Simple chunking implementation
            chunk_size = 2000  # Characters per chunk
            chunk_overlap = 200  # Overlap between chunks
            chunks = []
            
            if len(text) <= chunk_size:
                # Text is small enough, return as single chunk
                chunks = [{"text": text, "metadata": {"chunk_index": 0}}]
            else:
                # Split into overlapping chunks
                for i in range(0, len(text), chunk_size - chunk_overlap):
                    chunk_text = text[i:i + chunk_size]
                    chunks.append({
                        "text": chunk_text,
                        "metadata": {"chunk_index": len(chunks)}
                    })
                    
                    # If this chunk completes the text, stop
                    if i + chunk_size >= len(text):
                        break
            
            logger.debug(f"Text split into {len(chunks)} chunks successfully.")
            return chunks
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise