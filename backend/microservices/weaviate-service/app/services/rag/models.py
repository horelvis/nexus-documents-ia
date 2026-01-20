"""
Data models for the RAG Pipeline

These models define the data structures passed between the 5 layers
of the RAG pipeline.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class QueryIntent(str, Enum):
    """Classification of user query intent"""
    SEARCH = "search"           # Find specific information
    ANALYZE = "analyze"         # Deep analysis of content
    COMPARE = "compare"         # Compare multiple documents/concepts
    SUMMARIZE = "summarize"     # Create summary
    EXTRACT = "extract"         # Extract specific data points
    EXPLAIN = "explain"         # Explain a concept
    LIST = "list"               # List items/entities
    UNKNOWN = "unknown"         # Could not classify


@dataclass
class QueryAnalysis:
    """Result of Layer 1: Query Intelligence analysis"""
    original_query: str
    expanded_query: str                     # Query with expanded abbreviations
    query_variations: List[str]             # Alternative phrasings
    intent: QueryIntent                     # Classified intent
    extracted_filters: Dict[str, Any]       # Implicit filters (date, type, etc.)
    key_terms: List[str]                    # Important terms for matching
    language: str = "es"                    # Detected language
    embeddings: Optional[List[float]] = None  # Query embeddings
    graph_expansion: Optional[Dict[str, Any]] = None  # Graph expansion metadata

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "original_query": self.original_query,
            "expanded_query": self.expanded_query,
            "query_variations": self.query_variations,
            "intent": self.intent.value,
            "extracted_filters": self.extracted_filters,
            "key_terms": self.key_terms,
            "language": self.language,
        }
        if self.graph_expansion:
            result["graph_expansion"] = self.graph_expansion
        return result


@dataclass
class RetrievedDocument:
    """A document retrieved from the vector store"""
    id: str
    title: str
    content: str
    score: float                            # Combined relevance score
    vector_score: Optional[float] = None    # Vector similarity score
    bm25_score: Optional[float] = None      # BM25 keyword score
    rerank_score: Optional[float] = None    # Cross-encoder rerank score
    rrf_score: Optional[float] = None       # Reciprocal Rank Fusion score
    document_type: Optional[str] = None
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_index: Optional[int] = None       # Position in original document
    total_chunks: Optional[int] = None      # Total chunks in document
    # Soft selection fields (populated by SoftSelector)
    soft_weight: Optional[float] = None     # Softmax weight [0,1]
    cluster_id: Optional[int] = None        # K-means cluster assignment
    allocated_tokens: Optional[int] = None  # Proportional token budget

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "title": self.title,
            "content": self.content[:500] + "..." if len(self.content) > 500 else self.content,
            "score": self.score,
            "vector_score": self.vector_score,
            "bm25_score": self.bm25_score,
            "rerank_score": self.rerank_score,
            "rrf_score": self.rrf_score,
            "document_type": self.document_type,
            "metadata": self.metadata,
        }
        # Include soft selection fields if present
        if self.soft_weight is not None:
            result["soft_weight"] = self.soft_weight
        if self.cluster_id is not None:
            result["cluster_id"] = self.cluster_id
        if self.allocated_tokens is not None:
            result["allocated_tokens"] = self.allocated_tokens
        return result


@dataclass
class DocumentSection:
    """A section within a document (for Document Intelligence)"""
    title: str
    content: str
    section_type: str                       # intro, methodology, results, conclusion, etc.
    importance_score: float                 # 0.0 to 1.0
    entities: List[Dict[str, Any]]          # Extracted entities
    start_char: int
    end_char: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "section_type": self.section_type,
            "importance_score": self.importance_score,
            "entities": self.entities,
            "content_length": len(self.content),
        }


@dataclass
class AssembledContext:
    """Result of Layer 3: Context Assembly"""
    formatted_context: str                  # Final context string for LLM
    documents: List[RetrievedDocument]      # Documents included in context
    total_tokens: int                       # Estimated token count
    max_tokens: int                         # Token budget
    query_analysis: QueryAnalysis           # Original query analysis
    document_headers: List[str]             # Headers for each document
    truncated: bool = False                 # Whether context was truncated
    # Soft selection metadata (for debugging/metrics)
    selection_metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "total_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "documents_count": len(self.documents),
            "truncated": self.truncated,
            "document_ids": [d.id for d in self.documents],
        }
        # Include selection metrics if available
        if self.selection_metadata:
            result["selection_metadata"] = {
                "diversity_score": self.selection_metadata.get("diversity_score"),
                "coverage_score": self.selection_metadata.get("coverage_score"),
                "dropped_by_weight": self.selection_metadata.get("dropped_by_weight"),
                "dropped_by_cap": self.selection_metadata.get("dropped_by_cap"),
            }
        return result


@dataclass
class ClaimValidation:
    """Validation result for a single claim"""
    claim: str
    is_supported: bool
    supporting_document_ids: List[str]
    confidence: float                       # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim": self.claim,
            "is_supported": self.is_supported,
            "supporting_document_ids": self.supporting_document_ids,
            "confidence": self.confidence,
        }


@dataclass
class ValidatedResponse:
    """Result of Layer 4: Validated Generation"""
    answer: str                             # Generated answer
    claims: List[str]                       # Extracted factual claims
    validations: List[ClaimValidation]      # Validation results
    confidence_score: float                 # Overall confidence (0.0 to 1.0)
    citations: Dict[str, str]               # Citation markers to document IDs
    has_unsupported_claims: bool            # Whether any claims are unsupported

    def to_dict(self) -> Dict[str, Any]:
        return {
            "answer": self.answer,
            "claims_count": len(self.claims),
            "validated_claims": sum(1 for v in self.validations if v.is_supported),
            "confidence_score": self.confidence_score,
            "has_unsupported_claims": self.has_unsupported_claims,
            "citations": self.citations,
        }


@dataclass
class RAGResponse:
    """Final response from the RAG Pipeline"""
    query: str
    answer: str
    confidence_score: float
    sources: List[RetrievedDocument]
    query_analysis: QueryAnalysis
    context_info: Dict[str, Any]
    validation_info: Optional[Dict[str, Any]]
    execution_time_ms: float
    iterations: int = 1
    success: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "query": self.query,
            "answer": self.answer,
            "confidence_score": self.confidence_score,
            "sources": [s.to_dict() for s in self.sources],
            "query_analysis": self.query_analysis.to_dict(),
            "context_info": self.context_info,
            "validation_info": self.validation_info,
            "execution_time_ms": self.execution_time_ms,
            "iterations": self.iterations,
            "error": self.error,
        }

    def to_cag_response(self) -> Dict[str, Any]:
        """Convert to CAG API response format for backwards compatibility"""
        return {
            "success": self.success,
            "answer": self.answer,
            "quality_score": self.confidence_score,
            "iterations": self.iterations,
            "gaps_identified": 0,
            "context_chunks_used": len(self.sources),
            "execution_time": self.execution_time_ms / 1000,
            "metadata": {
                "decision_path": [f"rag_layer_{i}" for i in range(5)],
                "tools_used": ["query_intelligence", "retriever", "context_assembler", "generator"],
                "query_analysis": self.query_analysis.to_dict(),
                "sources": [{"id": s.id, "title": s.title, "score": s.score} for s in self.sources],
            },
            "error": self.error,
        }
