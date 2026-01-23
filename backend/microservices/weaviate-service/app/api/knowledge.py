"""
Knowledge Graph API endpoints for Emma AI.

Provides REST endpoints for searching and managing knowledge entities
extracted from documents.
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import logging

from app.core.security import verify_api_key as get_api_key
from app.services.knowledge import get_knowledge_service, KnowledgeExtractionService
from app.services.weaviate_service import WeaviateService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Singleton services
_weaviate_service: Optional[WeaviateService] = None


async def get_weaviate() -> WeaviateService:
    """Get or create Weaviate service."""
    global _weaviate_service
    if _weaviate_service is None:
        _weaviate_service = WeaviateService()
        await _weaviate_service.initialize()
    return _weaviate_service


# ============================================================================
# Request/Response Schemas
# ============================================================================

class KnowledgeSearchRequest(BaseModel):
    """Request for knowledge search."""
    query: str = Field(..., description="Search query")
    tenant_id: str = Field(..., description="Tenant identifier")
    entity_types: Optional[List[str]] = Field(None, description="Filter by entity types")
    domain: Optional[str] = Field(None, description="Filter by domain (legal, fiscal, hr)")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")
    user_id: Optional[str] = Field(None, description="User ID for ACL filtering")
    user_role_ids: Optional[List[str]] = Field(None, description="Role IDs for ACL")
    is_admin: bool = Field(False, description="Admin bypass for ACL")


class KnowledgeEntityResponse(BaseModel):
    """Response for a knowledge entity."""
    entity_id: str
    entity_type: str
    entity_value: str
    entity_label: Optional[str] = None
    domain: Optional[str] = None
    source_document_id: Optional[str] = None
    confidence: Optional[float] = None
    context_text: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    related_entity_ids: Optional[List[str]] = None
    related_document_ids: Optional[List[str]] = None
    similarity_score: Optional[float] = None
    weaviate_id: Optional[str] = None


class KnowledgeSearchResponse(BaseModel):
    """Response for knowledge search."""
    results: List[KnowledgeEntityResponse]
    total: int
    query: str


class KnowledgeStatsResponse(BaseModel):
    """Response for knowledge statistics."""
    tenant_id: str
    total_entities: int
    entities_by_type: Dict[str, int]
    entities_by_domain: Dict[str, int]


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    request: KnowledgeSearchRequest,
    _api_key: str = Depends(get_api_key)
):
    """
    Search knowledge entities semantically.

    Searches the knowledge graph for entities matching the query.
    Supports filtering by entity type, domain, and ACL.
    """
    try:
        weaviate = await get_weaviate()

        results = await weaviate.search_knowledge_entities(
            tenant_id=request.tenant_id,
            query=request.query,
            entity_types=request.entity_types,
            domain=request.domain,
            limit=request.limit,
            user_id=request.user_id,
            user_role_ids=request.user_role_ids,
            is_admin=request.is_admin
        )

        entities = [
            KnowledgeEntityResponse(**r) for r in results
        ]

        return KnowledgeSearchResponse(
            results=entities,
            total=len(entities),
            query=request.query
        )

    except Exception as e:
        logger.error(f"❌ Knowledge search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities", response_model=List[KnowledgeEntityResponse])
async def list_entities(
    tenant_id: str = Query(..., description="Tenant identifier"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    limit: int = Query(50, ge=1, le=200, description="Maximum results"),
    _api_key: str = Depends(get_api_key)
):
    """
    List knowledge entities for a tenant.

    Returns entities filtered by type and/or domain.
    """
    try:
        weaviate = await get_weaviate()

        # Use a generic query to list entities
        entity_types = [entity_type] if entity_type else None

        results = await weaviate.search_knowledge_entities(
            tenant_id=tenant_id,
            query="*",  # Match all
            entity_types=entity_types,
            domain=domain,
            limit=limit,
            min_certainty=0.0,  # Accept all
            is_admin=True  # No ACL filtering for list
        )

        return [KnowledgeEntityResponse(**r) for r in results]

    except Exception as e:
        logger.error(f"❌ List entities failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/entities/{entity_id}", response_model=KnowledgeEntityResponse)
async def get_entity(
    entity_id: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Get a specific knowledge entity by ID.
    """
    try:
        weaviate = await get_weaviate()

        # Search by entity_id
        results = await weaviate.search_knowledge_entities(
            tenant_id=tenant_id,
            query=entity_id,
            limit=1,
            min_certainty=0.0,
            is_admin=True
        )

        # Find exact match
        for r in results:
            if r.get("entity_id") == entity_id:
                return KnowledgeEntityResponse(**r)

        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Get entity failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entities/{entity_id}")
