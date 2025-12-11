"""
Document ACL Schemas

Pydantic schemas for document-level Access Control Lists.
Supports granular permissions (view, edit, delete, share) assigned to
users, roles, or entire tenant.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


# =====================================
# ENUMS
# =====================================

class GranteeType(str, Enum):
    """Type of entity receiving the permission."""
    USER = "user"
    ROLE = "role"
    EVERYONE = "everyone"


class ACLAction(str, Enum):
    """Actions recorded in ACL audit log."""
    GRANTED = "granted"
    REVOKED = "revoked"
    MODIFIED = "modified"
    EXPIRED = "expired"


class ACLSource(str, Enum):
    """Source of the ACL entry."""
    MANUAL = "manual"
    SHARE_LINK = "share_link"
    INHERITED = "inherited"
    MIGRATION = "migration"


class Permission(str, Enum):
    """Individual permission types."""
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"
    SHARE = "share"


# =====================================
# PERMISSION SCHEMAS
# =====================================

class PermissionSet(BaseModel):
    """Set of permissions for a document."""
    can_view: bool = True
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False

    @classmethod
    def full_access(cls) -> "PermissionSet":
        """Create a permission set with full access."""
        return cls(can_view=True, can_edit=True, can_delete=True, can_share=True)

    @classmethod
    def view_only(cls) -> "PermissionSet":
        """Create a permission set with view-only access."""
        return cls(can_view=True, can_edit=False, can_delete=False, can_share=False)

    @classmethod
    def edit_access(cls) -> "PermissionSet":
        """Create a permission set with edit access (view + edit)."""
        return cls(can_view=True, can_edit=True, can_delete=False, can_share=False)


# =====================================
# ACL ENTRY SCHEMAS
# =====================================

class DocumentACLBase(BaseModel):
    """Base schema for document ACL entries."""
    grantee_type: GranteeType
    grantee_id: Optional[UUID] = Field(
        None,
        description="ID of user or role. NULL for 'everyone' type."
    )
    can_view: bool = True
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False
    expires_at: Optional[datetime] = None

    @field_validator('grantee_id')
    @classmethod
    def validate_grantee_id(cls, v, info):
        """Ensure grantee_id is provided for user/role types."""
        grantee_type = info.data.get('grantee_type')
        if grantee_type in [GranteeType.USER, GranteeType.ROLE] and v is None:
            raise ValueError(f"grantee_id is required for grantee_type '{grantee_type}'")
        if grantee_type == GranteeType.EVERYONE and v is not None:
            raise ValueError("grantee_id must be NULL for grantee_type 'everyone'")
        return v


class DocumentACLCreate(DocumentACLBase):
    """Schema for creating a new ACL entry."""
    source: ACLSource = ACLSource.MANUAL


class DocumentACLUpdate(BaseModel):
    """Schema for updating an existing ACL entry."""
    can_view: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_share: Optional[bool] = None
    expires_at: Optional[datetime] = None


class DocumentACLResponse(DocumentACLBase):
    """Schema for ACL entry in API responses."""
    id: UUID
    document_id: UUID
    tenant_id: UUID
    granted_by: Optional[UUID] = None
    granted_at: datetime
    source: ACLSource
    created_at: datetime
    updated_at: datetime

    # Resolved names (populated by service layer)
    grantee_name: Optional[str] = None
    granter_name: Optional[str] = None
    is_expired: bool = False

    class Config:
        from_attributes = True


class DocumentACLListResponse(BaseModel):
    """Response schema for listing ACLs of a document."""
    document_id: UUID
    document_title: str
    owner_id: UUID
    owner_name: Optional[str] = None
    acls: List[DocumentACLResponse]
    total: int


# =====================================
# GRANT/REVOKE REQUEST SCHEMAS
# =====================================

class GrantPermissionRequest(BaseModel):
    """Request to grant permissions to a user, role, or everyone."""
    grantee_type: GranteeType
    grantee_id: Optional[UUID] = None
    permissions: PermissionSet = Field(default_factory=PermissionSet.view_only)
    expires_at: Optional[datetime] = None
    source: ACLSource = ACLSource.MANUAL

    @field_validator('grantee_id')
    @classmethod
    def validate_grantee_id(cls, v, info):
        """Ensure grantee_id is provided for user/role types."""
        grantee_type = info.data.get('grantee_type')
        if grantee_type in [GranteeType.USER, GranteeType.ROLE] and v is None:
            raise ValueError(f"grantee_id is required for grantee_type '{grantee_type}'")
        return v


class GrantPermissionBatchRequest(BaseModel):
    """Request to grant permissions to multiple grantees at once."""
    grants: List[GrantPermissionRequest]


class RevokePermissionRequest(BaseModel):
    """Request to revoke permissions from a user, role, or everyone."""
    grantee_type: GranteeType
    grantee_id: Optional[UUID] = None

    @field_validator('grantee_id')
    @classmethod
    def validate_grantee_id(cls, v, info):
        """Ensure grantee_id is provided for user/role types."""
        grantee_type = info.data.get('grantee_type')
        if grantee_type in [GranteeType.USER, GranteeType.ROLE] and v is None:
            raise ValueError(f"grantee_id is required for grantee_type '{grantee_type}'")
        return v


# =====================================
# PERMISSION CHECK SCHEMAS
# =====================================

class EffectivePermissions(BaseModel):
    """
    User's effective permissions on a document.

    Computed by combining all applicable ACL entries (user, roles, everyone)
    with any implicit permissions (owner, admin).
    """
    can_view: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False

    # Source of permissions (for debugging/UI)
    is_owner: bool = False
    is_admin: bool = False
    from_user_acl: bool = False
    from_role_acl: bool = False
    from_everyone_acl: bool = False

    # Additional context
    applicable_acl_ids: List[UUID] = Field(default_factory=list)


class CheckPermissionRequest(BaseModel):
    """Request to check if a user has a specific permission."""
    permission: Permission


class CheckPermissionResponse(BaseModel):
    """Response to permission check request."""
    document_id: UUID
    user_id: UUID
    permission: Permission
    allowed: bool
    reason: str  # Why permission was granted/denied


# =====================================
# AUDIT SCHEMAS
# =====================================

class DocumentACLAuditBase(BaseModel):
    """Base schema for ACL audit entries."""
    document_id: UUID
    tenant_id: UUID
    acl_id: Optional[UUID] = None
    action: ACLAction
    grantee_type: GranteeType
    grantee_id: Optional[UUID] = None
    permissions_before: Optional[Dict[str, bool]] = None
    permissions_after: Optional[Dict[str, bool]] = None
    performed_by: Optional[UUID] = None
    source: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class DocumentACLAuditResponse(DocumentACLAuditBase):
    """Schema for ACL audit entry in API responses."""
    id: UUID
    created_at: datetime

    # Resolved names (populated by service layer)
    grantee_name: Optional[str] = None
    performer_name: Optional[str] = None
    document_title: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentACLAuditListResponse(BaseModel):
    """Response schema for listing ACL audit entries."""
    document_id: Optional[UUID] = None
    tenant_id: UUID
    audits: List[DocumentACLAuditResponse]
    total: int
    page: int
    page_size: int


# =====================================
# BULK OPERATIONS
# =====================================

class BulkACLUpdateRequest(BaseModel):
    """Request to update ACLs on multiple documents at once."""
    document_ids: List[UUID]
    grant_permissions: Optional[List[GrantPermissionRequest]] = None
    revoke_permissions: Optional[List[RevokePermissionRequest]] = None


class BulkACLUpdateResponse(BaseModel):
    """Response from bulk ACL update operation."""
    success_count: int
    failure_count: int
    failures: List[Dict[str, Any]] = Field(default_factory=list)


# =====================================
# SHARE LINK SCHEMAS
# =====================================

class ShareLinkRequest(BaseModel):
    """Request to create a share link with ACL."""
    permissions: PermissionSet = Field(default_factory=PermissionSet.view_only)
    expires_at: Optional[datetime] = None
    recipient_email: Optional[str] = None
    recipient_name: Optional[str] = None
    message: Optional[str] = None


class ShareLinkResponse(BaseModel):
    """Response containing share link details."""
    share_token: str
    share_url: str
    document_id: UUID
    permissions: PermissionSet
    expires_at: Optional[datetime] = None
    created_at: datetime
