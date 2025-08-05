"""
Embedding Service - Handles text embeddings and chunking
"""
from typing import List, Dict, Any, Optional
from langchain.text_splitter import RecursiveCharacterTextSplitter
from loguru import logger
import asyncio


class EmbeddingService:
    """Service for generating embeddings and processing text"""
    
    def __init__(self, embeddings_model):
        self.embeddings = embeddings_model
        
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        if not self.embeddings:
            raise ValueError("Embeddings model not initialized")
            
        try:
            # Use async if available, otherwise run in executor
            if hasattr(self.embeddings, 'aembed_documents'):
                embeddings = await self.embeddings.aembed_documents(texts)
            else:
                loop = asyncio.get_event_loop()
                embeddings = await loop.run_in_executor(
                    None, 
                    self.embeddings.embed_documents, 
                    texts
                )
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
    
    async def get_embedding(self, text: str) -> List[float]:
        """Generate embedding for single text"""
        if not self.embeddings:
            raise ValueError("Embeddings model not initialized")
            
        try:
            # Use async if available, otherwise run in executor
            if hasattr(self.embeddings, 'aembed_query'):
                embedding = await self.embeddings.aembed_query(text)
            else:
                loop = asyncio.get_event_loop()
                embedding = await loop.run_in_executor(
                    None, 
                    self.embeddings.embed_query, 
                    text
                )
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating single embedding: {e}")
            raise
    
    def chunk_text(
        self, 
        text: str, 
        chunk_size: int = 1000, 
        chunk_overlap: int = 200
    ) -> List[Dict[str, Any]]:
        """Chunk text into smaller pieces with metadata"""
        
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
        )
        
        chunks = text_splitter.split_text(text)
        
        # Add metadata to each chunk
        chunk_data = []
        for i, chunk in enumerate(chunks):
            chunk_data.append({
                "text": chunk,
                "chunk_index": i,
                "chunk_size": len(chunk),
                "total_chunks": len(chunks)
            })
        
        return chunk_data