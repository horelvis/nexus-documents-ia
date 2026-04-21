"""
Unified Document Schema

Normalized document representation for ANY connector source (Alfresco, SharePoint,
Google Drive, S3, etc.). This is the data contract between connectors and the
indexing pipeline.

The UnifiedDocument abstracts away source-specific details and provides a common
structure that can flow through:
1. Connector Adapters (source → UnifiedDocument)
2. UnifiedIndexingService (orchestration)
3. IndexingPipeline (text extraction, chunking, embedding)
4. Weaviate (vector storage)
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from enum import Enum


class IndexingStatus(str, Enum):
    """Status of document in the indexing pipeline."""
    PENDING = "pending"           # Discovered but not yet processed
    DOWNLOADING = "downloading"   # Content being downloaded from source
    PROCESSING = "processing"     # Going through indexing pipeline
    INDEXED = "indexed"           # Successfully indexed in Weaviate
    FAILED = "failed"             # Processing failed
    ORPHANED = "orphaned"         # Connector deleted, document still exists


class ConnectorType(str, Enum):
    """Supported connector types."""
    ALFRESCO = "alfresco"
    SHAREPOINT = "sharepoint"
    ONEDRIVE = "onedrive"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_WORKSPACE = "google_workspace"
    S3 = "s3"
    AZURE_BLOB = "azure_blob"
    NETWORK_SHARE = "network_share"
    DROPBOX = "dropbox"
    BOX = "box"
    DATABASE = "database"  # Generic database BLOB storage
    DIRECT_UPLOAD = "direct_upload"  # Manual uploads (existing flow)


@dataclass
class UnifiedDocument:
    """
    Normalized document from ANY source.

    This is the core data structure that flows through the connector ingestion
    system. Every connector adapter produces UnifiedDocuments, and the
    UnifiedIndexingService consumes them.

    Key design decisions:
    - All IDs are UUIDs for consistency with PostgreSQL
    - `file_bytes` is Optional - allows for lazy loading (discovery vs download)
    - `content_hash` enables deduplication across sources
    - ACL is role-based: each document carries `roles=["EVERYONE"]` (default)
      or a list of KeyCloak roles such as `["LEGAL", "HR"]`.

    Example Usage:
        # From Alfresco adapter
        doc = UnifiedDocument(
            document_id=uuid4(),
            connector_id=connector.id,
            connector_type=ConnectorType.ALFRESCO,
            external_id="node-uuid-123",
            external_url="https://alfresco/share/...",
            filename="contract.pdf",
            mime_type="application/pdf",
            owner_id=admin.id,
            roles=["EVERYONE"],
        )
    """

    # === Identification ===
    document_id: UUID                    # Internal PostgreSQL UUID
    connector_id: UUID                   # Reference to connectors table
    connector_type: ConnectorType        # Type of connector
    external_id: str                     # ID in source system (node_id, driveItem id, etc.)
    external_url: Optional[str] = None   # URL to open document in source
    external_path: Optional[str] = None  # Path in source (/Documents/Project/file.docx)

    # === Content ===
    filename: str = ""
    file_bytes: Optional[bytes] = None   # Content (None until downloaded)
    mime_type: Optional[str] = None
    file_extension: Optional[str] = None
    size_bytes: int = 0
    content_hash: Optional[str] = None   # SHA-256 for deduplication

    # === Metadata ===
    title: str = ""
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    custom_metadata: Dict[str, Any] = field(default_factory=dict)

    # === Source Timestamps ===
    source_created_at: Optional[datetime] = None
    source_modified_at: Optional[datetime] = None

    # === Ownership and ACL ===
    owner_id: UUID = field(default_factory=lambda: UUID(int=0))
    roles: List[str] = field(default_factory=lambda: ["EVERYONE"])

    # === Processing State ===
    indexing_status: IndexingStatus = IndexingStatus.PENDING
    indexing_error: Optional[str] = None
    weaviate_id: Optional[UUID] = None
    weaviate_collection: Optional[str] = None
    indexed_at: Optional[datetime] = None
    chunk_count: int = 0
    entities_count: int = 0

    def has_content(self) -> bool:
        """Check if document content has been downloaded."""
        return self.file_bytes is not None and len(self.file_bytes) > 0

    def compute_hash(self) -> Optional[str]:
        """Compute SHA-256 hash of content for deduplication."""
        if not self.has_content():
            return None
        import hashlib
        self.content_hash = hashlib.sha256(self.file_bytes).hexdigest()
        return self.content_hash

    def extract_extension(self) -> Optional[str]:
        """Extract file extension from filename."""
        if self.filename and "." in self.filename:
            self.file_extension = self.filename.rsplit(".", 1)[-1].lower()
            return self.file_extension
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (excludes file_bytes to avoid large payloads)."""
        return {
            "document_id": str(self.document_id),
            "connector_id": str(self.connector_id),
            "connector_type": self.connector_type.value,
            "external_id": self.external_id,
            "external_url": self.external_url,
            "external_path": self.external_path,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "file_extension": self.file_extension,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "custom_metadata": self.custom_metadata,
            "source_created_at": self.source_created_at.isoformat() if self.source_created_at else None,
            "source_modified_at": self.source_modified_at.isoformat() if self.source_modified_at else None,
            "owner_id": str(self.owner_id),
            "roles": self.roles,
            "indexing_status": self.indexing_status.value,
            "indexing_error": self.indexing_error,
            "weaviate_id": str(self.weaviate_id) if self.weaviate_id else None,
            "weaviate_collection": self.weaviate_collection,
            "indexed_at": self.indexed_at.isoformat() if self.indexed_at else None,
            "chunk_count": self.chunk_count,
            "entities_count": self.entities_count,
            "has_content": self.has_content(),
        }


@dataclass
class HealthCheckResult:
    """Result of connector health check."""
    is_healthy: bool
    status: str                          # healthy, degraded, unhealthy
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.now)
    response_time_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_healthy": self.is_healthy,
            "status": self.status,
            "message": self.message,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
            "response_time_ms": self.response_time_ms,
        }


@dataclass
class SyncResult:
    """Result of connector sync operation."""
    success: bool
    items_found: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_deleted: int = 0
    items_failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    sync_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "items_found": self.items_found,
            "items_new": self.items_new,
            "items_updated": self.items_updated,
            "items_deleted": self.items_deleted,
            "items_failed": self.items_failed,
            "errors": self.errors,
            "sync_duration_ms": self.sync_duration_ms,
        }


@dataclass
class IndexingBatchResult:
    """Result of indexing a batch of documents."""
    total_documents: int = 0
    documents_indexed: int = 0
    documents_failed: int = 0
    documents_skipped: int = 0           # Already indexed or duplicate
    errors: List[Dict[str, Any]] = field(default_factory=list)
    batch_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_documents": self.total_documents,
            "documents_indexed": self.documents_indexed,
            "documents_failed": self.documents_failed,
            "documents_skipped": self.documents_skipped,
            "errors": self.errors,
            "batch_duration_ms": self.batch_duration_ms,
        }
