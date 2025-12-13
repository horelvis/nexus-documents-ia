"""Pydantic schemas for Elasticsearch operations"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel


# ========================================
# ACL-RELATED SCHEMAS
# ========================================

class DocumentACLData(BaseModel):
    """ACL data for a document"""
    acl_user_ids: List[str] = []
    acl_role_ids: List[str] = []
    acl_everyone: bool = False
    created_by: Optional[str] = None


class DocumentACLUpdateRequest(BaseModel):
    """Request to update document ACL in Elasticsearch"""
    collection_name: str
    acl_user_ids: List[str] = []
    acl_role_ids: List[str] = []
    acl_everyone: bool = False
    created_by: Optional[str] = None


class SearchUserContext(BaseModel):
    """User context for ACL-filtered searches"""
    user_id: str
    role_ids: List[str] = []
    is_admin: bool = False


# ========================================
# DOCUMENT INDEXING SCHEMAS
# ========================================

class DocumentIndexRequest(BaseModel):
    """Request to index a document"""
    doc_id: str
    title: str
    content: str
    description: Optional[str] = None
    content_vector: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    # ACL fields
    created_by: Optional[str] = None
    acl_user_ids: Optional[List[str]] = None
    acl_role_ids: Optional[List[str]] = None
    acl_everyone: bool = False


class SearchFilters(BaseModel):
    """Filters for search operations"""
    file_type: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None

class HybridSearchRequest(BaseModel):
    """Request for hybrid search"""
    query: str
    limit: int = 10
    filters: Optional[SearchFilters] = None
    boost_semantic: float = 1.0
    boost_keyword: float = 1.0
    # ACL-based filtering (optional for backward compatibility)
    user_context: Optional[SearchUserContext] = None

class SemanticSearchRequest(BaseModel):
    """Request for semantic search"""
    query_vector: List[float]
    limit: int = 10
    filters: Optional[SearchFilters] = None
    min_score: float = 0.7
    # ACL-based filtering (optional for backward compatibility)
    user_context: Optional[SearchUserContext] = None

class SearchResult(BaseModel):
    """Individual search result"""
    document: Dict[str, Any]
    score: float
    matches: List[Dict[str, Any]]

class SearchResponse(BaseModel):
    """Response for search operations"""
    results: List[SearchResult]
    total: int
    took_ms: int

class AnalyticsRequest(BaseModel):
    """Request for analytics"""
    date_from: Optional[str] = None
    date_to: Optional[str] = None

class FacetRequest(BaseModel):
    """Request for faceting"""
    query: Optional[str] = None
    filters: Optional[SearchFilters] = None
    facet_fields: List[str] = ["file_type", "category", "tags"]
    max_facet_values: int = 10

class FacetBucket(BaseModel):
    """Individual facet bucket"""
    key: str
    count: int
    selected: bool = False

class FacetResult(BaseModel):
    """Result for a single facet field"""
    field: str
    buckets: List[FacetBucket]
    total_count: int

class FacetResponse(BaseModel):
    """Response for faceting"""
    facets: List[FacetResult]
    total_documents: int

class AnalyticsResponse(BaseModel):
    """Response for analytics"""
    total_documents: int
    by_file_type: List[Dict[str, Any]]
    by_category: List[Dict[str, Any]]
    popular_tags: List[Dict[str, Any]]
    documents_timeline: List[Dict[str, Any]]

class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    elasticsearch_connected: bool
    index_count: int
    version: Optional[str] = None