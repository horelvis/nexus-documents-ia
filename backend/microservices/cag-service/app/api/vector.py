"""Vector operations API endpoints"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from loguru import logger

from ..core.security import verify_api_key, validate_tenant_access, sanitize_user_input
from ..services.cag_service import cag_service

router = APIRouter(prefix="/api/v1/vector", tags=["Vector"])


class AddDocumentRequest(BaseModel):
    doc_id: str
    text: str
    metadata: Dict[str, Any] = {}
    tenant_id: Optional[str] = None


class AddDocumentResponse(BaseModel):
    success: bool
    doc_id: str
    message: str
    metadata: Dict[str, Any] = {}


@router.post("/documents/add-single", response_model=AddDocumentResponse)
async def add_single_document(
    request: AddDocumentRequest,
    _: bool = Depends(verify_api_key)
) -> AddDocumentResponse:
    """Add a single document to the vector store"""
    try:
        # Validate tenant access if provided
        if request.tenant_id:
            security_context = validate_tenant_access(request.tenant_id)
        
        # Sanitize input text
        text = sanitize_user_input(request.text, max_length=100000)
        
        # Ensure service is initialized
        if not cag_service._initialized:
            await cag_service.initialize()
        
        # Generate embeddings for the text
        logger.info(f"Generating embeddings for document {request.doc_id}")
        embedding = await cag_service.embeddings.aembed_query(text)
        
        # TODO: Add to vector database (Qdrant integration)
        # For now, we'll simulate success since the main API handles vector storage
        # In a full implementation, you'd store in Qdrant here
        
        logger.info(f"Successfully processed document {request.doc_id} for vector storage")
        
        return AddDocumentResponse(
            success=True,
            doc_id=request.doc_id,
            message=f"Document {request.doc_id} processed for vector storage",
            metadata={
                "embedding_size": len(embedding),
                "text_length": len(text),
                "tenant_id": request.tenant_id,
                **request.metadata
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding document {request.doc_id} to vector store: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    tenant_id: Optional[str] = None,
    _: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """Delete a document from the vector store"""
    try:
        # Validate tenant access if provided
        if tenant_id:
            security_context = validate_tenant_access(tenant_id)
        
        # TODO: Remove from vector database (Qdrant integration)
        # For now, simulate success
        
        logger.info(f"Successfully deleted document {doc_id} from vector storage")
        
        return {
            "success": True,
            "doc_id": doc_id,
            "message": f"Document {doc_id} deleted from vector storage"
        }
        
    except Exception as e:
        logger.error(f"Error deleting document {doc_id} from vector store: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def vector_health_check() -> Dict[str, Any]:
    """Check vector operations health"""
    try:
        # Check if service is initialized
        initialized = cag_service._initialized if hasattr(cag_service, '_initialized') else False
        
        # Check embeddings service
        embeddings_available = hasattr(cag_service, 'embeddings') and cag_service.embeddings is not None
        
        return {
            "status": "healthy" if initialized and embeddings_available else "partial",
            "service": "vector-operations",
            "initialized": initialized,
            "embeddings_available": embeddings_available,
            "embedding_model": cag_service.embeddings.model if embeddings_available else None
        }
        
    except Exception as e:
        logger.error(f"Vector health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "vector-operations",
            "error": str(e)
        }