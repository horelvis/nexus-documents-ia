"""Pydantic schemas for Weaviate operations"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class DocumentCreate(BaseModel):
    """Schema for creating documents in Weaviate"""
    id: Optional[str] = None
    title: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    document_type: Optional[str] = "document"
    tags: List[str] = Field(default_factory=list)
    # Channel properties for RAG access control
    channel_id: Optional[str] = Field(default="", description="Information channel ID (empty for regular uploads)")
    channel_visibility: Optional[str] = Field(default="", description="personal, tenant, or empty")
    owner_user_id: Optional[str] = Field(default="", description="User ID who owns this document")
    source_type: Optional[str] = Field(default="upload", description="upload, gmail, google_drive, external_db")
    external_id: Optional[str] = Field(default="", description="External system identifier")

    class Config:
        json_schema_extra = {
            "example": {
                "title": "Sample Document",
                "content": "This is a sample document content for testing.",
                "metadata": {"author": "John Doe", "category": "test"},
                "tenant_id": "tenant-123",
                "document_type": "pdf",
                "tags": ["sample", "test"],
                "channel_id": "",
                "source_type": "upload"
            }
        }


class DocumentResponse(BaseModel):
    """Schema for document response from Weaviate"""
    id: str
    title: str
    content: str
    metadata: Dict[str, Any]
    tenant_id: str
    document_type: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    vector_id: Optional[str] = None
    similarity_score: Optional[float] = None


class SearchRequest(BaseModel):
    """Schema for search requests"""
    query: str
    limit: int = Field(default=10, ge=1, le=100)
    tenant_id: str
    user_id: Optional[str] = Field(default=None, description="User ID for channel and ACL access filtering")
    user_role_ids: Optional[List[str]] = Field(default=None, description="User's role IDs for ACL filtering")
    filters: Optional[Dict[str, Any]] = None
    search_type: str = Field(default="hybrid", pattern="^(vector|keyword|hybrid)$")
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    # Channel filtering options
    include_channels: bool = Field(default=True, description="Include documents from information channels")
    channel_ids: Optional[List[str]] = Field(default=None, description="Filter to specific channel IDs")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning algorithms",
                "limit": 10,
                "tenant_id": "tenant-123",
                "user_id": "user-456",
                "user_role_ids": ["role-admin", "role-analyst"],
                "search_type": "hybrid",
                "min_similarity": 0.5,
                "include_channels": True
            }
        }


class SearchResponse(BaseModel):
    """Schema for search response"""
    query: str
    results: List[DocumentResponse]
    total_results: int
    search_time_ms: int
    search_type: str
    tenant_id: str


class VectorQuery(BaseModel):
    """Schema for raw vector queries"""
    vector: List[float]
    limit: int = Field(default=10, ge=1, le=100)
    tenant_id: str
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
    tenant_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "nexus_tenant123_documents",
                "description": "Documents collection for tenant 123",
                "objects_count": 150,
                "properties": [
                    {"name": "title", "dataType": ["text"]},
                    {"name": "content", "dataType": ["text"]},
                    {"name": "metadata", "dataType": ["object"]}
                ],
                "vectorizer": "text2vec-transformers",
                "tenant_id": "tenant-123"
            }
        }