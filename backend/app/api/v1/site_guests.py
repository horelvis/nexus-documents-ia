"""
Site Guests API - Admin endpoints for managing external sharing.

Provides CRUD operations for Site Guests, permissions, and access logs.
Requires Clerk authentication (internal user).
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.async_database import get_async_db
from app.api.async_dependencies import get_current_user_async
from app.db.models import User
from app.services.site_guest_service import SiteGuestService
from app.schemas.site_guest import (
    SiteGuestCreate, SiteGuestUpdate, SiteGuestResponse, SiteGuestListResponse,
    SiteGuestInviteRequest,
    SiteGuestDocumentPermissionCreate, SiteGuestFolderPermissionCreate,
    SiteGuestPermissionResponse, SiteGuestPermissionListResponse,
    SiteGuestAccessLogResponse, SiteGuestAccessLogListResponse,
    TenantSiteSettingsUpdate, TenantSiteSettingsResponse,
    SiteGuestStatistics,
)
from app.schemas.general import SuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# =====================================
# SITE SETTINGS
# =====================================

@router.get("/site/settings", response_model=TenantSiteSettingsResponse)
async def get_site_settings(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get the current tenant's site settings.

    Returns site configuration including slug, enabled status, and guest counts.
    """
    tenant = await SiteGuestService.get_tenant_site_settings(db, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get guest counts
    guests, total = await SiteGuestService.list_guests(db, current_user.tenant_id, include_inactive=True)
    active_count = sum(1 for g in guests if g.is_active)

    return TenantSiteSettingsResponse(
        site_enabled=tenant.site_enabled or False,
        site_logo_url=tenant.site_logo_url,
        site_welcome_message=tenant.site_welcome_message,
        slug=tenant.slug,
        guest_count=total,
        active_guest_count=active_count
    )


@router.put("/site/settings", response_model=TenantSiteSettingsResponse)
async def update_site_settings(
    settings: TenantSiteSettingsUpdate,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update the current tenant's site settings.

    Allows enabling/disabling the site, setting custom slug, logo, and welcome message.
    """
    try:
        tenant = await SiteGuestService.update_tenant_site_settings(
            db, current_user.tenant_id, settings
        )

        # Get guest counts
        guests, total = await SiteGuestService.list_guests(db, current_user.tenant_id, include_inactive=True)
        active_count = sum(1 for g in guests if g.is_active)

        return TenantSiteSettingsResponse(
            site_enabled=tenant.site_enabled or False,
            site_logo_url=tenant.site_logo_url,
            site_welcome_message=tenant.site_welcome_message,
            slug=tenant.slug,
            guest_count=total,
            active_guest_count=active_count
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/site/statistics", response_model=SiteGuestStatistics)
async def get_site_statistics(
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get statistics for the tenant's site guests.

    Returns counts of guests, access metrics, and shared content.
    """
    stats = await SiteGuestService.get_statistics(db, current_user.tenant_id)
    return stats


# =====================================
# GUEST MANAGEMENT
# =====================================

@router.post("", response_model=SiteGuestResponse, status_code=status.HTTP_201_CREATED)
async def create_guest(
    guest_data: SiteGuestCreate,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create a new Site Guest.

    Creates an external user who can access the tenant's portal via OTP authentication.
    Optionally sends an invitation email immediately.
    """
    try:
        guest = await SiteGuestService.create_guest(
            db,
            current_user.tenant_id,
            guest_data,
            current_user.id
        )
        return _guest_to_response(guest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=SiteGuestListResponse)
async def list_guests(
    include_inactive: bool = Query(False, description="Include deactivated guests"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all Site Guests for the current tenant.

    Returns paginated list of guests with their status and permissions.
    """
    guests, total = await SiteGuestService.list_guests(
        db, current_user.tenant_id, include_inactive, page, per_page
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
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific Site Guest by ID.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Guest not found")

    return _guest_to_response(guest)


@router.put("/{guest_id}", response_model=SiteGuestResponse)
async def update_guest(
    guest_id: UUID,
    updates: SiteGuestUpdate,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Update a Site Guest.

    Can modify name, active status, permissions, and expiration.
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        updated_guest = await SiteGuestService.update_guest(db, guest_id, updates)
        return _guest_to_response(updated_guest)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{guest_id}", response_model=SuccessResponse)
async def deactivate_guest(
    guest_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Deactivate a Site Guest (soft delete).

    The guest will no longer be able to access the portal.
    All active sessions are revoked.
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
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
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Resend invitation email to a Site Guest.
    """
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Guest not found")

    success = await SiteGuestService.send_invitation_email(db, guest)
    if success:
        return SuccessResponse(message="Invitation email sent successfully")
    else:
        raise HTTPException(status_code=500, detail="Failed to send invitation email")


# =====================================
# PERMISSION MANAGEMENT
# =====================================

@router.get("/{guest_id}/permissions", response_model=SiteGuestPermissionListResponse)
async def list_guest_permissions(
    guest_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List all permissions for a Site Guest.
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
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
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Grant document permission to a Site Guest.

    permission_type must be one of: view, download, upload
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        permission = await SiteGuestService.grant_document_permission(
            db,
            guest_id,
            permission_data.document_id,
            permission_data.permission_type,
            current_user.id,
            permission_data.expires_at
        )
        return _permission_to_response(permission)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{guest_id}/permissions/folder", response_model=SiteGuestPermissionResponse)
async def grant_folder_permission(
    guest_id: UUID,
    permission_data: SiteGuestFolderPermissionCreate,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Grant folder permission to a Site Guest.

    All documents within the folder path will be accessible.
    permission_type must be one of: view, download, upload
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Guest not found")

    try:
        permission = await SiteGuestService.grant_folder_permission(
            db,
            guest_id,
            permission_data.folder_path,
            permission_data.permission_type,
            current_user.id,
            permission_data.expires_at
        )
        return _permission_to_response(permission)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{guest_id}/permissions/{permission_id}", response_model=SuccessResponse)
async def revoke_permission(
    guest_id: UUID,
    permission_id: UUID,
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Revoke a permission from a Site Guest.
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
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
    current_user: User = Depends(get_current_user_async),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get access logs for a Site Guest.

    Returns audit trail of all guest actions including logins, views, and downloads.
    """
    # Verify guest belongs to tenant
    guest = await SiteGuestService.get_guest(db, guest_id)
    if not guest or guest.tenant_id != current_user.tenant_id:
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
        tenant_id=guest.tenant_id,
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