async def delete_entity(
    entity_id: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Delete a knowledge entity.
    """
    try:
        weaviate = await get_weaviate()

        success = await weaviate.delete_knowledge_entity(
            tenant_id=tenant_id,
            entity_id=entity_id
        )

        if success:
            return {"status": "deleted", "entity_id": entity_id}
        else:
            raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Delete entity failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{document_id}/knowledge")
async def delete_document_knowledge(
    document_id: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Delete all knowledge entities from a document.
    """
    try:
        weaviate = await get_weaviate()

        deleted_count = await weaviate.delete_knowledge_by_document(
            tenant_id=tenant_id,
            document_id=document_id
        )

        return {
            "status": "deleted",
            "document_id": document_id,
            "entities_deleted": deleted_count
        }

    except Exception as e:
        logger.error(f"❌ Delete document knowledge failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=KnowledgeStatsResponse)
async def get_knowledge_stats(
    tenant_id: str = Query(..., description="Tenant identifier"),
    _api_key: str = Depends(get_api_key)
):
    """
    Get knowledge graph statistics for a tenant.

    Combines data from multiple sources:
    1. Weaviate Knowledge collection (extracted entities)
    2. SIL structural graph (document types from connectors)

    This ensures on-premise deployments with connector documents
    also show meaningful knowledge statistics.
    """
    try:
        weaviate = await get_weaviate()

        # Get entities from Weaviate Knowledge collection
        results = await weaviate.search_knowledge_entities(
            tenant_id=tenant_id,
            query="*",
            limit=1000,
            min_certainty=0.0,
            is_admin=True
        )

        # Compute stats from Weaviate entities
        entities_by_type: Dict[str, int] = {}
        entities_by_domain: Dict[str, int] = {}

        for r in results:
            entity_type = r.get("entity_type", "unknown")
            domain = r.get("domain", "general")

            entities_by_type[entity_type] = entities_by_type.get(entity_type, 0) + 1
            entities_by_domain[domain] = entities_by_domain.get(domain, 0) + 1

        total_entities = len(results)

        # If no entities in Weaviate, also check SIL structural graph
        # This is important for on-premise deployments where documents
        # come from connectors and may not have extracted entities yet
        if total_entities == 0:
            try:
                from app.services.sil.structural_graph import structural_graph

                sil_stats = await structural_graph.get_graph_stats(tenant_id=tenant_id)

                if not sil_stats.get("error"):
                    # Use SIL document types as entity types
                    types_breakdown = sil_stats.get("types_breakdown", {})
                    total_docs = sil_stats.get("total_documents", 0)

                    if total_docs > 0:
                        # Map document types to entity-like representation
                        for doc_type, count in types_breakdown.items():
                            # Convert document types to entity type format
                            entity_type = f"document:{doc_type}" if doc_type else "document:unknown"
                            entities_by_type[entity_type] = count

                        # Set total to documents in SIL graph
                        total_entities = total_docs

                        # Add domain based on document presence
                        entities_by_domain["structural"] = total_docs

                        logger.info(
                            f"Knowledge stats enriched from SIL: {total_docs} documents, "
                            f"{len(types_breakdown)} types"
                        )
            except Exception as sil_error:
                logger.warning(f"Could not get SIL stats for knowledge enrichment: {sil_error}")

        return KnowledgeStatsResponse(
            tenant_id=tenant_id,
            total_entities=total_entities,
            entities_by_type=entities_by_type,
            entities_by_domain=entities_by_domain
        )

    except Exception as e:
        logger.error(f"❌ Get knowledge stats failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
