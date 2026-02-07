"""
API endpoints for Connector management (admin-only).

Connectors are external data source configurations that admins create.
Users then authorize and sync their data through these connectors.
"""
import logging
from math import ceil
from typing import Optional, List
from uuid import UUID

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response
from sqlalchemy import delete, func, select, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

# MCP service URLs for sync/indexing task dispatch
MCP_ALFRESCO_URL = getattr(settings, 'MCP_ALFRESCO_URL', 'http://mcp-alfresco:8000')
MCP_GOOGLE_DRIVE_URL = getattr(settings, 'MCP_GOOGLE_DRIVE_URL', 'http://mcp-google-drive:8000')
MCP_ONEDRIVE_URL = getattr(settings, 'MCP_ONEDRIVE_URL', 'http://mcp-onedrive:8000')

# Map connector_type → MCP service URL
_MCP_URL_BY_TYPE = {
    "alfresco": MCP_ALFRESCO_URL,
    "google_drive": MCP_GOOGLE_DRIVE_URL,
    "onedrive": MCP_ONEDRIVE_URL,
}

# Connector types that use OAuth (popup flow) instead of service-account credentials
_OAUTH_CONNECTOR_TYPES = {"google_drive", "onedrive"}


def _get_mcp_url(connector_type: str) -> str:
    """Get the MCP service URL for a given connector type."""
    url = _MCP_URL_BY_TYPE.get(connector_type)
    if not url:
        raise HTTPException(
            status_code=400,
            detail=f"Sync not supported for connector type: {connector_type}",
        )
    return url

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
            # Merge config — copy dict so SQLAlchemy detects the JSONB change
            current_config = dict(connector.config or {})
            current_config.update(value)
            connector.config = current_config
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

    # Use raw SQL DELETE to trigger DB-level CASCADE on all related tables
    from sqlalchemy import text
    await db.execute(text("DELETE FROM connectors WHERE id = :id"), {"id": str(connector_id)})
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

    # Get error breakdown for failed documents
    error_breakdown = await db.execute(
        select(
            func.count(IndexedDocument.id).label("count"),
            IndexedDocument.indexing_error,
        )
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexing_status == "failed")
        .group_by(IndexedDocument.indexing_error)
        .order_by(func.count(IndexedDocument.id).desc())
        .limit(10)  # Top 10 error types
    )
    error_rows = error_breakdown.fetchall()

    # Format error breakdown
    errors_by_type = []
    for row in error_rows:
        error_msg = row.indexing_error or "Unknown error"
        # Truncate long error messages for display
        if len(error_msg) > 100:
            error_msg = error_msg[:100] + "..."
        errors_by_type.append({
            "count": row.count,
            "error": error_msg,
        })

    # Calculate average indexing time from historical data
    # Priority: Use indexing_duration_seconds (actual processing time) if available
    avg_indexing_seconds = None

    # Try to get actual processing time from the new column
    try:
        avg_indexing_time = await db.execute(
            select(
                func.avg(IndexedDocument.indexing_duration_seconds).label("avg_seconds")
            )
            .where(IndexedDocument.connector_id == connector_id)
            .where(IndexedDocument.indexing_status == "indexed")
            .where(IndexedDocument.indexing_duration_seconds.isnot(None))
            .where(IndexedDocument.indexing_duration_seconds > 0)
        )
        avg_seconds_row = avg_indexing_time.first()
        if avg_seconds_row and avg_seconds_row.avg_seconds:
            avg_indexing_seconds = float(avg_seconds_row.avg_seconds)
    except Exception:
        # Column might not exist yet (migration not applied)
        pass

    # Fallback: Use reasonable default based on typical processing times
    # ~2-3 seconds for text extraction + chunking + embedding + storage
    if avg_indexing_seconds is None:
        avg_indexing_seconds = 3.0  # Reasonable estimate for typical documents

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
        # Real document processing stats with error breakdown
        "documents": {
            "total": (doc_row.total or 0) if doc_row else 0,
            "pending": (doc_row.pending or 0) if doc_row else 0,
            "processing": (doc_row.processing or 0) if doc_row else 0,
            "indexed": (doc_row.indexed or 0) if doc_row else 0,
            "failed": (doc_row.failed or 0) if doc_row else 0,
            "total_size_bytes": (doc_row.total_size_bytes or 0) if doc_row else 0,
            "last_indexed_at": last_indexed_at.isoformat() if last_indexed_at else None,
            "avg_indexing_seconds": avg_indexing_seconds,  # Historical average time per document
            "errors_by_type": errors_by_type,
        },
    }


