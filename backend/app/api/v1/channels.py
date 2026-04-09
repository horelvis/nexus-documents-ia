"""
API endpoints for Information Channels management.

Supports Gmail, Google Drive, and External Database channels for RAG pipeline.
"""
import logging
import os
import secrets

# Allow OAuth to accept scopes different from requested
# (Google may return previously granted scopes)
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
from math import ceil
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
import requests
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.config import settings
from app.db.async_database import get_async_db
from app.db.models import User
from app.schemas.channel import (
    ChannelCreate,
    ChannelUpdate,
    ChannelResponse,
    ChannelListResponse,
    ChannelType,
    ChannelVisibility,
    SyncLogResponse,
    SyncHistoryResponse,
    ChannelDocumentResponse,
    ChannelDocumentsResponse,
    OAuthUrlResponse,
    SyncTriggerRequest,
    SyncTriggerResponse,
    SyncTriggerType,
    DBCredentialsCreate,
    TestConnectionResponse,
)
from app.services.channels import ChannelService, ChannelCredentialService

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory state storage for OAuth (in production, use Redis)
_oauth_states: dict[str, dict] = {}


def _get_channel_service(db: AsyncSession) -> ChannelService:
    """Get channel service instance."""
    return ChannelService(db)


def _get_credential_service(db: AsyncSession) -> ChannelCredentialService:
    """Get credential service instance."""
    return ChannelCredentialService(db)


# =============================================================================
# Channel CRUD Endpoints
# =============================================================================

