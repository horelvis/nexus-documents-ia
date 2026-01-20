"""
API endpoints for User Document Sync management.

These endpoints allow users to:
- View available connectors and their authorization status
- Authorize their accounts with connectors (OAuth flow)
- Configure their document sync preferences
- Trigger manual syncs
- View their indexed documents
"""
import logging
import secrets
from datetime import datetime, timezone
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import get_current_user_async, get_current_tenant_id_async
from app.core.config import settings
from app.db.async_database import get_async_db
from app.db.models import (
    User, Connector, UserConnectorAuth, UserDocumentSync, IndexedDocument
)
from app.schemas.connector import (
    ConnectorType,
    ConnectorAuthType,
    SyncStatus,
    UserConnectorAuthResponse,
    ConnectorOAuthUrlResponse,
    UserSyncConfigCreate,
    UserSyncConfigUpdate,
    UserDocumentSyncResponse,
    UserSyncListResponse,
    TriggerSyncRequest,
    TriggerSyncResponse,
    IndexedDocumentResponse,
    IndexedDocumentListResponse,
    ConnectorOnboardingItem,
    OnboardingStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory state storage for OAuth (in production, use Redis)
_connector_oauth_states: dict[str, dict] = {}


# =============================================================================
# Onboarding Endpoints
# =============================================================================

@router.get("/onboarding", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get user's onboarding status with available connectors.

    This is the main endpoint for the new user onboarding flow.
    Returns all active connectors and whether the user has authorized/synced each one.
    """
    # Get all active connectors for tenant
    connectors_result = await db.execute(
        select(Connector)
        .where(Connector.tenant_id == UUID(tenant_id))
        .where(Connector.is_active == True)
        .order_by(Connector.name)
    )
    connectors = connectors_result.scalars().all()

    # Get user's authorizations
    auths_result = await db.execute(
        select(UserConnectorAuth)
        .where(UserConnectorAuth.user_id == current_user.id)
    )
    user_auths = {auth.connector_id: auth for auth in auths_result.scalars().all()}

    # Get user's syncs
    syncs_result = await db.execute(
        select(UserDocumentSync)
        .where(UserDocumentSync.user_id == current_user.id)
    )
    user_syncs = {sync.connector_id: sync for sync in syncs_result.scalars().all()}

    # Build onboarding items
    items = []
    connected_count = 0
    syncing_count = 0

    for connector in connectors:
        auth = user_auths.get(connector.id)
        sync = user_syncs.get(connector.id)

        is_authorized = auth is not None and auth.is_valid
        is_syncing = sync is not None and sync.sync_enabled

        if is_authorized:
            connected_count += 1
        if is_syncing:
            syncing_count += 1

        items.append(ConnectorOnboardingItem(
            id=connector.id,
            name=connector.name,
            description=connector.description,
            connector_type=ConnectorType(connector.connector_type),
            auth_type=ConnectorAuthType(connector.auth_type),
            is_authorized=is_authorized,
            is_syncing=is_syncing,
            documents_indexed=sync.documents_indexed if sync else 0,
        ))

    # Consider onboarding complete if user has at least one syncing connector
    has_completed = syncing_count > 0

    return OnboardingStatusResponse(
        available_connectors=items,
        has_completed_onboarding=has_completed,
        total_connectors=len(connectors),
        connected_count=connected_count,
        syncing_count=syncing_count,
    )


# =============================================================================
# Authorization Endpoints
# =============================================================================

@router.get("/connectors/{connector_id}/auth-status", response_model=UserConnectorAuthResponse)
async def get_connector_auth_status(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get user's authorization status for a specific connector.
    """
    # Verify connector exists and belongs to tenant
    connector_result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
        .where(Connector.is_active == True)
    )
    connector = connector_result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Get user's auth for this connector
    auth_result = await db.execute(
        select(UserConnectorAuth)
        .where(UserConnectorAuth.user_id == current_user.id)
        .where(UserConnectorAuth.connector_id == connector_id)
    )
    auth = auth_result.scalar_one_or_none()

    return UserConnectorAuthResponse(
        connector_id=connector.id,
        connector_name=connector.name,
        connector_type=ConnectorType(connector.connector_type),
        is_authorized=auth is not None and auth.is_valid,
        oauth_email=None,  # Would be populated from stored token metadata
        scopes=auth.scopes if auth else [],
        expires_at=auth.expires_at if auth else None,
        last_used_at=auth.last_used_at if auth else None,
        error_message=auth.error_message if auth and not auth.is_valid else None,
    )


@router.get("/connectors/{connector_id}/oauth-url", response_model=ConnectorOAuthUrlResponse)
async def get_connector_oauth_url(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Get OAuth authorization URL to connect user's account to a connector.

    Returns a URL to redirect the user for OAuth consent.
    """
    # Verify connector exists
    connector_result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
        .where(Connector.is_active == True)
    )
    connector = connector_result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Only delegated auth requires user OAuth
    if connector.auth_type != "delegated":
        raise HTTPException(
            status_code=400,
            detail="This connector uses service account authentication, no user OAuth required"
        )

    connector_type = connector.connector_type
    config = connector.config or {}

    # Generate OAuth URL based on connector type
    state = secrets.token_urlsafe(32)
    _connector_oauth_states[state] = {
        "connector_id": str(connector_id),
        "user_id": str(current_user.id),
        "tenant_id": tenant_id,
        "connector_type": connector_type,
    }

    auth_url = None

    if connector_type in ["sharepoint", "onedrive"]:
        # Microsoft OAuth
        ms_tenant = config.get("tenant_id", "common")
        client_id = config.get("client_id")

        if not client_id:
            raise HTTPException(status_code=500, detail="Connector not properly configured")

        scopes = "offline_access openid profile User.Read Files.Read.All Sites.Read.All"
        redirect_uri = f"{settings.API_BASE_URL}/api/v1/user-sync/oauth/callback"

        auth_url = (
            f"https://login.microsoftonline.com/{ms_tenant}/oauth2/v2.0/authorize"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
            f"&state={state}"
            f"&prompt=consent"
        )

    elif connector_type in ["google_drive", "google_workspace"]:
        # Google OAuth
        client_id = config.get("client_id")

        if not client_id:
            raise HTTPException(status_code=500, detail="Connector not properly configured")

        scopes = "openid email profile https://www.googleapis.com/auth/drive.readonly"
        redirect_uri = f"{settings.API_BASE_URL}/api/v1/user-sync/oauth/callback"

        auth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={scopes}"
            f"&state={state}"
            f"&access_type=offline"
            f"&prompt=consent"
        )

    else:
        raise HTTPException(
            status_code=400,
            detail=f"OAuth not supported for connector type: {connector_type}"
        )

    return ConnectorOAuthUrlResponse(
        auth_url=auth_url,
        state=state,
        connector_id=connector_id,
        connector_type=ConnectorType(connector_type),
    )


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    OAuth callback endpoint for connector authorization.

    Called by identity providers after user authorizes.
    Exchanges code for tokens and stores them.
    """
    state_data = _connector_oauth_states.pop(state, None)

    if error:
        logger.error(f"OAuth error: {error}")
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/auth/oauth-error?error={error}"
        )

    if not state_data:
        logger.error(f"Invalid OAuth state: {state}")
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/auth/oauth-error?error=invalid_state"
        )

    connector_id = UUID(state_data["connector_id"])
    user_id = UUID(state_data["user_id"])
    tenant_id = state_data["tenant_id"]
    connector_type = state_data["connector_type"]

    try:
        # Get connector config
        connector_result = await db.execute(
            select(Connector).where(Connector.id == connector_id)
        )
        connector = connector_result.scalar_one_or_none()

        if not connector:
            raise ValueError("Connector not found")

        config = connector.config or {}
        redirect_uri = f"{settings.API_BASE_URL}/api/v1/user-sync/oauth/callback"

        # Exchange code for tokens based on provider
        import httpx

        if connector_type in ["sharepoint", "onedrive"]:
            ms_tenant = config.get("tenant_id", "common")
            token_url = f"https://login.microsoftonline.com/{ms_tenant}/oauth2/v2.0/token"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data={
                        "client_id": config.get("client_id"),
                        "client_secret": config.get("client_secret"),
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                tokens = response.json()

        elif connector_type in ["google_drive", "google_workspace"]:
            token_url = "https://oauth2.googleapis.com/token"

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    token_url,
                    data={
                        "client_id": config.get("client_id"),
                        "client_secret": config.get("client_secret"),
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                tokens = response.json()

        else:
            raise ValueError(f"Unsupported connector type: {connector_type}")

        # Calculate expiry
        expires_in = tokens.get("expires_in", 3600)
        expires_at = datetime.now(timezone.utc).replace(
            microsecond=0
        ) + __import__("datetime").timedelta(seconds=expires_in)

        # Store or update user auth
        existing_auth = await db.execute(
            select(UserConnectorAuth)
            .where(UserConnectorAuth.user_id == user_id)
            .where(UserConnectorAuth.connector_id == connector_id)
        )
        auth = existing_auth.scalar_one_or_none()

        if auth:
            auth.access_token = tokens.get("access_token")
            auth.refresh_token = tokens.get("refresh_token", auth.refresh_token)
            auth.token_type = tokens.get("token_type", "Bearer")
            auth.expires_at = expires_at
            auth.scopes = tokens.get("scope", "").split() if tokens.get("scope") else []
            auth.is_valid = True
            auth.error_message = None
            auth.updated_at = datetime.now(timezone.utc)
        else:
            auth = UserConnectorAuth(
                user_id=user_id,
                connector_id=connector_id,
                access_token=tokens.get("access_token"),
                refresh_token=tokens.get("refresh_token"),
                token_type=tokens.get("token_type", "Bearer"),
                expires_at=expires_at,
                scopes=tokens.get("scope", "").split() if tokens.get("scope") else [],
                is_valid=True,
            )
            db.add(auth)

        await db.commit()

        logger.info(f"OAuth successful for user {user_id} on connector {connector_id}")

        # Redirect to frontend success page
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/onboarding/oauth-success?connector_id={connector_id}"
        )

    except Exception as e:
        logger.exception(f"OAuth callback error: {e}")
        return RedirectResponse(
            f"{settings.FRONTEND_URL}/auth/oauth-error?error=token_exchange_failed"
        )


@router.delete("/connectors/{connector_id}/auth", status_code=204)
async def revoke_connector_auth(
    connector_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Revoke user's authorization for a connector.

    This will:
    - Remove stored tokens
    - Stop any active syncs
    - Keep indexed documents (they become orphaned for cleanup)
    """
    # Delete user's auth for this connector
    auth_result = await db.execute(
        select(UserConnectorAuth)
        .where(UserConnectorAuth.user_id == current_user.id)
        .where(UserConnectorAuth.connector_id == connector_id)
    )
    auth = auth_result.scalar_one_or_none()

    if auth:
        await db.delete(auth)

    # Disable sync if exists
    sync_result = await db.execute(
        select(UserDocumentSync)
        .where(UserDocumentSync.user_id == current_user.id)
        .where(UserDocumentSync.connector_id == connector_id)
    )
    sync = sync_result.scalar_one_or_none()

    if sync:
        sync.sync_enabled = False
        sync.status = "paused"
        sync.status_message = "Authorization revoked"

    await db.commit()

    return Response(status_code=204)


# =============================================================================
# Sync Configuration Endpoints
# =============================================================================

@router.get("/syncs", response_model=UserSyncListResponse)
async def list_user_syncs(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List all document syncs for the current user.
    """
    # Get syncs with connector info
    syncs_result = await db.execute(
        select(UserDocumentSync)
        .options(selectinload(UserDocumentSync.connector))
        .where(UserDocumentSync.user_id == current_user.id)
        .order_by(UserDocumentSync.created_at.desc())
    )
    syncs = syncs_result.scalars().all()

    items = []
    for sync in syncs:
        items.append(UserDocumentSyncResponse(
            id=sync.id,
            connector_id=sync.connector_id,
            connector_name=sync.connector.name if sync.connector else "Unknown",
            connector_type=ConnectorType(sync.connector.connector_type) if sync.connector else ConnectorType.SHAREPOINT,
            sync_enabled=sync.sync_enabled,
            include_paths=sync.include_paths or [],
            exclude_paths=sync.exclude_paths or [],
            status=SyncStatus(sync.status),
            status_message=sync.status_message,
            documents_total=sync.documents_total or 0,
            documents_indexed=sync.documents_indexed or 0,
            documents_failed=sync.documents_failed or 0,
            total_size_bytes=sync.total_size_bytes or 0,
            last_sync_started_at=sync.last_sync_started_at,
            last_sync_completed_at=sync.last_sync_completed_at,
            next_sync_at=sync.next_sync_at,
            last_error=sync.last_error,
        ))

    return UserSyncListResponse(items=items, total=len(items))


@router.post("/connectors/{connector_id}/sync", response_model=UserDocumentSyncResponse, status_code=201)
async def create_user_sync(
    connector_id: UUID,
    config: UserSyncConfigCreate = UserSyncConfigCreate(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Enable document sync for a connector.

    User must have authorized the connector first (for delegated auth).
    """
    # Verify connector exists
    connector_result = await db.execute(
        select(Connector)
        .where(Connector.id == connector_id)
        .where(Connector.tenant_id == UUID(tenant_id))
        .where(Connector.is_active == True)
    )
    connector = connector_result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # For delegated auth, verify user has authorized
    if connector.auth_type == "delegated":
        auth_result = await db.execute(
            select(UserConnectorAuth)
            .where(UserConnectorAuth.user_id == current_user.id)
            .where(UserConnectorAuth.connector_id == connector_id)
            .where(UserConnectorAuth.is_valid == True)
        )
        if not auth_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="You must authorize this connector before enabling sync"
            )

    # Check if sync already exists
    existing_sync = await db.execute(
        select(UserDocumentSync)
        .where(UserDocumentSync.user_id == current_user.id)
        .where(UserDocumentSync.connector_id == connector_id)
    )
    sync = existing_sync.scalar_one_or_none()

    if sync:
        # Update existing sync config
        sync.sync_enabled = config.sync_enabled
        sync.include_paths = config.include_paths
        sync.exclude_paths = config.exclude_paths
        sync.status = "pending"
        sync.updated_at = datetime.now(timezone.utc)
    else:
        # Create new sync
        sync = UserDocumentSync(
            user_id=current_user.id,
            connector_id=connector_id,
            sync_enabled=config.sync_enabled,
            include_paths=config.include_paths,
            exclude_paths=config.exclude_paths,
            status="pending",
        )
        db.add(sync)

    await db.commit()
    await db.refresh(sync)

    # Reload with connector relationship
    await db.refresh(sync, ["connector"])

    logger.info(f"User {current_user.id} enabled sync for connector {connector_id}")

    # TODO: Trigger initial sync in background

    return UserDocumentSyncResponse(
        id=sync.id,
        connector_id=sync.connector_id,
        connector_name=connector.name,
        connector_type=ConnectorType(connector.connector_type),
        sync_enabled=sync.sync_enabled,
        include_paths=sync.include_paths or [],
        exclude_paths=sync.exclude_paths or [],
        status=SyncStatus(sync.status),
        status_message=sync.status_message,
        documents_total=sync.documents_total or 0,
        documents_indexed=sync.documents_indexed or 0,
        documents_failed=sync.documents_failed or 0,
        total_size_bytes=sync.total_size_bytes or 0,
        last_sync_started_at=sync.last_sync_started_at,
        last_sync_completed_at=sync.last_sync_completed_at,
        next_sync_at=sync.next_sync_at,
        last_error=sync.last_error,
    )


@router.put("/syncs/{sync_id}", response_model=UserDocumentSyncResponse)
async def update_user_sync(
    sync_id: UUID,
    config: UserSyncConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Update sync configuration.
    """
    sync_result = await db.execute(
        select(UserDocumentSync)
        .options(selectinload(UserDocumentSync.connector))
        .where(UserDocumentSync.id == sync_id)
        .where(UserDocumentSync.user_id == current_user.id)
    )
    sync = sync_result.scalar_one_or_none()

    if not sync:
        raise HTTPException(status_code=404, detail="Sync not found")

    # Update fields
    update_data = config.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(sync, field, value)

    sync.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sync)

    return UserDocumentSyncResponse(
        id=sync.id,
        connector_id=sync.connector_id,
        connector_name=sync.connector.name if sync.connector else "Unknown",
        connector_type=ConnectorType(sync.connector.connector_type) if sync.connector else ConnectorType.SHAREPOINT,
        sync_enabled=sync.sync_enabled,
        include_paths=sync.include_paths or [],
        exclude_paths=sync.exclude_paths or [],
        status=SyncStatus(sync.status),
        status_message=sync.status_message,
        documents_total=sync.documents_total or 0,
        documents_indexed=sync.documents_indexed or 0,
        documents_failed=sync.documents_failed or 0,
        total_size_bytes=sync.total_size_bytes or 0,
        last_sync_started_at=sync.last_sync_started_at,
        last_sync_completed_at=sync.last_sync_completed_at,
        next_sync_at=sync.next_sync_at,
        last_error=sync.last_error,
    )


@router.delete("/syncs/{sync_id}", status_code=204)
async def delete_user_sync(
    sync_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Delete a sync configuration (stops syncing, keeps indexed documents).
    """
    sync_result = await db.execute(
        select(UserDocumentSync)
        .where(UserDocumentSync.id == sync_id)
        .where(UserDocumentSync.user_id == current_user.id)
    )
    sync = sync_result.scalar_one_or_none()

    if not sync:
        raise HTTPException(status_code=404, detail="Sync not found")

    await db.delete(sync)
    await db.commit()

    return Response(status_code=204)


@router.post("/syncs/{sync_id}/trigger", response_model=TriggerSyncResponse)
async def trigger_manual_sync(
    sync_id: UUID,
    request: TriggerSyncRequest = TriggerSyncRequest(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    Trigger a manual sync for a connector.
    """
    sync_result = await db.execute(
        select(UserDocumentSync)
        .where(UserDocumentSync.id == sync_id)
        .where(UserDocumentSync.user_id == current_user.id)
    )
    sync = sync_result.scalar_one_or_none()

    if not sync:
        raise HTTPException(status_code=404, detail="Sync not found")

    if not sync.sync_enabled:
        raise HTTPException(status_code=400, detail="Sync is disabled")

    if sync.status == "syncing":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Update status to pending
    sync.status = "pending"
    sync.status_message = "Manual sync triggered"
    await db.commit()

    logger.info(f"Manual sync triggered for user {current_user.id}, sync {sync_id}")

    # TODO: Queue actual sync task via Celery

    return TriggerSyncResponse(
        sync_id=sync_id,
        connector_id=sync.connector_id,
        status="queued",
        message="Sync has been queued and will start shortly",
    )


# =============================================================================
# Indexed Documents Endpoints
# =============================================================================

@router.get("/documents", response_model=IndexedDocumentListResponse)
async def list_my_indexed_documents(
    connector_id: Optional[UUID] = Query(None, description="Filter by connector"),
    status: Optional[str] = Query(None, description="Filter by indexing status"),
    search: Optional[str] = Query(None, description="Search in title"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
):
    """
    List documents indexed from user's connectors.
    """
    # Build query - only show documents owned by current user
    query = (
        select(IndexedDocument)
        .where(IndexedDocument.owner_id == current_user.id)
        .where(IndexedDocument.tenant_id == UUID(tenant_id))
    )

    if connector_id:
        query = query.where(IndexedDocument.connector_id == connector_id)
    if status:
        query = query.where(IndexedDocument.indexing_status == status)
    if search:
        query = query.where(IndexedDocument.title.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    query = query.order_by(IndexedDocument.indexed_at.desc().nulls_last())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    documents = result.scalars().all()

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
            size_bytes=doc.size_bytes or 0,
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
