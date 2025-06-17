"""
Pydantic schemas for LangGraph API endpoints
"""
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from enum import Enum


class GraphType(str, Enum):
    """Available graph types"""
    TAG_GENERATION = "tag_generation"
    DOCUMENT_PROCESSING = "document_processing"
    RAG = "rag"


class TagType(str, Enum):
    """Tag generation types"""
    GENERAL = "general"
    TECHNICAL = "technical"
    BUSINESS = "business"


# Base schemas
class GraphRunRequest(BaseModel):
    """Request to run a graph"""
    graph_type: GraphType
    input_data: Dict[str, Any]
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    thread_id: Optional[str] = None
    checkpoint_id: Optional[str] = None


class GraphRunResponse(BaseModel):
    """Response from graph execution"""
    run_id: str
    graph_type: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float
    iterations: int


# Tag generation schemas
class TagGenerationRequest(BaseModel):
    """Request for tag generation"""
    text: str = Field(..., min_length=10, max_length=50000)
    max_tags: int = Field(default=5, ge=1, le=20)
    tag_type: TagType = Field(default=TagType.GENERAL)


class TagGenerationResponse(BaseModel):
    """Response from tag generation"""
    tags: List[str]
    confidence_scores: Dict[str, float]
    reasoning: Optional[str] = None


# Document processing schemas
class DocumentProcessingRequest(BaseModel):
    """Request for document processing"""
    document_id: str
    content: str = Field(..., min_length=1)
    filename: str
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class DocumentChunk(BaseModel):
    """Document chunk information"""
    chunk_id: str
    document_id: str
    chunk_index: int
    content: str
    metadata: Dict[str, Any]


class DocumentProcessingResponse(BaseModel):
    """Response from document processing"""
    document_id: str
    chunks: List[DocumentChunk]
    embeddings_generated: bool
    metadata: Dict[str, Any]
    quality_score: Optional[float] = None
    processing_notes: List[str]


# RAG schemas
class RAGQueryRequest(BaseModel):
    """Request for RAG query"""
    query: str = Field(..., min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=20)
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    include_sources: bool = Field(default=True)


class RAGSource(BaseModel):
    """Source document information"""
    content: str
    metadata: Dict[str, Any]
    score: float


class RAGQueryResponse(BaseModel):
    """Response from RAG query"""
    answer: str
    sources: Optional[List[RAGSource]] = None
    confidence_score: float
    search_results: Optional[List[Dict[str, Any]]] = None
    refinement_notes: Optional[str] = None


# Graph management schemas
class GraphTypeResponse(BaseModel):
    """List of available graph types"""
    graph_types: List[str]
    count: int


class GraphNode(BaseModel):
    """Information about a graph node"""
    id: str
    name: str
    type: str
    description: Optional[str] = None
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class GraphStructure(BaseModel):
    """Structure of a graph"""
    graph_type: str
    nodes: List[GraphNode]
    edges: List[Dict[str, str]]
    entry_point: str
    description: Optional[str] = None