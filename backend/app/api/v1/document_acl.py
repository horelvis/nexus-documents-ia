"""
Document ACL API Endpoints

Provides REST API for managing document-level Access Control Lists.
Supports granting/revoking permissions to users, roles, or entire tenant.
"""

from typing import Optional
from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.api.async_dependencies import (
    get_current_user_async,
    get_current_tenant_id_async
)
from app.db.async_database import get_async_db
from app.db.models import User, Document
from app.schemas.document_acl import (
    GranteeType, Permission,
    DocumentACLResponse, DocumentACLListResponse,
    GrantPermissionRequest, GrantPermissionBatchRequest, RevokePermissionRequest,
    EffectivePermissions, CheckPermissionResponse,
    DocumentACLAuditListResponse,
    BulkACLUpdateRequest, BulkACLUpdateResponse,
)
from app.services.document_acl_service import DocumentACLService

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_client_info(request: Request) -> tuple[str | None, str | None]:
    """Extract client IP and user agent from request."""
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


# ========================================
# LIST/GET ACLs
# ========================================

@router.get("/{document_id}/acl", response_model=DocumentACLListResponse)
async def list_document_acls(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    List all ACL entries for a document.

    Returns all users, roles, and 'everyone' entries that have
    access to this document.

    Requires: Document exists and user has view permission on it.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check if user has at least view permission
        has_permission = await acl_service.check_permission(
            db, document_id, Permission.VIEW, current_user
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="You don't have permission to view this document")

        return await acl_service.list_document_acls(db, document_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing ACLs: {e}")
        raise HTTPException(status_code=500, detail="Failed to list document ACLs")


@router.get("/{document_id}/acl/{acl_id}", response_model=DocumentACLResponse)
async def get_acl_entry(
    document_id: UUID,
    acl_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """Get a specific ACL entry by ID."""
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check view permission
        has_permission = await acl_service.check_permission(
            db, document_id, Permission.VIEW, current_user
        )
        if not has_permission:
            raise HTTPException(status_code=403, detail="You don't have permission to view this document")

        acl = await acl_service.get_acl(db, acl_id)
        if not acl:
            raise HTTPException(status_code=404, detail="ACL entry not found")

        return acl

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting ACL: {e}")
        raise HTTPException(status_code=500, detail="Failed to get ACL entry")


# ========================================
# CHECK PERMISSIONS
# ========================================

@router.get("/{document_id}/acl/my-permissions", response_model=EffectivePermissions)
async def get_my_permissions(
    document_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get current user's effective permissions on a document.

    Returns all permissions (view, edit, delete, share) along with
    information about where each permission comes from (owner, admin,
    user ACL, role ACL, or everyone ACL).
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))
        return await acl_service.get_effective_permissions(db, document_id, current_user)

    except Exception as e:
        logger.error(f"Error getting permissions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get permissions")


@router.get("/{document_id}/acl/check/{permission}", response_model=CheckPermissionResponse)
async def check_permission(
    document_id: UUID,
    permission: Permission,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Check if current user has a specific permission on a document.

    Returns whether the permission is granted and the reason why.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        effective = await acl_service.get_effective_permissions(db, document_id, current_user)

        permission_map = {
            Permission.VIEW: effective.can_view,
            Permission.EDIT: effective.can_edit,
            Permission.DELETE: effective.can_delete,
            Permission.SHARE: effective.can_share,
        }

        allowed = permission_map.get(permission, False)

        # Determine reason
        if effective.is_owner:
            reason = "Document owner"
        elif effective.is_admin:
            reason = "Tenant administrator"
        elif effective.from_user_acl:
            reason = "Direct user permission"
        elif effective.from_role_acl:
            reason = "Role-based permission"
        elif effective.from_everyone_acl:
            reason = "Tenant-wide permission"
        else:
            reason = "No applicable permission"

        return CheckPermissionResponse(
            document_id=document_id,
            user_id=current_user.id,
            permission=permission,
            allowed=allowed,
            reason=reason
        )

    except Exception as e:
        logger.error(f"Error checking permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to check permission")


# ========================================
# GRANT PERMISSIONS
# ========================================

@router.post("/{document_id}/acl", response_model=DocumentACLResponse)
async def grant_permission(
    document_id: UUID,
    request: GrantPermissionRequest,
    req: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Grant permissions on a document to a user, role, or everyone.

    Requires: User must have 'share' permission on the document.

    Security: Users cannot grant permissions they don't have themselves.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check share permission
        has_permission = await acl_service.check_permission(
            db, document_id, Permission.SHARE, current_user
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to share this document"
            )

        # Security: Can't grant permissions you don't have
        my_permissions = await acl_service.get_effective_permissions(db, document_id, current_user)

        if request.permissions.can_edit and not my_permissions.can_edit:
            raise HTTPException(
                status_code=403,
                detail="You cannot grant edit permission because you don't have it"
            )
        if request.permissions.can_delete and not my_permissions.can_delete:
            raise HTTPException(
                status_code=403,
                detail="You cannot grant delete permission because you don't have it"
            )
        if request.permissions.can_share and not my_permissions.can_share:
            raise HTTPException(
                status_code=403,
                detail="You cannot grant share permission because you don't have it"
            )

        ip_address, user_agent = _get_client_info(req)

        return await acl_service.grant_permission(
            db, document_id, request, ip_address, user_agent
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error granting permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to grant permission")


@router.post("/{document_id}/acl/batch", response_model=list[DocumentACLResponse])
async def grant_permissions_batch(
    document_id: UUID,
    request: GrantPermissionBatchRequest,
    req: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Grant permissions to multiple grantees at once.

    Requires: User must have 'share' permission on the document.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check share permission
        has_permission = await acl_service.check_permission(
            db, document_id, Permission.SHARE, current_user
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to share this document"
            )

        ip_address, user_agent = _get_client_info(req)

        results = []
        for grant in request.grants:
            try:
                acl = await acl_service.grant_permission(
                    db, document_id, grant, ip_address, user_agent
                )
                results.append(acl)
            except Exception as e:
                logger.warning(f"Failed to grant permission in batch: {e}")
                # Continue with other grants

        return results

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in batch grant: {e}")
        raise HTTPException(status_code=500, detail="Failed to grant permissions")


# ========================================
# REVOKE PERMISSIONS
# ========================================

@router.delete("/{document_id}/acl/{acl_id}")
async def revoke_permission_by_id(
    document_id: UUID,
    acl_id: UUID,
    req: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Revoke a specific ACL entry by its ID.

    Requires: User must have 'share' permission on the document.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check share permission
        has_permission = await acl_service.check_permission(
            db, document_id, Permission.SHARE, current_user
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to modify access to this document"
            )

        ip_address, user_agent = _get_client_info(req)

        success = await acl_service.revoke_by_acl_id(
            db, document_id, acl_id, ip_address, user_agent
        )

        if not success:
            raise HTTPException(status_code=404, detail="ACL entry not found")

        return {"status": "success", "message": "Permission revoked"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke permission")


@router.post("/{document_id}/acl/revoke")
async def revoke_permission(
    document_id: UUID,
    request: RevokePermissionRequest,
    req: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Revoke permissions from a user, role, or everyone.

    Requires: User must have 'share' permission on the document.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check share permission
        has_permission = await acl_service.check_permission(
            db, document_id, Permission.SHARE, current_user
        )
        if not has_permission:
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to modify access to this document"
            )

        ip_address, user_agent = _get_client_info(req)

        success = await acl_service.revoke_permission(
            db, document_id, request, ip_address, user_agent
        )

        if not success:
            raise HTTPException(status_code=404, detail="ACL entry not found")

        return {"status": "success", "message": "Permission revoked"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking permission: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke permission")


# ========================================
# BULK OPERATIONS
# ========================================

@router.post("/bulk-update", response_model=BulkACLUpdateResponse)
async def bulk_update_acls(
    request: BulkACLUpdateRequest,
    req: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Update ACLs on multiple documents at once.

    Requires: User must have 'share' permission on ALL documents.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Check share permission on all documents
        for doc_id in request.document_ids:
            has_permission = await acl_service.check_permission(
                db, doc_id, Permission.SHARE, current_user
            )
            if not has_permission:
                raise HTTPException(
                    status_code=403,
                    detail=f"You don't have permission to share document {doc_id}"
                )

        ip_address, user_agent = _get_client_info(req)

        return await acl_service.bulk_update_acls(
            db, request, ip_address, user_agent
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in bulk update: {e}")
        raise HTTPException(status_code=500, detail="Failed to bulk update ACLs")


# ========================================
# AUDIT LOG
# ========================================

@router.get("/{document_id}/acl/audit", response_model=DocumentACLAuditListResponse)
async def get_document_acl_audit(
    document_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get ACL audit log for a specific document.

    Returns all permission changes (granted, revoked, modified, expired)
    with timestamps and actor information.

    Requires: User must be owner or admin to view audit log.
    """
    try:
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

        # Only owner or admin can view audit log
        effective = await acl_service.get_effective_permissions(db, document_id, current_user)
        if not (effective.is_owner or effective.is_admin):
            raise HTTPException(
                status_code=403,
                detail="Only document owner or admin can view audit log"
            )

        return await acl_service.get_audit_log(db, document_id, page, page_size)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting audit log: {e}")
        raise HTTPException(status_code=500, detail="Failed to get audit log")


@router.get("/audit", response_model=DocumentACLAuditListResponse)
async def get_tenant_acl_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get ACL audit log for all documents in tenant.

    Requires: User must be tenant admin.
    """
    try:
        # Only admin can view tenant-wide audit
        if not current_user.is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only administrators can view tenant-wide audit log"
            )

        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))
        return await acl_service.get_audit_log(db, None, page, page_size)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting tenant audit log: {e}")
        raise HTTPException(status_code=500, detail="Failed to get audit log")
