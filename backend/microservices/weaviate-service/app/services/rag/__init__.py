"""
RAG Pipeline - Indexing & Chunking Components

This module provides the document indexing pipeline:
- Semantic chunking (structure-aware)
- Document intelligence (quality scoring)
- Indexing pipeline (document processing)
- Context enrichment
- RRF fusion utilities

Note: RAG query pipeline (retrieval, caching, monitoring) has been
moved to emma-agent-service.
"""

from .models import (
    QueryAnalysis,
    QueryIntent,
    RetrievedDocument,
    AssembledContext,
    ValidatedResponse,
    RAGResponse,
    DocumentSection,
)
from .rrf_fusion import reciprocal_rank_fusion, multi_list_rrf, RRFResult
from .semantic_chunker import SemanticChunker, DocumentChunk, DocumentType, semantic_chunker
from .document_intelligence import (
    DocumentIntelligence,
    DocumentAnalysis,
    DetectedTable,
    DocumentQuality,
    ContentIssue,
    document_intelligence,
)
from .indexing_pipeline import IndexingPipeline, IndexingResult, indexing_pipeline

__all__ = [
    # Models
    "QueryAnalysis",
    "QueryIntent",
    "RetrievedDocument",
    "AssembledContext",
    "ValidatedResponse",
    "RAGResponse",
    "DocumentSection",
    # RRF Fusion
    "reciprocal_rank_fusion",
    "multi_list_rrf",
    "RRFResult",
    # Semantic Chunking
    "SemanticChunker",
    "DocumentChunk",
    "DocumentType",
    "semantic_chunker",
    # Document Intelligence (Layer 0)
    "DocumentIntelligence",
    "DocumentAnalysis",
    "DetectedTable",
    "DocumentQuality",
    "ContentIssue",
    "document_intelligence",
    # Indexing Pipeline
    "IndexingPipeline",
    "IndexingResult",
    "indexing_pipeline",
]
