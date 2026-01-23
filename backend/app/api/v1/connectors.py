"""
API endpoints for Connector management (admin-only).

Connectors are external data source configurations that admins create.
Users then authorize and sync their data through these connectors.
"""
import logging
from math import ceil
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

# Background worker URL for task dispatch
BACKGROUND_WORKER_URL = getattr(settings, 'BACKGROUND_TASKS_URL', 'http://background-worker:8100')

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.db.async_database import get_async_db
from app.db.models import User, Connector, UserConnectorAuth, UserDocumentSync
from app.schemas.connector import (
    ConnectorCreate,
    ConnectorUpdate,
    ConnectorResponse,
    ConnectorListResponse,
    ConnectorHealthCheckResponse,
    ConnectorHealthStatus,
    ConnectorType,
    ConnectorAuthType,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _redact_sensitive_config(config: dict, connector_type: str) -> dict:
    """Remove sensitive fields from config before returning to client."""
    sensitive_keys = {
        "client_secret", "secret_access_key", "password",
        "connection_string", "service_account_json", "access_key_id"
    }
    redacted = {}
    for key, value in config.items():
        if key.lower() in sensitive_keys:
            redacted[key] = "***REDACTED***" if value else None
        else:
            redacted[key] = value
    return redacted


async def _check_admin_permission(user: User, tenant_id: str) -> None:
    """Verify user has admin permissions for the tenant."""
    # For now, check if user is the tenant creator or has admin role
    # This will be enhanced with proper RBAC later
    if str(user.tenant_id) != tenant_id:
        raise HTTPException(status_code=403, detail="Not authorized for this tenant")

    # TODO: Check user has admin role in tenant
    # For now, allow any authenticated user in the tenant to manage connectors
    # In production, this should check user.roles for admin permission


async def _connector_to_response(
    connector: Connector,
    db: AsyncSession
) -> ConnectorResponse:
    """Convert connector model to response with computed fields."""
    from app.db.models import IndexedDocument

    # Count users with active auth
    users_connected_result = await db.execute(
        select(func.count(UserConnectorAuth.id))
        .where(UserConnectorAuth.connector_id == connector.id)
        .where(UserConnectorAuth.is_valid == True)
    )
    users_connected = users_connected_result.scalar() or 0

    # Count users with active sync
    users_syncing_result = await db.execute(
        select(func.count(UserDocumentSync.id))
        .where(UserDocumentSync.connector_id == connector.id)
        .where(UserDocumentSync.sync_enabled == True)
    )
    users_syncing = users_syncing_result.scalar() or 0

    # Get document counts by status from IndexedDocument
    doc_counts = await db.execute(
        select(
            func.count(IndexedDocument.id).label("total"),
            func.sum(func.cast(IndexedDocument.indexing_status == "pending", Integer)).label("pending"),
            func.sum(func.cast(IndexedDocument.indexing_status == "indexed", Integer)).label("indexed"),
            func.sum(func.cast(IndexedDocument.indexing_status == "failed", Integer)).label("failed"),
        )
        .where(IndexedDocument.connector_id == connector.id)
    )
    doc_row = doc_counts.first()

    return ConnectorResponse(
        id=connector.id,
        tenant_id=connector.tenant_id,
        name=connector.name,
        description=connector.description,
        connector_type=ConnectorType(connector.connector_type),
        auth_type=ConnectorAuthType(connector.auth_type),
        config=_redact_sensitive_config(connector.config or {}, connector.connector_type),
        sync_enabled=connector.sync_enabled,
        sync_interval_hours=connector.sync_interval_hours,
        is_active=connector.is_active,
        health_status=ConnectorHealthStatus(connector.health_status or "unknown"),
        health_message=connector.health_message,
        last_health_check=connector.last_health_check,
        created_by_id=connector.created_by_id,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
        users_connected=users_connected,
        users_syncing=users_syncing,
        # NEW: Document processing counts (use 'or 0' to handle NULL from SQL SUM)
        documents_total=(doc_row.total or 0) if doc_row else 0,
        documents_pending=(doc_row.pending or 0) if doc_row else 0,
        documents_indexed=(doc_row.indexed or 0) if doc_row else 0,
        documents_failed=(doc_row.failed or 0) if doc_row else 0,
    )


# =============================================================================
# Connector CRUD Endpoints (Admin Only)
# =============================================================================

@router.get("", response_model=ConnectorListResponse)
async def list_connectors(
    connector_type: Optional[ConnectorType] = Query(None, description="Filter by type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List all connectors for the tenant (admin view).

    Returns connectors with statistics on connected/syncing users.
    """
    await _check_admin_permission(current_user, tenant_id)

    # Build query
    query = select(Connector).where(Connector.tenant_id == UUID(tenant_id))

    if connector_type:
        query = query.where(Connector.connector_type == connector_type.value)
    if is_active is not None:
        query = query.where(Connector.is_active == is_active)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.order_by(Connector.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    connectors = result.scalars().all()

    items = [await _connector_to_response(c, db) for c in connectors]

    return ConnectorListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 1,
    )


@router.post("", response_model=ConnectorResponse, status_code=201)
async def create_connector(
    connector_data: ConnectorCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Create a new connector (admin only).

    After creating, users can authorize and start syncing their documents.
    """
    await _check_admin_permission(current_user, tenant_id)

    # Check for duplicate name/type combination
    existing = await db.execute(
        select(Connector)
        .where(Connector.tenant_id == UUID(tenant_id))
        .where(Connector.connector_type == connector_data.connector_type.value)
        .where(Connector.name == connector_data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail=f"Connector with name '{connector_data.name}' and type '{connector_data.connector_type}' already exists"
        )

    # Create connector
    connector = Connector(
        tenant_id=UUID(tenant_id),
        name=connector_data.name,
        description=connector_data.description,
        connector_type=connector_data.connector_type.value,
        auth_type=connector_data.auth_type.value,
        config=connector_data.config,
        sync_enabled=connector_data.sync_enabled,
        sync_interval_hours=connector_data.sync_interval_hours,
        is_active=True,
        health_status="unknown",
        created_by_id=current_user.id,
    )

    db.add(connector)
    await db.commit()
    await db.refresh(connector)

    logger.info(f"Created connector {connector.id} ({connector_data.connector_type}) for tenant {tenant_id}")

    return await _connector_to_response(connector, db)


@router.get("/{connector_id}", response_model=ConnectorResponse)
async def get_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get details of a specific connector (admin only).
    """
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    return await _connector_to_response(connector, db)


@router.put("/{connector_id}", response_model=ConnectorResponse)
async def update_connector(
    connector_id: UUID,
    connector_data: ConnectorUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update a connector's configuration (admin only).
    """
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Update fields
    update_data = connector_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "config" and value:
            # Merge config instead of replacing
            current_config = connector.config or {}
            current_config.update(value)
            setattr(connector, field, current_config)
        else:
            setattr(connector, field, value)

    await db.commit()
    await db.refresh(connector)

    logger.info(f"Updated connector {connector_id}")

    return await _connector_to_response(connector, db)


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Delete a connector (admin only).

    This will:
    - Remove the connector configuration
    - Revoke all user authorizations
    - Stop all active syncs
    - Mark indexed documents as orphaned (cleanup separately)
    """
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Delete will cascade to user_connector_auths and user_document_syncs
    await db.delete(connector)
    await db.commit()

    logger.info(f"Deleted connector {connector_id}")

    # TODO: Trigger background task to clean up indexed documents in Weaviate

    return Response(status_code=204)


# =============================================================================
# Health Check Endpoint
# =============================================================================

@router.post("/{connector_id}/health-check", response_model=ConnectorHealthCheckResponse)
async def check_connector_health(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Check the health of a connector (admin only).

    This verifies:
    - Configuration is valid
    - Service account credentials work (if applicable)
    - External service is reachable
    """
    from datetime import datetime, timezone
    from app.services.connector_health_service import get_connector_health_service

    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Perform actual health check based on connector type
    health_service = get_connector_health_service()
    health_result = await health_service.check_health(
        connector_type=connector.connector_type,
        config=connector.config or {}
    )

    # Map status to enum
    status_map = {
        "healthy": ConnectorHealthStatus.HEALTHY,
        "degraded": ConnectorHealthStatus.DEGRADED,
        "unhealthy": ConnectorHealthStatus.UNHEALTHY,
        "unknown": ConnectorHealthStatus.UNKNOWN,
    }
    health_status = status_map.get(health_result.status, ConnectorHealthStatus.UNKNOWN)

    # Update connector with health check results
    connector.last_health_check = datetime.now(timezone.utc)
    connector.health_status = health_result.status
    connector.health_message = health_result.message

    await db.commit()

    logger.info(
        f"Health check for connector {connector_id}: {health_result.status} - {health_result.message}"
    )

    return ConnectorHealthCheckResponse(
        connector_id=connector_id,
        status=health_status,
        message=health_result.message,
        checked_at=connector.last_health_check,
        details=health_result.details,
    )


# =============================================================================
# Statistics Endpoint
# =============================================================================

@router.get("/{connector_id}/stats")
async def get_connector_stats(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get detailed statistics for a connector (admin only).

    Returns:
    - authorizations: OAuth token stats
    - syncs: User sync configuration stats (legacy)
    - documents: Real document indexing statistics from IndexedDocument table
    """
    from app.db.models import IndexedDocument

    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Get user auth stats
    auth_stats = await db.execute(
        select(
            func.count(UserConnectorAuth.id).label("total"),
            func.sum(func.cast(UserConnectorAuth.is_valid, Integer)).label("valid"),
        )
        .where(UserConnectorAuth.connector_id == connector_id)
    )
    auth_row = auth_stats.first()

    # Get sync stats (legacy - from UserDocumentSync)
    sync_stats = await db.execute(
        select(
            func.count(UserDocumentSync.id).label("total"),
            func.sum(func.cast(UserDocumentSync.sync_enabled, Integer)).label("enabled"),
            func.sum(UserDocumentSync.documents_total).label("documents_total"),
            func.sum(UserDocumentSync.documents_indexed).label("documents_indexed"),
            func.sum(UserDocumentSync.documents_failed).label("documents_failed"),
            func.sum(UserDocumentSync.total_size_bytes).label("total_size_bytes"),
        )
        .where(UserDocumentSync.connector_id == connector_id)
    )
    sync_row = sync_stats.first()

    # Get REAL document stats from IndexedDocument table
    doc_stats = await db.execute(
        select(
            func.count(IndexedDocument.id).label("total"),
            func.sum(func.cast(IndexedDocument.indexing_status == "pending", Integer)).label("pending"),
            func.sum(func.cast(IndexedDocument.indexing_status == "processing", Integer)).label("processing"),
            func.sum(func.cast(IndexedDocument.indexing_status == "indexed", Integer)).label("indexed"),
            func.sum(func.cast(IndexedDocument.indexing_status == "failed", Integer)).label("failed"),
            func.sum(IndexedDocument.size_bytes).label("total_size_bytes"),
        )
        .where(IndexedDocument.connector_id == connector_id)
    )
    doc_row = doc_stats.first()

    # Get last indexed document timestamp
    last_indexed = await db.execute(
        select(IndexedDocument.indexed_at)
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexed_at.isnot(None))
        .order_by(IndexedDocument.indexed_at.desc())
        .limit(1)
    )
    last_indexed_at = last_indexed.scalar_one_or_none()

    return {
        "connector_id": str(connector_id),
        "authorizations": {
            "total": auth_row.total if auth_row else 0,
            "valid": auth_row.valid if auth_row else 0,
        },
        "syncs": {
            "total_users": (sync_row.total or 0) if sync_row else 0,
            "users_enabled": (sync_row.enabled or 0) if sync_row else 0,
            "documents_total": (sync_row.documents_total or 0) if sync_row else 0,
            "documents_indexed": (sync_row.documents_indexed or 0) if sync_row else 0,
            "documents_failed": (sync_row.documents_failed or 0) if sync_row else 0,
            "total_size_bytes": (sync_row.total_size_bytes or 0) if sync_row else 0,
        },
        # NEW: Real document processing stats
        "documents": {
            "total": (doc_row.total or 0) if doc_row else 0,
            "pending": (doc_row.pending or 0) if doc_row else 0,
            "processing": (doc_row.processing or 0) if doc_row else 0,
            "indexed": (doc_row.indexed or 0) if doc_row else 0,
            "failed": (doc_row.failed or 0) if doc_row else 0,
            "total_size_bytes": (doc_row.total_size_bytes or 0) if doc_row else 0,
            "last_indexed_at": last_indexed_at.isoformat() if last_indexed_at else None,
        },
    }


# =============================================================================
# Sync Endpoints
# =============================================================================

@router.post("/{connector_id}/sync-model")
async def sync_content_model(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Discover and sync the content model (types, aspects, properties) from Alfresco.

    This should be called BEFORE syncing documents to ensure all custom properties
    are discovered and can be properly indexed.

    The discovered model is stored in ConnectorContentModel and includes:
    - content_types: All content types with their properties
    - aspects: All aspects with their properties
    - property_definitions: Flat dict of all property definitions
    - custom namespaces detected (exp:, pmreg:, etc.)

    Returns:
        Summary of discovered model elements
    """
    from datetime import datetime, timezone
    from app.db.models import ConnectorContentModel

    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    if connector.connector_type != "alfresco":
        raise HTTPException(status_code=400, detail="Content model sync only supported for Alfresco connectors")

    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is not active")

    # Import and create adapter
    from app.services.connectors.alfresco import AlfrescoAdapter

    try:
        adapter = AlfrescoAdapter(connector, connector.config)
        content_model = await adapter.fetch_content_model()

        # Convert types list to dict keyed by type ID
        types_dict = {t["id"]: t for t in content_model.get("types", [])}
        aspects_dict = {a["id"]: a for a in content_model.get("aspects", [])}

        # Check if content model already exists for this connector
        existing_model = await db.execute(
            select(ConnectorContentModel)
            .where(ConnectorContentModel.connector_id == connector_id)
        )
        model_record = existing_model.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if model_record:
            # Update existing
            model_record.content_types = types_dict
            model_record.aspects = aspects_dict
            model_record.property_definitions = content_model.get("properties", {})
            model_record.association_types = content_model.get("association_types", {})
            model_record.discovery_method = "public_api"
            model_record.last_updated_at = now
        else:
            # Create new
            model_record = ConnectorContentModel(
                connector_id=connector_id,
                tenant_id=UUID(tenant_id),
                content_types=types_dict,
                aspects=aspects_dict,
                property_definitions=content_model.get("properties", {}),
                association_types=content_model.get("association_types", {}),
                discovery_method="public_api",
                discovered_at=now,
            )
            db.add(model_record)

        await db.commit()

        logger.info(
            f"Content model synced for connector {connector_id}: "
            f"{len(types_dict)} types, {len(aspects_dict)} aspects, "
            f"{len(content_model.get('properties', {}))} properties"
        )

        return {
            "status": "success",
            "connector_id": str(connector_id),
            "model_id": str(model_record.id),
            "model_summary": {
                "types_count": len(types_dict),
                "aspects_count": len(aspects_dict),
                "properties_count": len(content_model.get("properties", {})),
                "association_types_count": len(content_model.get("association_types", {})),
                "custom_namespaces": content_model.get("custom_namespaces", []),
            },
            "message": "Content model discovered and saved to ConnectorContentModel",
        }

    except Exception as e:
        logger.error(f"Failed to sync content model for connector {connector_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync content model: {str(e)}"
        )


@router.get("/{connector_id}/model")
async def get_content_model(
    connector_id: UUID,
    include_properties: bool = Query(True, description="Include full property definitions"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get the discovered content model for a connector.

    Returns the full schema including types, aspects, properties,
    and associations that were discovered during sync-model.
    """
    from app.db.models import ConnectorContentModel

    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Get content model from separate table
    model_result = await db.execute(
        select(ConnectorContentModel)
        .where(ConnectorContentModel.connector_id == connector_id)
    )
    content_model = model_result.scalar_one_or_none()

    if not content_model:
        raise HTTPException(
            status_code=404,
            detail="Content model not yet discovered. Call POST /sync-model first."
        )

    response = {
        "connector_id": str(connector_id),
        "connector_name": connector.name,
        "model_id": str(content_model.id),
        "discovery_method": content_model.discovery_method,
        "discovered_at": content_model.discovered_at.isoformat() if content_model.discovered_at else None,
        "last_updated_at": content_model.last_updated_at.isoformat() if content_model.last_updated_at else None,
        "types": content_model.content_types,
        "aspects": content_model.aspects,
        "association_types": content_model.association_types,
    }

    if include_properties:
        response["property_definitions"] = content_model.property_definitions

    # Also include semantic enrichments if available
    if content_model.type_semantics:
        response["type_semantics"] = content_model.type_semantics
    if content_model.property_semantics:
        response["property_semantics"] = content_model.property_semantics

    return response


@router.post("/{connector_id}/sync-folders")
async def sync_folders(
    connector_id: UUID,
    root_node_id: str = Query("-root-", description="Root folder node ID to start from"),
    max_depth: int = Query(10, description="Maximum folder depth to crawl"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Sync folders with their properties from Alfresco.

    Recursively crawls the folder structure starting from root_node_id
    and captures all folder properties based on the discovered content model.

    Returns:
        List of folders with their properties
    """
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    if connector.connector_type != "alfresco":
        raise HTTPException(status_code=400, detail="Folder sync only supported for Alfresco connectors")

    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is not active")

    from app.services.connectors.alfresco import AlfrescoAdapter

    try:
        adapter = AlfrescoAdapter(connector, connector.config)
        folders = await adapter.list_all_folders_recursive(
            root_node_id=root_node_id,
            max_depth=max_depth,
        )

        # TODO: Store folders in database table (indexed_folders)
        # For now, return the folder list directly

        return {
            "status": "success",
            "connector_id": str(connector_id),
            "folders_count": len(folders),
            "folders": folders,
        }

    except Exception as e:
        logger.error(f"Failed to sync folders for connector {connector_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync folders: {str(e)}"
        )


@router.post("/{connector_id}/sync")
async def trigger_connector_sync(
    connector_id: UUID,
    full_sync: bool = Query(False, description="Force full resync instead of incremental"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Trigger a manual sync for a connector (admin only).

    This dispatches a Celery task to:
    1. Sync document metadata from the source (Alfresco, SharePoint, etc.)
    2. Index pending documents to Weaviate

    Args:
        connector_id: UUID of the connector to sync
        full_sync: If True, resync all documents instead of incremental

    Returns:
        Task ID and status message
    """
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is not active")

    # Dispatch task via background-worker HTTP API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BACKGROUND_WORKER_URL}/tasks/connector/sync",
                json={
                    "connector_id": str(connector_id),
                    "full_sync": full_sync,
                    "batch_size": 10,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
            response.raise_for_status()
            result = response.json()
            task_id = result.get("job_id", "unknown")

        logger.info(f"Triggered sync for connector {connector_id}, task_id={task_id}")

        return {
            "status": "queued",
            "task_id": task_id,
            "connector_id": str(connector_id),
            "message": f"Sync {'(full)' if full_sync else '(incremental)'} queued for processing",
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to queue sync task: {e.response.text}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue sync task: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Failed to queue sync task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue sync task: {e}"
        )


@router.post("/{connector_id}/index-pending")
async def trigger_index_pending(
    connector_id: UUID,
    batch_size: int = Query(10, ge=1, le=100, description="Documents per batch"),
    max_documents: Optional[int] = Query(None, ge=1, description="Max documents to process"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Trigger indexing of pending documents for a connector (admin only).

    This processes documents that have been synced (metadata in PostgreSQL)
    but not yet indexed to Weaviate.

    Args:
        connector_id: UUID of the connector
        batch_size: Number of documents to process per batch
        max_documents: Maximum documents to process (None = all pending)

    Returns:
        Task ID and status message
    """
    from sqlalchemy import func

    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    if not connector.is_active:
        raise HTTPException(status_code=400, detail="Connector is not active")

    # Count pending documents
    from app.db.models import IndexedDocument

    pending_count_result = await db.execute(
        select(func.count(IndexedDocument.id))
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexing_status == "pending")
    )
    pending_count = pending_count_result.scalar() or 0

    if pending_count == 0:
        return {
            "status": "no_pending",
            "connector_id": str(connector_id),
            "pending_count": 0,
            "message": "No pending documents to index",
        }

    # Dispatch task via background-worker HTTP API
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{BACKGROUND_WORKER_URL}/tasks/connector/index-pending",
                json={
                    "connector_id": str(connector_id),
                    "batch_size": batch_size,
                    "max_documents": max_documents,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
            response.raise_for_status()
            result = response.json()
            task_id = result.get("job_id", "unknown")

        logger.info(
            f"Triggered index-pending for connector {connector_id}, "
            f"pending={pending_count}, task_id={task_id}"
        )

        return {
            "status": "queued",
            "task_id": task_id,
            "connector_id": str(connector_id),
            "pending_count": pending_count,
            "message": f"Indexing {pending_count} pending documents",
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"Failed to queue index task: {e.response.text}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue index task: {e.response.text}"
        )
    except Exception as e:
        logger.error(f"Failed to queue index task: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to queue index task: {e}"
        )


@router.get("/{connector_id}/pending-documents")
async def get_pending_documents(
    connector_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List pending documents for a connector (admin only).

    Returns documents that have been synced but not yet indexed to Weaviate.
    """
    from app.db.models import IndexedDocument
    from app.schemas.connector import IndexedDocumentResponse, IndexedDocumentListResponse

    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Build query for pending documents
    query = (
        select(IndexedDocument)
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexing_status == "pending")
        .order_by(IndexedDocument.created_at.desc())
    )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.offset((page - 1) * page_size).limit(page_size)

    docs_result = await db.execute(query)
    documents = docs_result.scalars().all()

    items = [
        IndexedDocumentResponse(
            id=doc.id,
            connector_id=doc.connector_id,
            external_id=doc.external_id,
            external_url=doc.external_url,
            external_path=doc.external_path,
            title=doc.title,
            description=doc.description,
            mime_type=doc.mime_type,
            file_extension=doc.file_extension,
            size_bytes=doc.size_bytes,
            is_tenant_public=doc.is_tenant_public,
            indexing_status=doc.indexing_status,
            indexing_error=doc.indexing_error,
            source_created_at=doc.source_created_at,
            source_modified_at=doc.source_modified_at,
            indexed_at=doc.indexed_at,
        )
        for doc in documents
    ]

    return IndexedDocumentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 1,
    )


@router.get("/indexed-documents")
async def get_all_indexed_documents(
    tenant_id: str = Query(..., description="Tenant ID"),
    status: Optional[str] = Query("indexed", description="Filter by indexing status"),
    limit: Optional[int] = Query(1000, ge=1, le=5000, description="Maximum documents to return"),
    connector_id: Optional[UUID] = Query(None, description="Filter by connector ID"),
    x_api_key: Optional[str] = Query(None, alias="X-API-Key", description="Microservice API key"),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get all indexed documents for a tenant (internal API for SIL reindexing).

    This endpoint is used by the SIL (Structural Intelligence Layer) service
    to fetch documents that need to be indexed to the structural graph.

    Returns documents from IndexedDocument table (connector-sourced documents).

    Authentication: Accepts either user auth (via middleware) or X-API-Key header
    for internal microservice calls.
    """
    # Validate API key for internal service calls
    if x_api_key:
        expected_key = settings.MICROSERVICES_API_KEY
        if x_api_key != expected_key:
            raise HTTPException(status_code=401, detail="Invalid API key")
    from app.db.models import IndexedDocument
    from typing import List, Dict, Any

    # Build query for indexed documents
    query = (
        select(IndexedDocument)
        .where(IndexedDocument.tenant_id == UUID(tenant_id))
    )

    # Filter by status if provided
    if status:
        query = query.where(IndexedDocument.indexing_status == status)

    # Filter by connector if provided
    if connector_id:
        query = query.where(IndexedDocument.connector_id == connector_id)

    # Apply limit
    query = query.order_by(IndexedDocument.created_at.desc()).limit(limit)

    result = await db.execute(query)
    documents = result.scalars().all()

    # Return in format expected by SIL service
    return {
        "documents": [
            {
                "id": str(doc.id),
                "connector_id": str(doc.connector_id) if doc.connector_id else None,
                "external_id": doc.external_id,
                "external_path": doc.external_path,
                "title": doc.title,
                "description": doc.description,
                "mime_type": doc.mime_type,
                "file_extension": doc.file_extension,
                "size_bytes": doc.size_bytes,
                "source_metadata": doc.source_metadata or {},
                "learned_context": doc.learned_context or {},
                "weaviate_id": str(doc.weaviate_id) if doc.weaviate_id else None,
                "indexing_status": doc.indexing_status,
                "source_created_at": doc.source_created_at.isoformat() if doc.source_created_at else None,
                "source_modified_at": doc.source_modified_at.isoformat() if doc.source_modified_at else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
            for doc in documents
        ],
        "total": len(documents),
        "tenant_id": tenant_id,
    }
