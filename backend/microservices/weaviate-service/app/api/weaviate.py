"""Weaviate API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging

from app.core.security import verify_api_key
from app.services.weaviate_service import weaviate_service
from app.schemas.weaviate import (
    DocumentCreate, DocumentResponse, SearchRequest, SearchResponse,
    CollectionInfo, VectorQuery
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================================
# Request Models
# ========================================

class DocumentACLUpdate(BaseModel):
    """Schema for updating document ACL properties"""
    collection_name: str
    acl_user_ids: List[str] = []
    acl_role_ids: List[str] = []
    acl_everyone: bool = False

@router.post("/collections/{collection_name}/documents", response_model=DocumentResponse)
async def add_document(
    collection_name: str,
    document: DocumentCreate,
    _: bool = Depends(verify_api_key)
):
    """Add a document to Weaviate collection"""
    try:
        result = await weaviate_service.add_document(collection_name, document)
        return result
    except Exception as e:
        logger.error(f"❌ Failed to add document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/search", response_model=SearchResponse)
async def search_documents(
    collection_name: str,
    search_request: SearchRequest,
    _: bool = Depends(verify_api_key)
):
    """Search documents in Weaviate collection"""
    try:
        results = await weaviate_service.search_documents(collection_name, search_request)
        return results
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections/{collection_name}/info", response_model=CollectionInfo)
async def get_collection_info(
    collection_name: str,
    _: bool = Depends(verify_api_key)
):
    """Get information about a Weaviate collection"""
    try:
        info = await weaviate_service.get_collection_info(collection_name)
        return info
    except Exception as e:
        logger.error(f"❌ Failed to get collection info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/create")
async def create_collection(
    collection_name: str,
    schema: Optional[Dict[str, Any]] = None,
    _: bool = Depends(verify_api_key)
):
    """Create a new Weaviate collection"""
    try:
        result = await weaviate_service.create_collection(collection_name, schema)
        return {"status": "success", "collection": collection_name, "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to create collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collections/{collection_name}")
async def delete_collection(
    collection_name: str,
    _: bool = Depends(verify_api_key)
):
    """Delete a Weaviate collection"""
    try:
        result = await weaviate_service.delete_collection(collection_name)
        return {"status": "success", "collection": collection_name, "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to delete collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/collections/{collection_name}/documents/{document_id}")
async def delete_document(
    collection_name: str,
    document_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    Delete a document from Weaviate collection.

    Args:
        collection_name: Name of the Weaviate collection
        document_id: The PostgreSQL document UUID (stored in document_id property)

    Returns:
        Success status
    """
    try:
        success = await weaviate_service.delete_document(collection_name, document_id)
        if success:
            return {"status": "success", "document_id": document_id, "collection": collection_name}
        else:
            raise HTTPException(status_code=500, detail="Failed to delete document")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/batch")
async def batch_add_documents(
    collection_name: str,
    documents: List[DocumentCreate],
    _: bool = Depends(verify_api_key)
):
    """Batch add multiple documents to Weaviate"""
    try:
        results = await weaviate_service.batch_add_documents(collection_name, documents)
        return {
            "status": "success",
            "collection": collection_name,
            "processed": len(documents),
            "results": results
        }
    except Exception as e:
        logger.error(f"❌ Batch operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/collections")
async def list_collections(_: bool = Depends(verify_api_key)):
    """List all Weaviate collections"""
    try:
        collections = await weaviate_service.list_collections()
        return {"collections": collections}
    except Exception as e:
        logger.error(f"❌ Failed to list collections: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/collections/{collection_name}/vector-query", response_model=SearchResponse)
async def vector_query(
    collection_name: str,
    query: VectorQuery,
    _: bool = Depends(verify_api_key)
):
    """Perform raw vector query on Weaviate collection"""
    try:
        results = await weaviate_service.vector_query(collection_name, query)
        return results
    except Exception as e:
        logger.error(f"❌ Vector query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/documents/{document_id}/acl")
