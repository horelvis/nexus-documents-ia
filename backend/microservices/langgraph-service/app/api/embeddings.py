"""
Embeddings API endpoints - Migrated from LangChain service
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from loguru import logger

from app.core.langgraph_manager import LangGraphManager
from app.core.security import validate_service_access
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService


router = APIRouter(prefix="/embeddings", tags=["embeddings"])


# Pydantic models
class EmbeddingRequest(BaseModel):
    texts: List[str]


class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]


class ChunkRequest(BaseModel):
    text: str
    chunk_size: int = 1000
    chunk_overlap: int = 200


class ChunkResponse(BaseModel):
    chunks: List[Dict[str, Any]]


@router.post("/generate", response_model=EmbeddingResponse)
async def generate_embeddings(
    request: EmbeddingRequest,
    context: dict = Depends(validate_service_access)
):
    """Generate embeddings for multiple texts"""
    try:
        manager = LangGraphManager()
        embedding_service = EmbeddingService(manager.embeddings)
        
        embeddings = await embedding_service.get_embeddings(request.texts)
        
        return EmbeddingResponse(embeddings=embeddings)
        
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-single", response_model=Dict[str, List[float]])
async def generate_single_embedding(
    request: Dict[str, str],
    context: dict = Depends(validate_service_access)
):
    """Generate embedding for single text"""
    try:
        manager = LangGraphManager()
        embedding_service = EmbeddingService(manager.embeddings)
        
        embedding = await embedding_service.get_embedding(request["text"])
        
        return {"embedding": embedding}
        
    except Exception as e:
        logger.error(f"Error generating single embedding: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chunk", response_model=ChunkResponse)
async def chunk_text(
    request: ChunkRequest,
    context: dict = Depends(validate_service_access)
):
    """Chunk text into smaller pieces with overlap"""
    try:
        embedding_service = EmbeddingService(None)  # Chunking doesn't need embeddings
        
        chunks = embedding_service.chunk_text(
            request.text,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap
        )
        
        return ChunkResponse(chunks=chunks)
        
    except Exception as e:
        logger.error(f"Error chunking text: {e}")
        raise HTTPException(status_code=500, detail=str(e))