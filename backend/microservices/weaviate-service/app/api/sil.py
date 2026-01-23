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


class RecentDocument(BaseModel):
    """A recently indexed document."""
    id: str
    title: str
    type: str
    created_at: str


class TopFolder(BaseModel):
    """A folder with document count."""
    path: str
    count: int


class GraphStatsResponse(BaseModel):
    """Response with graph statistics."""
    tenant_id: str
    total_documents: int = 0
    total_folders: int = 0
    total_relationships: int = 0
    types_breakdown: Dict[str, int] = Field(default_factory=dict)
    domains_breakdown: Dict[str, int] = Field(default_factory=dict)
    relationships_breakdown: Dict[str, int] = Field(default_factory=dict)
    top_folders: List[TopFolder] = Field(default_factory=list)
    recent_documents: List[RecentDocument] = Field(default_factory=list)
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
        # Handle both enum and string values for reasoning_type (due to use_enum_values=True)
        reasoning_type_str = (
            result.reasoning_result.type.value
            if hasattr(result.reasoning_result.type, 'value')
            else result.reasoning_result.type
        )
        response = SILQueryResponse(
            original_query=request.query,
            reasoning_type=reasoning_type_str,
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
            f"→ {reasoning_type_str} "
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

        # Get enum values safely (handle both enum and string due to use_enum_values=True)
        semantic_type_str = (
            metadata.semantic_type.value
            if hasattr(metadata.semantic_type, 'value')
            else metadata.semantic_type
        ) if metadata.semantic_type else None
        domain_str = (
            metadata.domain.value
            if hasattr(metadata.domain, 'value')
            else metadata.domain
        ) if metadata.domain else None

        # Convert folder_semantics to dict if it's a Pydantic model
        folder_semantics_dict = (
            metadata.folder_semantics.model_dump()
            if metadata.folder_semantics and hasattr(metadata.folder_semantics, 'model_dump')
            else metadata.folder_semantics or {}
        )

        return StructuralMetadataResponse(
            document_id=request.document_id,
            semantic_type=semantic_type_str,
            domain=domain_str,
            folder_path=metadata.folder_path,
            importance=metadata.importance,
            structural_description=metadata.structural_description,
            key_properties=metadata.key_properties,
            folder_semantics=folder_semantics_dict,
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
    - Total relationships
    - Breakdown by semantic type
    - Breakdown by domain
    - Breakdown by relationship type
    - Top 10 folders by document count
    - 5 most recently indexed documents
    """
    try:
        stats = await structural_graph.get_graph_stats(tenant_id=tenant_id)

        # Convert top_folders to Pydantic models
        top_folders = [
            TopFolder(path=f["path"], count=f["count"])
            for f in stats.get("top_folders", [])
        ]

        # Convert recent_documents to Pydantic models
        recent_documents = [
            RecentDocument(
                id=d["id"],
                title=d["title"],
                type=d["type"],
                created_at=d["created_at"]
            )
            for d in stats.get("recent_documents", [])
        ]

        return GraphStatsResponse(
            tenant_id=tenant_id,
            total_documents=stats.get("total_documents", 0),
            total_folders=stats.get("total_folders", 0),
            total_relationships=stats.get("total_relationships", 0),
            types_breakdown=stats.get("types_breakdown", {}),
            domains_breakdown=stats.get("domains_breakdown", {}),
            relationships_breakdown=stats.get("relationships_breakdown", {}),
            top_folders=top_folders,
            recent_documents=recent_documents,
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


# ============================================================================
# Graph Management Endpoints
# ============================================================================

class ReindexRequest(BaseModel):
    """Request for re-indexing documents."""
    tenant_id: str = Field(..., description="Tenant identifier")
    full_reindex: bool = Field(False, description="If true, clear graph and re-index all. If false, only new documents.")
    limit: Optional[int] = Field(None, description="Maximum documents to process")
    connector_id: Optional[str] = Field(None, description="Filter by connector ID")


class ReindexResponse(BaseModel):
    """Response from re-index operation."""
    success: bool
    total_documents: int = 0
    documents_processed: int = 0
    documents_skipped: int = 0
    errors: int = 0
    message: str = ""


@router.delete("/graph/clear")
async def clear_graph(
    tenant_id: Optional[str] = None,
    api_key: str = Depends(get_api_key),
):
    """
    Clear the structural graph.

    If tenant_id is provided, only clears data for that tenant.
    Otherwise, clears all data (use with caution).
    """
    try:
        # Clear Weaviate structural collection
        weaviate_result = await structural_collection.clear_collection(tenant_id=tenant_id)

        # Clear graph nodes
        graph_result = await structural_graph.clear_graph(tenant_id=tenant_id)

        return {
            "success": True,
            "tenant_id": tenant_id,
            "weaviate_cleared": weaviate_result,
            "graph_cleared": graph_result,
            "message": f"Graph cleared for {'tenant ' + tenant_id if tenant_id else 'all tenants'}",
        }

    except Exception as e:
        logger.error(f"Failed to clear graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/document-ids")
async def get_indexed_document_ids(
    tenant_id: Optional[str] = None,
    limit: int = 10000,
    api_key: str = Depends(get_api_key),
):
    """
    Get list of document IDs already indexed in the graph.

    Useful for incremental indexing to avoid re-processing
    documents that are already in the graph.
    """
    try:
        # Get from graph
        document_ids = await structural_graph.get_document_ids(
            tenant_id=tenant_id,
            limit=limit,
        )

        return {
            "document_ids": document_ids,
            "count": len(document_ids),
            "tenant_id": tenant_id,
        }

    except Exception as e:
        logger.error(f"Failed to get document IDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_documents(
    request: ReindexRequest,
    api_key: str = Depends(get_api_key),
):
    """
    Re-index documents to the structural graph.

    Modes:
    - full_reindex=True: Clear graph and re-index ALL documents
    - full_reindex=False: Only index NEW documents not in graph

    This endpoint triggers the re-indexing process. For large datasets,
    consider using the background task version.
    """
    try:
        from app.services.sil import sil_reindex_service

        result = await sil_reindex_service.reindex_documents(
            tenant_id=request.tenant_id,
            full_reindex=request.full_reindex,
            limit=request.limit,
            connector_id=request.connector_id,
        )

        return ReindexResponse(
            success=result.get("success", False),
            total_documents=result.get("total_documents", 0),
            documents_processed=result.get("documents_processed", 0),
            documents_skipped=result.get("documents_skipped", 0),
            errors=result.get("errors", 0),
            message=result.get("message", "Re-index completed"),
        )

    except ImportError:
        # Service not yet implemented - return helpful error
        raise HTTPException(
            status_code=501,
            detail="SIL reindex service not yet implemented. Use the CLI script: python scripts/index_structural_metadata.py --full-reindex"
        )
    except Exception as e:
        logger.error(f"Failed to reindex documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))
