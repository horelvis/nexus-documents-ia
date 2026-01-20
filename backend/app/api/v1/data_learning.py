"""
API endpoints for Data Learning System.

The Data Learning System enables Emma AI to learn the nature of data from external
connectors (Alfresco, SharePoint, FileSystem) by discovering:
- Content model (types, aspects, properties)
- Folder structure semantics (department, year, classification)
- Property mappings with search weights
- Relationship types for Knowledge Graph expansion
- Optimal indexing strategies per document type
"""
import logging
from math import ceil
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.async_database import get_async_db
from app.db.models import (
    User,
    Connector,
    ConnectorContentModel,
    LearnedFolderPattern,
    LearnedPropertyMapping,
    LearnedRelationshipType,
    ConnectorIndexingStrategy,
    DataLearningJob,
)
from app.schemas.data_learning import (
    # Content Model
    ConnectorContentModelResponse,
    ContentModelSummary,
    # Folder Patterns
    LearnedFolderPatternResponse,
    LearnedFolderPatternUpdate,
    # Property Mappings
    LearnedPropertyMappingResponse,
    LearnedPropertyMappingUpdate,
    # Relationship Types
    LearnedRelationshipTypeResponse,
    LearnedRelationshipTypeUpdate,
    # Indexing Strategies
    ConnectorIndexingStrategyResponse,
    ConnectorIndexingStrategyCreate,
    ConnectorIndexingStrategyUpdate,
    ChunkingType,
    # Learning Jobs
    DataLearningJobResponse,
    DataLearningJobListResponse,
    TriggerLearningRequest,
    TriggerLearningResponse,
    ConnectorLearningStatusResponse,
    DataLearningJobType,
    DataLearningJobStatus,  # Use schema enum for FastAPI Query params
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _check_admin_permission(user: User, tenant_id: str) -> None:
    """Verify user has admin permissions for the tenant."""
    if str(user.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")


async def _get_connector_or_404(
    connector_id: UUID,
    tenant_id: str,
    db: AsyncSession,
) -> Connector:
    """Get connector by ID or raise 404."""
    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    return connector


# =============================================================================
# Learning Status and Trigger Endpoints
# =============================================================================

@router.get("/{connector_id}/learning-status", response_model=ConnectorLearningStatusResponse)
async def get_learning_status(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get overall learning status for a connector.

    Returns:
    - Whether content model has been discovered
    - Counts of folder patterns, property mappings, relationships
    - Active indexing strategies
    - Latest learning job status
    - Recommendations for improving learning
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import LearningOrchestrator

    orchestrator = LearningOrchestrator(db)

    try:
        status = await orchestrator.get_connector_learning_status(connector_id)
        return status
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{connector_id}/learn", response_model=TriggerLearningResponse)
async def trigger_learning(
    connector_id: UUID,
    request: TriggerLearningRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Trigger a learning job for a connector.

    Learning types:
    - FULL_LEARNING: Run all phases (content model, folders, properties, relationships, strategies)
    - CONTENT_MODEL_DISCOVERY: Only discover types, aspects, properties
    - FOLDER_ANALYSIS: Only analyze folder structure patterns
    - PROPERTY_MAPPING: Only generate property-to-field mappings
    - RELATIONSHIP_LEARNING: Only learn relationship types
    - STRATEGY_OPTIMIZATION: Only generate indexing strategies

    The job runs synchronously for now (will be async via Celery in production).
    """
    await _check_admin_permission(current_user, tenant_id)
    connector = await _get_connector_or_404(connector_id, tenant_id, db)

    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is not active")

    from app.services.data_learning import LearningOrchestrator

    orchestrator = LearningOrchestrator(db)

    try:
        response = await orchestrator.trigger_learning(
            connector_id=connector_id,
            request=request,
            user_id=current_user.id,
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Learning job failed: {e}")
        raise HTTPException(status_code=500, detail=f"Learning job failed: {e}")


# =============================================================================
# Content Model Endpoints
# =============================================================================

@router.get("/{connector_id}/model", response_model=Optional[ConnectorContentModelResponse])
async def get_content_model(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get the discovered content model for a connector.

    Returns:
    - content_types: Document types (e.g., gdapm:expediente)
    - aspects: Aspects with properties (e.g., cm:auditable)
    - property_definitions: All property definitions
    - type_semantics: LLM-enriched semantic understanding
    - property_semantics: Property importance and search weights
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(ConnectorContentModel)
        .where(ConnectorContentModel.connector_id == connector_id)
    )
    content_model = result.scalar_one_or_none()

    if not content_model:
        return None

    return ConnectorContentModelResponse.model_validate(content_model)


@router.get("/{connector_id}/model/summary", response_model=Optional[ContentModelSummary])
async def get_content_model_summary(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get a summary of the discovered content model.

    Returns counts and key type names without full definitions.
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import ContentModelDiscoveryService

    service = ContentModelDiscoveryService(db)
    summary = await service.get_content_model_summary(connector_id)

    return summary


# =============================================================================
# Folder Pattern Endpoints
# =============================================================================

@router.get("/{connector_id}/folder-patterns")
async def list_folder_patterns(
    connector_id: UUID,
    verified_only: bool = Query(False, description="Only show verified patterns"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List learned folder patterns for a connector.

    Folder patterns map path levels to semantic meanings:
    - /Sites/{site}/RRHH/{year}/Expedientes → department=RRHH, year=2024, type=Expedientes
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    query = (
        select(LearnedFolderPattern)
        .where(LearnedFolderPattern.connector_id == connector_id)
    )

    if verified_only:
        query = query.where(LearnedFolderPattern.is_verified == True)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(LearnedFolderPattern.confidence.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    patterns = result.scalars().all()

    items = [LearnedFolderPatternResponse.model_validate(p) for p in patterns]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total > 0 else 1,
    }


@router.get("/{connector_id}/folder-patterns/{pattern_id}", response_model=LearnedFolderPatternResponse)
async def get_folder_pattern(
    connector_id: UUID,
    pattern_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Get a specific folder pattern."""
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(LearnedFolderPattern)
        .where(LearnedFolderPattern.id == pattern_id)
        .where(LearnedFolderPattern.connector_id == connector_id)
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise HTTPException(status_code=404, detail="Folder pattern not found")

    return LearnedFolderPatternResponse.model_validate(pattern)


@router.put("/{connector_id}/folder-patterns/{pattern_id}", response_model=LearnedFolderPatternResponse)
async def update_folder_pattern(
    connector_id: UUID,
    pattern_id: UUID,
    update: LearnedFolderPatternUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update a folder pattern.

    Use this to:
    - Verify a learned pattern (is_verified=True)
    - Adjust level semantics
    - Change priority
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(LearnedFolderPattern)
        .where(LearnedFolderPattern.id == pattern_id)
        .where(LearnedFolderPattern.connector_id == connector_id)
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise HTTPException(status_code=404, detail="Folder pattern not found")

    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(pattern, key, value)

    await db.commit()
    await db.refresh(pattern)

    return LearnedFolderPatternResponse.model_validate(pattern)


class FolderContextRequest(BaseModel):
    """Request for getting folder context."""
    path: str


class FolderContextResponse(BaseModel):
    """Response with folder context."""
    path: str
    semantics: Dict[str, Any]
    pattern_id: Optional[UUID] = None
    confidence: float = 0.0


@router.post("/{connector_id}/folder-context", response_model=FolderContextResponse)
async def get_folder_context(
    connector_id: UUID,
    request: FolderContextRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get the semantic context for a folder path.

    Uses learned folder patterns to determine the semantic meaning of
    each level in the folder hierarchy (e.g., department, year, project).
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning.folder_structure_analyzer import FolderStructureAnalyzer

    analyzer = FolderStructureAnalyzer(db)
    folder_context = await analyzer.get_folder_context(
        connector_id=connector_id,
        path=request.path,
    )

    if not folder_context:
        return FolderContextResponse(
            path=request.path,
            semantics={},
            pattern_id=None,
            confidence=0.0,
        )

    return FolderContextResponse(
        path=request.path,
        semantics=folder_context.semantics,
        pattern_id=folder_context.pattern_id,
        confidence=folder_context.confidence,
    )


# =============================================================================
# Property Mapping Endpoints
# =============================================================================

@router.get("/{connector_id}/property-mappings")
async def list_property_mappings(
    connector_id: UUID,
    source_type: Optional[str] = Query(None, description="Filter by document type"),
    include_in_embedding: Optional[bool] = Query(None, description="Filter by embedding inclusion"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List property mappings for a connector.

    Property mappings define:
    - source_property: Native property name (e.g., gdapm:numExpediente)
    - target_field: Normalized field name (e.g., identifier)
    - search_weight: Importance for search ranking (0.0-2.0)
    - include_in_embedding: Whether to include in vector embedding
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    query = (
        select(LearnedPropertyMapping)
        .where(LearnedPropertyMapping.connector_id == connector_id)
    )

    if source_type:
        query = query.where(
            (LearnedPropertyMapping.source_type == source_type) |
            (LearnedPropertyMapping.source_type.is_(None))
        )
    if include_in_embedding is not None:
        query = query.where(LearnedPropertyMapping.include_in_embedding == include_in_embedding)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(LearnedPropertyMapping.search_weight.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    mappings = result.scalars().all()

    items = [LearnedPropertyMappingResponse.model_validate(m) for m in mappings]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total > 0 else 1,
    }


@router.get("/{connector_id}/property-mappings/{mapping_id}", response_model=LearnedPropertyMappingResponse)
async def get_property_mapping(
    connector_id: UUID,
    mapping_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Get a specific property mapping."""
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(LearnedPropertyMapping)
        .where(LearnedPropertyMapping.id == mapping_id)
        .where(LearnedPropertyMapping.connector_id == connector_id)
    )
    mapping = result.scalar_one_or_none()

    if not mapping:
        raise HTTPException(status_code=404, detail="Property mapping not found")

    return LearnedPropertyMappingResponse.model_validate(mapping)


@router.put("/{connector_id}/property-mappings/{mapping_id}", response_model=LearnedPropertyMappingResponse)
async def update_property_mapping(
    connector_id: UUID,
    mapping_id: UUID,
    update: LearnedPropertyMappingUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update a property mapping.

    Use this to:
    - Adjust search_weight to boost/reduce importance
    - Change target_field for normalization
    - Toggle include_in_embedding
    - Set is_filterable/is_facetable for search UI
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import MetadataIntelligenceService

    service = MetadataIntelligenceService(db)
    mapping = await service.update_property_mapping(mapping_id, update)

    if not mapping:
        raise HTTPException(status_code=404, detail="Property mapping not found")

    return LearnedPropertyMappingResponse.model_validate(mapping)


# =============================================================================
# Relationship Type Endpoints
# =============================================================================

@router.get("/{connector_id}/relationship-types")
async def list_relationship_types(
    connector_id: UUID,
    include_in_retrieval: Optional[bool] = Query(None, description="Filter by retrieval inclusion"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List learned relationship types for a connector.

    Relationship types map connector associations to Knowledge Graph edges:
    - cm:references → references (bidirectional)
    - peer:related → relates_to (peer association)
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    query = (
        select(LearnedRelationshipType)
        .where(LearnedRelationshipType.connector_id == connector_id)
    )

    if include_in_retrieval is not None:
        query = query.where(LearnedRelationshipType.include_in_retrieval == include_in_retrieval)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(LearnedRelationshipType.weight.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    types = result.scalars().all()

    items = [LearnedRelationshipTypeResponse.model_validate(t) for t in types]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total > 0 else 1,
    }


@router.put("/{connector_id}/relationship-types/{type_id}", response_model=LearnedRelationshipTypeResponse)
async def update_relationship_type(
    connector_id: UUID,
    type_id: UUID,
    update: LearnedRelationshipTypeUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update a relationship type mapping.

    Use this to:
    - Change KG edge type name
    - Adjust weight for retrieval expansion
    - Toggle include_in_retrieval
    - Modify expansion_depth
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import RelationshipLearner

    learner = RelationshipLearner(db)
    rel_type = await learner.update_relationship_type(type_id, update)

    if not rel_type:
        raise HTTPException(status_code=404, detail="Relationship type not found")

    return LearnedRelationshipTypeResponse.model_validate(rel_type)


# =============================================================================
# Indexing Strategy Endpoints
# =============================================================================

@router.get("/{connector_id}/indexing-strategies")
async def list_indexing_strategies(
    connector_id: UUID,
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List indexing strategies for a connector.

    Strategies define how documents are processed:
    - chunking_type: semantic, legal_sections, markdown_headers, page_based
    - embedding_fields: Which fields to include in vector embedding
    - extract_entities: Whether to extract named entities
    - priority: Higher priority strategies match first
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    query = (
        select(ConnectorIndexingStrategy)
        .where(ConnectorIndexingStrategy.connector_id == connector_id)
    )

    if is_active is not None:
        query = query.where(ConnectorIndexingStrategy.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(ConnectorIndexingStrategy.priority.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    strategies = result.scalars().all()

    items = [ConnectorIndexingStrategyResponse.model_validate(s) for s in strategies]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total > 0 else 1,
    }


@router.get("/{connector_id}/indexing-strategies/{strategy_id}", response_model=ConnectorIndexingStrategyResponse)
async def get_indexing_strategy(
    connector_id: UUID,
    strategy_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Get a specific indexing strategy."""
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(ConnectorIndexingStrategy)
        .where(ConnectorIndexingStrategy.id == strategy_id)
        .where(ConnectorIndexingStrategy.connector_id == connector_id)
    )
    strategy = result.scalar_one_or_none()

    if not strategy:
        raise HTTPException(status_code=404, detail="Indexing strategy not found")

    return ConnectorIndexingStrategyResponse.model_validate(strategy)


@router.post("/{connector_id}/indexing-strategies", response_model=ConnectorIndexingStrategyResponse, status_code=201)
async def create_indexing_strategy(
    connector_id: UUID,
    create: ConnectorIndexingStrategyCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Create a custom indexing strategy.

    Use this to define specific processing rules for document types or MIME types.
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import IndexingStrategyOptimizer

    optimizer = IndexingStrategyOptimizer(db)
    strategy = await optimizer.create_strategy(connector_id, create)

    return ConnectorIndexingStrategyResponse.model_validate(strategy)


@router.put("/{connector_id}/indexing-strategies/{strategy_id}", response_model=ConnectorIndexingStrategyResponse)
async def update_indexing_strategy(
    connector_id: UUID,
    strategy_id: UUID,
    update: ConnectorIndexingStrategyUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update an indexing strategy.

    Use this to:
    - Change chunking configuration
    - Adjust embedding fields and weights
    - Toggle entity extraction
    - Enable/disable the strategy
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import IndexingStrategyOptimizer

    optimizer = IndexingStrategyOptimizer(db)
    strategy = await optimizer.update_strategy(strategy_id, update)

    if not strategy:
        raise HTTPException(status_code=404, detail="Indexing strategy not found")

    return ConnectorIndexingStrategyResponse.model_validate(strategy)


@router.delete("/{connector_id}/indexing-strategies/{strategy_id}", status_code=204)
async def delete_indexing_strategy(
    connector_id: UUID,
    strategy_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Delete an indexing strategy."""
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(ConnectorIndexingStrategy)
        .where(ConnectorIndexingStrategy.id == strategy_id)
        .where(ConnectorIndexingStrategy.connector_id == connector_id)
    )
    strategy = result.scalar_one_or_none()

    if not strategy:
        raise HTTPException(status_code=404, detail="Indexing strategy not found")

    await db.delete(strategy)
    await db.commit()

    return None


# =============================================================================
# Learning Job Endpoints
# =============================================================================

@router.get("/{connector_id}/learning-jobs", response_model=DataLearningJobListResponse)
async def list_learning_jobs(
    connector_id: UUID,
    status: Optional[DataLearningJobStatus] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List learning jobs for a connector.

    Returns job history with status, progress, and results.
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    query = (
        select(DataLearningJob)
        .where(DataLearningJob.connector_id == connector_id)
    )

    if status:
        query = query.where(DataLearningJob.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination and ordering
    query = query.order_by(DataLearningJob.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    items = [DataLearningJobResponse.model_validate(j) for j in jobs]

    return DataLearningJobListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/{connector_id}/learning-jobs/{job_id}", response_model=DataLearningJobResponse)
async def get_learning_job(
    connector_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Get details of a specific learning job."""
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    result = await db.execute(
        select(DataLearningJob)
        .where(DataLearningJob.id == job_id)
        .where(DataLearningJob.connector_id == connector_id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Learning job not found")

    return DataLearningJobResponse.model_validate(job)


@router.post("/{connector_id}/learning-jobs/{job_id}/cancel")
async def cancel_learning_job(
    connector_id: UUID,
    job_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Cancel a running learning job.

    Only jobs with status RUNNING or PENDING can be cancelled.
    """
    await _check_admin_permission(current_user, tenant_id)
    await _get_connector_or_404(connector_id, tenant_id, db)

    from app.services.data_learning import LearningOrchestrator

    orchestrator = LearningOrchestrator(db)
    cancelled = await orchestrator.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(
            status_code=400,
            detail="Job not found or cannot be cancelled (not running)"
        )

    return {"status": "cancelled", "job_id": str(job_id)}
