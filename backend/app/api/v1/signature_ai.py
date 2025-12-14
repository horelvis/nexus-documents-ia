"""
API endpoints for AI-powered signature placement
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.api.async_dependencies import (
    get_async_db, 
    get_current_active_user_async,
    get_current_tenant_id_async
)
from app.db.models import User
from app.services.signature_ai_service import SignatureAIService
from app.schemas.signature import SignatureRequestCreate

router = APIRouter()


# Request/Response Schemas
class DocumentAnalysisRequest(BaseModel):
    document_id: UUID
    metadata: Optional[Dict[str, Any]] = None


class SignatureFieldSuggestion(BaseModel):
    type: str
    signer_role: str
    x: float
    y: float
    width: float
    height: float
    page: int
    confidence: float
    reason: str
    source: str = Field(..., description="poi_detection, learned_pattern, or defaults")


class DocumentAnalysisResponse(BaseModel):
    document_type: str
    confidence: float
    suggested_fields: List[SignatureFieldSuggestion]
    detected_zones: List[Dict[str, Any]]
    similar_documents: List[Dict[str, Any]]
    learning_data: Dict[str, Any]


class PlacementFeedback(BaseModel):
    document_id: UUID
    document_type: str
    placed_fields: List[Dict[str, Any]]


class SignerInfo(BaseModel):
    id: str
    email: str
    name: str
    role: Optional[str] = "signer"


class PlacementSuggestionRequest(BaseModel):
    document_id: UUID
    signers: List[SignerInfo]
    document_analysis: Optional[Dict[str, Any]] = None


# API Endpoints
@router.post("/analyze", response_model=DocumentAnalysisResponse)
async def analyze_document(
    request: DocumentAnalysisRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Analyze a document and get AI suggestions for signature placement
    """
    try:
        # Get document content
        from app.services.async_document_service import AsyncDocumentService
        doc_service = AsyncDocumentService(tenant_id=str(tenant_id), user_id=str(current_user.id))
        document = await doc_service.get_document(db, str(request.document_id))
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get document content from storage
        from app.services.async_storage_service import AsyncStorageService
        storage_service = AsyncStorageService(str(tenant_id), str(current_user.id))
        document_content = await storage_service.download_file(document.file_path or '')
        
        if not document_content:
            raise HTTPException(status_code=500, detail="Could not retrieve document content")
        
        # Initialize AI service
        ai_service = SignatureAIService(tenant_id)
        
        # Analyze document
        analysis_result = await ai_service.analyze_document(
            db=db,
            document_id=request.document_id,
            document_content=document_content,
            metadata={
                "filename": document.filename,
                "category": document.category,
                "file_type": document.file_type,
                **(request.metadata or {})
            }
        )
        
        return DocumentAnalysisResponse(**analysis_result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/analyze-file", response_model=DocumentAnalysisResponse)
async def analyze_uploaded_file(
    file: UploadFile = File(...),
    metadata: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Analyze an uploaded file without saving it to get signature suggestions
    """
    try:
        # Read file content
        document_content = await file.read()
        
        # Parse metadata if provided
        import json
        parsed_metadata = json.loads(metadata) if metadata else {}
        
        # Initialize AI service
        ai_service = SignatureAIService(tenant_id)
        
        # Analyze document
        analysis_result = await ai_service.analyze_document(
            db=db,
            document_id=UUID('00000000-0000-0000-0000-000000000000'),  # Temporary ID
            document_content=document_content,
            metadata={
                "filename": file.filename,
                "content_type": file.content_type,
                **parsed_metadata
            }
        )
        
        return DocumentAnalysisResponse(**analysis_result)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.post("/learn")
async def learn_from_placement(
    feedback: PlacementFeedback,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Submit user's actual field placements for AI learning
    """
    try:
        ai_service = SignatureAIService(tenant_id)
        
        success = await ai_service.learn_from_placement(
            db=db,
            document_id=feedback.document_id,
            document_type=feedback.document_type,
            placed_fields=feedback.placed_fields,
            user_id=current_user.id
        )
        
        if success:
            return {"status": "success", "message": "Placement data recorded for learning"}
        else:
            raise HTTPException(status_code=500, detail="Failed to record placement data")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Learning failed: {str(e)}")


@router.post("/suggest-placements")
async def suggest_placements_for_signers(
    request: PlacementSuggestionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Get specific field placement suggestions for given signers
    """
    try:
        ai_service = SignatureAIService(tenant_id)
        
        # If no analysis provided, analyze first
        if not request.document_analysis:
            # Get document and analyze
            from app.services.async_document_service import AsyncDocumentService
            doc_service = AsyncDocumentService(tenant_id=str(tenant_id), user_id=str(current_user.id))
            document = await doc_service.get_document(db, str(request.document_id))
            
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            # Get content and analyze
            from app.services.async_storage_service import AsyncStorageService
            storage_service = AsyncStorageService(str(tenant_id), str(current_user.id))
            document_content = await storage_service.download_file(document.file_path or '')
            
            document_analysis = await ai_service.analyze_document(
                db=db,
                document_id=request.document_id,
                document_content=document_content,
                metadata={"filename": document.filename}
            )
        else:
            document_analysis = request.document_analysis
        
        # Get placement suggestions
        signers_dict = [s.dict() for s in request.signers]
        suggestions = await ai_service.get_placement_suggestions_for_signers(
            db=db,
            document_id=request.document_id,
            signers=signers_dict,
            document_analysis=document_analysis
        )
        
        return {
            "document_type": document_analysis["document_type"],
            "suggested_fields": suggestions,
            "confidence": document_analysis["confidence"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Suggestion failed: {str(e)}")


@router.get("/patterns/{document_type}")
async def get_learned_patterns(
    document_type: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Get learned patterns for a specific document type
    """
    try:
        from sqlalchemy import select
        from app.db.models import SignaturePlacementPattern
        
        stmt = select(SignaturePlacementPattern).filter(
            SignaturePlacementPattern.tenant_id == tenant_id,
            SignaturePlacementPattern.document_type == document_type,
            SignaturePlacementPattern.is_active == True
        ).order_by(SignaturePlacementPattern.confidence.desc())
        
        result = await db.execute(stmt)
        patterns = result.scalars().all()
        
        return {
            "document_type": document_type,
            "patterns": [
                {
                    "id": str(p.id),
                    "field_configurations": p.field_configurations,
                    "confidence": p.confidence,
                    "usage_count": p.usage_count,
                    "source": p.source,
                    "created_at": p.created_at.isoformat()
                }
                for p in patterns
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve patterns: {str(e)}")


@router.get("/document-types")
async def get_document_types(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Get configured document types for the tenant
    """
    try:
        from sqlalchemy import select
        from app.db.models import DocumentTypeClassification
        
        stmt = select(DocumentTypeClassification).filter(
            DocumentTypeClassification.tenant_id == tenant_id,
            DocumentTypeClassification.is_active == True
        )
        
        result = await db.execute(stmt)
        doc_types = result.scalars().all()
        
        # Add default types if none configured
        if not doc_types:
            default_types = [
                {"name": "contract", "display_name": "Contract", "default_signer_count": 2},
                {"name": "agreement", "display_name": "Agreement", "default_signer_count": 2},
                {"name": "form", "display_name": "Form", "default_signer_count": 1},
                {"name": "letter", "display_name": "Letter", "default_signer_count": 1},
                {"name": "invoice", "display_name": "Invoice", "default_signer_count": 1}
            ]
            return {"document_types": default_types}
        
        return {
            "document_types": [
                {
                    "id": str(dt.id),
                    "name": dt.name,
                    "display_name": dt.display_name,
                    "description": dt.description,
                    "default_signer_count": dt.default_signer_count,
                    "keywords": dt.keywords,
                    "patterns": dt.patterns
                }
                for dt in doc_types
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document types: {str(e)}")


@router.post("/generate-message")
async def generate_signature_message(
    request: Dict[str, Any],
    current_user: User = Depends(get_current_active_user_async),
    tenant_id: UUID = Depends(get_current_tenant_id_async)
):
    """
    Generate AI-powered message for signature request
    """
    try:
        document_title = request.get("document_title", "document")
        signer_count = request.get("signer_count", 1)
        document_type = request.get("document_type", "general")
        
        ai_service = SignatureAIService(tenant_id)
        message = ai_service.generate_signature_message(
            document_title=document_title,
            signer_count=signer_count,
            document_type=document_type
        )
        
        return {
            "message": message,
            "generated": True
        }
        
    except Exception as e:
        # Return fallback message on error
        signer_text = "signature" if signer_count == 1 else "signatures"
        fallback_message = f"""Hello,

I'm requesting your signature on \"{document_title}\". Please review the document and sign where indicated.

This document requires {signer_count} {signer_text}. You'll receive a confirmation once all parties have signed.

Thank you for your prompt attention to this matter."""
        
        return {
            "message": fallback_message,
            "generated": False
        }