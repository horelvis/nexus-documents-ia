"""
Site Guests API - Admin endpoints for managing external sharing.

Provides CRUD operations for Site Guests, permissions, and access logs.
Requires internal user authentication. Guest creation restricted to ADMIN role.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.async_database import get_async_db
from app.api.async_dependencies import get_current_user_async
from app.core.auth.base import UserProfile
from app.core.auth.superuser import require_superuser
from app.db.models import SiteGuestShareDocument
from app.services.site_guest_service import SiteGuestService
from app.schemas.site_guest import (
    SiteGuestCreate, SiteGuestUpdate, SiteGuestResponse, SiteGuestListResponse,
    SiteGuestInviteRequest,
    SiteGuestDocumentPermissionCreate, SiteGuestFolderPermissionCreate,
    SiteGuestPermissionResponse, SiteGuestPermissionListResponse,
    SiteGuestAccessLogResponse, SiteGuestAccessLogListResponse,
    TenantSiteSettingsUpdate, TenantSiteSettingsResponse,
    SiteGuestStatistics,
    CreateGuestWithShareRequest, CreateGuestWithShareResponse,
    SiteGuestShareResponse, SiteGuestShareListResponse,
)
from app.schemas.general import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================
# SITE SETTINGS
# =====================================

@router.get("/site/settings", response_model=TenantSiteSettingsResponse)
async def get_site_settings(
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the site settings.

    Returns site configuration including slug, enabled status, and guest counts.
    """
    site = await SiteGuestService.get_tenant_site_settings(db)
    if not site:
        raise HTTPException(status_code=404, detail="Site settings not found")

    # Get guest counts
    guests, total = await SiteGuestService.list_guests(db, include_inactive=True)
    active_count = sum(1 for g in guests if g.is_active)

    return TenantSiteSettingsResponse(
        site_enabled=getattr(site, "site_enabled", False) or False,
        site_logo_url=getattr(site, "site_logo_url", None),
        site_welcome_message=getattr(site, "site_welcome_message", None),
        slug=site.slug,
        guest_count=total,
        active_guest_count=active_count
    )


