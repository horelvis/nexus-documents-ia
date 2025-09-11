"""Elasticsearch API endpoints"""
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any
import logging

from app.core.security import verify_api_key
from app.services.elasticsearch_service import ElasticsearchService
from app.schemas.elasticsearch import (
    DocumentIndexRequest, HybridSearchRequest, SemanticSearchRequest,
    SearchResponse, AnalyticsRequest, AnalyticsResponse, HealthResponse
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/index/{tenant_id}")
async def index_document(
    tenant_id: str,
    request: DocumentIndexRequest,
    _: bool = Depends(verify_api_key)
):
    """Index a document in Elasticsearch"""
    try:
        service = ElasticsearchService(tenant_id)

        # Create index if it doesn't exist
        service.create_index_if_not_exists()

        success = await service.index_document(
            doc_id=request.doc_id,
            title=request.title,
            content=request.content,
            description=request.description,
            content_vector=request.content_vector,
            metadata=request.metadata
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
    """Perform hybrid search"""
    try:
        service = ElasticsearchService(tenant_id)
        results = await service.hybrid_search(
            query=request.query,
            limit=request.limit,
            filters=request.filters.dict() if request.filters else None,
            boost_semantic=request.boost_semantic,
            boost_keyword=request.boost_keyword
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
    """Perform semantic search with vector"""
    try:
        service = ElasticsearchService(tenant_id)
        results = await service.semantic_search_with_vector(
            query_vector=request.query_vector,
            limit=request.limit,
            filters=request.filters.dict() if request.filters else None,
            min_score=request.min_score
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
        service = ElasticsearchService(tenant_id)
        analytics = await service.get_analytics(
            date_from=request.date_from,
            date_to=request.date_to
        )

        return AnalyticsResponse(**analytics)

    except Exception as e:
        logger.error(f"❌ Analytics failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/document/{tenant_id}/{doc_id}")
async def delete_document(
    tenant_id: str,
    doc_id: str,
    _: bool = Depends(verify_api_key)
):
    """Delete a document from Elasticsearch"""
    try:
        service = ElasticsearchService(tenant_id)
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
        service = ElasticsearchService(tenant_id)
        success = service.create_index_if_not_exists()

        if success:
            return {"status": "success", "message": f"Index created for tenant {tenant_id}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to create index")

    except Exception as e:
        logger.error(f"❌ Create index failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))