@router.get("/{connector_id}/failed-documents")
async def get_failed_documents(
    connector_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximum documents to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    error_filter: Optional[str] = Query(None, description="Filter by error message (partial match)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List failed documents for a connector with full details (admin only).

    Returns documents that failed indexing with:
    - Document metadata (title, path, size, type)
    - Error message and timestamp
    - External URL for preview (if available)
    - Actions available (retry, skip, etc.)

    Use error_filter to find specific error types, e.g.:
    - "No text content" - PDFs without extractable text
    - "Unsupported extension" - Files with unrecognized extensions
    - "timeout" - Processing timeouts
    """
    from app.db.models import IndexedDocument

    await _check_admin_permission(current_user, tenant_id)

    # Verify connector exists
    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Build query for failed documents
    query = (
        select(IndexedDocument)
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexing_status == "failed")
    )

    # Apply error filter if provided
    if error_filter:
        query = query.where(IndexedDocument.indexing_error.ilike(f"%{error_filter}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    # Get paginated results
    query = query.order_by(IndexedDocument.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    documents = result.scalars().all()

    # Format response with preview URLs and actions
    items = []
    for doc in documents:
        # Build external URL for preview (Alfresco document library)
        external_preview_url = None
        if doc.external_url:
            external_preview_url = doc.external_url
        elif doc.external_id and connector.connector_type == "alfresco":
            # Build Alfresco document library URL
            base_url = connector.config.get("base_url", "").rstrip("/")
            if base_url:
                external_preview_url = f"{base_url}/share/page/document-details?nodeRef=workspace://SpacesStore/{doc.external_id}"

        items.append({
            "id": str(doc.id),
            "title": doc.title,
            "external_id": doc.external_id,
            "external_path": doc.external_path,
            "external_url": external_preview_url,
            "file_extension": doc.file_extension,
            "mime_type": doc.mime_type,
            "size_bytes": doc.size_bytes,
            "indexing_error": doc.indexing_error,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            "source_modified_at": doc.source_modified_at.isoformat() if doc.source_modified_at else None,
            "actions": {
                "can_retry": True,
                "can_skip": True,
                "can_preview": external_preview_url is not None,
            },
        })

    return {
        "connector_id": str(connector_id),
        "total_count": total_count,
        "offset": offset,
        "limit": limit,
        "items": items,
    }


@router.post("/{connector_id}/retry-failed")
async def retry_failed_documents(
    connector_id: UUID,
    document_ids: Optional[List[str]] = Body(None, description="Specific document IDs to retry, or null for all"),
    error_filter: Optional[str] = Body(None, description="Only retry documents matching this error"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Retry indexing for failed documents (admin only).

    Options:
    - document_ids: List of specific document IDs to retry
    - error_filter: Only retry documents matching this error pattern
    - Both null: Retry ALL failed documents for this connector
    """
    from sqlalchemy import update as sql_update
    from app.db.models import IndexedDocument

    await _check_admin_permission(current_user, tenant_id)

    # Verify connector exists
    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Build update query
    update_query = (
        sql_update(IndexedDocument)
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexing_status == "failed")
    )

    # Apply filters
    if document_ids:
        update_query = update_query.where(IndexedDocument.id.in_([UUID(did) for did in document_ids]))

    if error_filter:
        update_query = update_query.where(IndexedDocument.indexing_error.ilike(f"%{error_filter}%"))

    # Count before update
    count_query = (
        select(func.count(IndexedDocument.id))
        .where(IndexedDocument.connector_id == connector_id)
        .where(IndexedDocument.indexing_status == "failed")
    )
    if document_ids:
        count_query = count_query.where(IndexedDocument.id.in_([UUID(did) for did in document_ids]))
    if error_filter:
        count_query = count_query.where(IndexedDocument.indexing_error.ilike(f"%{error_filter}%"))

    count_result = await db.execute(count_query)
    affected_count = count_result.scalar() or 0

    if affected_count == 0:
        return {
            "success": True,
            "reset_count": 0,
            "message": "No matching failed documents to retry",
        }

    # Reset to pending
    update_query = update_query.values(
        indexing_status="pending",
        indexing_error=None,
    )
    await db.execute(update_query)
    await db.commit()

    logger.info(
        f"🔄 Reset {affected_count} failed documents to pending "
        f"for connector {connector_id} (filter={error_filter})"
    )

    return {
        "success": True,
        "reset_count": affected_count,
        "message": f"Reset {affected_count} documents to pending for re-indexing",
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
    retry_failed: bool = Query(False, description="Also retry previously failed documents"),
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
        retry_failed: If True, reset failed documents to pending before sync

    Returns:
        Task ID and status message
    """
    from sqlalchemy import func, update

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

    # If retry_failed is True, reset failed documents to pending
    failed_reset_count = 0
    if retry_failed:
        from app.db.models import IndexedDocument

        failed_count_result = await db.execute(
            select(func.count(IndexedDocument.id))
            .where(IndexedDocument.connector_id == connector_id)
            .where(IndexedDocument.indexing_status == "failed")
        )
        failed_reset_count = failed_count_result.scalar() or 0

        if failed_reset_count > 0:
            await db.execute(
                update(IndexedDocument)
                .where(IndexedDocument.connector_id == connector_id)
                .where(IndexedDocument.indexing_status == "failed")
                .values(indexing_status="pending", indexing_error=None)
            )
            await db.commit()
            logger.info(
                f"🔄 Reset {failed_reset_count} failed documents to pending "
                f"for connector {connector_id}"
            )

    # Dispatch task to the appropriate MCP service based on connector type
    mcp_url = _get_mcp_url(connector.connector_type)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{mcp_url}/sync",
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

        sync_type = "full" if full_sync else "incremental"
        logger.info(
            f"Triggered sync for connector {connector_id}, "
            f"type={sync_type}, failed_reset={failed_reset_count}, task_id={task_id}"
        )

        message = f"Sync ({sync_type}) queued for processing"
        if failed_reset_count > 0:
            message += f" - reset {failed_reset_count} failed documents"

        return {
            "status": "queued",
            "task_id": task_id,
            "connector_id": str(connector_id),
            "failed_reset": failed_reset_count,
            "message": message,
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
    retry_failed: bool = Query(False, description="Also retry previously failed documents"),
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
        retry_failed: If True, reset failed documents to pending before indexing

    Returns:
        Task ID and status message
    """
    from sqlalchemy import func, update

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

    # Import IndexedDocument model
    from app.db.models import IndexedDocument

    # If retry_failed is True, reset failed documents to pending
    failed_reset_count = 0
    if retry_failed:
        failed_count_result = await db.execute(
            select(func.count(IndexedDocument.id))
            .where(IndexedDocument.connector_id == connector_id)
            .where(IndexedDocument.indexing_status == "failed")
        )
        failed_reset_count = failed_count_result.scalar() or 0

        if failed_reset_count > 0:
            await db.execute(
                update(IndexedDocument)
                .where(IndexedDocument.connector_id == connector_id)
                .where(IndexedDocument.indexing_status == "failed")
                .values(indexing_status="pending", indexing_error=None)
            )
            await db.commit()
            logger.info(
                f"🔄 Reset {failed_reset_count} failed documents to pending "
                f"for connector {connector_id}"
            )

    # Count pending documents (now includes reset failed ones)
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
            "failed_reset": failed_reset_count,
            "message": "No pending documents to index",
        }

    # Dispatch task to the appropriate MCP service based on connector type
    mcp_url = _get_mcp_url(connector.connector_type)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{mcp_url}/index-pending",
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
            f"pending={pending_count}, failed_reset={failed_reset_count}, task_id={task_id}"
        )

        message = f"Indexing {pending_count} pending documents"
        if failed_reset_count > 0:
            message += f" (including {failed_reset_count} previously failed)"

        return {
            "status": "queued",
            "task_id": task_id,
            "connector_id": str(connector_id),
            "pending_count": pending_count,
            "failed_reset": failed_reset_count,
            "message": message,
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


# =============================================================================
# OAuth Proxy Endpoints (Google Drive, OneDrive)
# =============================================================================

@router.get("/{connector_id}/oauth/authorize")
async def oauth_authorize(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Initiate OAuth2 flow for an OAuth connector (admin only).

    Proxies the request to the appropriate MCP service which handles the
    OAuth flow and redirects the user to the consent screen.
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

    if connector.connector_type not in _OAUTH_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth authorize is only available for {', '.join(_OAUTH_CONNECTOR_TYPES)} connectors",
        )

    mcp_url = _MCP_URL_BY_TYPE[connector.connector_type]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{mcp_url}/oauth/authorize",
                params={
                    "connector_id": str(connector_id),
                    "tenant_id": tenant_id,
                },
                follow_redirects=False,
            )

        if response.status_code in (301, 302, 307, 308):
            return {"auth_url": response.headers["location"]}

        return response.json()
    except Exception as e:
        logger.error(f"OAuth authorize proxy failed: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth authorize failed: {e}")


