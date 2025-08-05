"""
Document Analyzer API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from typing import Dict, Any, List, Optional
import logging

from app.api.v1.deps import get_current_user, get_current_active_user, get_client_manager
from app.db.models import User
from app.services.document_analyzer_client import DocumentAnalyzerClient
from app.services.client_manager import ClientManager
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class DocumentAnalysisRequest(BaseModel):
    """Request for document analysis"""
    document_id: Optional[str] = None
    content: Optional[str] = None
    analysis_type: str = "comprehensive"
    language: str = "auto"
    options: Optional[Dict[str, Any]] = None


class DocumentAnalysisResponse(BaseModel):
    """Response from document analysis"""
    document_id: Optional[str]
    analysis_type: str
    results: Dict[str, Any]
    metadata: Dict[str, Any]
    confidence_score: float
    processing_time: float


@router.post("/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document(
    request: DocumentAnalysisRequest,
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Analyze a document using advanced CAG-based analysis
    
    Analysis types:
    - comprehensive: Full analysis including summary, entities, topics, and sentiment
    - summary: Concise summary of main points
    - entities: Extract people, organizations, locations, dates, etc.
    - topics: Identify and explain main topics
    - sentiment: Analyze tone and emotional content
    """
    
    try:
        analyzer_client = DocumentAnalyzerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await analyzer_client.analyze_document(
            document_id=request.document_id,
            content=request.content,
            analysis_type=request.analysis_type,
            language=request.language,
            options=request.options
        )
        
        return DocumentAnalysisResponse(**result)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Document analysis failed: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed")


@router.post("/analyze-file", response_model=DocumentAnalysisResponse)
async def analyze_file(
    file: UploadFile = File(...),
    analysis_type: str = Form("comprehensive"),
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Analyze an uploaded file
    
    Supported formats:
    - PDF documents
    - Word documents (DOC, DOCX)
    - Text files (TXT)
    - CSV files
    - JSON files
    """
    
    try:
        # Read file content
        content = await file.read()
        
        analyzer_client = DocumentAnalyzerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await analyzer_client.analyze_file(
            file_content=content,
            filename=file.filename,
            content_type=file.content_type,
            analysis_type=analysis_type
        )
        
        return DocumentAnalysisResponse(**result)
        
    except Exception as e:
        logger.error(f"File analysis failed: {e}")
        raise HTTPException(status_code=500, detail="File analysis failed")


@router.post("/compare")
async def compare_documents(
    document_ids: List[str],
    comparison_type: str = "similarity",
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Compare multiple documents
    
    Comparison types:
    - similarity: Find common themes and overlapping content
    - differences: Highlight unique content and contradictions
    - common_topics: Analyze topic overlap and evolution
    """
    
    try:
        analyzer_client = DocumentAnalyzerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await analyzer_client.compare_documents(
            document_ids=document_ids,
            comparison_type=comparison_type
        )
        
        return result
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Document comparison failed: {e}")
        raise HTTPException(status_code=500, detail="Comparison failed")


@router.get("/analysis-types")
async def get_analysis_types(
    client_manager: ClientManager = Depends(get_client_manager)
):
    """Get available analysis types with descriptions"""
    
    try:
        analyzer_client = DocumentAnalyzerClient(
            http_client=client_manager.http_client
        )
        
        return await analyzer_client.get_analysis_types()
        
    except Exception as e:
        logger.error(f"Failed to get analysis types: {e}")
        raise HTTPException(status_code=500, detail="Failed to get analysis types")


@router.post("/analyze/{document_id}")
async def analyze_existing_document(
    document_id: str,
    analysis_type: str = "comprehensive",
    current_user: User = Depends(get_current_active_user),
    client_manager: ClientManager = Depends(get_client_manager)
):
    """
    Analyze an existing document by ID
    
    This will fetch the document content and perform the requested analysis
    """
    
    try:
        # TODO: Fetch document content from storage service
        # For now, we'll use the document_id directly
        
        analyzer_client = DocumentAnalyzerClient(
            http_client=client_manager.http_client,
            tenant_id=str(current_user.tenant_id),
            user_id=str(current_user.id)
        )
        
        result = await analyzer_client.analyze_document(
            document_id=document_id,
            analysis_type=analysis_type
        )
        
        return DocumentAnalysisResponse(**result)
        
    except Exception as e:
        logger.error(f"Document analysis failed for {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed")