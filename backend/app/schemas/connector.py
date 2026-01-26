"""Pydantic schemas for Connectors (admin-managed external data sources)."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class ConnectorType(str, Enum):
    """Supported connector types for external data sources."""
    SHAREPOINT = "sharepoint"
    ONEDRIVE = "onedrive"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_WORKSPACE = "google_workspace"
    DROPBOX = "dropbox"
    BOX = "box"
    S3 = "s3"
    AZURE_BLOB = "azure_blob"
    NETWORK_SHARE = "network_share"  # SMB/CIFS
    ALFRESCO = "alfresco"  # Alfresco 7.x ECM
    DATABASE = "database"  # Generic database BLOB storage


class ConnectorAuthType(str, Enum):
    """Authentication type for connectors."""
    DELEGATED = "delegated"  # Each user authorizes with their own account
    SERVICE_ACCOUNT = "service_account"  # Single service account for all users
    API_KEY = "api_key"  # API key based authentication


class ConnectorHealthStatus(str, Enum):
    """Health status of a connector."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class SyncStatus(str, Enum):
    """Status of user document sync."""
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


# =============================================================================
# SharePoint Configuration
# =============================================================================

class SharePointConfig(BaseModel):
    """SharePoint/OneDrive connector configuration."""
    tenant_id: str = Field(..., description="Azure AD tenant ID")
    client_id: str = Field(..., description="Azure AD app client ID")
    client_secret: Optional[str] = Field(None, description="Client secret (for service account)")
    site_url: Optional[str] = Field(None, description="SharePoint site URL (optional filter)")
    drive_id: Optional[str] = Field(None, description="Specific drive ID (optional)")


class OneDriveConfig(BaseModel):
    """OneDrive for Business connector configuration."""
    tenant_id: str = Field(..., description="Azure AD tenant ID")
    client_id: str = Field(..., description="Azure AD app client ID")
    client_secret: Optional[str] = Field(None, description="Client secret (for service account)")


# =============================================================================
# Google Workspace Configuration
# =============================================================================

class GoogleWorkspaceConfig(BaseModel):
    """Google Workspace connector configuration."""
    client_id: str = Field(..., description="Google OAuth client ID")
    client_secret: str = Field(..., description="Google OAuth client secret")
    domain: Optional[str] = Field(None, description="G Suite domain (optional filter)")
    service_account_json: Optional[str] = Field(None, description="Service account JSON (for domain-wide delegation)")


# =============================================================================
# S3/Azure Blob Configuration
# =============================================================================

class S3Config(BaseModel):
    """AWS S3 connector configuration."""
    bucket_name: str = Field(..., description="S3 bucket name")
    region: str = Field(default="us-east-1", description="AWS region")
    access_key_id: Optional[str] = Field(None, description="AWS access key (for service account)")
    secret_access_key: Optional[str] = Field(None, description="AWS secret key (for service account)")
    prefix: Optional[str] = Field(None, description="Key prefix filter")
    role_arn: Optional[str] = Field(None, description="IAM role ARN for assumed role access")


class AzureBlobConfig(BaseModel):
    """Azure Blob Storage connector configuration."""
    storage_account: str = Field(..., description="Storage account name")
    container_name: str = Field(..., description="Container name")
    connection_string: Optional[str] = Field(None, description="Connection string (for service account)")
    prefix: Optional[str] = Field(None, description="Blob prefix filter")


# =============================================================================
# Network Share Configuration
# =============================================================================

class NetworkShareConfig(BaseModel):
    """SMB/CIFS Network Share connector configuration."""
    server: str = Field(..., description="Server hostname or IP")
    share_name: str = Field(..., description="Share name")
    domain: Optional[str] = Field(None, description="Active Directory domain")
    username: Optional[str] = Field(None, description="Service account username")
    password: Optional[str] = Field(None, description="Service account password")
    base_path: Optional[str] = Field(None, description="Base path within share")


