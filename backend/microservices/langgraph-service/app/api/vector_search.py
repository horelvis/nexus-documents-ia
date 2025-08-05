"""
Vector Search API endpoints - Migrated from LangChain service
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from loguru import logger

from app.core.langgraph_manager import LangGraphManager
from app.core.security import validate_service_access, validate_tenant_access
from app.services.vector_service import VectorService


router = APIRouter(prefix="/vector", tags=["vector-search"])


# Pydantic models
class AddDocumentRequest(BaseModel):
    tenant_id: str
    doc_id: str
    texts: List[str]
    metadatas: List[Dict[str, Any]]


class AddSingleDocumentRequest(BaseModel):
    tenant_id: str
    doc_id: str
    text: str
    metadata: Dict[str, Any] = {}


class SearchRequest(BaseModel):
    tenant_id: str
    query: str
    limit: int = 5
    doc_ids: Optional[List[str]] = None
    filters: Optional[Dict[str, Any]] = None


class SearchResponse(BaseModel):
    results: List[Dict[str, Any]]


@router.post("/documents/add")
async def add_documents(
    request: AddDocumentRequest,
    context: dict = Depends(validate_service_access)
):
    """Add multiple documents to vector store"""
    try:
        tenant_id = validate_tenant_access(request.tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        success = await vector_service.add_documents(
            doc_id=request.doc_id,
            texts=request.texts,
            metadatas=request.metadatas
        )
        
        return {"success": success}
        
    except Exception as e:
        logger.error(f"Error adding documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/add-single")
async def add_single_document(
    request: AddSingleDocumentRequest,
    context: dict = Depends(validate_service_access)
):
    """Add single document to vector store"""
    try:
        tenant_id = validate_tenant_access(request.tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        success = await vector_service.add_document(
            doc_id=request.doc_id,
            text=request.text,
            metadata=request.metadata
        )
        
        return {"success": success}
        
    except Exception as e:
        logger.error(f"Error adding single document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search_similar(
    request: SearchRequest,
    context: dict = Depends(validate_service_access)
):
    """Search for similar documents using vector similarity"""
    try:
        tenant_id = validate_tenant_access(request.tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        if request.doc_ids:
            results = await vector_service.search_by_document_ids(
                doc_ids=request.doc_ids,
                query=request.query,
                limit=request.limit
            )
        else:
            results = await vector_service.search_similar(
                query=request.query,
                limit=request.limit,
                filters=request.filters
            )
        
        return SearchResponse(results=results)
        
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{tenant_id}/{doc_id}")
async def delete_document(
    tenant_id: str,
    doc_id: str,
    context: dict = Depends(validate_service_access)
):
    """Delete document from vector store"""
    try:
        tenant_id = validate_tenant_access(tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        success = await vector_service.delete_document(doc_id)
        
        return {"success": success}
        
    except Exception as e:
        logger.error(f"Error deleting document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collection/{tenant_id}/info")
async def get_collection_info(
    tenant_id: str,
    context: dict = Depends(validate_service_access)
):
    """Get vector collection information"""
    try:
        tenant_id = validate_tenant_access(tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        info = await vector_service.get_collection_info()
        
        return info
        
    except Exception as e:
        logger.error(f"Error getting collection info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collection/{tenant_id}/recreate")
async def recreate_collection(
    tenant_id: str,
    context: dict = Depends(validate_service_access)
):
    """Recreate collection with correct dimensions"""
    try:
        tenant_id = validate_tenant_access(tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        success = await vector_service.recreate_collection()
        
        if success:
            return {
                "success": True,
                "message": "Collection recreated successfully with correct dimensions"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to recreate collection")
            
    except Exception as e:
        logger.error(f"Error recreating collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collection/{tenant_id}/health")
async def check_collection_health(
    tenant_id: str,
    context: dict = Depends(validate_service_access)
):
    """Check collection health and dimensions"""
    try:
        tenant_id = validate_tenant_access(tenant_id, context)
        
        manager = LangGraphManager()
        vector_service = VectorService(
            tenant_id=tenant_id,
            qdrant_client=manager.qdrant_client,
            embeddings=manager.embeddings
        )
        
        health = await vector_service.check_health()
        
        return health
        
    except Exception as e:
        logger.error(f"Error checking collection health: {e}")
        return {
            "status": "error",
            "error": str(e)
        }