@router.get("/oauth/callback")
async def oauth_callback_proxy(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Proxy OAuth callback to the appropriate MCP service.

    The OAuth provider redirects the browser here after authorization.
    We determine which MCP service to forward to by parsing the connector_id
    from the state parameter (format: "connector_id:tenant_id") and looking
    up the connector type in the database.
    """
    try:
        # Determine MCP destination from state → connector_id → connector_type
        mcp_url = MCP_GOOGLE_DRIVE_URL  # default fallback
        if state and ":" in state:
            connector_id_str = state.split(":", 1)[0]
            try:
                result = await db.execute(
                    select(Connector).where(Connector.id == UUID(connector_id_str))
                )
                connector = result.scalar_one_or_none()
                if connector:
                    mcp_url = _MCP_URL_BY_TYPE.get(connector.connector_type, MCP_GOOGLE_DRIVE_URL)
            except (ValueError, Exception) as exc:
                logger.warning(f"Could not resolve connector from state '{state}': {exc}")

        params = {}
        if code:
            params["code"] = code
        if state:
            params["state"] = state
        if error:
            params["error"] = error

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{mcp_url}/oauth/callback",
                params=params,
                follow_redirects=False,
            )

        from starlette.responses import HTMLResponse
        return HTMLResponse(
            content=response.text,
            status_code=response.status_code,
        )
    except Exception as e:
        logger.error(f"OAuth callback proxy failed: {e}")
        from starlette.responses import HTMLResponse
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Error</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#fafafa}}
.card{{background:#fff;border-radius:12px;padding:2rem;box-shadow:0 2px 8px rgba(0,0,0,.1);text-align:center;max-width:400px}}
button{{background:#18181b;color:#fff;border:none;padding:.5rem 1.5rem;border-radius:6px;cursor:pointer;font-size:.9rem}}
button:hover{{background:#27272a}}</style></head>
<body><div class="card"><div style="color:#dc2626;font-size:1.2rem;margin-bottom:1rem">✕ Error de conexión</div>
<p style="color:#666;margin-bottom:1.5rem">{str(e)}</p>
<button onclick="window.close()">Cerrar</button></div></body></html>""",
            status_code=500,
        )


