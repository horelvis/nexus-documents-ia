from pydantic import BaseModel
from typing import Optional, Any


# --- Embedding ---

class EmbedRequest(BaseModel):
    text: Optional[str] = None
    texts: Optional[list[str]] = None
    task: str = "retrieval.passage"


class EmbedSingleResponse(BaseModel):
    embedding: list[float]
    dimensions: int
    model: str
    provider: str


class EmbedBatchResponse(BaseModel):
    embeddings: list[list[float]]
    dimensions: int
    model: str
    provider: str


# --- Extraction ---

class ExtractedChunkResponse(BaseModel):
    """Pre-built chunk from a page-aware extractor (Docling HybridChunker)."""
    text: str
    chunk_index: int
    page_start: int = 0
    page_end: int = 0
    headings: list[str] = []


class ExtractResponse(BaseModel):
    text: str
    language: str
    metadata: dict[str, Any] = {}
    # When the extractor exposes its own page-aware chunker, the chunks
    # ride alongside the flat text. Consumers (weaviate-service) use them
    # directly so per-chunk page numbers survive into Weaviate.
    chunks: list[ExtractedChunkResponse] | None = None


# --- Entities ---

class EntityResponse(BaseModel):
    type: str
    value: str
    provider: str
    confidence: float = 1.0
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None
    attributes: dict[str, Any] = {}


class EntitiesRequest(BaseModel):
    text: str
    language: str = "es"
    document_type: str = "general"


class EntitiesResponse(BaseModel):
    entities: list[EntityResponse]


# --- Classification ---

class ClassifyRequest(BaseModel):
    text: str
    filename: str = ""


class ClassifyResponse(BaseModel):
    document_type: str
    confidence: float
    provider: str = ""


# --- Process (combined pipeline) ---

class ProcessOptions(BaseModel):
    extract: bool = True
    embed: bool = True
    entities: bool = True
    embedding_task: str = "retrieval.passage"
    language: str = ""


class ProcessResponse(BaseModel):
    text: str
    language: str
    metadata: dict[str, Any] = {}
    vector: Optional[list[float]] = None
    entities: list[EntityResponse] = []
    processing_time_ms: int = 0


# --- Health ---

class ProviderStatus(BaseModel):
    name: str
    available: bool
    model: Optional[str] = None
    device: Optional[str] = None
    dimensions: Optional[int] = None
    url: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    providers: dict[str, list[ProviderStatus]]