# =============================================================================
# Alfresco 7.x ECM Configuration
# =============================================================================

class AlfrescoConfig(BaseModel):
    """
    Alfresco 7.x Content Services connector configuration.

    Supports both Alfresco Community and Enterprise editions.
    Uses Alfresco REST API v1 for document operations and Search API for AFTS queries.

    API Documentation:
    https://docs.alfresco.com/content-services/latest/develop/rest-api-guide/

    AFTS Query Examples:
    - TYPE:"cm:content" - Filter by node type
    - ASPECT:"cm:titled" - Filter by aspect
    - PATH:"/app:company_home/st:sites/cm:mysite//*" - Filter by path
    - @cm\\:content.mimetype:"application/pdf" - Filter by MIME type
    """
    url: str = Field(
        ...,
        description="Alfresco base URL (e.g., https://alfresco.company.com)"
    )
    username: str = Field(
        ...,
        description="Service account username with API access"
    )
    password: str = Field(
        ...,
        description="Service account password"
    )

    # API paths (Alfresco 7.x defaults)
    api_path: str = Field(
        default="/alfresco/api/-default-/public/alfresco/versions/1",
        description="REST API base path"
    )
    search_api_path: str = Field(
        default="/alfresco/api/-default-/public/search/versions/1",
        description="Search API base path for AFTS queries"
    )

    # Default locations
    default_site_id: Optional[str] = Field(
        None,
        description="Default Alfresco site ID for operations"
    )
    default_folder_id: Optional[str] = Field(
        None,
        description="Default folder node ID (UUID)"
    )

    # ==========================================================================
    # AFTS Sync Filters - Control which documents are synchronized
    # ==========================================================================
    afts_type_filter: Optional[List[str]] = Field(
        default=None,
        description=(
            "Node types to include (e.g., ['cm:content', 'cm:document']). "
            "Generates AFTS: TYPE:\"cm:content\" OR TYPE:\"cm:document\""
        )
    )
    afts_aspect_filter: Optional[List[str]] = Field(
        default=None,
        description=(
            "Aspects to filter by (e.g., ['cm:titled', 'cm:versionable']). "
            "Generates AFTS: ASPECT:\"cm:titled\" AND ASPECT:\"cm:versionable\""
        )
    )
    afts_path_filter: Optional[str] = Field(
        default=None,
        description=(
            "AFTS path pattern to restrict sync scope. "
            "Example: '/app:company_home/st:sites/cm:mysite/cm:documentLibrary//*' "
            "for all documents in mysite's document library"
        )
    )
    afts_mime_types: Optional[List[str]] = Field(
        default=None,
        description=(
            "MIME types to include (e.g., ['application/pdf', 'application/msword']). "
            "If not specified, syncs all supported document types"
        )
    )
    afts_custom_query: Optional[str] = Field(
        default=None,
        description=(
            "Custom AFTS query fragment to append. "
            "Example: '@cm\\:author:\"John Doe\"' to filter by author. "
            "Combined with other filters using AND"
        )
    )
    afts_exclude_paths: Optional[List[str]] = Field(
        default=None,
        description=(
            "Path patterns to exclude from sync. "
            "Example: ['/app:company_home/st:sites/cm:archive//*']"
        )
    )

    # Timeouts
    timeout_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Request timeout in seconds"
    )
    download_timeout_seconds: int = Field(
        default=300,
        ge=60,
        le=900,
        description="Download timeout for large files"
    )

    # Limits
    max_results: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum search results per request"
    )
    max_upload_size_mb: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum upload file size in MB"
    )

    def build_sync_afts_query(self) -> str:
        """
        Build AFTS query from configured filters.

        Returns:
            Complete AFTS query string for document sync

        Note on Alfresco Site structure:
            Sites contain multiple containers: documentLibrary, wiki, links, etc.
            Documents are stored in: /st:sites/cm:{shortname}/cm:documentLibrary/
            When using SITE filter, we also filter by documentLibrary PATH.
        """
        parts = []

        # Default to content nodes if no type filter
        if self.afts_type_filter:
            type_conditions = " OR ".join(f'TYPE:"{t}"' for t in self.afts_type_filter)
            parts.append(f"({type_conditions})")
        else:
            parts.append('TYPE:"cm:content"')

        # Folder filter using ANCESTOR (most specific, uses node UUID)
        # This is the preferred way to search within a specific folder like documentLibrary
        if self.default_folder_id:
            parts.append(f'ANCESTOR:"workspace://SpacesStore/{self.default_folder_id}"')
        elif self.default_site_id:
            # Site filter - the adapter should resolve this to documentLibrary nodeId
            # and use ANCESTOR instead. This is a fallback if that fails.
            parts.append(f'SITE:"{self.default_site_id}"')

        # Path filter (additional custom path restriction)
        if self.afts_path_filter:
            parts.append(f'PATH:"{self.afts_path_filter}"')

        # Aspect filters
        if self.afts_aspect_filter:
            for aspect in self.afts_aspect_filter:
                parts.append(f'ASPECT:"{aspect}"')

        # MIME type filter
        if self.afts_mime_types:
            mime_conditions = " OR ".join(
                f'@cm\\:content.mimetype:"{mt}"' for mt in self.afts_mime_types
            )
            parts.append(f"({mime_conditions})")

        # Custom query
        if self.afts_custom_query:
            parts.append(f"({self.afts_custom_query})")

        # Exclude paths (NOT)
        if self.afts_exclude_paths:
            for exclude_path in self.afts_exclude_paths:
                parts.append(f'-PATH:"{exclude_path}"')

        return " AND ".join(parts)


