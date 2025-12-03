"""
API endpoints for Public Knowledge Base
Provides access to shared specialized documents (legislation, regulations, etc.)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
import logging

from app.schemas.public_knowledge import (
    PublicDocumentCreate,
    PublicDocumentResponse,
    PublicSearchRequest,
    PublicSearchResponse,
    CombinedSearchRequest,
    CombinedSearchResponse,
    PublicKnowledgeStats,
    PublicDocumentCategory,
    Jurisdiction
)
from app.services.public_knowledge_service import public_knowledge_service
from app.core.security import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public-knowledge", tags=["public-knowledge"])


@router.get("/health")
async def health_check():
    """Check public knowledge base health"""
    try:
        await public_knowledge_service.initialize()
        return {
            "status": "healthy",
            "service": "public-knowledge-base",
            "collection": "PublicKnowledge"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.get("/stats", response_model=PublicKnowledgeStats)
async def get_statistics():
    """Get public knowledge base statistics"""
    try:
        return await public_knowledge_service.get_stats()
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents", response_model=PublicDocumentResponse)
async def add_document(
    document: PublicDocumentCreate,
    api_key: str = Depends(verify_api_key)
):
    """
    Add a document to the public knowledge base.
    Requires API key authentication (admin only).
    """
    try:
        return await public_knowledge_service.add_document(document)
    except Exception as e:
        logger.error(f"Failed to add document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/batch")
async def batch_add_documents(
    documents: List[PublicDocumentCreate],
    api_key: str = Depends(verify_api_key)
):
    """
    Add multiple documents in batch.
    Requires API key authentication (admin only).
    """
    try:
        return await public_knowledge_service.batch_add_documents(documents)
    except Exception as e:
        logger.error(f"Batch add failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}", response_model=PublicDocumentResponse)
async def get_document(document_id: str):
    """Get a specific document by ID"""
    document = await public_knowledge_service.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    api_key: str = Depends(verify_api_key)
):
    """
    Delete a document from the public knowledge base.
    Requires API key authentication (admin only).
    """
    success = await public_knowledge_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found or could not be deleted")
    return {"status": "deleted", "document_id": document_id}


@router.post("/search", response_model=PublicSearchResponse)
async def search_public_knowledge(request: PublicSearchRequest):
    """
    Search the public knowledge base.
    Supports filtering by category, jurisdiction, topics, and dates.
    """
    try:
        return await public_knowledge_service.search(request)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search", response_model=PublicSearchResponse)
async def search_public_knowledge_get(
    query: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Max results"),
    categories: Optional[List[PublicDocumentCategory]] = Query(None, description="Filter by categories"),
    jurisdictions: Optional[List[Jurisdiction]] = Query(None, description="Filter by jurisdictions"),
    topics: Optional[List[str]] = Query(None, description="Filter by topics"),
    verified_only: bool = Query(False, description="Only verified documents"),
    search_type: str = Query("hybrid", pattern="^(vector|keyword|hybrid)$", description="Search type")
):
    """
    Search the public knowledge base (GET method for simpler queries).
    """
    request = PublicSearchRequest(
        query=query,
        limit=limit,
        categories=categories,
        jurisdictions=jurisdictions,
        topics=topics,
        verified_only=verified_only,
        search_type=search_type
    )
    try:
        return await public_knowledge_service.search(request)
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/combined-search", response_model=CombinedSearchResponse)
async def combined_search(
    request: CombinedSearchRequest,
    collection_name: str = Query(..., description="Tenant collection name")
):
    """
    Search both tenant documents and public knowledge base.
    Results can be merged using different strategies.
    """
    try:
        return await public_knowledge_service.combined_search(request, collection_name)
    except Exception as e:
        logger.error(f"Combined search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def list_categories():
    """List available document categories"""
    return {
        "categories": [
            {
                "value": cat.value,
                "name": cat.name,
                "description": _get_category_description(cat)
            }
            for cat in PublicDocumentCategory
        ]
    }


@router.get("/jurisdictions")
async def list_jurisdictions():
    """List available jurisdictions"""
    return {
        "jurisdictions": [
            {
                "value": jur.value,
                "name": jur.name,
                "description": _get_jurisdiction_description(jur)
            }
            for jur in Jurisdiction
        ]
    }


def _get_category_description(category: PublicDocumentCategory) -> str:
    """Get description for a category"""
    descriptions = {
        PublicDocumentCategory.LEGISLATION: "Leyes, decretos, códigos",
        PublicDocumentCategory.REGULATION: "Normativas, reglamentos",
        PublicDocumentCategory.JURISPRUDENCE: "Sentencias, jurisprudencia",
        PublicDocumentCategory.TEMPLATE: "Plantillas de documentos legales",
        PublicDocumentCategory.GUIDELINE: "Guías, manuales, procedimientos",
        PublicDocumentCategory.REFERENCE: "Material de referencia general",
        PublicDocumentCategory.FORM: "Formularios oficiales",
        PublicDocumentCategory.TREATY: "Tratados, convenios internacionales"
    }
    return descriptions.get(category, "")


def _get_jurisdiction_description(jurisdiction: Jurisdiction) -> str:
    """Get description for a jurisdiction"""
    descriptions = {
        Jurisdiction.SPAIN: "Legislación española",
        Jurisdiction.EUROPEAN_UNION: "Legislación de la Unión Europea",
        Jurisdiction.INTERNATIONAL: "Legislación internacional",
        Jurisdiction.REGIONAL: "Legislación autonómica / regional"
    }
    return descriptions.get(jurisdiction, "")
