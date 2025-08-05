"""
LLM API endpoints - Migrated from LangChain service
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from loguru import logger

from app.core.langgraph_manager import LangGraphManager
from app.core.security import validate_service_access, validate_tenant_access
from app.services.llm_service import LLMService


router = APIRouter(prefix="/llm", tags=["llm"])


# Pydantic models
class LLMRequest(BaseModel):
    query: str
    tenant_id: Optional[str] = None
    doc_ids: Optional[List[str]] = None
    max_tokens: int = 500
    temperature: float = 0.7


class LLMResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]] = []
    context_used: Optional[int] = None


class TagSuggestionRequest(BaseModel):
    text: str
    num_tags: int = 5


class MetadataExtractionRequest(BaseModel):
    text: str


class SummarizeRequest(BaseModel):
    text: str
    max_length: int = 200


class EntityExtractionRequest(BaseModel):
    text: str


@router.post("/generate", response_model=LLMResponse)
async def generate_llm_response(
    request: LLMRequest,
    context: dict = Depends(validate_service_access)
):
    """Generate LLM response with optional RAG"""
    try:
        manager = LangGraphManager()
        llm_service = LLMService(
            llm=manager.llm,
            embeddings=manager.embeddings,
            qdrant_client=manager.qdrant_client
        )
        
        response = await llm_service.generate_response(
            query=request.query,
            tenant_id=request.tenant_id,
            doc_ids=request.doc_ids,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )
        
        return LLMResponse(
            answer=response["answer"],
            sources=response.get("sources", []),
            context_used=response.get("context_used")
        )
        
    except Exception as e:
        logger.error(f"Error generating LLM response: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggest-tags")
async def suggest_tags(
    request: TagSuggestionRequest,
    context: dict = Depends(validate_service_access)
):
    """Suggest tags for text using LLM"""
    try:
        manager = LangGraphManager()
        llm_service = LLMService(llm=manager.llm)
        
        tags = await llm_service.suggest_tags(
            text=request.text,
            num_tags=request.num_tags
        )
        
        return {"tags": tags}
        
    except Exception as e:
        logger.error(f"Error suggesting tags: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-metadata")
async def extract_metadata(
    request: MetadataExtractionRequest,
    context: dict = Depends(validate_service_access)
):
    """Extract metadata from text using LLM"""
    try:
        manager = LangGraphManager()
        llm_service = LLMService(llm=manager.llm)
        
        metadata = await llm_service.extract_metadata(request.text)
        
        return {"metadata": metadata}
        
    except Exception as e:
        logger.error(f"Error extracting metadata: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summarize")
async def summarize_text(
    request: SummarizeRequest,
    context: dict = Depends(validate_service_access)
):
    """Summarize text using LLM"""
    try:
        manager = LangGraphManager()
        llm_service = LLMService(llm=manager.llm)
        
        summary = await llm_service.summarize_text(
            text=request.text,
            max_length=request.max_length
        )
        
        return {"summary": summary}
        
    except Exception as e:
        logger.error(f"Error summarizing text: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-entities")
async def extract_entities(
    request: EntityExtractionRequest,
    context: dict = Depends(validate_service_access)
):
    """Extract named entities from text using LLM"""
    try:
        manager = LangGraphManager()
        llm_service = LLMService(llm=manager.llm)
        
        entities = await llm_service.extract_entities(request.text)
        
        return {"entities": entities}
        
    except Exception as e:
        logger.error(f"Error extracting entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))