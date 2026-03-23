"""
Entity Graph API

Endpoints for storing and querying extracted entities in the sector graph.
Called by weaviate-service during indexing to persist entities from
the KnowledgeExtractionService into FalkorDB.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.security import verify_api_key
from app.services.entity_graph_bridge import entity_graph_bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tree/entities", tags=["entity-graph"])


# ─── Request/Response Models ─────────────────────────────────

class EntityItem(BaseModel):
    type: str = Field(..., description="Entity type (person, organization, etc.)")
    value: str = Field(..., description="Entity value (e.g., 'Juan Garcia')")
    confidence: float = Field(0.8, ge=0.0, le=1.0)
    attributes: Dict[str, Any] = Field(default_factory=dict)


class RelationshipItem(BaseModel):
    source: str = Field(..., description="Source entity value")
    target: str = Field(..., description="Target entity value")
    type: str = Field("relates_to", description="Relationship type")
    strength: float = Field(0.5, ge=0.0, le=1.0)


class StoreEntitiesRequest(BaseModel):
    tenant_id: str
    document_id: str
    entities: List[EntityItem] = Field(default_factory=list)
    relationships: List[RelationshipItem] = Field(default_factory=list)


class StoreEntitiesResponse(BaseModel):
    success: bool
    entities_stored: int = 0
    entities_skipped: int = 0
    relationships_stored: int = 0
    relationships_skipped: int = 0
    errors: List[str] = Field(default_factory=list)


# ─── Endpoints ────────────────────────────────────────────────

@router.post("/store", response_model=StoreEntitiesResponse)
async def store_entities(
    request: StoreEntitiesRequest,
    _: bool = Depends(verify_api_key),
):
    """
    Store extracted entities and relationships in the sector graph.

    Called by weaviate-service's KnowledgeExtractionService after
    entity extraction. Creates typed nodes (Persona, Organizacion)
    with INSTANCE_OF edges to the ontology and EXTRACTED_FROM edges
    to the source document.
    """
    response = StoreEntitiesResponse(success=True)

    # Store entities
    if request.entities:
        entity_result = await entity_graph_bridge.store_entities(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            entities=[e.model_dump() for e in request.entities],
        )
        response.entities_stored = entity_result.get("stored", 0)
        response.entities_skipped = entity_result.get("skipped", 0)
        response.errors.extend(entity_result.get("errors", []))

    # Store relationships
    if request.relationships:
        rel_result = await entity_graph_bridge.store_relationships(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            relationships=[r.model_dump() for r in request.relationships],
        )
        response.relationships_stored = rel_result.get("stored", 0)
        response.relationships_skipped = rel_result.get("skipped", 0)

    return response


@router.get("/by-document/{document_id}")
async def get_document_entities(
    document_id: str,
    tenant_id: str = Query(..., description="Tenant identifier"),
):
    """Get all entities extracted from a specific document."""
    entities = await entity_graph_bridge.get_document_entities(
        tenant_id=tenant_id,
        document_id=document_id,
    )
    return {"document_id": document_id, "entities": entities}


@router.get("/search")
async def search_entity(
    value: str = Query(..., description="Entity value to search for"),
    tenant_id: str = Query(..., description="Tenant identifier"),
    type: Optional[str] = Query(None, description="Entity type filter (person, organization)"),
    max_depth: int = Query(2, ge=1, le=4, description="Graph traversal depth"),
    limit: int = Query(20, ge=1, le=100),
):
    """
    Search for an entity and its neighborhood in the sector graph.

    Returns the entity, its graph neighbors, and connected documents.
    Used by SmartSearch for graph-based query expansion.
    """
    result = await entity_graph_bridge.search_entity(
        tenant_id=tenant_id,
        entity_value=value,
        entity_type=type,
        max_depth=max_depth,
        limit=limit,
    )
    return result
