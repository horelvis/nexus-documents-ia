"""Elasticsearch API endpoints"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
import logging

from app.core.security import verify_api_key
from app.services.elasticsearch_service import ElasticsearchService
from app.schemas.elasticsearch import (
    DocumentIndexRequest, HybridSearchRequest, SemanticSearchRequest,
    SearchResponse, AnalyticsRequest, AnalyticsResponse, FacetRequest, FacetResponse, HealthResponse,
    DocumentACLUpdateRequest
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================================
# ACL SYNCHRONIZATION ENDPOINT
# ========================================

@router.put("/documents/{document_id}/acl")
async def sync_document_acl(
    document_id: str,
    request: DocumentACLUpdateRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Synchronize document ACL from PostgreSQL to Elasticsearch.

    Called by the main API when document permissions change.
    This keeps Elasticsearch in sync with the ACL source of truth.
    """
    try:
        # Extract tenant_id from collection_name (format: Nexus_{tenant_id}_documents)
        # Example: Nexus_1a94d369_8426_4d2b_afec_8971073fce1e_documents
        collection_parts = request.collection_name.split("_")
        if len(collection_parts) >= 2:
            # Reconstruct tenant_id from collection name (with hyphens)
            tenant_id = "_".join(collection_parts[1:-1])  # Remove "Nexus_" prefix and "_documents" suffix
        else:
            raise HTTPException(status_code=400, detail="Invalid collection_name format")

        async with ElasticsearchService(tenant_id) as service:
            success = await service.update_document_acl(
                doc_id=document_id,
                acl_user_ids=request.acl_user_ids,
                acl_role_ids=request.acl_role_ids,
                acl_everyone=request.acl_everyone,
                created_by=request.created_by
            )

        if success:
            return {
                "status": "success",
                "message": f"ACL updated for document {document_id}",
                "acl_user_ids": len(request.acl_user_ids),
                "acl_role_ids": len(request.acl_role_ids),
                "acl_everyone": request.acl_everyone
            }
        else:
            # Document not found is not an error - it may not be indexed yet
            return {
                "status": "not_found",
                "message": f"Document {document_id} not found in Elasticsearch (may not be indexed yet)"
            }

    except Exception as e:
        logger.error(f"❌ ACL sync failed for document {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{tenant_id}/{document_id}")