async def update_document_acl(
    document_id: str,
    acl_update: DocumentACLUpdate,
    _: bool = Depends(verify_api_key)
):
    """
    Update document ACL properties in Weaviate.

    Called by the main API's DocumentACLService when ACLs change in PostgreSQL.
    This keeps Weaviate's document properties in sync for efficient ACL filtering
    during vector/hybrid searches.
    """
    try:
        result = await weaviate_service.update_document_acl(
            collection_name=acl_update.collection_name,
            document_id=document_id,
            acl_user_ids=acl_update.acl_user_ids,
            acl_role_ids=acl_update.acl_role_ids,
            acl_everyone=acl_update.acl_everyone
        )
        return {"status": "success", "document_id": document_id, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to update document ACL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# CACHE INVALIDATION (Security)
# ========================================

class CacheInvalidationRequest(BaseModel):
    """Request to invalidate cache entries for a document"""
    tenant_id: str
    document_id: str


class CacheInvalidationResponse(BaseModel):
    """Response from cache invalidation"""
    status: str
    document_id: str
    tenant_id: str
    entries_invalidated: int


@router.post("/cache/invalidate-by-document", response_model=CacheInvalidationResponse)
async def invalidate_cache_by_document(
    request: CacheInvalidationRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Invalidate semantic cache entries that reference a specific document.

    SECURITY: This endpoint must be called when a document's ACL changes to prevent
    stale cached responses from being returned to users who no longer have access.

    Called by the main API's DocumentACLService after updating ACL in:
    - PostgreSQL (source of truth)
    - Weaviate (vector search filter)
    - Elasticsearch (full-text search filter)

    The semantic cache stores complete RAG responses. When a document's permissions
    change, any cached response that used that document as a source must be invalidated
    to ensure users only see documents they're authorized to access.

    Args:
        request: Contains tenant_id and document_id

    Returns:
        Number of cache entries that were invalidated
    """
    try:
        from app.services.rag.semantic_cache import semantic_cache

        # Ensure cache is initialized
        await semantic_cache.initialize()

        # Invalidate all cache entries referencing this document
        invalidated = await semantic_cache.invalidate_by_document(
            tenant_id=request.tenant_id,
            document_id=request.document_id
        )

        logger.info(
            f"🔄 Cache invalidation: document={request.document_id}, "
            f"tenant={request.tenant_id}, entries_invalidated={invalidated}"
        )

        return CacheInvalidationResponse(
            status="success",
            document_id=request.document_id,
            tenant_id=request.tenant_id,
            entries_invalidated=invalidated
        )
    except Exception as e:
        logger.error(f"❌ Failed to invalidate cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Weaviate service health check"""
    try:
        status = await weaviate_service.health_check()
        return status
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ========================================
# Multimodal Embedding Endpoints
# ========================================

class MultimodalHealthResponse(BaseModel):
    """Response model for multimodal health check"""
    tei: Dict[str, Any]
    multimodal: Dict[str, Any]


class VisualSearchRequest(BaseModel):
    """Request model for visual content search"""
    query: str
    tenant_id: str
    user_id: Optional[str] = None
    user_role_ids: Optional[List[str]] = None
    content_types: Optional[List[str]] = None  # image, table_image, diagram
    document_ids: Optional[List[str]] = None
    limit: int = 10


class VisualSearchResult(BaseModel):
    """Single visual search result"""
    visual_id: str
    content_type: str
    caption: Optional[str]
    document_id: str
    page_number: int
    bbox: Optional[tuple]
    width: Optional[int]
    height: Optional[int]
    certainty: Optional[float]


class VisualSearchResponse(BaseModel):
    """Response model for visual content search"""
    results: List[Dict[str, Any]]
    total: int
    query: str
    multimodal_enabled: bool


@router.get("/multimodal/health", response_model=MultimodalHealthResponse)
async def multimodal_health_check(
    _: bool = Depends(verify_api_key)
):
    """
    Check health of multimodal embedding services.

    Returns status of:
    - TEI (text embeddings) - bge-m3
    - Multimodal (visual embeddings) - Qwen3-VL-Embedding-2B
    """
    try:
        from app.services.multimodal_embedding_service import multimodal_embedding_service
        status = await multimodal_embedding_service.health_check()
        return status
    except ImportError:
        return {
            "tei": {"healthy": False, "error": "Multimodal service not available"},
            "multimodal": {"enabled": False, "healthy": False},
        }
    except Exception as e:
        logger.error(f"❌ Multimodal health check failed: {e}")
        return {
            "tei": {"healthy": False, "error": str(e)},
            "multimodal": {"enabled": False, "healthy": False, "error": str(e)},
        }


@router.post("/multimodal/search", response_model=VisualSearchResponse)
async def search_visual_content(
    request: VisualSearchRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Search for visual content (images, tables, diagrams) using text query.

    This endpoint uses Qwen3-VL-Embedding-2B to generate a query embedding
    and searches the visual content collection for matching images/tables.

    Supports cross-modal search: text queries find relevant visual content.
    """
    try:
        from app.core.config import settings
        from app.services.multimodal_embedding_service import multimodal_embedding_service

        if not settings.multimodal_embedding_enabled:
            return VisualSearchResponse(
                results=[],
                total=0,
                query=request.query,
                multimodal_enabled=False,
            )

        # Generate query embedding with Qwen3-VL for cross-modal compatibility
        embedding_result = await multimodal_embedding_service.embed_texts(
            texts=[request.query],
            use_multimodal=True,
        )

        if not embedding_result.success or not embedding_result.vectors:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate query embedding: {embedding_result.error}"
            )

        # Search visual content
        results = await weaviate_service.search_visual_content(
            tenant_id=request.tenant_id,
            query_vector=embedding_result.vectors[0],
            user_id=request.user_id,
            user_role_ids=request.user_role_ids,
            content_types=request.content_types,
            document_ids=request.document_ids,
            limit=request.limit,
        )

        return VisualSearchResponse(
            results=results,
            total=len(results),
            query=request.query,
            multimodal_enabled=True,
        )

    except ImportError:
        return VisualSearchResponse(
            results=[],
            total=0,
            query=request.query,
            multimodal_enabled=False,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Visual search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/visual/{tenant_id}/create-collection")
async def create_visual_collection(
    tenant_id: str,
    _: bool = Depends(verify_api_key)
):
    """Create visual content collection for a tenant"""
    try:
        result = await weaviate_service.create_visual_collection(tenant_id)
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to create visual collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/visual/{tenant_id}/documents/{document_id}")
async def delete_visual_by_document(
    tenant_id: str,
    document_id: str,
    _: bool = Depends(verify_api_key)
):
    """Delete all visual content from a specific document"""
    try:
        deleted_count = await weaviate_service.delete_visual_by_document(
            tenant_id=tenant_id,
            document_id=document_id,
        )
        return {
            "status": "success",
            "deleted_count": deleted_count,
            "document_id": document_id,
        }
    except Exception as e:
        logger.error(f"❌ Failed to delete visual content: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Connector Ingestion Endpoints
# ========================================

class LearnedContextSchema(BaseModel):
    """
    Learned context from Data Learning System.

    This context is used to enrich documents during indexing and retrieval:
    - folder_semantics: What the folder structure means (department, year, classification)
    - property_weights: Which properties are important for search (boost values)
    - relationships: Document relationships from source system
    - semantic_type: Inferred document type (contract, invoice, etc.)
    - domain: Business domain (legal, hr, finance, etc.)
    """
    folder_semantics: Dict[str, Any] = {}
    property_weights: Dict[str, float] = {}
    normalized_properties: Dict[str, Any] = {}
    relationships: List[Dict[str, Any]] = []
    semantic_type: Optional[str] = None
    domain: Optional[str] = None
    folder_pattern_id: Optional[str] = None
    folder_confidence: Optional[float] = None


class IndexingStrategySchema(BaseModel):
    """
    Indexing strategy from Data Learning System.

    Configures how documents should be processed based on learned patterns:
    - chunking_type: semantic, legal_sections, markdown_headers, etc.
    - chunking_config: Target chunk size, overlap, etc.
    - embedding_fields: Which fields to include in embedding
    - extract_entities: Whether to extract named entities
    """
    chunking_type: str = "semantic"  # semantic, legal_sections, markdown_headers, paragraph
    chunking_config: Dict[str, Any] = {}  # target_chunk_size, overlap, etc.
    embedding_fields: List[str] = []  # Fields to prioritize in embedding
    extract_entities: bool = True
    entity_types: List[str] = []  # person, organization, date, etc.
    priority_score: float = 1.0


class ConnectorIndexRequest(BaseModel):
    """
    Request to index a document from an external connector.

    This endpoint receives documents from the UnifiedIndexingService
    which downloads content from Alfresco, SharePoint, etc.

    NEW: Includes learned_context and indexing_strategy from Data Learning System
    for adaptive, intelligent indexing based on connector-specific knowledge.
    """
    document_id: str
    file_bytes_base64: str  # Base64 encoded file content
    filename: str
    mime_type: Optional[str] = None
    tenant_id: str
    owner_id: str
    metadata: Dict[str, Any] = {}
    acl: Dict[str, Any] = {}
    # NEW: Data Learning System integration
    learned_context: Optional[LearnedContextSchema] = None
    indexing_strategy: Optional[IndexingStrategySchema] = None


class ConnectorIndexResponse(BaseModel):
    """Response from connector document indexing"""
    success: bool
    document_id: str
    weaviate_id: Optional[str] = None
    collection: Optional[str] = None
    chunk_count: int = 0
    entities_count: int = 0
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    # Text preview for downstream operations (categorization, entity extraction)
    extracted_text_preview: Optional[str] = None  # First 5000 chars
    extraction_language: Optional[str] = None


@router.post("/index/from-connector", response_model=ConnectorIndexResponse)
async def index_from_connector(
    request: ConnectorIndexRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Index a document from an external connector.

    This is the endpoint called by UnifiedIndexingService when processing
    documents synced from Alfresco, SharePoint, Google Drive, etc.

    The flow is:
    1. Background worker discovers documents via connector sync
    2. Background worker downloads content from source
    3. Background worker POSTs to this endpoint with base64 content
    4. This endpoint runs the full IndexingPipeline
    5. Returns weaviate_id for background worker to store

    This enables the same IndexingPipeline used for manual uploads
    to be used for connector-sourced documents.
    """
    import base64
    import time

    start_time = time.time()

    try:
        # Decode base64 content
        try:
            file_bytes = base64.b64decode(request.file_bytes_base64)
        except Exception as e:
            logger.error(f"Failed to decode base64 content: {e}")
            return ConnectorIndexResponse(
                success=False,
                document_id=request.document_id,
                error=f"Invalid base64 content: {e}",
            )

        # Log with learned context info
        has_learned_context = request.learned_context is not None
        has_strategy = request.indexing_strategy is not None
        logger.info(
            f"📥 Indexing connector document: {request.filename} "
            f"({len(file_bytes)} bytes) for tenant {request.tenant_id} "
            f"[learned_context={has_learned_context}, strategy={has_strategy}]"
        )

        # Import indexing pipeline
        from app.services.rag.indexing_pipeline import IndexingPipeline

        pipeline = IndexingPipeline()

        # Build metadata from request
        metadata = {
            **request.metadata,
            "source": "connector",
            "owner_id": request.owner_id,
            "mime_type": request.mime_type,
            # ACL fields for search filtering
            "is_tenant_public": request.acl.get("is_tenant_public", False),
            "acl_user_ids": request.acl.get("shared_with_users", []),
            "acl_role_ids": request.acl.get("shared_with_groups", []),
        }

        # Convert indexing strategy to dict for pipeline
        strategy_config = None
        if request.indexing_strategy:
            strategy_config = request.indexing_strategy.model_dump()
            logger.info(
                f"📋 Using indexing strategy: chunking_type={request.indexing_strategy.chunking_type}, "
                f"extract_entities={request.indexing_strategy.extract_entities}"
            )

        # Run indexing pipeline with strategy
        result = await pipeline.process_file(
            document_id=request.document_id,
            file_bytes=file_bytes,
            filename=request.filename,
            metadata=metadata,
            tenant_id=request.tenant_id,
            indexing_strategy=strategy_config,  # NEW: Pass strategy to pipeline
        )

        if not result.success:
            error_msg = "; ".join(result.errors) if result.errors else "Unknown error"
            logger.error(f"❌ Pipeline failed for {request.filename}: {error_msg}")
            return ConnectorIndexResponse(
                success=False,
                document_id=request.document_id,
                error=error_msg,
                processing_time_ms=(time.time() - start_time) * 1000,
            )

        # Store chunks in Weaviate
        from app.schemas.weaviate import DocumentCreate

        collection_name = f"Nouxcube_{request.tenant_id.replace('-', '_')}_documents"

        # Ensure collection exists
        await weaviate_service.ensure_collection_exists(collection_name)

        # Build learned context for storage (enriches retrieval)
        learned_context_dict = None
        if request.learned_context:
            learned_context_dict = request.learned_context.model_dump()
            logger.info(
                f"🧠 Storing learned context: semantic_type={request.learned_context.semantic_type}, "
                f"domain={request.learned_context.domain}, "
                f"folder_semantics={list(request.learned_context.folder_semantics.keys())}"
            )

        # Create document with chunks and learned context
        doc_create = DocumentCreate(
            id=request.document_id,
            title=request.filename,
            tenant_id=request.tenant_id,
            content=result.extracted_text[:30000] if result.extracted_text else "",  # First 30k chars (unified with upload flow)
            owner_user_id=request.owner_id,
            external_id=request.metadata.get("external_id", "") if request.metadata else "",
            source_type="connector",
            metadata={
                **metadata,
                "filename": request.filename,
                "chunk_count": len(result.chunks),
                "quality": result.analysis.quality.value if result.analysis else "unknown",
                "language": result.extraction_language,
                "entities_count": result.knowledge_result.entities_count if result.knowledge_result else 0,
                # NEW: Data Learning enrichment
                "learned_context": learned_context_dict,
                "semantic_type": request.learned_context.semantic_type if request.learned_context else None,
                "domain": request.learned_context.domain if request.learned_context else None,
                "folder_semantics": request.learned_context.folder_semantics if request.learned_context else {},
                "property_weights": request.learned_context.property_weights if request.learned_context else {},
            },
            chunks=[
                {
                    "content": chunk.content,
                    "metadata": {
                        **chunk.metadata,
                        # Enrich each chunk with learned context for retrieval
                        "semantic_type": request.learned_context.semantic_type if request.learned_context else None,
                        "domain": request.learned_context.domain if request.learned_context else None,
                    },
                    "chunk_index": i,
                }
                for i, chunk in enumerate(result.chunks)
            ],
        )

        # Add to Weaviate
        weaviate_result = await weaviate_service.add_document(collection_name, doc_create)

        processing_time = (time.time() - start_time) * 1000

        logger.info(
            f"✅ Indexed connector document: {request.filename} → "
            f"Weaviate ID: {weaviate_result.id}, "
            f"{len(result.chunks)} chunks, {processing_time:.0f}ms"
        )

        # Prepare text preview for downstream operations (categorization, etc.)
        text_preview = None
        if result.extracted_text:
            text_preview = result.extracted_text[:5000]

        return ConnectorIndexResponse(
            success=True,
            document_id=request.document_id,
            weaviate_id=str(weaviate_result.id) if weaviate_result.id else None,
            collection=collection_name,
            chunk_count=len(result.chunks),
            entities_count=result.knowledge_result.entities_count if result.knowledge_result else 0,
            processing_time_ms=processing_time,
            extracted_text_preview=text_preview,
            extraction_language=result.extraction_language,
        )

    except Exception as e:
        logger.exception(f"❌ Failed to index connector document: {e}")
        return ConnectorIndexResponse(
            success=False,
            document_id=request.document_id,
            error=str(e),
            processing_time_ms=(time.time() - start_time) * 1000,
        )


# ========================================
# Document Content Retrieval (for NexusLM)
# ========================================

class DocumentContentResponse(BaseModel):
    """Response with full document content from all chunks"""
    document_id: str
    title: str
    content: str
    chunk_count: int
    word_count: int
    source_type: Optional[str] = None


@router.get("/documents/{tenant_id}/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_full_content(
    tenant_id: str,
    document_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    Get the full content of a document by concatenating all its chunks.

    This endpoint is used by NexusLM to retrieve document content for podcast generation.
    Chunks are sorted by chunk_index and concatenated with newlines.

    Args:
        tenant_id: Tenant identifier
        document_id: Document ID (from IndexedDocument or Document table)

    Returns:
        DocumentContentResponse with full concatenated content
    """
    try:
        result = await weaviate_service.get_document_full_content(
            tenant_id=tenant_id,
            document_id=document_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found in tenant {tenant_id}"
            )

        return DocumentContentResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get document content: {e}")
        raise HTTPException(status_code=500, detail=str(e))