@router.get("", response_model=ChannelListResponse)
async def list_channels(
    channel_type: Optional[ChannelType] = Query(None, description="Filter by channel type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    List information channels accessible to the current user.

    Returns:
    - Tenant-wide channels visible to all users
    - Personal channels created by the current user
    """
    service = _get_channel_service(db)
    channels, total = await service.list_channels(
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
        channel_type=channel_type,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )

    return ChannelListResponse(
        items=[service.channel_to_response(ch) for ch in channels],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total > 0 else 1,
    )


@router.post("", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel_data: ChannelCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Create a new information channel.

    For Google channels (Gmail, Google Drive), you must complete OAuth
    authorization after creating the channel.
    """
    service = _get_channel_service(db)

    channel = await service.create_channel(
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
        channel_type=channel_data.channel_type,
        name=channel_data.name,
        description=channel_data.description,
        visibility=channel_data.visibility,
        configuration=channel_data.configuration,
        sync_interval_minutes=channel_data.sync_interval_minutes,
    )

    logger.info(f"Created channel {channel.id} ({channel_data.channel_type}) for user {current_user.id}")
    return service.channel_to_response(channel)


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get details of a specific channel.

    Only accessible if:
    - Channel is tenant-wide, or
    - Channel is personal and created by the current user
    """
    service = _get_channel_service(db)
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    return service.channel_to_response(channel)


@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: UUID,
    channel_data: ChannelUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Update a channel's configuration.

    Only the channel creator can update it.
    """
    service = _get_channel_service(db)
    channel = await service.update_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
        update_data=channel_data,
    )

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found or not authorized")

    return service.channel_to_response(channel)


@router.delete("/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Delete a channel and all associated data.

    Only the channel creator can delete it.
    This removes:
    - The channel configuration
    - Stored credentials
    - Document references (Weaviate documents need separate cleanup)
    - Sync history
    """
    service = _get_channel_service(db)
    deleted = await service.delete_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found or not authorized")

    # TODO: Trigger Weaviate cleanup in background task

    return Response(status_code=204)


# =============================================================================
# OAuth Endpoints (for Gmail and Google Drive)
# =============================================================================

@router.get("/{channel_id}/oauth-url", response_model=OAuthUrlResponse)
async def get_oauth_url(
    channel_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get OAuth authorization URL for a Google channel.

    Returns a URL to redirect the user to for Google OAuth consent.
    After authorization, Google will redirect to the callback endpoint.
    """
    service = _get_channel_service(db)
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.channel_type not in ["gmail", "google_drive"]:
        raise HTTPException(status_code=400, detail="OAuth only supported for Gmail and Google Drive channels")

    # Verify channel owner
    if channel.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only channel owner can authorize")

    # Determine scopes based on channel type
    if channel.channel_type == "gmail":
        scopes = settings.gmail_oauth_scopes_list
    else:  # google_drive
        scopes = settings.google_oauth_scopes_list

    # Create OAuth flow
    if not settings.GOOGLE_OAUTH_CLIENT_ID or not settings.GOOGLE_OAUTH_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="Google OAuth not configured")

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

    flow = Flow.from_client_config(client_config, scopes=scopes)
    flow.redirect_uri = settings.CHANNEL_OAUTH_REDIRECT_URI

    # Generate state token
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = {
        "channel_id": str(channel_id),
        "user_id": str(current_user.id),
        "tenant_id": tenant_id,
    }

    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",  # Don't include previously granted scopes
        prompt="consent",  # Force consent to get fresh scopes
        state=state,
    )

    return OAuthUrlResponse(auth_url=authorization_url, state=state)


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_db),
):
    """
    OAuth callback endpoint for Google authorization.

    This is called by Google after user authorizes. It:
    1. Exchanges the authorization code for tokens
    2. Stores encrypted credentials
    3. Redirects to frontend success/error page
    """
    # Validate state first to get tenant_id for error redirects
    state_data = _oauth_states.pop(state, None)
    tenant_id = state_data.get("tenant_id") if state_data else None

    # Build base error URL with tenant_id if available
    error_base_url = settings.CHANNEL_OAUTH_ERROR_REDIRECT_URL
    if tenant_id:
        error_base_url = f"{error_base_url}?tenant_id={tenant_id}"

    # Check for errors from Google
    if error:
        logger.error(f"OAuth error from Google: {error}")
        separator = "&" if tenant_id else "?"
        return RedirectResponse(f"{error_base_url}{separator}error={error}")

    # Validate state was found
    if not state_data:
        logger.error(f"Invalid OAuth state: {state}")
        return RedirectResponse(
            f"{settings.CHANNEL_OAUTH_ERROR_REDIRECT_URL}?error=invalid_state"
        )

    channel_id = UUID(state_data["channel_id"])
    user_id = UUID(state_data["user_id"])
    tenant_id = state_data["tenant_id"]

    try:
        # Get channel to determine scopes
        service = _get_channel_service(db)
        channel = await service.get_channel(
            channel_id=channel_id,
            tenant_id=UUID(tenant_id),
            user_id=user_id,
        )

        if not channel:
            raise ValueError("Channel not found")

        # Determine scopes
        if channel.channel_type == "gmail":
            scopes = settings.gmail_oauth_scopes_list
        else:
            scopes = settings.google_oauth_scopes_list

        # Exchange code for tokens
        client_config = {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }

        flow = Flow.from_client_config(client_config, scopes=scopes, state=state)
        flow.redirect_uri = settings.CHANNEL_OAUTH_REDIRECT_URI
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Fetch user info
        userinfo_response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=10,
        )
        userinfo_response.raise_for_status()
        userinfo = userinfo_response.json()

        # Store credentials
        credential_service = _get_credential_service(db)
        await credential_service.store_oauth_credentials(
            channel_id=channel_id,
            credentials=credentials,
            userinfo=userinfo,
            scopes=scopes,
        )

        logger.info(f"OAuth successful for channel {channel_id}, email: {userinfo.get('email')}")

        # Redirect to success page with tenant_id and channel_id
        success_url = settings.CHANNEL_OAUTH_SUCCESS_REDIRECT_URL
        return RedirectResponse(f"{success_url}?tenant_id={tenant_id}&channel_id={channel_id}")

    except Exception as e:
        logger.exception(f"OAuth callback error: {e}")
        return RedirectResponse(f"{error_base_url}&error=token_exchange_failed")


