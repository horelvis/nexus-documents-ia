"""Pydantic schemas for Information Channels."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ChannelType(str, Enum):
    """Supported channel types."""
    GMAIL = "gmail"
    GOOGLE_DRIVE = "google_drive"
    EXTERNAL_DB = "external_db"


class ChannelVisibility(str, Enum):
    """Channel visibility options for RAG access control."""
    PERSONAL = "personal"  # Only visible to creator
    TENANT = "tenant"  # Visible to all tenant users


class ChannelSyncStatus(str, Enum):
    """Status of channel synchronization."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class SyncTriggerType(str, Enum):
    """How the sync was triggered."""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"


# =============================================================================
# Gmail Channel Configuration
# =============================================================================

class GmailConfig(BaseModel):
    """Gmail channel configuration."""
    labels: List[str] = Field(default=["INBOX"], description="Gmail labels to sync")
    max_age_days: int = Field(default=90, ge=1, le=365, description="Maximum email age to sync")
    include_attachments: bool = Field(default=True, description="Process email attachments")
    attachment_types: List[str] = Field(
        default=["pdf", "docx", "doc", "xlsx", "xls", "txt"],
        description="Allowed attachment types"
    )
    max_emails_per_sync: int = Field(default=100, ge=1, le=500, description="Max emails per sync")


# =============================================================================
# Google Drive Channel Configuration
# =============================================================================

class GoogleDriveConfig(BaseModel):
    """Google Drive channel configuration."""
    folder_id: str = Field(..., description="Google Drive folder ID")
    folder_name: str = Field(default="", description="Folder name for display")
    include_subfolders: bool = Field(default=True, description="Recursively sync subfolders")
    file_types: List[str] = Field(
        default=["pdf", "docx", "doc", "xlsx", "xls", "txt", "pptx", "ppt"],
        description="File types to sync"
    )
    max_file_size_mb: int = Field(default=50, ge=1, le=100, description="Max file size in MB")


# =============================================================================
# External Database Channel Configuration (Future)
# =============================================================================

class DatabaseType(str, Enum):
    """Supported external database types."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLSERVER = "sqlserver"


class ExternalDBConfig(BaseModel):
    """External database channel configuration."""
    db_type: DatabaseType
    host: str
    port: int = Field(ge=1, le=65535)
    database: str
    query: str = Field(..., description="SQL query to extract data")
    id_column: str = Field(default="id", description="Column to use as document ID")
    content_columns: List[str] = Field(..., description="Columns to combine as content")
    metadata_columns: List[str] = Field(default=[], description="Columns for metadata")
    max_rows: int = Field(default=1000, ge=1, le=10000, description="Max rows per sync")


# =============================================================================
# Channel CRUD Schemas
# =============================================================================

class ChannelBase(BaseModel):
    """Base channel fields."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: ChannelVisibility = Field(default=ChannelVisibility.PERSONAL)
    sync_interval_minutes: int = Field(default=60, ge=0, le=1440)


class ChannelCreate(ChannelBase):
    """Schema for creating a channel."""
    channel_type: ChannelType
    configuration: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("configuration")
    @classmethod
    def validate_configuration(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        """Validate configuration based on channel type."""
        # Validation will be done in the service layer based on channel_type
        return v


class GmailChannelCreate(ChannelBase):
    """Schema for creating a Gmail channel."""
    configuration: GmailConfig = Field(default_factory=GmailConfig)


class GoogleDriveChannelCreate(ChannelBase):
    """Schema for creating a Google Drive channel."""
    configuration: GoogleDriveConfig


class ExternalDBChannelCreate(ChannelBase):
    """Schema for creating an External Database channel."""
    configuration: ExternalDBConfig


class ChannelUpdate(BaseModel):
    """Schema for updating a channel."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    visibility: Optional[ChannelVisibility] = None
    configuration: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    sync_interval_minutes: Optional[int] = Field(None, ge=0, le=1440)


class ChannelResponse(ChannelBase):
    """Schema for channel response."""
    id: UUID
    tenant_id: UUID
    created_by: UUID
    channel_type: ChannelType
    configuration: Dict[str, Any]
    is_active: bool
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    last_sync_error: Optional[str] = None
    documents_indexed: int = 0
    next_sync_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    # OAuth info (for Google channels)
    oauth_email: Optional[str] = None
    has_credentials: bool = False

    class Config:
        from_attributes = True


class ChannelListResponse(BaseModel):
    """Schema for paginated channel list."""
    items: List[ChannelResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# =============================================================================
# Sync Log Schemas
# =============================================================================

class SyncLogResponse(BaseModel):
    """Schema for sync log entry."""
    id: UUID
    channel_id: UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    trigger_type: str
    items_found: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_failed: int = 0
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class SyncHistoryResponse(BaseModel):
    """Schema for sync history list."""
    items: List[SyncLogResponse]
    total: int


# =============================================================================
# Channel Document Schemas
# =============================================================================

class ChannelDocumentResponse(BaseModel):
    """Schema for channel document reference."""
    id: UUID
    channel_id: UUID
    external_id: str
    external_url: Optional[str] = None
    title: Optional[str] = None
    weaviate_id: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    source_created_at: Optional[datetime] = None
    source_modified_at: Optional[datetime] = None
    first_indexed_at: Optional[datetime] = None
    last_indexed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChannelDocumentsResponse(BaseModel):
    """Schema for channel documents list."""
    items: List[ChannelDocumentResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# OAuth Schemas
# =============================================================================

class OAuthUrlResponse(BaseModel):
    """OAuth authorization URL response."""
    auth_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    """OAuth callback data."""
    code: str
    state: str


# =============================================================================
# Sync Trigger Schemas
# =============================================================================

class SyncTriggerRequest(BaseModel):
    """Request to trigger manual sync."""
    full_sync: bool = Field(default=False, description="Force full resync")


class SyncTriggerResponse(BaseModel):
    """Response from sync trigger."""
    sync_id: UUID
    channel_id: UUID
    status: str
    message: str


# =============================================================================
# Database Credentials (for external DB channels)
# =============================================================================

class DBCredentialsCreate(BaseModel):
    """Database credentials for external DB channel."""
    username: str
    password: str


class TestConnectionResponse(BaseModel):
    """Response from connection test."""
    success: bool
    message: str
    row_count: Optional[int] = None
