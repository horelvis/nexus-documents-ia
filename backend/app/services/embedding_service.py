"""
Embedding Service using LangChain microservice HTTP client
"""
import asyncio
import logging
import httpx # Added httpx import
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
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                # Pass tenant_id as it's part of LangChainClient's get_embeddings signature
                embeddings = await lc_client.get_embeddings(texts=texts, tenant_id=self.tenant_id)
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
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                # Adapt to use get_embeddings for a single text
                embeddings_list = await lc_client.get_embeddings(texts=[text], tenant_id=self.tenant_id)
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
        Divide texto en chunks usando el microservicio LangChain.
        
        Args:
            text: Texto a dividir
            
        Returns:
            Lista de diccionarios con chunks de texto
        """
        try:
            logger.debug(f"Chunking text of length: {len(text)}")
            async with httpx.AsyncClient(timeout=30.0) as http_client:
                lc_client = LangChainClient(http_client=http_client)
                chunks = await lc_client.chunk_text(text=text, tenant_id=self.tenant_id)
            logger.debug(f"Text split into {len(chunks)} chunks successfully.")
            return chunks
        except Exception as e:
            logger.error(f"Error chunking text: {str(e)}")
            raise