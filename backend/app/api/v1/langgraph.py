"""
LangGraph API endpoints for advanced graph-based workflows
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List, Optional
import httpx
import logging

from app.api.dependencies import get_current_active_user, get_current_active_superuser
from app.core.database import get_async_db
from app.db.models import User
from app.services.langgraph_client import LangGraphClient
from app.schemas.langgraph import (
    GraphRunRequest,
    GraphRunResponse,
    TagGenerationRequest,
    TagGenerationResponse,
    DocumentProcessingRequest,
    DocumentProcessingResponse,
    RAGQueryRequest,
    RAGQueryResponse,
    GraphTypeResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/run", response_model=GraphRunResponse)
async def run_graph(
    request: GraphRunRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Run a LangGraph workflow
    
    Available graph types:
    - tag_generation: Generate tags from text with confidence scoring
    - document_processing: Process documents with intelligent chunking
    - rag: Enhanced RAG with multiple search strategies
    """
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id)
            )
            
            result = await langgraph_client.run_graph(
                graph_type=request.graph_type,
                input_data=request.input_data,
                config=request.config,
                thread_id=request.thread_id,
                checkpoint_id=request.checkpoint_id
            )
            
            return GraphRunResponse(
                run_id=result["run_id"],
                graph_type=result["graph_type"],
                status=result["status"],
                result=result.get("result"),
                error=result.get("error"),
                execution_time=result.get("execution_time", 0),
                iterations=result.get("iterations", 0)
            )
            
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from LangGraph service: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LangGraph service unavailable"
        )
    except Exception as e:
        logger.error(f"Error running graph: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/tags/generate", response_model=TagGenerationResponse)
async def generate_tags(
    request: TagGenerationRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generate tags from text using LangGraph
    
    Features:
    - Multiple tag types: general, technical, business
    - Confidence scoring for each tag
    - Automatic validation and refinement
    """
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id)
            )
            
            result = await langgraph_client.generate_tags(
                text=request.text,
                max_tags=request.max_tags,
                tag_type=request.tag_type
            )
            
            return TagGenerationResponse(
                tags=result.get("tags", []),
                confidence_scores=result.get("confidence_scores", {}),
                reasoning=result.get("reasoning")
            )
            
    except Exception as e:
        logger.error(f"Error generating tags: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/documents/process", response_model=DocumentProcessingResponse)
async def process_document(
    request: DocumentProcessingRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Process document with intelligent chunking and quality checks
    
    Features:
    - Adaptive chunk sizing based on content
    - Quality scoring and reprocessing
    - Metadata extraction using LLM
    - Multi-tenant vector storage
    """
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id)
            )
            
            result = await langgraph_client.process_document(
                document_id=request.document_id,
                content=request.content,
                filename=request.filename,
                metadata=request.metadata
            )
            
            return DocumentProcessingResponse(
                document_id=result["document_id"],
                chunks=result.get("chunks", []),
                embeddings_generated=result.get("embeddings_generated", False),
                metadata=result.get("metadata", {}),
                quality_score=result.get("quality_score"),
                processing_notes=result.get("processing_notes", [])
            )
            
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/rag/query", response_model=RAGQueryResponse)
async def rag_query(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Execute enhanced RAG query with multiple search strategies
    
    Features:
    - Parallel search: vector, keyword, metadata
    - Result fusion and reranking
    - Answer quality checks and refinement
    - Source attribution
    """
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id),
                user_id=str(current_user.id)
            )
            
            result = await langgraph_client.rag_query(
                query=request.query,
                max_results=request.max_results,
                filters=request.filters,
                include_sources=request.include_sources
            )
            
            return RAGQueryResponse(
                answer=result.get("answer", ""),
                sources=result.get("sources", []) if request.include_sources else None,
                confidence_score=result.get("confidence_score", 0.0),
                search_results=result.get("search_results", []) if request.include_sources else None,
                refinement_notes=result.get("refinement_notes")
            )
            
    except Exception as e:
        logger.error(f"Error executing RAG query: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/graphs/types", response_model=GraphTypeResponse)
async def list_graph_types(
    current_user: User = Depends(get_current_active_user)
):
    """Get list of available graph types"""
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id)
            )
            
            types = await langgraph_client.get_graph_types()
            
            return GraphTypeResponse(
                graph_types=types,
                count=len(types)
            )
            
    except Exception as e:
        logger.error(f"Error getting graph types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/graphs/structure/{graph_type}")
async def get_graph_structure(
    graph_type: str,
    current_user: User = Depends(get_current_active_user)
):
    """Get structure of a specific graph type"""
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id)
            )
            
            structure = await langgraph_client.get_graph_structure(graph_type)
            
            if not structure:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Graph type '{graph_type}' not found"
                )
            
            return structure
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting graph structure: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/health")
async def langgraph_health_check(
    current_user: User = Depends(get_current_active_user)
):
    """Check LangGraph service health"""
    try:
        async with httpx.AsyncClient() as client:
            langgraph_client = LangGraphClient(
                http_client=client,
                tenant_id=str(current_user.tenant_id)
            )
            
            is_healthy = await langgraph_client.health_check()
            
            return {
                "service": "langgraph",
                "healthy": is_healthy,
                "status": "operational" if is_healthy else "degraded"
            }
            
    except Exception as e:
        logger.error(f"Error checking LangGraph health: {e}")
        return {
            "service": "langgraph",
            "healthy": False,
            "status": "error",
            "error": str(e)
        }


# Admin endpoints for graph management
@router.post("/graphs/import", dependencies=[Depends(get_current_active_superuser)])
async def import_graph_definition(
    graph_definition: Dict[str, Any],
    current_user: User = Depends(get_current_active_superuser)
):
    """
    Import a custom graph definition (Admin only)
    
    This endpoint allows importing graph definitions created in tools like Langflow
    """
    # This would be implemented to allow custom graph imports
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Graph import functionality coming soon"
    )