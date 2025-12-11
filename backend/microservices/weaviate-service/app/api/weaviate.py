"""Weaviate API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging

from app.core.security import verify_api_key
from app.services.weaviate_service import weaviate_service
from app.schemas.weaviate import (
    DocumentCreate, DocumentResponse, SearchRequest, SearchResponse,
    CollectionInfo, VectorQuery
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================================
# Request Models
# ========================================

class DocumentACLUpdate(BaseModel):
    """Schema for updating document ACL properties"""
    collection_name: str
    acl_user_ids: List[str] = []
    acl_role_ids: List[str] = []
    acl_everyone: bool = False

@router.post("/collections/{collection_name}/documents", response_model=DocumentResponse)
async def add_document(
    collection_name: str,
    document: DocumentCreate,
    _: bool = Depends(verify_api_key)
):
    """Add a document to Weaviate collection"""
    try:
        result = await weaviate_service.add_document(collection_name, document)
        return result
    except Exception as e:
        logger.error(f"❌ Failed to add document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/search", response_model=SearchResponse)
async def search_documents(
    collection_name: str,
    search_request: SearchRequest,
    _: bool = Depends(verify_api_key)
):
    """Search documents in Weaviate collection"""
    try:
        results = await weaviate_service.search_documents(collection_name, search_request)
        return results
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections/{collection_name}/info", response_model=CollectionInfo)
async def get_collection_info(
    collection_name: str,
    _: bool = Depends(verify_api_key)
):
    """Get information about a Weaviate collection"""
    try:
        info = await weaviate_service.get_collection_info(collection_name)
        return info
    except Exception as e:
        logger.error(f"❌ Failed to get collection info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/create")
async def create_collection(
    collection_name: str,
    schema: Optional[Dict[str, Any]] = None,
    _: bool = Depends(verify_api_key)
):
    """Create a new Weaviate collection"""
    try:
        result = await weaviate_service.create_collection(collection_name, schema)
        return {"status": "success", "collection": collection_name, "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to create collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collections/{collection_name}")
async def delete_collection(
    collection_name: str,
    _: bool = Depends(verify_api_key)
):
    """Delete a Weaviate collection"""
    try:
        result = await weaviate_service.delete_collection(collection_name)
        return {"status": "success", "collection": collection_name, "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to delete collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(
    collection_name: str,
    document_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    Delete a document from Weaviate collection.

    Args:
        collection_name: Name of the Weaviate collection
        document_id: The PostgreSQL document UUID (stored in document_id property)

    Returns:
        Success status
    """
    try:
        success = await weaviate_service.delete_document(collection_name, document_id)
        if success:
            return {"status": "success", "document_id": document_id, "collection": collection_name}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/batch")
async def batch_add_documents(
    collection_name: str,
    documents: List[DocumentCreate],
    _: bool = Depends(verify_api_key)
):
    """Batch add multiple documents to Weaviate"""
    try:
        results = await weaviate_service.batch_add_documents(collection_name, documents)
        return {
            "status": "success",
            "collection": collection_name,
            "processed": len(documents),
            "results": results
        }
    except Exception as e:
        logger.error(f"❌ Batch operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections")
async def list_collections(_: bool = Depends(verify_api_key)):
    """List all Weaviate collections"""
    try:
        collections = await weaviate_service.list_collections()
        return {"collections": collections}
    except Exception as e:
        logger.error(f"❌ Failed to list collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/vector-query", response_model=SearchResponse)
async def vector_query(
    collection_name: str,
    query: VectorQuery,
    _: bool = Depends(verify_api_key)
):
    """Perform raw vector query on Weaviate collection"""
    try:
        results = await weaviate_service.vector_query(collection_name, query)
        return results
    except Exception as e:
        logger.error(f"❌ Vector query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/documents/{document_id}/acl")
async def update_document_acl(
    document_id: str,
    acl_update: DocumentACLUpdate,
    _: bool = Depends(verify_api_key)
):
    """
    Update document ACL properties in Weaviate.

    Called by the main API's DocumentACLService when ACLs change in PostgreSQL.
    This keeps Weaviate's document properties in sync for efficient ACL filtering
    during vector/hybrid searches.
    """
    try:
        result = await weaviate_service.update_document_acl(
            collection_name=acl_update.collection_name,
            document_id=document_id,
            acl_user_ids=acl_update.acl_user_ids,
            acl_role_ids=acl_update.acl_role_ids,
            acl_everyone=acl_update.acl_everyone
        )
        return {"status": "success", "document_id": document_id, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to update document ACL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Weaviate service health check"""
    try:
        status = await weaviate_service.health_check()
        return status
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}