# =============================================================================
# Sync Endpoints
# =============================================================================

@router.post("/{channel_id}/sync", response_model=SyncTriggerResponse)
async def trigger_sync(
    channel_id: UUID,
    request: SyncTriggerRequest = SyncTriggerRequest(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Trigger a manual sync for a channel.

    This queues a sync task in the background worker.
    """
    service = _get_channel_service(db)
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if not channel.is_active:
        raise HTTPException(status_code=400, detail="Channel is not active")

    # Check if channel has credentials
    credential_service = _get_credential_service(db)
    has_creds = await credential_service.has_credentials(channel_id)
    if not has_creds and channel.channel_type in ["gmail", "google_drive"]:
        raise HTTPException(
            status_code=400,
            detail="Channel not authorized. Complete OAuth first."
        )

    # Check if already syncing
    if channel.last_sync_status == "running":
        raise HTTPException(status_code=409, detail="Sync already in progress")

    # Start sync
    sync_log = await service.start_sync(
        channel_id=channel_id,
        trigger_type=SyncTriggerType.MANUAL,
    )

    # TODO: Queue Celery task for actual sync
    # sync_channel_task.delay(str(channel_id), str(sync_log.id), request.full_sync)

    logger.info(f"Manual sync triggered for channel {channel_id}")

    return SyncTriggerResponse(
        sync_id=sync_log.id,
        channel_id=channel_id,
        status="queued",
        message="Sync has been queued",
    )


@router.get("/{channel_id}/sync-history", response_model=SyncHistoryResponse)
async def get_sync_history(
    channel_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Get sync history for a channel.
    """
    service = _get_channel_service(db)

    # Verify access
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    logs = await service.get_sync_history(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        limit=limit,
    )

    return SyncHistoryResponse(
        items=[SyncLogResponse.model_validate(log) for log in logs],
        total=len(logs),
    )


# =============================================================================
# Channel Documents Endpoints
# =============================================================================

@router.get("/{channel_id}/documents", response_model=ChannelDocumentsResponse)
async def list_channel_documents(
    channel_id: UUID,
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    List documents indexed from a channel.
    """
    service = _get_channel_service(db)

    # Verify access
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    documents, total = await service.list_channel_documents(
        channel_id=channel_id,
        status=status,
        page=page,
        page_size=page_size,
    )

    return ChannelDocumentsResponse(
        items=[ChannelDocumentResponse.model_validate(doc) for doc in documents],
        total=total,
        page=page,
        page_size=page_size,
    )


# =============================================================================
# External Database Credentials Endpoints
# =============================================================================

@router.post("/{channel_id}/db-credentials", status_code=204)
async def set_db_credentials(
    channel_id: UUID,
    credentials: DBCredentialsCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Set database credentials for an external database channel.

    Only the channel creator can set credentials.
    """
    service = _get_channel_service(db)
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.channel_type != "external_db":
        raise HTTPException(
            status_code=400,
            detail="DB credentials only supported for external database channels"
        )

    if channel.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Only channel owner can set credentials")

    credential_service = _get_credential_service(db)
    await credential_service.store_db_credentials(
        channel_id=channel_id,
        username=credentials.username,
        password=credentials.password,
    )

    return Response(status_code=204)


@router.post("/{channel_id}/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    channel_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
):
    """
    Test connection to an external database channel.

    Verifies that:
    - Credentials are valid
    - Database is reachable
    - Query executes successfully
    """
    service = _get_channel_service(db)
    channel = await service.get_channel(
        channel_id=channel_id,
        tenant_id=UUID(tenant_id),
        user_id=current_user.id,
    )

    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    if channel.channel_type != "external_db":
        raise HTTPException(
            status_code=400,
            detail="Connection test only supported for external database channels"
        )

    # TODO: Implement actual connection test
    # This will be implemented in the ExternalDBChannelService

    return TestConnectionResponse(
        success=False,
        message="External database connection test not yet implemented",
    )
