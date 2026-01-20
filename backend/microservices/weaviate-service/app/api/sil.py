"""
Structural Intelligence Layer (SIL) API endpoints.

Provides REST endpoints for:
- Structural queries (answer without RAG)
- Structural metadata retrieval
- Structural indexing
- Graph statistics

These endpoints leverage the SIL to answer questions about document
structure WITHOUT reading document content in most cases.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import logging

from app.core.security import verify_api_key as get_api_key
from app.services.sil import (
    sil_engine,
    structural_extractor,
    structural_collection,
    structural_graph,
    sil_rag_integration,
    StructuralMetadata,
    ReasoningType,
    RAGMode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sil", tags=["structural-intelligence"])


# ============================================================================
# Request/Response Schemas
# ============================================================================

class SILQueryRequest(BaseModel):
    """Request for structural query."""
    query: str = Field(..., description="Natural language query")
    tenant_id: str = Field(..., description="Tenant identifier")
    include_context: bool = Field(True, description="Include structural context in response")


class SILQueryResponse(BaseModel):
    """Response from structural query."""
    original_query: str
    reasoning_type: str = Field(..., description="Type of reasoning: structural, temporal, multihop, focused_rag, full_rag")
    requires_rag: bool = Field(..., description="Whether RAG is needed for full answer")

    # Direct answer (if available)
    answer: Optional[str] = Field(None, description="Direct answer (if structural only)")
    answer_confidence: float = Field(0.0, description="Confidence in direct answer")

    # Structural context
    structural_context: Optional[str] = Field(None, description="Formatted structural context for LLM")

    # Target documents (if focused RAG)
    target_document_ids: List[str] = Field(default_factory=list, description="Documents to query for focused RAG")

    # Performance metrics
    processing_time_ms: float = Field(0.0, description="Processing time in milliseconds")
    tokens_saved: int = Field(0, description="Estimated tokens saved vs full RAG")

    # Metadata
    success: bool = True
    error: Optional[str] = None


class StructuralMetadataRequest(BaseModel):
    """Request to extract/index structural metadata."""
    document_id: str = Field(..., description="Document UUID")
    tenant_id: str = Field(..., description="Tenant identifier")
    file_path: Optional[str] = Field(None, description="File path for structure inference")
    connector_metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata from connector")
    learned_context: Optional[Dict[str, Any]] = Field(None, description="Context from previous learning")
    weaviate_document_id: Optional[str] = Field(None, description="Weaviate document collection UUID")
    connector_id: Optional[str] = Field(None, description="Connector ID")


class StructuralMetadataResponse(BaseModel):
    """Response with structural metadata."""
    document_id: str
    semantic_type: Optional[str] = None
    domain: Optional[str] = None
    folder_path: Optional[str] = None
    importance: float = 0.5
    structural_description: Optional[str] = None
    key_properties: Dict[str, Any] = Field(default_factory=dict)
    folder_semantics: Dict[str, Any] = Field(default_factory=dict)
    indexed_to_weaviate: bool = False
    indexed_to_graph: bool = False
    weaviate_id: Optional[str] = None


class StructuralDocumentResponse(BaseModel):
    """Response with structural document info."""
    id: str
    document_id: str
    tenant_id: str
    semantic_type: Optional[str] = None
    domain: Optional[str] = None
    folder_path: Optional[str] = None
    title: Optional[str] = None
    importance: float = 0.5
    created_at: Optional[str] = None


class GraphStatsResponse(BaseModel):
    """Response with graph statistics."""
    tenant_id: str
    total_documents: int = 0
    total_folders: int = 0
    types_breakdown: Dict[str, int] = Field(default_factory=dict)
    graph_name: str = "knowledge_graph"
    sil_enabled: bool = True
    error: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/query", response_model=SILQueryResponse)
async def structural_query(
    request: SILQueryRequest,
    api_key: str = Depends(get_api_key),
):
    """
    Process a query through the Structural Intelligence Layer.

    This endpoint analyzes the query and determines if it can be answered
    structurally (without reading document content) or if RAG is needed.

    Returns:
    - Direct answer for structural queries (count, exists, location)
    - Structural context for augmented RAG
    - Target documents for focused RAG

    Examples:
    - "¿Cuántos contratos tiene ACME?" → Direct answer from graph
    - "¿Dónde está el contrato master?" → Location from structure
    - "¿Qué cambió esta semana?" → Temporal structural answer
    """
    try:
        # Process through SIL
        result = await sil_engine.process_query(
            query=request.query,
            tenant_id=request.tenant_id,
        )

        # Build response
        response = SILQueryResponse(
            original_query=request.query,
            reasoning_type=result.reasoning_result.type.value,
            requires_rag=result.reasoning_result.requires_rag,
            answer=result.answer,
            answer_confidence=result.answer_confidence,
            structural_context=result.context_for_llm if request.include_context else None,
            target_document_ids=result.reasoning_result.target_document_ids,
            processing_time_ms=result.total_processing_time_ms,
            tokens_saved=result.tokens_saved,
            success=result.success,
            error=result.error,
        )

        logger.info(
            f"SIL query processed: '{request.query[:50]}...' "
            f"→ {result.reasoning_result.type.value} "
            f"(requires_rag={result.reasoning_result.requires_rag}, "
            f"tokens_saved={result.tokens_saved})"
        )

        return response

    except Exception as e:
        logger.error(f"SIL query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index-structural", response_model=StructuralMetadataResponse)
async def index_structural_metadata(
    request: StructuralMetadataRequest,
    api_key: str = Depends(get_api_key),
):
    """
    Extract and index structural metadata for a document.

    This should be called during document indexing to populate
    the structural graph and Weaviate collection.

    The endpoint:
    1. Extracts structural metadata from document info
    2. Indexes to Weaviate StructuralDocument collection
    3. Creates nodes/edges in Apache AGE graph
    """
    try:
        # Extract structural metadata
        metadata = await structural_extractor.extract_structural_metadata(
            document_id=request.document_id,
            file_path=request.file_path or "",
            connector_metadata=request.connector_metadata or {},
            learned_context=request.learned_context or {},
        )

        # Index to Weaviate
        weaviate_id = await structural_collection.index_structural_metadata(
            metadata=metadata,
            document_id=request.document_id,
            weaviate_document_id=request.weaviate_document_id,
            tenant_id=request.tenant_id,
            connector_id=request.connector_id,
        )

        # Index to graph
        graph_success = await structural_graph.add_structural_document(
            document_id=request.document_id,
            tenant_id=request.tenant_id,
            metadata=metadata,
            weaviate_document_id=request.weaviate_document_id,
            connector_id=request.connector_id,
        )

        return StructuralMetadataResponse(
            document_id=request.document_id,
            semantic_type=metadata.semantic_type.value if metadata.semantic_type else None,
            domain=metadata.domain.value if metadata.domain else None,
            folder_path=metadata.folder_path,
            importance=metadata.importance,
            structural_description=metadata.structural_description,
            key_properties=metadata.key_properties,
            folder_semantics=metadata.folder_semantics,
            indexed_to_weaviate=weaviate_id is not None,
            indexed_to_graph=graph_success,
            weaviate_id=weaviate_id,
        )

    except Exception as e:
        logger.error(f"Structural indexing failed for {request.document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/structure/{document_id}", response_model=StructuralDocumentResponse)
async def get_structural_metadata(
    document_id: str,
    tenant_id: str,
    api_key: str = Depends(get_api_key),
):
    """
    Get structural metadata for a specific document.

    Returns the structural information stored in Weaviate,
    including semantic type, domain, folder path, and key properties.
    """
    try:
        result = await structural_collection.get_by_document_id(
            document_id=document_id,
            tenant_id=tenant_id,
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"Document {document_id} not found")

        props = result.get("properties", {})

        return StructuralDocumentResponse(
            id=result.get("id", ""),
            document_id=props.get("document_id", document_id),
            tenant_id=props.get("tenant_id", tenant_id),
            semantic_type=props.get("semantic_type"),
            domain=props.get("domain"),
            folder_path=props.get("folder_path"),
            title=props.get("prop_title"),
            importance=props.get("importance", 0.5),
            created_at=props.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get structural metadata for {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/stats", response_model=GraphStatsResponse)
async def get_graph_stats(
    tenant_id: str,
    api_key: str = Depends(get_api_key),
):
    """
    Get statistics about the structural graph for a tenant.

    Returns:
    - Total documents indexed
    - Total folders tracked
    - Breakdown by semantic type
    """
    try:
        stats = await structural_graph.get_graph_stats(tenant_id=tenant_id)

        return GraphStatsResponse(
            tenant_id=tenant_id,
            total_documents=stats.get("total_documents", 0),
            total_folders=stats.get("total_folders", 0),
            types_breakdown=stats.get("types_breakdown", {}),
            graph_name=stats.get("graph_name", "knowledge_graph"),
            sil_enabled=True,
            error=stats.get("error"),
        )

    except Exception as e:
        logger.error(f"Failed to get graph stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search-structural")
async def search_structural_documents(
    query: str,
    tenant_id: str,
    limit: int = 10,
    semantic_type: Optional[str] = None,
    domain: Optional[str] = None,
    api_key: str = Depends(get_api_key),
):
    """
    Search structural documents by semantic similarity.

    This searches the structural description embeddings, NOT document content.
    Useful for finding documents by their structural characteristics.

    Example: "contracts in the finance department from 2024"
    """
    try:
        filters = {}
        if semantic_type:
            filters["semantic_type"] = semantic_type
        if domain:
            filters["domain"] = domain

        results = await structural_collection.search_structural(
            query=query,
            tenant_id=tenant_id,
            limit=limit,
            filters=filters if filters else None,
        )

        return {
            "query": query,
            "results": results,
            "total": len(results),
        }

    except Exception as e:
        logger.error(f"Structural search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/folder/{folder_path:path}")
async def get_folder_contents(
    folder_path: str,
    tenant_id: str,
    include_subfolders: bool = False,
    api_key: str = Depends(get_api_key),
):
    """
    Get contents of a structural folder.

    Returns all documents contained in the folder,
    optionally including nested subfolders.
    """
    try:
        # Ensure path starts with /
        if not folder_path.startswith("/"):
            folder_path = "/" + folder_path

        contents = await structural_graph.get_folder_contents(
            folder_path=folder_path,
            tenant_id=tenant_id,
            include_subfolders=include_subfolders,
        )

        return {
            "folder_path": folder_path,
            "documents": contents,
            "total": len(contents),
            "include_subfolders": include_subfolders,
        }

    except Exception as e:
        logger.error(f"Failed to get folder contents for {folder_path}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/related/{document_id}")
async def get_related_documents(
    document_id: str,
    tenant_id: str,
    relationship_type: Optional[str] = None,
    max_depth: int = 2,
    api_key: str = Depends(get_api_key),
):
    """
    Get documents related to a given document.

    Traverses the structural graph to find:
    - Sibling documents (same folder)
    - Related documents (explicit relationships)
    - Version chains
    """
    try:
        related = await structural_graph.get_related_documents(
            document_id=document_id,
            tenant_id=tenant_id,
            relationship_type=relationship_type,
            max_depth=max_depth,
        )

        return {
            "document_id": document_id,
            "related_documents": related,
            "total": len(related),
            "max_depth": max_depth,
        }

    except Exception as e:
        logger.error(f"Failed to get related documents for {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/structure/{document_id}")
async def mark_document_removed(
    document_id: str,
    tenant_id: str,
    api_key: str = Depends(get_api_key),
):
    """
    Mark a document as removed in the structural graph.

    This preserves the structural metadata for temporal queries
    while indicating the document is no longer current.
    """
    try:
        # Mark in Weaviate
        weaviate_success = await structural_collection.mark_document_removed(
            document_id=document_id,
            tenant_id=tenant_id,
        )

        # Mark in graph
        graph_success = await structural_graph.mark_document_removed(
            document_id=document_id,
            tenant_id=tenant_id,
        )

        return {
            "document_id": document_id,
            "marked_removed": weaviate_success or graph_success,
            "weaviate_updated": weaviate_success,
            "graph_updated": graph_success,
        }

    except Exception as e:
        logger.error(f"Failed to mark document as removed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
