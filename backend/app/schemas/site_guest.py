"""
Pydantic schemas for Site Guest access system.

Implements SharePoint-like external sharing with OTP authentication.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, EmailStr, Field, field_validator
from uuid import UUID


# =====================================
# SITE GUEST SCHEMAS
# =====================================

class SiteGuestBase(BaseModel):
    """Base schema for Site Guest."""
    email: EmailStr = Field(..., description="Guest email address")
    name: Optional[str] = Field(None, max_length=255, description="Guest display name")
    can_view: bool = Field(default=True, description="Can view documents")
    can_download: bool = Field(default=False, description="Can download documents")
    can_upload: bool = Field(default=False, description="Can upload documents")
    expires_at: Optional[datetime] = Field(None, description="Guest access expiration date")


class SiteGuestCreate(SiteGuestBase):
    """Schema for creating a new Site Guest."""
    send_invitation: bool = Field(default=True, description="Send invitation email immediately")


class SiteGuestUpdate(BaseModel):
    """Schema for updating an existing Site Guest."""
    name: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None
    can_view: Optional[bool] = None
    can_download: Optional[bool] = None
    can_upload: Optional[bool] = None
    expires_at: Optional[datetime] = None


class SiteGuestResponse(SiteGuestBase):
    """Schema for Site Guest responses."""
    id: UUID
    is_active: bool
    invited_by_user_id: Optional[UUID] = None
    invited_at: datetime
    last_access_at: Optional[datetime] = None
    access_count: int
    created_at: datetime
    updated_at: datetime

    # Computed fields
    is_expired: bool = False
    is_valid: bool = True

    class Config:
        from_attributes = True


class SiteGuestListResponse(BaseModel):
    """Schema for paginated list of guests."""
    guests: List[SiteGuestResponse]
    total: int
    page: int
    per_page: int


class SiteGuestInviteRequest(BaseModel):
    """Schema for sending/resending invitation email."""
    custom_message: Optional[str] = Field(None, description="Custom message to include in invitation")


# =====================================
# OTP AUTHENTICATION SCHEMAS
# =====================================

class OTPRequestPayload(BaseModel):
    """Schema for requesting an OTP code."""
    email: EmailStr = Field(..., description="Guest email to send OTP to")


class OTPRequestResponse(BaseModel):
    """Schema for OTP request response."""
    success: bool
    message: str
    expires_in_seconds: int = Field(default=600, description="OTP expiry time in seconds")


class OTPVerifyPayload(BaseModel):
    """Schema for verifying an OTP code."""
    email: EmailStr = Field(..., description="Guest email")
    otp_code: str = Field(..., min_length=6, max_length=6, description="6-digit OTP code")

    @field_validator('otp_code')
    @classmethod
    def validate_otp_format(cls, v):
        if not v.isdigit():
            raise ValueError('OTP code must contain only digits')
        return v


class OTPVerifyResponse(BaseModel):
    """Schema for successful OTP verification."""
    success: bool
    session_token: Optional[str] = Field(None, description="Session token for authenticated requests")
    expires_at: Optional[datetime] = Field(None, description="Session expiry time")
    guest: Optional["SiteGuestResponse"] = None
    error: Optional[str] = None


# =====================================
# SESSION SCHEMAS
# =====================================

class SiteGuestSessionResponse(BaseModel):
    """Schema for Site Guest session."""
    id: UUID
    guest_id: UUID
    created_at: datetime
    expires_at: datetime
    last_activity_at: Optional[datetime] = None
    is_active: bool
    ip_address: Optional[str] = None

    class Config:
        from_attributes = True


class SiteGuestSessionListResponse(BaseModel):
    """Schema for list of guest sessions."""
    sessions: List[SiteGuestSessionResponse]
    total: int


# =====================================
# PERMISSION SCHEMAS
# =====================================

class SiteGuestPermissionBase(BaseModel):
    """Base schema for Site Guest permission."""
    permission_type: str = Field(..., description="Permission type: view, download, upload")
    expires_at: Optional[datetime] = Field(None, description="Permission expiration date")

    @field_validator('permission_type')
    @classmethod
    def validate_permission_type(cls, v):
        allowed_types = ['view', 'download', 'upload']
        if v not in allowed_types:
            raise ValueError(f'Permission type must be one of {allowed_types}')
        return v


class SiteGuestDocumentPermissionCreate(SiteGuestPermissionBase):
    """Schema for granting document permission to a guest."""
    document_id: UUID = Field(..., description="Document ID to grant permission for")


class SiteGuestFolderPermissionCreate(SiteGuestPermissionBase):
    """Schema for granting folder permission to a guest."""
    folder_path: str = Field(..., max_length=2000, description="Folder path to grant permission for")


class SiteGuestPermissionResponse(SiteGuestPermissionBase):
    """Schema for Site Guest permission response."""
    id: UUID
    guest_id: UUID
    document_id: Optional[UUID] = None
    folder_path: Optional[str] = None
    granted_by_user_id: Optional[UUID] = None
    granted_at: datetime
    created_at: datetime

    # Document info (when applicable)
    document_title: Optional[str] = None
    document_filename: Optional[str] = None

    class Config:
        from_attributes = True


class SiteGuestPermissionListResponse(BaseModel):
    """Schema for list of guest permissions."""
    permissions: List[SiteGuestPermissionResponse]
    total: int


# =====================================
# ACCESS LOG SCHEMAS
# =====================================

class SiteGuestAccessLogResponse(BaseModel):
    """Schema for Site Guest access log entry."""
    id: UUID
    guest_id: UUID
    session_id: Optional[UUID] = None
    action: str
    success: bool
    error_message: Optional[str] = None
    document_id: Optional[UUID] = None
    folder_path: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    created_at: datetime

    # Document info
    document_title: Optional[str] = None

    class Config:
        from_attributes = True


class SiteGuestAccessLogListResponse(BaseModel):
    """Schema for paginated access logs."""
    logs: List[SiteGuestAccessLogResponse]
    total: int
    page: int
    per_page: int


# =====================================
# PORTAL CONTENT SCHEMAS
# =====================================

class PortalDocumentInfo(BaseModel):
    """Schema for document info in guest portal."""
    id: UUID
    title: str
    filename: str
    file_type: str
    file_size: int
    mime_type: Optional[str] = None
    folder_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    # Permissions for this guest
    can_view: bool = True
    can_download: bool = False


class PortalFolderInfo(BaseModel):
    """Schema for folder info in guest portal."""
    path: str
    name: str
    document_count: int

    # Permissions for this guest
    can_view: bool = True
    can_download: bool = False
    can_upload: bool = False


class PortalShareInfo(BaseModel):
    """Schema for share/collection info in guest portal."""
    id: UUID
    name: str
    description: Optional[str] = None
    permission_type: str
    document_count: int
    created_at: datetime
    expires_at: Optional[datetime] = None


class PortalShareDocumentsResponse(BaseModel):
    """Schema for documents inside a specific share/collection."""
    share: PortalShareInfo
    documents: List[PortalDocumentInfo]
    total_documents: int


class PortalContentResponse(BaseModel):
    """Schema for guest portal content."""
    shares: List[PortalShareInfo] = Field(default_factory=list)
    total_shares: int = 0
    documents: List[PortalDocumentInfo]
    folders: List[PortalFolderInfo]
    total_documents: int
    total_folders: int


class GuestMeResponse(BaseModel):
    """Schema for authenticated guest info."""
    guest: SiteGuestResponse
    tenant_name: str
    tenant_logo_url: Optional[str] = None
    session_expires_at: datetime


# =====================================
# TENANT SITE SETTINGS SCHEMAS
# =====================================

class TenantSiteInfo(BaseModel):
    """Schema for public site info (resolved by slug).

    Retained as `TenantSiteInfo` for backwards compatibility with the
    frontend client. In single-tenant mode the "tenant" concept collapses
    to the single organization.
    """
    tenant_name: str
    slug: str
    site_enabled: bool
    logo_url: Optional[str] = None
    welcome_message: Optional[str] = None


class TenantSiteSettingsUpdate(BaseModel):
    """Schema for updating tenant site settings."""
    site_enabled: Optional[bool] = None
    site_logo_url: Optional[str] = Field(None, max_length=500)
    site_welcome_message: Optional[str] = None
    slug: Optional[str] = Field(None, min_length=3, max_length=100)

    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v):
        if v is not None:
            import re
            if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', v):
                raise ValueError('Slug must be lowercase alphanumeric with hyphens, starting and ending with alphanumeric')
        return v


class TenantSiteSettingsResponse(BaseModel):
    """Schema for tenant site settings response."""
    site_enabled: bool
    site_logo_url: Optional[str] = None
    site_welcome_message: Optional[str] = None
    slug: Optional[str] = None
    guest_count: int = 0
    active_guest_count: int = 0


# =====================================
# STATISTICS SCHEMAS
# =====================================

class SiteGuestStatistics(BaseModel):
    """Schema for site guest statistics."""
    total_guests: int
    active_guests: int
    inactive_guests: int
    expired_guests: int
    total_access_count: int
    recent_accesses: int  # Last 24 hours
    documents_shared: int
    folders_shared: int
    access_by_action: Dict[str, int]
    access_by_date: Dict[str, int]


# =====================================
# SHARE/COLLECTION SCHEMAS
# =====================================

class CreateGuestWithShareRequest(BaseModel):
    """
    Combined request to create guest + share with documents.

    This is the simplified flow from the Documents page:
    - If guest exists by email, reuse them (don't create duplicate)
    - Creates a new share/collection with the specified documents
    - Optionally sends invitation email
    """
    # Guest info
    email: EmailStr = Field(..., description="Guest email address")
    name: Optional[str] = Field(None, max_length=255, description="Guest display name")

    # Share info
    share_name: str = Field(..., max_length=255, description="Name for the document collection")
    share_description: Optional[str] = Field(None, description="Optional description")
    document_ids: List[UUID] = Field(..., min_length=1, description="List of document IDs to share")
    permission_type: str = Field(default="view", description="Permission type: view, download, upload")
    expires_at: Optional[datetime] = Field(None, description="Share expiration date")
    send_invitation: bool = Field(default=True, description="Send notification email")

    @field_validator('permission_type')
    @classmethod
    def validate_permission_type(cls, v):
        allowed_types = ['view', 'download', 'upload']
        if v not in allowed_types:
            raise ValueError(f'Permission type must be one of {allowed_types}')
        return v


class SiteGuestShareResponse(BaseModel):
    """Response for a share/collection."""
    id: UUID
    name: str
    description: Optional[str] = None
    permission_type: str
    document_count: int
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SiteGuestShareDocumentResponse(BaseModel):
    """Response for a document in a share."""
    id: UUID
    title: str
    filename: str
    file_type: str
    file_size: int
    mime_type: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class SiteGuestShareDetailResponse(BaseModel):
    """Detailed response for a share including documents."""
    id: UUID
    name: str
    description: Optional[str] = None
    permission_type: str
    documents: List[SiteGuestShareDocumentResponse]
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CreateGuestWithShareResponse(BaseModel):
    """Response after creating guest + share."""
    guest: SiteGuestResponse
    share: SiteGuestShareResponse
    is_new_guest: bool = Field(description="True if a new guest was created, False if existing")
    message: str


class SiteGuestShareListResponse(BaseModel):
    """List of shares for a guest."""
    shares: List[SiteGuestShareResponse]
    total: int


# =====================================
# PORTAL SHARE SCHEMAS (for guest view)
# =====================================
class PortalShareContentResponse(BaseModel):
    """Schema for guest portal content with shares."""
    shares: List[PortalShareInfo]
    total_shares: int
    # Legacy support - individual documents without share
    documents: List[PortalDocumentInfo] = Field(default_factory=list)
    folders: List[PortalFolderInfo] = Field(default_factory=list)
