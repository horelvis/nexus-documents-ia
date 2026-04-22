"""Pydantic schemas for Weaviate operations"""
import json
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional
from datetime import datetime


class DocumentCreate(BaseModel):
    """Schema for creating documents in Weaviate"""
    id: Optional[str] = None
    title: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    document_type: Optional[str] = "document"
    tags: List[str] = Field(default_factory=list)
    # Channel properties for RAG access control
    channel_id: Optional[str] = Field(default="", description="Information channel ID (empty for regular uploads)")
    channel_visibility: Optional[str] = Field(default="", description="personal, tenant, or empty")
    owner_user_id: Optional[str] = Field(default="", description="User ID who owns this document")
    source_type: Optional[str] = Field(default="upload", description="upload, gmail, google_drive, external_db")
    external_id: Optional[str] = Field(default="", description="External system identifier")
    # Folder hierarchy for path-based filtering in RAG
    folder_path: Optional[str] = Field(default="", description="Full folder path (e.g., /Contracts/ACME/2024)")
    folder_hierarchy: List[str] = Field(default_factory=list, description="Array of folder levels for filtering")
    connector_id: Optional[str] = Field(default="", description="Connector that indexed this document")
    # Enrichment properties for multi-signal retrieval
    semantic_type: Optional[str] = Field(default="", description="Semantic document type (e.g., factura, contrato)")
    quality_score: Optional[float] = Field(default=0.0, description="Quality score 0.0-1.0")
    associated_person: Optional[str] = Field(default="", description="Associated person name")
    # ACL properties for document-level access control
    acl_user_ids: List[str] = Field(default_factory=list, description="User UUIDs with explicit access")
    acl_role_ids: List[str] = Field(default_factory=list, description="Role UUIDs with access")
    acl_everyone: bool = Field(default=True, description="If True, all tenant users can access")

    @field_validator("acl_user_ids", "acl_role_ids", mode="before")
    @classmethod
    def _coerce_str_to_list(cls, v):
        """Handle JSON-stringified lists from JSONB columns (e.g. '[]' → [])."""
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                pass
            return []
        return v

    # Chunks for batch insertion
    chunks: List[Dict[str, Any]] = Field(default_factory=list, description="Document chunks with content and metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Sample Document",
                "content": "This is a sample document content for testing.",
                "metadata": {"author": "John Doe", "category": "test"},
                "document_type": "pdf",
                "tags": ["sample", "test"],
                "channel_id": "",
                "source_type": "upload",
                "folder_path": "/Contracts/ACME",
                "folder_hierarchy": ["/", "/Contracts", "/Contracts/ACME"]
            }
        }


class DocumentResponse(BaseModel):
    """Schema for document response from Weaviate"""
    id: str
    title: str
    content: str
    metadata: Dict[str, Any]
    document_type: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    vector_id: Optional[str] = None
    similarity_score: Optional[float] = None
    # Folder hierarchy for path-based filtering
    folder_path: Optional[str] = None
    folder_hierarchy: List[str] = Field(default_factory=list)
    connector_id: Optional[str] = None
    # Chunk-level source attribution (for page/excerpt in citations)
    chunk_index: Optional[int] = None
    page_number: Optional[int] = None
    document_id: Optional[str] = None  # parent document UUID
    # Enrichment properties for multi-signal retrieval
    semantic_type: Optional[str] = None
    quality_score: Optional[float] = None
    associated_person: Optional[str] = None


class SearchRequest(BaseModel):
    """Schema for search requests with ACL support"""
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0, description="Number of results to skip (for pagination)")
    user_id: Optional[str] = Field(default=None, description="User ID for channel and ACL access filtering")
    user_roles: List[str] = Field(default_factory=list, description="User roles for ACL filtering")
    is_admin: bool = Field(default=False, description="Admin users bypass ACL checks")
    filters: Optional[Dict[str, Any]] = None
    search_type: str = Field(default="hybrid", pattern="^(vector|keyword|hybrid)$")
    alpha: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Hybrid search alpha: 0=keyword, 1=vector. Defaults to 0.7 if not set.")
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    # Channel filtering options
    include_channels: bool = Field(default=True, description="Include documents from information channels")
    channel_ids: Optional[List[str]] = Field(default=None, description="Filter to specific channel IDs")
    # Folder hierarchy filtering for path-based RAG queries
    folder_path: Optional[str] = Field(default=None, description="Filter to exact folder path (e.g., /Contracts/ACME)")
    folder_hierarchy_contains: Optional[str] = Field(default=None, description="Filter to documents in folder or any subfolder")
    # Enrichment filters for multi-signal retrieval
    semantic_type_filter: Optional[str] = Field(default=None, description="Filter by semantic type (e.g., factura, contrato)")
    person_filter: Optional[str] = Field(default=None, description="Filter by associated person name")
    min_quality: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Minimum quality score threshold")
    # Temporal filters
    date_from: Optional[str] = Field(default=None, description="Filter docs created on or after this date (ISO 8601, e.g. '2026-02-01')")
    date_to: Optional[str] = Field(default=None, description="Filter docs created on or before this date (ISO 8601, e.g. '2026-03-04')")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning algorithms",
                "limit": 10,
                "user_id": "user-456",
                "user_roles": ["LEGAL", "ANALYST"],
                "is_admin": False,
                "search_type": "hybrid",
                "min_similarity": 0.5,
                "include_channels": True,
                "folder_path": "/Contracts/ACME",
                "folder_hierarchy_contains": "/Contracts"
            }
        }


class SearchResponse(BaseModel):
    """Schema for search response"""
    query: str
    results: List[DocumentResponse]
    total_results: int
    search_time_ms: int
    search_type: str


class VectorQuery(BaseModel):
    """Schema for raw vector queries"""
    vector: List[float]
    limit: int = Field(default=10, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None
    include_vector: bool = False


class CollectionInfo(BaseModel):
    """Schema for collection information"""
    name: str
    description: Optional[str] = None
    objects_count: int
    properties: List[Dict[str, Any]]
    vectorizer: Optional[str] = None
    created_at: datetime
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Nouxcube_documents",
                "description": "Documents collection",
                "objects_count": 150,
                "properties": [
                    {"name": "title", "dataType": ["text"]},
                    {"name": "content", "dataType": ["text"]},
                    {"name": "metadata", "dataType": ["object"]}
                ],
                "vectorizer": "text2vec-transformers"
            }
        }