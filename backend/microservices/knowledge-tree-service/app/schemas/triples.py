"""Pydantic schemas for TrustGraph triple API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TripleExtractionRequest(BaseModel):
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    document_id: str
    collection: str = "default"
    chunks: List[str] = Field(..., min_length=1)
    title: str = ""
    file_path: str = ""
    semantic_type: str = ""


class TripleExtractionResponse(BaseModel):
    success: bool
    document_uri: str = ""
    triples_created: int = 0
    contradictions_found: int = 0
    extraction_time_ms: int = 0
    errors: List[str] = []


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


class TripleQueryRequest(BaseModel):
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    subject_uri: Optional[str] = None
    predicate_uri: Optional[str] = None
    object_value: Optional[str] = None
    object_is_node: bool = False
    collection: Optional[str] = None
    limit: int = Field(default=100, ge=1, le=1000)


class TripleResult(BaseModel):
    subject: str
    predicate: str
    object: str
    object_type: str  # "node" or "literal"
    extraction_method: Optional[str] = None
    source_chunk: Optional[str] = None


class TripleQueryResponse(BaseModel):
    triples: List[TripleResult]
    count: int


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


class ContextRequest(BaseModel):
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)


class ContextResponse(BaseModel):
    success: bool
    context_for_llm: str
    metadata: Dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class StatsResponse(BaseModel):
    nodes: int
    literals: int
    rels: int
    contradictions: int = 0
    entity_types: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Structural indexing
# ---------------------------------------------------------------------------


class StructuralIndexRequest(BaseModel):
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    document_id: str
    collection: str = "default"
    file_path: str = ""
    title: str = ""
    semantic_type: str = ""
    connector_id: Optional[str] = None
    connector_type: Optional[str] = None


class StructuralIndexResponse(BaseModel):
    success: bool
    document_uri: str = ""


# ---------------------------------------------------------------------------
# Batch neighbors (BFS subgraph traversal)
# ---------------------------------------------------------------------------


class BatchNeighborsRequest(BaseModel):
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    seed_uris: List[str] = Field(..., min_length=1)
    collection: Optional[str] = None
    max_hops: int = Field(default=2, ge=1, le=5)
    max_edges: int = Field(default=150, ge=1, le=500)
    exclude_predicates: List[str] = Field(default_factory=list)


class BatchNeighborsResponse(BaseModel):
    edges: List[TripleResult]
    entities_visited: int
    hops_used: int
    count: int


# ---------------------------------------------------------------------------
# Trace sources (provenance resolution)
# ---------------------------------------------------------------------------


class TraceSourcesRequest(BaseModel):
    edges: List[Dict[str, str]]
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    collection: str = "default"


class TraceSourceResult(BaseModel):
    subject_uri: str
    predicate_uri: str
    object_uri: str
    document_id: str
    chunk_offset: int = 0
    chunk_uri: Optional[str] = None
    confidence: Optional[float] = None
    source_chunk: str = ""


class TraceSourcesResponse(BaseModel):
    sources: List[TraceSourceResult]


# ---------------------------------------------------------------------------
# Reindex
# ---------------------------------------------------------------------------


class ReindexRequest(BaseModel):
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    collection: str = "default"


class ReindexResponse(BaseModel):
    success: bool
    documents_processed: int = 0
    triples_created: int = 0
    errors: List[str] = []


# ---------------------------------------------------------------------------
# Template execution
# ---------------------------------------------------------------------------


class TemplateRequest(BaseModel):
    """Execute a named Cypher template."""
    user_roles: List[str] = Field(default_factory=list)
    user_id: Optional[str] = None
    template_name: str
    collection: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class TemplateListItem(BaseModel):
    name: str
    description: str
    hops: int


class TemplateResponse(BaseModel):
    results: List[Dict[str, Any]]
    template: str
    hops: int
    count: int
