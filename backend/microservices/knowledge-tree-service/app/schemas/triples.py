"""Pydantic schemas for TrustGraph triple API."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


class TripleExtractionRequest(BaseModel):
    tenant_id: str
    document_id: str
    collection: str = "default"
    chunks: List[str] = Field(..., min_length=1)
    title: str = ""
    file_path: str = ""
    semantic_type: str = ""
    domain: str = ""


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
    tenant_id: str
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
    tenant_id: str
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
    tenant_id: str
    document_id: str
    collection: str = "default"
    file_path: str = ""
    title: str = ""
    semantic_type: str = ""
    domain: str = ""
    connector_id: Optional[str] = None
    connector_type: Optional[str] = None


class StructuralIndexResponse(BaseModel):
    success: bool
    document_uri: str = ""


# ---------------------------------------------------------------------------
# Reindex
# ---------------------------------------------------------------------------


class ReindexRequest(BaseModel):
    tenant_id: str
    collection: str = "default"


class ReindexResponse(BaseModel):
    success: bool
    documents_processed: int = 0
    triples_created: int = 0
    errors: List[str] = []