# =============================================================================
# Database Connector Configuration (Multi-type support)
# =============================================================================

class DatabaseEngine(str, Enum):
    """Supported database engines."""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MARIADB = "mariadb"
    SQLITE = "sqlite"
    MSSQL = "mssql"  # SQL Server
    ORACLE = "oracle"


class DocumentStorageType(str, Enum):
    """How documents are stored in the database."""
    BLOB = "blob"  # Binary data in a column
    FILE_PATH = "file_path"  # Path to file on disk/network
    URL = "url"  # URL to fetch document


class DatabaseConfig(BaseModel):
    """
    Database connector configuration for extracting documents from RDBMS.

    Supports multiple database engines via SQLAlchemy. Documents can be stored
    as BLOBs, file paths, or URLs.

    Example configurations:

    PostgreSQL with BLOB storage:
    {
        "engine": "postgresql",
        "host": "localhost",
        "port": 5432,
        "database": "documents_db",
        "username": "reader",
        "password": "secret",
        "table_name": "documents",
        "storage_type": "blob",
        "column_mapping": {
            "id": "doc_id",
            "content": "file_data",
            "filename": "original_filename",
            "mime_type": "content_type",
            "created_at": "created_date",
            "modified_at": "updated_date"
        }
    }

    MySQL with file path storage:
    {
        "engine": "mysql",
        "host": "db.company.com",
        "database": "fileserver",
        "username": "sync_user",
        "password": "secret",
        "table_name": "file_metadata",
        "storage_type": "file_path",
        "file_base_path": "/mnt/documents",
        "column_mapping": {
            "id": "file_id",
            "content": "relative_path",
            "filename": "display_name",
            "size": "file_size_bytes"
        }
    }

    SQL Server with custom query:
    {
        "engine": "mssql",
        "host": "sqlserver.local",
        "database": "DocumentArchive",
        "username": "sa",
        "password": "secret",
        "custom_query": "SELECT id, content, name FROM dbo.Archives WHERE status = 'active'",
        "storage_type": "blob"
    }
    """
    # Database connection
    engine: DatabaseEngine = Field(
        ...,
        description="Database engine type"
    )
    host: str = Field(
        ...,
        description="Database host"
    )
    port: Optional[int] = Field(
        None,
        description="Database port (uses default for engine if not specified)"
    )
    database: str = Field(
        ...,
        description="Database name"
    )
    username: str = Field(
        ...,
        description="Database username"
    )
    password: str = Field(
        ...,
        description="Database password"
    )
    schema_name: Optional[str] = Field(
        None,
        description="Schema name (for PostgreSQL, SQL Server, Oracle)"
    )

    # SSL/TLS options
    ssl_enabled: bool = Field(
        default=False,
        description="Enable SSL connection"
    )
    ssl_ca_cert: Optional[str] = Field(
        None,
        description="Path to CA certificate file"
    )
    ssl_verify: bool = Field(
        default=True,
        description="Verify SSL certificate"
    )

    # Table configuration (use either table_name OR custom_query)
    table_name: Optional[str] = Field(
        None,
        description="Table containing documents"
    )
    custom_query: Optional[str] = Field(
        None,
        description="Custom SQL query to fetch documents (overrides table_name)"
    )

    # Storage type
    storage_type: DocumentStorageType = Field(
        default=DocumentStorageType.BLOB,
        description="How document content is stored"
    )
    file_base_path: Optional[str] = Field(
        None,
        description="Base path for file_path storage type"
    )

    # Column mapping - maps our standard fields to actual column names
    column_mapping: Dict[str, str] = Field(
        default_factory=lambda: {
            "id": "id",
            "content": "content",
            "filename": "filename",
            "mime_type": "mime_type",
            "size": "size",
            "created_at": "created_at",
            "modified_at": "modified_at",
        },
        description="Map standard fields to actual column names"
    )

    # Optional columns for additional metadata
    extra_columns: List[str] = Field(
        default_factory=list,
        description="Additional columns to extract as metadata"
    )

    # Filtering
    where_clause: Optional[str] = Field(
        None,
        description="WHERE clause for filtering (without 'WHERE' keyword)"
    )
    order_by: Optional[str] = Field(
        default="modified_at DESC",
        description="ORDER BY clause for consistent pagination"
    )

    # Performance
    batch_size: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Number of documents to fetch per batch"
    )
    timeout_seconds: int = Field(
        default=60,
        ge=10,
        le=300,
        description="Query timeout in seconds"
    )
    max_blob_size_mb: int = Field(
        default=100,
        ge=1,
        le=500,
        description="Maximum BLOB size to process in MB"
    )

    def get_default_port(self) -> int:
        """Get default port for the database engine."""
        defaults = {
            DatabaseEngine.POSTGRESQL: 5432,
            DatabaseEngine.MYSQL: 3306,
            DatabaseEngine.MARIADB: 3306,
            DatabaseEngine.SQLITE: 0,  # N/A
            DatabaseEngine.MSSQL: 1433,
            DatabaseEngine.ORACLE: 1521,
        }
        return defaults.get(self.engine, 5432)

    def get_connection_url(self, include_password: bool = True) -> str:
        """
        Build SQLAlchemy connection URL.

        Args:
            include_password: Include password in URL (False for logging)

        Returns:
            SQLAlchemy connection string
        """
        # Driver mapping
        drivers = {
            DatabaseEngine.POSTGRESQL: "postgresql+asyncpg",
            DatabaseEngine.MYSQL: "mysql+aiomysql",
            DatabaseEngine.MARIADB: "mysql+aiomysql",
            DatabaseEngine.SQLITE: "sqlite+aiosqlite",
            DatabaseEngine.MSSQL: "mssql+aioodbc",
            DatabaseEngine.ORACLE: "oracle+oracledb",
        }

        driver = drivers.get(self.engine, "postgresql+asyncpg")
        port = self.port or self.get_default_port()
        password = self.password if include_password else "***"

        if self.engine == DatabaseEngine.SQLITE:
            return f"{driver}:///{self.database}"

        url = f"{driver}://{self.username}:{password}@{self.host}:{port}/{self.database}"

        # Add schema for supported databases
        if self.schema_name and self.engine in [
            DatabaseEngine.POSTGRESQL,
            DatabaseEngine.MSSQL,
            DatabaseEngine.ORACLE
        ]:
            url += f"?options=-c%20search_path={self.schema_name}"

        return url

    def build_select_query(self) -> str:
        """
        Build SELECT query based on configuration.

        Returns:
            SQL SELECT query string
        """
        if self.custom_query:
            return self.custom_query

        if not self.table_name:
            raise ValueError("Either table_name or custom_query must be specified")

        # Build column list
        columns = []
        for std_name, col_name in self.column_mapping.items():
            if col_name:
                columns.append(f"{col_name} AS {std_name}")

        # Add extra columns
        for col in self.extra_columns:
            columns.append(col)

        # Build query
        table = f"{self.schema_name}.{self.table_name}" if self.schema_name else self.table_name
        query = f"SELECT {', '.join(columns)} FROM {table}"

        if self.where_clause:
            query += f" WHERE {self.where_clause}"

        if self.order_by:
            query += f" ORDER BY {self.order_by}"

        return query

    @field_validator("custom_query")
    @classmethod
    def validate_custom_query(cls, v: Optional[str]) -> Optional[str]:
        """Validate custom query is safe (no dangerous keywords)."""
        if v is None:
            return v

        v_upper = v.upper()
        dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "INSERT", "UPDATE", "ALTER", "CREATE", "EXEC", "EXECUTE"]

        for keyword in dangerous_keywords:
            if keyword in v_upper:
                raise ValueError(f"Custom query cannot contain {keyword} keyword")

        if not v_upper.strip().startswith("SELECT"):
            raise ValueError("Custom query must be a SELECT statement")

        return v