async def get_document(
    tenant_id: str,
    document_id: str,
    _: bool = Depends(verify_api_key)
):
    """Get a single document by ID"""
    try:
        async with ElasticsearchService(tenant_id) as service:
            document = await service.get_document(document_id)

        if document:
            return {"status": "success", "document": document}
        else:
            raise HTTPException(status_code=404, detail="Document not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Get document failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# DOCUMENT INDEXING ENDPOINTS
# ========================================

@router.post("/index/{tenant_id}")
async def index_document(
    tenant_id: str,
    request: DocumentIndexRequest,
    _: bool = Depends(verify_api_key)
):
    """Index a document in Elasticsearch with ACL support"""
    try:
        async with ElasticsearchService(tenant_id) as service:
            # Create index if it doesn't exist
            service.create_index_if_not_exists()

            success = await service.index_document(
                doc_id=request.doc_id,
                title=request.title,
                content=request.content,
                description=request.description,
                content_vector=request.content_vector,
                metadata=request.metadata,
                # ACL fields
                created_by=request.created_by,
                acl_user_ids=request.acl_user_ids,
                acl_role_ids=request.acl_role_ids,
                acl_everyone=request.acl_everyone
            )

        if success:
            return {"status": "success", "message": f"Document {request.doc_id} indexed"}
        else:
            raise HTTPException(status_code=500, detail="Failed to index document")

    except Exception as e:
        logger.error(f"❌ Index document failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search/hybrid/{tenant_id}", response_model=SearchResponse)
async def hybrid_search(
    tenant_id: str,
    request: HybridSearchRequest,
    _: bool = Depends(verify_api_key)
):
    """Perform hybrid search with ACL-based filtering"""
    try:
        # Extract user context for ACL filtering
        user_id = None
        role_ids = []
        is_admin = False

        if request.user_context:
            user_id = request.user_context.user_id
            role_ids = request.user_context.role_ids
            is_admin = request.user_context.is_admin
            logger.debug(f"🔐 Search with ACL context: user={user_id}, roles={len(role_ids)}, admin={is_admin}")

        async with ElasticsearchService(tenant_id) as service:
            results = await service.hybrid_search(
                query=request.query,
                limit=request.limit,
                filters=request.filters.dict() if request.filters else None,
                boost_semantic=request.boost_semantic,
                boost_keyword=request.boost_keyword,
                # ACL parameters
                user_id=user_id,
                role_ids=role_ids,
                is_admin=is_admin
            )

        return SearchResponse(
            results=results,
            total=len(results),
            took_ms=0  # Could be enhanced to track timing
        )

    except Exception as e:
        logger.error(f"❌ Hybrid search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search/semantic/{tenant_id}", response_model=SearchResponse)
async def semantic_search(
    tenant_id: str,
    request: SemanticSearchRequest,
    _: bool = Depends(verify_api_key)
):
    """Perform semantic search with vector and ACL-based filtering"""
    try:
        # Extract user context for ACL filtering
        user_id = None
        role_ids = []
        is_admin = False

        if request.user_context:
            user_id = request.user_context.user_id
            role_ids = request.user_context.role_ids
            is_admin = request.user_context.is_admin

        async with ElasticsearchService(tenant_id) as service:
            results = await service.semantic_search_with_vector(
                query_vector=request.query_vector,
                limit=request.limit,
                filters=request.filters.dict() if request.filters else None,
                min_score=request.min_score,
                # ACL parameters
                user_id=user_id,
                role_ids=role_ids,
                is_admin=is_admin
            )

        return SearchResponse(
            results=results,
            total=len(results),
            took_ms=0
        )

    except Exception as e:
        logger.error(f"❌ Semantic search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/analytics/{tenant_id}", response_model=AnalyticsResponse)
async def get_analytics(
    tenant_id: str,
    request: AnalyticsRequest,
    _: bool = Depends(verify_api_key)
):
    """Get search and document analytics"""
    try:
        async with ElasticsearchService(tenant_id) as service:
            analytics = await service.get_analytics(
                date_from=request.date_from,
                date_to=request.date_to
            )

        return AnalyticsResponse(**analytics)

    except Exception as e:
        logger.error(f"❌ Analytics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/facets/{tenant_id}", response_model=FacetResponse)
async def get_facets(
    tenant_id: str,
    request: FacetRequest,
    _: bool = Depends(verify_api_key)
):
    """Get facets for search results"""
    try:
        async with ElasticsearchService(tenant_id) as service:
            facets = await service.get_facets(
                query=request.query,
                filters=request.filters.dict() if request.filters else None,
                facet_fields=request.facet_fields,
                max_facet_values=request.max_facet_values
            )

        return FacetResponse(**facets)

    except Exception as e:
        logger.error(f"❌ Facets failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/document/{tenant_id}/{doc_id}")
async def delete_document(
    tenant_id: str,
    doc_id: str,
    _: bool = Depends(verify_api_key)
):
    """Delete a document from Elasticsearch"""
    try:
        async with ElasticsearchService(tenant_id) as service:
            success = await service.delete_document(doc_id)

        if success:
            return {"status": "success", "message": f"Document {doc_id} deleted"}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")

    except Exception as e:
        logger.error(f"❌ Delete document failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/index/create/{tenant_id}")
async def create_index(
    tenant_id: str,
    _: bool = Depends(verify_api_key)
):
    """Create Elasticsearch index for tenant"""
    try:
        async with ElasticsearchService(tenant_id) as service:
            success = service.create_index_if_not_exists()

        if success:
            return {"status": "success", "message": f"Index created for tenant {tenant_id}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create index")

    except Exception as e:
        logger.error(f"❌ Create index failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