@router.put("/site/settings", response_model=TenantSiteSettingsResponse)
async def update_site_settings(
    site_update: TenantSiteSettingsUpdate,
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update the site settings.

    NOTE: no-op in single-tenant on-premise mode.
    """
    try:
        site = await SiteGuestService.update_tenant_site_settings(db, site_update)

        # Get guest counts
        guests, total = await SiteGuestService.list_guests(db, include_inactive=True)
        active_count = sum(1 for g in guests if g.is_active)

        return TenantSiteSettingsResponse(
            site_enabled=getattr(site, "site_enabled", False) or False,
            site_logo_url=getattr(site, "site_logo_url", None),
            site_welcome_message=getattr(site, "site_welcome_message", None),
            slug=site.slug,
            guest_count=total,
            active_guest_count=active_count
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/site/statistics", response_model=SiteGuestStatistics)
async def get_site_statistics(
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get statistics for site guests.

    Returns counts of guests, access metrics, and shared content.
    """
    stats = await SiteGuestService.get_statistics(db)
    return stats


# =====================================
# GUEST MANAGEMENT
# =====================================

@router.post("", response_model=SiteGuestResponse, status_code=status.HTTP_201_CREATED)
async def create_guest(
    guest_data: SiteGuestCreate,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new Site Guest.

    ADMIN-only. Creates an external user who can access the portal via OTP authentication.
    Optionally sends an invitation email immediately.
    """
    try:
        guest = await SiteGuestService.create_guest(
            db,
            guest_data,
            UUID(current_user.sub)
        )
        return _guest_to_response(guest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=SiteGuestListResponse)
async def list_guests(
    include_inactive: bool = Query(False, description="Include deactivated guests"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all Site Guests.

    Returns paginated list of guests with their status and permissions.
    """
    guests, total = await SiteGuestService.list_guests(
        db, include_inactive, page, per_page
    )

    return SiteGuestListResponse(
        guests=[_guest_to_response(g) for g in guests],
        total=total,
        page=page,
        per_page=per_page
    )


@router.get("/{guest_id}", response_model=SiteGuestResponse)
async def get_guest(
    guest_id: UUID,
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific Site Guest by ID.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    return _guest_to_response(guest)


@router.put("/{guest_id}", response_model=SiteGuestResponse)
async def update_guest(
    guest_id: UUID,
    updates: SiteGuestUpdate,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update a Site Guest.

    ADMIN-only. Can modify name, active status, permissions, and expiration.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        updated_guest = await SiteGuestService.update_guest(db, guest_id, updates)
        return _guest_to_response(updated_guest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{guest_id}", response_model=SuccessResponse)
async def deactivate_guest(
    guest_id: UUID,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deactivate a Site Guest (soft delete).

    ADMIN-only. The guest will no longer be able to access the portal.
    All active sessions are revoked.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        await SiteGuestService.deactivate_guest(db, guest_id)
        return SuccessResponse(message="Guest deactivated successfully")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{guest_id}/invite", response_model=SuccessResponse)
async def resend_invitation(
    guest_id: UUID,
    invite_request: Optional[SiteGuestInviteRequest] = None,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resend invitation email to a Site Guest.

    ADMIN-only.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    success = await SiteGuestService.send_invitation_email(db, guest)
    if success:
        return SuccessResponse(message="Invitation email sent successfully")
    else:
        raise HTTPException(status_code=500, detail="Failed to send invitation email")


# =====================================
# SHARE/COLLECTION MANAGEMENT
# =====================================

@router.post("/with-share", response_model=CreateGuestWithShareResponse, status_code=status.HTTP_201_CREATED)
async def create_guest_with_share(
    request: CreateGuestWithShareRequest,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a guest and share documents with them in one operation.

    ADMIN-only. This is the simplified flow from the Documents page:
    1. Creates guest if not exists (or reuses existing by email)
    2. Creates a share/collection with the specified documents
    3. Sends invitation email with portal link
    """
    try:
        # Get or create guest (doesn't create duplicates)
        guest, is_new_guest = await SiteGuestService.get_or_create_guest(
            db=db,
            email=request.email,
            name=request.name,
            invited_by_user_id=UUID(current_user.sub)
        )

        # Create share with documents
        share = await SiteGuestService.create_share(
            db=db,
            guest_id=guest.id,
            name=request.share_name,
            document_ids=request.document_ids,
            permission_type=request.permission_type,
            description=request.share_description,
            expires_at=request.expires_at,
            created_by_user_id=UUID(current_user.sub)
        )

        share_count = (
            await db.execute(
                select(func.count())
                .select_from(SiteGuestShareDocument)
                .where(SiteGuestShareDocument.share_id == share.id)
            )
        ).scalar() or 0

        # Send notification email
        if request.send_invitation:
            await SiteGuestService.send_share_notification(
                db=db,
                guest=guest,
                share=share,
                is_new_guest=is_new_guest
            )

        return CreateGuestWithShareResponse(
            guest=_guest_to_response(guest),
            share=SiteGuestShareResponse(
                id=share.id,
                name=share.name,
                description=share.description,
                permission_type=share.permission_type,
                document_count=share_count,
                created_at=share.created_at,
                expires_at=share.expires_at
            ),
            is_new_guest=is_new_guest,
            message=f"Shared {share_count} document(s) with {request.email}"
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating guest with share: {e}")
        raise HTTPException(status_code=500, detail="Failed to create share")


@router.get("/{guest_id}/shares", response_model=SiteGuestShareListResponse)
async def list_guest_shares(
    guest_id: UUID,
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all shares/collections for a guest.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    shares = await SiteGuestService.list_guest_shares(db, guest_id)

    return SiteGuestShareListResponse(
        shares=[
            SiteGuestShareResponse(
                id=s.id,
                name=s.name,
                description=s.description,
                permission_type=s.permission_type,
                document_count=len(s.documents) if s.documents else 0,
                created_at=s.created_at,
                expires_at=s.expires_at
            )
            for s in shares
        ],
        total=len(shares)
    )


# =====================================
# PERMISSION MANAGEMENT
# =====================================

@router.get("/{guest_id}/permissions", response_model=SiteGuestPermissionListResponse)
async def list_guest_permissions(
    guest_id: UUID,
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all permissions for a Site Guest.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    permissions = await SiteGuestService.list_guest_permissions(db, guest_id)

    return SiteGuestPermissionListResponse(
        permissions=[_permission_to_response(p) for p in permissions],
        total=len(permissions)
    )


@router.post("/{guest_id}/permissions/document", response_model=SiteGuestPermissionResponse)
async def grant_document_permission(
    guest_id: UUID,
    permission_data: SiteGuestDocumentPermissionCreate,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Grant document permission to a Site Guest.

    ADMIN-only. permission_type must be one of: view, download, upload
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        permission = await SiteGuestService.grant_document_permission(
            db,
            guest_id,
            permission_data.document_id,
            permission_data.permission_type,
            UUID(current_user.sub),
            permission_data.expires_at
        )
        return _permission_to_response(permission)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{guest_id}/permissions/folder", response_model=SiteGuestPermissionResponse)
async def grant_folder_permission(
    guest_id: UUID,
    permission_data: SiteGuestFolderPermissionCreate,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Grant folder permission to a Site Guest.

    ADMIN-only. All documents within the folder path will be accessible.
    permission_type must be one of: view, download, upload
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        permission = await SiteGuestService.grant_folder_permission(
            db,
            guest_id,
            permission_data.folder_path,
            permission_data.permission_type,
            UUID(current_user.sub),
            permission_data.expires_at
        )
        return _permission_to_response(permission)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{guest_id}/permissions/{permission_id}", response_model=SuccessResponse)
async def revoke_permission(
    guest_id: UUID,
    permission_id: UUID,
    current_user: UserProfile = Depends(require_superuser),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Revoke a permission from a Site Guest.

    ADMIN-only.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    success = await SiteGuestService.revoke_permission(db, permission_id)
    if success:
        return SuccessResponse(message="Permission revoked successfully")
    else:
        raise HTTPException(status_code=404, detail="Permission not found")


# =====================================
# ACCESS LOGS
# =====================================

@router.get("/{guest_id}/access-logs", response_model=SiteGuestAccessLogListResponse)
async def get_guest_access_logs(
    guest_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: UserProfile = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get access logs for a Site Guest.

    Returns audit trail of all guest actions including logins, views, and downloads.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    logs, total = await SiteGuestService.get_guest_access_logs(db, guest_id, page, per_page)

    return SiteGuestAccessLogListResponse(
        logs=[_log_to_response(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page
    )


# =====================================
# HELPER FUNCTIONS
# =====================================

def _guest_to_response(guest) -> SiteGuestResponse:
    """Convert SiteGuest model to response schema."""
    return SiteGuestResponse(
        id=guest.id,
        email=guest.email,
        name=guest.name,
        is_active=guest.is_active,
        can_view=guest.can_view,
        can_download=guest.can_download,
        can_upload=guest.can_upload,
        expires_at=guest.expires_at,
        invited_by_user_id=guest.invited_by_user_id,
        invited_at=guest.invited_at,
        last_access_at=guest.last_access_at,
        access_count=guest.access_count,
        created_at=guest.created_at,
        updated_at=guest.updated_at,
        is_expired=guest.is_expired(),
        is_valid=guest.is_valid()
    )


def _permission_to_response(permission) -> SiteGuestPermissionResponse:
    """Convert SiteGuestPermission model to response schema."""
    return SiteGuestPermissionResponse(
        id=permission.id,
        guest_id=permission.guest_id,
        document_id=permission.document_id,
        folder_path=permission.folder_path,
        permission_type=permission.permission_type,
        granted_by_user_id=permission.granted_by_user_id,
        granted_at=permission.granted_at,
        expires_at=permission.expires_at,
        created_at=permission.created_at,
        document_title=None,  # TODO: Join with document
        document_filename=None
    )


def _log_to_response(log) -> SiteGuestAccessLogResponse:
    """Convert SiteGuestAccessLog model to response schema."""
    return SiteGuestAccessLogResponse(
        id=log.id,
        guest_id=log.guest_id,
        session_id=log.session_id,
        action=log.action,
        success=log.success,
        error_message=log.error_message,
        document_id=log.document_id,
        folder_path=log.folder_path,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        details=log.details,
        created_at=log.created_at,
        document_title=None  # TODO: Join with document
    )