@router.get("/{connector_id}/oauth/status")
async def oauth_status(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Check OAuth status for an OAuth connector (Google Drive, OneDrive)."""
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    if connector.connector_type not in _OAUTH_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth status is only available for {', '.join(_OAUTH_CONNECTOR_TYPES)} connectors",
        )

    mcp_url = _MCP_URL_BY_TYPE[connector.connector_type]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{mcp_url}/oauth/status",
                params={
                    "connector_id": str(connector_id),
                    "tenant_id": tenant_id,
                },
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"OAuth status proxy failed: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth status check failed: {e}")


@router.get("/{connector_id}/folders")
async def list_drive_folders(
    connector_id: UUID,
    parent_id: str = Query("root", description="Parent folder ID"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List folders for an OAuth connector (admin only).

    Proxies the request to the appropriate MCP service /folders endpoint.
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

    if connector.connector_type not in _OAUTH_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Folder listing is only available for {', '.join(_OAUTH_CONNECTOR_TYPES)} connectors",
        )

    mcp_url = _MCP_URL_BY_TYPE[connector.connector_type]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{mcp_url}/folders",
                params={
                    "connector_id": str(connector_id),
                    "tenant_id": tenant_id,
                    "parent_id": parent_id,
                },
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        detail = e.response.text
        raise HTTPException(status_code=status, detail=detail)
    except Exception as e:
        logger.error(f"Folder listing proxy failed: {e}")
        raise HTTPException(status_code=500, detail=f"Folder listing failed: {e}")


@router.post("/{connector_id}/oauth/revoke")
async def oauth_revoke(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """Revoke OAuth tokens for an OAuth connector (admin only)."""
    await _check_admin_permission(current_user, tenant_id)

    result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
    )
    connector = result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    if connector.connector_type not in _OAUTH_CONNECTOR_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth revoke is only available for {', '.join(_OAUTH_CONNECTOR_TYPES)} connectors",
        )

    mcp_url = _MCP_URL_BY_TYPE[connector.connector_type]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{mcp_url}/oauth/revoke",
                json={
                    "connector_id": str(connector_id),
                    "tenant_id": tenant_id,
                },
                headers={"X-API-Key": settings.MICROSERVICES_API_KEY},
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"OAuth revoke proxy failed: {e}")
        raise HTTPException(status_code=500, detail=f"OAuth revoke failed: {e}")
