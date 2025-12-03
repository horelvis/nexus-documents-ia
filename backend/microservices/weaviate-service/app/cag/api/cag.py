"""CAG API endpoints"""
from typing import Dict, Any, Optional, AsyncGenerator, List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
import json
import asyncio
from loguru import logger

from ..schemas.cag import (
    CAGQueryRequest, CAGQueryResponse,
    DocumentAnalysisRequest, DocumentAnalysisResponse
)
from ..core.security import verify_api_key, validate_tenant_access, sanitize_user_input
from ..services.cag_service import cag_service

router = APIRouter(prefix="/api/v1/cag", tags=["CAG"])


@router.get("/agents/available")
async def get_available_agents(
    tenant_id: str = "default",
    _: bool = Depends(verify_api_key)
):
    """Get REAL available agents information from CrewAI - NO HARDCODE"""
    try:
        # Obtener información REAL de agentes desde CrewAI
        agents_info = await cag_service.get_available_agents_info(tenant_id)
        return agents_info
    except Exception as e:
        logger.error(f"Error getting REAL agents info: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get REAL agents: {str(e)}")


@router.post("/query", response_model=CAGQueryResponse)
async def process_query(
    request: CAGQueryRequest,
    _: bool = Depends(verify_api_key)
) -> CAGQueryResponse:
    """Process a query using CAG"""
    try:
        # Validate tenant access
        security_context = validate_tenant_access(request.tenant_id, request.context)
        
        # Sanitize input
        query = sanitize_user_input(request.query, max_length=5000)
        
        # Process with CAG
        result = await cag_service.process_query(
            query=query,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            context=request.context
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Processing failed"))
        
        return CAGQueryResponse(
            success=True,
            query=query,
            answer=result["answer"],
            quality_score=result["quality_score"],
            iterations=result["iterations"],
            gaps_identified=result["gaps_identified"],
            context_chunks_used=result["context_chunks_used"],
            execution_time=result["execution_time"],
            metadata=result["metadata"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/embeddings")
async def generate_embeddings(
    texts: List[str],
    tenant_id: Optional[str] = None,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Generate embeddings for texts"""
    try:
        return await cag_service.generate_embeddings(texts, tenant_id)
        
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document(
    request: DocumentAnalysisRequest,
    _: bool = Depends(verify_api_key)
) -> DocumentAnalysisResponse:
    """Analyze a document using CAG"""
    try:
        # Validate tenant access
        security_context = validate_tenant_access(request.tenant_id)
        
        # Sanitize input
        document_content = sanitize_user_input(request.document_content, max_length=50000)
        
        # Process with CAG
        result = await cag_service.analyze_document(
            document_content=document_content,
            document_id=request.document_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            analysis_type=request.analysis_type
        )
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result.get("error", "Analysis failed"))
        
        return DocumentAnalysisResponse(
            success=True,
            document_id=request.document_id,
            document_type=result.get("document_type"),  # Add document type
            confidence=result.get("confidence", 0.0),  # Add confidence
            analysis_type=request.analysis_type,
            analysis=result.get("answer", result.get("response", "No analysis generated")),  # Use answer or response field
            quality_score=result.get("quality_score", 0.0),
            execution_time=result.get("execution_time", 0.0),
            metadata=result.get("metadata", {})
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error analyzing document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/stream")
async def process_query_stream(
    request: CAGQueryRequest,
    _: bool = Depends(verify_api_key)
) -> StreamingResponse:
    """Process a query using CAG with streaming progress"""
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Validate tenant access
            security_context = validate_tenant_access(request.tenant_id)
            
            # Sanitize input
            query = sanitize_user_input(request.query)
            
            # Send initial progress
            yield f"data: {json.dumps({'type': 'progress', 'content': 'Inicializando motor Elysia...', 'progress': 10})}\n\n"
            
            # Process with CAG (we'll need to add streaming support to the service)
            async for event in cag_service.process_query_stream(
                query=query,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                context=request.context
            ):
                yield f"data: {json.dumps(event)}\n\n"
            
            yield f"data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Error in streaming query: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/analyze/stream")
async def analyze_document_stream(
    request: DocumentAnalysisRequest,
    _: bool = Depends(verify_api_key)
) -> StreamingResponse:
    """Analyze a document using CAG with streaming progress"""
    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            # Validate tenant access
            security_context = validate_tenant_access(request.tenant_id)
            
            # Sanitize input
            document_content = sanitize_user_input(request.document_content, max_length=50000)
            
            # Send initial progress
            yield f"data: {json.dumps({'type': 'progress', 'content': 'Elysia analizando documento...', 'progress': 5})}\n\n"
            
            # Process with CAG
            async for event in cag_service.analyze_document_stream(
                document_content=document_content,
                document_id=request.document_id,
                tenant_id=request.tenant_id,
                user_id=request.user_id,
                analysis_type=request.analysis_type
            ):
                yield f"data: {json.dumps(event)}\n\n"
            
            yield f"data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Error in streaming analysis: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Check CAG service health"""
    return await cag_service.health_check()