# =============================================================================
# Connector CRUD Schemas
# =============================================================================

class ConnectorBase(BaseModel):
    """Base connector fields."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    sync_enabled: bool = Field(default=True, description="Enable automatic sync")
    sync_interval_hours: int = Field(default=24, ge=1, le=168, description="Sync interval in hours")


class ConnectorCreate(ConnectorBase):
    """Schema for creating a connector (admin only)."""
    connector_type: ConnectorType
    auth_type: ConnectorAuthType = Field(default=ConnectorAuthType.DELEGATED)
    config: Dict[str, Any] = Field(default_factory=dict, description="Type-specific configuration")

    @field_validator("config")
    @classmethod
    def validate_config(cls, v: Dict[str, Any], info) -> Dict[str, Any]:
        """Configuration validation happens in service layer based on connector_type."""
        return v


class ConnectorUpdate(BaseModel):
    """Schema for updating a connector (admin only)."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    sync_enabled: Optional[bool] = None
    sync_interval_hours: Optional[int] = Field(None, ge=1, le=168)
    is_active: Optional[bool] = None


class ConnectorResponse(ConnectorBase):
    """Schema for connector response."""
    id: UUID
    tenant_id: UUID
    connector_type: ConnectorType
    auth_type: ConnectorAuthType
    config: Dict[str, Any]  # Note: sensitive fields should be redacted
    is_active: bool
    health_status: ConnectorHealthStatus
    health_message: Optional[str] = None
    last_health_check: Optional[datetime] = None
    created_by_id: Optional[UUID] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    # Computed fields - Users
    users_connected: int = 0  # Number of users with active auth
    users_syncing: int = 0  # Number of users with active sync

    # Computed fields - Document Processing (from IndexedDocument table)
    documents_total: int = 0  # Total documents synced
    documents_pending: int = 0  # Awaiting indexing
    documents_indexed: int = 0  # Successfully indexed to Weaviate
    documents_failed: int = 0  # Failed to index

    class Config:
        from_attributes = True


class ConnectorListResponse(BaseModel):
    """Schema for paginated connector list."""
    items: List[ConnectorResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# =============================================================================
# Health Check Schemas
# =============================================================================

class ConnectorHealthCheckResponse(BaseModel):
    """Response from connector health check."""
    connector_id: UUID
    status: ConnectorHealthStatus
    message: str
    checked_at: datetime
    details: Optional[Dict[str, Any]] = None


# =============================================================================
# User Connector Auth Schemas (user's OAuth tokens)
# =============================================================================

class UserConnectorAuthResponse(BaseModel):
    """User's authorization status for a connector."""
    connector_id: UUID
    connector_name: str
    connector_type: ConnectorType
    is_authorized: bool
    oauth_email: Optional[str] = None
    scopes: List[str] = []
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class ConnectorOAuthUrlResponse(BaseModel):
    """OAuth authorization URL for user to connect."""
    auth_url: str
    state: str
    connector_id: UUID
    connector_type: ConnectorType


# =============================================================================
# User Document Sync Schemas
# =============================================================================

class UserSyncConfigCreate(BaseModel):
    """Configuration for user's document sync."""
    sync_enabled: bool = Field(default=True)
    include_paths: List[str] = Field(default_factory=list, description="Paths/folders to include")
    exclude_paths: List[str] = Field(default_factory=list, description="Paths/folders to exclude")


class UserSyncConfigUpdate(BaseModel):
    """Update user's sync configuration."""
    sync_enabled: Optional[bool] = None
    include_paths: Optional[List[str]] = None
    exclude_paths: Optional[List[str]] = None


class UserDocumentSyncResponse(BaseModel):
    """User's document sync status for a connector."""
    id: UUID
    connector_id: UUID
    connector_name: str
    connector_type: ConnectorType
    sync_enabled: bool
    include_paths: List[str]
    exclude_paths: List[str]
    status: SyncStatus
    status_message: Optional[str] = None
    documents_total: int = 0
    documents_indexed: int = 0
    documents_failed: int = 0
    total_size_bytes: int = 0
    last_sync_started_at: Optional[datetime] = None
    last_sync_completed_at: Optional[datetime] = None
    next_sync_at: Optional[datetime] = None
    last_error: Optional[str] = None

    class Config:
        from_attributes = True


class UserSyncListResponse(BaseModel):
    """List of user's document syncs."""
    items: List[UserDocumentSyncResponse]
    total: int


class TriggerSyncRequest(BaseModel):
    """Request to trigger manual sync."""
    full_resync: bool = Field(default=False, description="Force full resync instead of incremental")


class TriggerSyncResponse(BaseModel):
    """Response from sync trigger."""
    sync_id: UUID
    connector_id: UUID
    status: str
    message: str


# =============================================================================
# Indexed Document Schemas
# =============================================================================

class IndexedDocumentResponse(BaseModel):
    """Metadata for a document indexed from a connector."""
    id: UUID
    connector_id: Optional[UUID]
    external_id: str
    external_url: Optional[str] = None
    external_path: Optional[str] = None
    title: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    file_extension: Optional[str] = None
    size_bytes: int = 0
    is_tenant_public: bool = False
    indexing_status: str
    indexing_error: Optional[str] = None
    source_created_at: Optional[datetime] = None
    source_modified_at: Optional[datetime] = None
    indexed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class IndexedDocumentListResponse(BaseModel):
    """Paginated list of indexed documents."""
    items: List[IndexedDocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# =============================================================================
# Onboarding Schemas (for new user flow)
# =============================================================================

class ConnectorOnboardingItem(BaseModel):
    """Connector info for user onboarding."""
    id: UUID
    name: str
    description: Optional[str]
    connector_type: ConnectorType
    auth_type: ConnectorAuthType
    is_authorized: bool  # Has user completed OAuth?
    is_syncing: bool  # Has user enabled sync?
    documents_indexed: int = 0


class OnboardingStatusResponse(BaseModel):
    """User onboarding status response."""
    available_connectors: List[ConnectorOnboardingItem]
    has_completed_onboarding: bool
    total_connectors: int
    connected_count: int
    syncing_count: int
