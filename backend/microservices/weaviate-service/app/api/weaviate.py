"""Weaviate API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.core.security import verify_api_key
from app.core.config import settings
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

@router.get("/tenants/{tenant_id}/count-by-type")
async def count_by_semantic_type(
    tenant_id: str,
    semantic_type: Optional[str] = Query(default=None, description="Specific semantic type to count"),
    _: bool = Depends(verify_api_key),
):
    """Count documents by semantic_type from Weaviate enrichment properties."""
    try:
        return await weaviate_service.count_by_semantic_type(tenant_id, semantic_type)
    except Exception as e:
        logger.error(f"count_by_semantic_type failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


# Mapping from MIME type to file extension for filename normalization
MIME_TO_EXTENSION = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/vnd.ms-powerpoint": ".ppt",
    "text/plain": ".txt",
    "text/html": ".html",
    "text/csv": ".csv",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "application/rtf": ".rtf",
    "application/xml": ".xml",
    "text/xml": ".xml",
}

# Valid file extensions that intelligence-docs-service supports
VALID_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".html", ".htm", ".csv", ".rtf", ".xml",
    ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif",
    ".odt", ".ods", ".odp", ".epub", ".md", ".markdown",
}


def normalize_filename_extension(filename: str, mime_type: str | None) -> str:
    """
    Ensure filename has a valid extension for text extraction.

    IMPORTANT: MIME type is prioritized over filename extension because:
    - MIME type comes from the source system (Alfresco, SharePoint, etc.)
    - Source systems detect actual file content, not just the filename
    - Filenames can be misleading: "GESTOR.docx.pdf" might actually be a DOCX

    Handles edge cases like:
    - "CamScanner 06-18-2020 13.15.09" -> "CamScanner 06-18-2020 13.15.09.pdf"
    - "GESTOR.docx.pdf" with mime=application/msword -> "GESTOR.docx.pdf.docx" or replace
    - Files with timestamps that look like extensions

    Args:
        filename: Original filename (may lack extension or have misleading dots)
        mime_type: MIME type of the file (trusted source of truth)

    Returns:
        Filename with proper extension based on MIME type
    """
    import os

    # Get the current "extension" from filename
    _, current_ext = os.path.splitext(filename)
    current_ext_lower = current_ext.lower()

    # PRIORITY 1: If we have a valid MIME type, use it as the source of truth
    if mime_type:
        mime_type_lower = mime_type.lower()
        expected_ext = MIME_TO_EXTENSION.get(mime_type_lower)

        if expected_ext:
            # Check if the current extension matches what the MIME type says
            if current_ext_lower != expected_ext:
                # Extension mismatch! Trust MIME type over filename
                # Examples:
                # - "GESTOR.docx.pdf" + mime=application/msword -> file is actually a DOC
                # - "report.txt" + mime=application/pdf -> file is actually a PDF
                logger.info(
                    f"📎 Filename extension mismatch: '{filename}' has '{current_ext}' "
                    f"but MIME type '{mime_type}' indicates '{expected_ext}'. "
                    f"Using MIME-based extension."
                )

                # Replace the wrong extension with the correct one
                if current_ext_lower in VALID_EXTENSIONS:
                    # Has a valid but wrong extension - replace it
                    base_name = filename[:-len(current_ext)] if current_ext else filename
                    return f"{base_name}{expected_ext}"
                else:
                    # Has invalid extension (like .09) - append correct one
                    return f"{filename}{expected_ext}"
            else:
                # Extension matches MIME type - all good
                return filename

    # PRIORITY 2: No MIME type available, fall back to extension validation
    if current_ext_lower in VALID_EXTENSIONS:
        return filename  # Has valid extension, no MIME to contradict it

    # PRIORITY 3: Invalid extension and no MIME type
    # This shouldn't happen often if connectors provide MIME types
    logger.warning(
        f"⚠️ Cannot determine extension for '{filename}' (mime={mime_type}). "
        "Will attempt extraction anyway - Tika may auto-detect."
    )

    return filename


def _extract_folder_path(external_path: str) -> str:
    """
    Extract folder path from external_path (remove filename).

    Examples:
        "/Sites/legal/docs/contract.pdf" → "/Sites/legal/docs"
        "/Contracts/ACME/2024/report.docx" → "/Contracts/ACME/2024"
        "contract.pdf" → ""
    """
    if not external_path:
        return ""

    # Normalize path separators
    path = external_path.replace("\\", "/").strip()

    # Remove filename (last component after /)
    if "/" in path:
        folder_path = path.rsplit("/", 1)[0]
        return folder_path if folder_path else "/"

    return ""


def _generate_folder_hierarchy(folder_path: str) -> list:
    """
    Generate folder hierarchy array from folder path.

    Examples:
        "/Contracts/ACME/2024" → ["/", "/Contracts", "/Contracts/ACME", "/Contracts/ACME/2024"]
        "/docs" → ["/", "/docs"]
        "" → []
    """
    if not folder_path:
        return []

    # Normalize path
    path = folder_path.replace("\\", "/").strip()
    if not path.startswith("/"):
        path = "/" + path

    hierarchy = ["/"]  # Always start with root

    parts = [p for p in path.split("/") if p]  # Filter empty parts
    current = ""

    for part in parts:
        current = f"{current}/{part}"
        hierarchy.append(current)

    return hierarchy



def _extract_person_from_path(folder_path: str) -> str:
    """
    Heuristic: extract person name from folder path.

    Many EDMS organise documents as /Empleados/Nombre Apellido/... or
    /Clientes/Empresa/Persona/... . If the first folder segment matches a
    known container keyword, return the second segment as person/entity name.

    Examples:
        "/Empleados/Javier Martinez/Contratos" → "Javier Martinez"
        "/Clientes/ACME Corp/2024" → "ACME Corp"
        "/Documentos/facturas" → ""
    """
    if not folder_path:
        return ""
    parts = [p for p in folder_path.replace("\\", "/").split("/") if p]
    if len(parts) < 2:
        return ""
    _PERSON_CONTAINERS = {
        "empleados", "employees", "personal", "personas", "rrhh",
        "clientes", "clients", "customers", "proveedores", "suppliers",
    }
    if parts[0].lower() in _PERSON_CONTAINERS:
        return parts[1]
    return ""


async def _generate_document_memory(
    tenant_id: str,
    document_id: str,
    document_text: str,
    filename: str,
    domain: str,
    semantic_type: str,
) -> None:
    """Fire-and-forget call to emma-agent-service to generate a document memory."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.emma_agent_service_url}/emma/memory/generate",
                json={
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "document_text": document_text[:8000],
                    "filename": filename,
                    "domain": domain,
                    "semantic_type": semantic_type,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                },
            )
            if response.status_code == 200:
                logger.debug(f"Memory generated for doc {document_id}")
            else:
                logger.debug(f"Memory generation returned {response.status_code} for doc {document_id}")
    except Exception as e:
        logger.debug(f"Memory generation failed for doc {document_id}: {e}")


async def _memorize_document(
    tenant_id: str,
    document_id: str,
    document_text: str,
    filename: str,
    domain: str,
    semantic_type: str,
) -> None:
    """Fire-and-forget call to emma-agent-service MemoRAG memorize endpoint."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.emma_agent_service_url}/emma/memorag/memorize",
                json={
                    "tenant_id": tenant_id,
                    "document_id": document_id,
                    "document_text": document_text[:8000],
                    "filename": filename,
                    "domain": domain,
                    "semantic_type": semantic_type,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": settings.MICROSERVICES_API_KEY,
                },
            )
            if response.status_code == 200:
                logger.debug(f"MemoRAG memorized doc {document_id}")
            else:
                logger.debug(f"MemoRAG memorize returned {response.status_code} for doc {document_id}")
    except Exception as e:
        logger.debug(f"MemoRAG memorize failed for doc {document_id}: {e}")


async def _cache_original_file(
    tenant_id: str, document_id: str, filename: str, file_bytes: bytes,
) -> Optional[str]:
    """Cache original file in storage-service (MinIO) for offline access.
    Returns the object_name (cached_path) or None if caching failed."""
    import httpx
    try:
        object_name = f"originals/{document_id}/{filename}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.storage_service_url}/files/{object_name}",
                params={"tenant_id": tenant_id},
                content=file_bytes,
            )
            response.raise_for_status()
        return object_name
    except Exception as e:
        logger.warning(f"Content cache failed for {document_id}: {e}")
        return None


async def _cache_extracted_text(
    tenant_id: str, document_id: str, extracted_text: str,
) -> Optional[str]:
    """Cache extracted text for database connector documents (no file bytes)."""
    import httpx
    try:
        object_name = f"originals/{document_id}/extracted.txt"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.storage_service_url}/files/{object_name}",
                params={"tenant_id": tenant_id},
                content=extracted_text.encode("utf-8"),
            )
            response.raise_for_status()
        return object_name
    except Exception as e:
        logger.warning(f"Text cache failed for {document_id}: {e}")
        return None


async def _update_cached_path(tenant_id: str, document_id: str, cached_path: str) -> None:
    """Direct DB update for cached_path using asyncpg."""
    try:
        import asyncpg
        import uuid as _uuid
        dsn = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        conn = await asyncpg.connect(dsn)
        await conn.execute(
            "UPDATE indexed_documents SET cached_path = $1 WHERE id = $2 AND tenant_id = $3",
            cached_path, _uuid.UUID(document_id), _uuid.UUID(tenant_id),
        )
        await conn.close()
    except Exception as e:
        logger.debug(f"Failed to update cached_path for {document_id}: {e}")


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

        # Cache original file in MinIO for offline access
        cached_path = await _cache_original_file(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            filename=request.filename,
            file_bytes=file_bytes,
        )

        # Normalize filename to ensure valid extension for text extraction
        # Handles edge cases like "CamScanner 06-18-2020 13.15.09" -> adds .pdf
        normalized_filename = normalize_filename_extension(
            request.filename,
            request.mime_type
        )

        # Log with learned context info
        has_learned_context = request.learned_context is not None
        has_strategy = request.indexing_strategy is not None
        logger.info(
            f"📥 Indexing connector document: {normalized_filename} "
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
            filename=normalized_filename,  # Use normalized filename with proper extension
            metadata=metadata,
            tenant_id=request.tenant_id,
            indexing_strategy=strategy_config,  # NEW: Pass strategy to pipeline
        )

        if not result.success:
            error_msg = "; ".join(result.errors) if result.errors else "Unknown error"
            logger.error(f"❌ Pipeline failed for {normalized_filename}: {error_msg}")
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

        # Extract folder hierarchy from external_path for RAG filtering
        external_path = request.metadata.get("external_path", "") if request.metadata else ""
        folder_path = _extract_folder_path(external_path)
        folder_hierarchy = _generate_folder_hierarchy(folder_path)
        connector_id = request.metadata.get("connector_id", "") if request.metadata else ""

        if folder_path:
            logger.info(f"📁 Folder hierarchy: {folder_path} → {folder_hierarchy}")

        # Build learned context for storage (enriches retrieval)
        learned_context_dict = None
        if request.learned_context:
            learned_context_dict = request.learned_context.model_dump()
            logger.info(
                f"🧠 Storing learned context: semantic_type={request.learned_context.semantic_type}, "
                f"domain={request.learned_context.domain}, "
                f"folder_semantics={list(request.learned_context.folder_semantics.keys())}"
            )

        # Determine document_type from available sources:
        # 1. learned_context.semantic_type (e.g., "contract", "invoice")
        # 2. MIME type mapping (e.g., application/pdf → "pdf")
        # 3. Fallback: "document"
        _MIME_TO_DOCTYPE = {
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
            "application/msword": "doc",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            "application/vnd.ms-excel": "xls",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
            "application/vnd.ms-powerpoint": "ppt",
            "text/plain": "txt",
            "text/html": "html",
            "text/markdown": "markdown",
            "text/csv": "csv",
            "application/json": "json",
            "application/xml": "xml",
            "image/png": "image",
            "image/jpeg": "image",
        }
        doc_type = "document"
        if request.learned_context and request.learned_context.semantic_type:
            doc_type = request.learned_context.semantic_type
        elif request.mime_type:
            doc_type = _MIME_TO_DOCTYPE.get(request.mime_type, "document")

        # Infer semantic type from filename + text content using embeddings
        # This gives a content-level classification (e.g., "factura", "contrato")
        # distinct from the format-level doc_type (e.g., "pdf", "docx")
        inferred_semantic_type = None
        if not (request.learned_context and request.learned_context.semantic_type):
            try:
                from app.services.rag.semantic_type_classifier import classify_semantic_type
                text_preview = result.extracted_text[:500] if result.extracted_text else ""
                classification = await classify_semantic_type(request.filename, text_preview)
                if classification:
                    inferred_semantic_type, confidence = classification
                    logger.info(
                        f"🏷️ Classified semantic_type='{inferred_semantic_type}' "
                        f"(confidence={confidence:.3f}) for {request.filename}"
                    )
            except Exception as e:
                logger.warning(f"⚠️ Semantic type classification failed: {e}")

        # Create document with chunks and learned context
        doc_create = DocumentCreate(
            id=request.document_id,
            title=request.filename,
            tenant_id=request.tenant_id,
            document_type=doc_type,
            # Content field stores preview when using chunks, full text otherwise
            # When chunks are present, each chunk is stored as separate Weaviate object
            content=result.extracted_text[:2000] if result.chunks else (result.extracted_text or ""),  # Preview for chunked docs
            owner_user_id=request.owner_id,
            external_id=request.metadata.get("external_id", "") if request.metadata else "",
            source_type="connector",
            # Folder hierarchy for RAG path-based filtering
            folder_path=folder_path,
            folder_hierarchy=folder_hierarchy,
            connector_id=connector_id,
            # ACL fields for document-level access control
            acl_user_ids=request.acl.get("shared_with_users", []) if request.acl else [],
            acl_role_ids=request.acl.get("shared_with_groups", []) if request.acl else [],
            acl_everyone=request.acl.get("is_tenant_public", True) if request.acl else True,
            # Enrichment properties for multi-signal retrieval
            # Fallback chain: learned_context → inferred → contextual_domain → empty
            domain=(
                (request.learned_context.domain if request.learned_context and request.learned_context.domain else None)
                or result.contextual_domain
                or ""
            ),
            semantic_type=(
                (request.learned_context.semantic_type if request.learned_context and request.learned_context.semantic_type else None)
                or inferred_semantic_type  # Content-level: "factura", "contrato", etc.
                or ""  # No fallback to format-level doc_type — semantic_type must be a real type or empty
            ),
            quality_score=result.analysis.confidence if result.analysis else 0.0,
            associated_person=_extract_person_from_path(folder_path),
            metadata={
                **metadata,
                "filename": request.filename,
                "chunk_count": len(result.chunks),
                "quality": result.analysis.quality.value if result.analysis else "unknown",
                "language": result.extraction_language,
                "entities_count": result.knowledge_result.entities_count if result.knowledge_result else 0,
                # NEW: Data Learning enrichment
                "learned_context": learned_context_dict,
                "semantic_type": (request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                "domain": (request.learned_context.domain if request.learned_context else None) or result.contextual_domain,
                "folder_semantics": request.learned_context.folder_semantics if request.learned_context else {},
                "property_weights": request.learned_context.property_weights if request.learned_context else {},
            },
            chunks=[
                {
                    "content": chunk.content,
                    "metadata": {
                        **chunk.metadata,
                        # Enrich each chunk with learned context + pipeline inference
                        "semantic_type": (request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                        "domain": (request.learned_context.domain if request.learned_context else None) or result.contextual_domain,
                        "quality_score": result.analysis.confidence if result.analysis else 0.0,
                        # Folder hierarchy for chunk-level filtering
                        "folder_path": folder_path,
                        "folder_hierarchy": folder_hierarchy,
                        "connector_id": connector_id,
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

        # Persist cached_path to DB (fire-and-forget)
        if cached_path:
            import asyncio
            asyncio.create_task(
                _update_cached_path(request.tenant_id, request.document_id, cached_path)
            )

        # Fire-and-forget: structural indexing → AGE graph (structural_document/folder nodes)
        if True:
            import asyncio
            try:
                from app.clients.knowledge_tree_client import knowledge_tree_legal_client
                asyncio.create_task(
                    knowledge_tree_legal_client.index_structural(
                        tenant_id=request.tenant_id,
                        document_id=request.document_id,
                        file_path=external_path,
                        connector_metadata=request.metadata or {},
                        learned_context=learned_context_dict or {},
                        weaviate_document_id=str(weaviate_result.id) if weaviate_result.id else None,
                        connector_id=connector_id or None,
                        connector_type=request.metadata.get("connector_type") if request.metadata else None,
                    )
                )
            except Exception as e:
                logger.debug(f"Structural indexing skipped: {e}")

        # Fire-and-forget: memorize document via MemoRAG (fallback to memory bank)
        if result.extracted_text:
            import asyncio
            if settings.memorag_enabled:
                asyncio.create_task(
                    _memorize_document(
                        tenant_id=request.tenant_id,
                        document_id=request.document_id,
                        document_text=result.extracted_text,
                        filename=request.filename,
                        domain=(request.learned_context.domain if request.learned_context else None) or result.contextual_domain or "",
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                    )
                )
            elif settings.memory_bank_enabled:
                asyncio.create_task(
                    _generate_document_memory(
                        tenant_id=request.tenant_id,
                        document_id=request.document_id,
                        document_text=result.extracted_text,
                        filename=request.filename,
                        domain=(request.learned_context.domain if request.learned_context else None) or result.contextual_domain or "",
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                    )
                )
            # BKG Phase 6: Legal reference detection + APLICA edges
            try:
                from app.clients.knowledge_tree_client import knowledge_tree_legal_client
                asyncio.create_task(
                    knowledge_tree_legal_client.extract_and_link_legal(
                        tenant_id=request.tenant_id,
                        document_id=request.document_id,
                        text_sample=result.extracted_text[:2000] if result.extracted_text else "",
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                        domain=(request.learned_context.domain if request.learned_context else None) or result.contextual_domain or "",
                    )
                )
            except Exception as e:
                logger.debug(f"Legal reference extraction skipped: {e}")

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


# ========================================
# Enrichment Backfill
# ========================================

@router.post("/collections/{collection_name}/backfill-semantic-types")
async def backfill_semantic_types(
    collection_name: str,
    threshold: float = Query(default=0.68, ge=0.3, le=0.9, description="Min cosine similarity"),
    force: bool = Query(default=False, description="Re-classify ALL objects (including already classified)"),
    _: bool = Depends(verify_api_key),
):
    """
    Backfill semantic_type for all objects in a collection using embedding classification.

    Two-stage classifier:
    - Stage 1: Title keyword matching (fast, high-precision)
    - Stage 2: BGE-M3 embedding similarity (fallback, higher threshold)

    Set force=true to re-classify ALL objects including previously classified ones.
    """
    from app.services.rag.semantic_type_classifier import classify_semantic_type

    _FORMAT_TYPES = {"pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
                     "txt", "html", "markdown", "csv", "json", "xml",
                     "image", "document", ""}

    # Sentinel to distinguish "classified as None" from "not yet classified"
    _NOT_CACHED = object()

    try:
        await weaviate_service.initialize()

        if not weaviate_service.client.collections.exists(collection_name):
            raise HTTPException(status_code=404, detail=f"Collection {collection_name} not found")

        collection = weaviate_service.client.collections.get(collection_name)

        updated = 0
        cleared = 0
        skipped = 0
        errors = 0
        classifications: Dict[str, int] = {}  # type → count
        # Cache: document_id → classification result (or None).
        # All chunks of the same document share the same title, so we only
        # need to classify once per document (~100 embeddings vs ~22K).
        doc_cache: Dict[str, Any] = {}

        for item in collection.iterator(
            include_vector=False,
            return_properties=["title", "content", "semantic_type", "document_id"]
        ):
            current_type = (item.properties.get("semantic_type") or "").strip()

            # Skip if already has a meaningful semantic type (unless force)
            if not force and current_type and current_type not in _FORMAT_TYPES:
                skipped += 1
                continue

            title = item.properties.get("title", "") or ""
            content = item.properties.get("content", "") or ""
            doc_id = item.properties.get("document_id", "") or ""

            # Check document-level cache to avoid redundant embeddings
            cached = doc_cache.get(doc_id, _NOT_CACHED) if doc_id else _NOT_CACHED

            if cached is _NOT_CACHED:
                try:
                    result = await classify_semantic_type(title, content[:500], threshold)
                except Exception as e:
                    logger.warning(f"Classification failed for {item.uuid}: {e}")
                    errors += 1
                    continue
                if doc_id:
                    doc_cache[doc_id] = result
            else:
                result = cached

            if result:
                inferred_type, confidence = result
                try:
                    collection.data.update(
                        uuid=item.uuid,
                        properties={"semantic_type": inferred_type}
                    )
                    updated += 1
                    classifications[inferred_type] = classifications.get(inferred_type, 0) + 1
                except Exception as e:
                    logger.warning(f"Failed to update {item.uuid}: {e}")
                    errors += 1
            else:
                # If force mode, clear any previous value (including format types like "pdf", "docx")
                if force and current_type:
                    try:
                        collection.data.update(
                            uuid=item.uuid,
                            properties={"semantic_type": ""}
                        )
                        cleared += 1
                    except Exception:
                        pass
                skipped += 1

        return {
            "collection": collection_name,
            "updated": updated,
            "cleared": cleared,
            "skipped": skipped,
            "errors": errors,
            "classifications": classifications,
            "threshold": threshold,
            "force": force,
            "unique_documents": len(doc_cache),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections/{collection_name}/backfill-embeddings")
async def backfill_embeddings(
    collection_name: str,
    batch_size: int = Query(default=32, ge=1, le=128, description="Batch size for embedding generation"),
    dry_run: bool = Query(default=False, description="Only count objects missing vectors, don't fix"),
    _: bool = Depends(verify_api_key),
):
    """
    Backfill vector embeddings for objects that were indexed without vectors.

    This happens when intelligence-docs-service was unavailable during indexing.
    Iterates all objects, detects those missing vectors, generates embeddings
    via intelligence-docs-service, and updates them in-place.
    """
    from app.services.weaviate_service import generate_embedding_batch, generate_embedding

    try:
        await weaviate_service.initialize()

        if not weaviate_service.client.collections.exists(collection_name):
            raise HTTPException(status_code=404, detail=f"Collection {collection_name} not found")

        collection = weaviate_service.client.collections.get(collection_name)

        missing = 0
        fixed = 0
        already_has_vector = 0
        errors = 0

        # Collect objects missing vectors in batches
        pending_batch: list[dict] = []  # [{uuid, text}]

        async def flush_batch():
            nonlocal fixed, errors
            if not pending_batch:
                return
            texts = [item["text"] for item in pending_batch]
            try:
                embeddings = await generate_embedding_batch(texts)
                if embeddings and len(embeddings) == len(pending_batch):
                    for item, vector in zip(pending_batch, embeddings):
                        try:
                            collection.data.update(
                                uuid=item["uuid"],
                                vector=vector,
                            )
                            fixed += 1
                        except Exception as e:
                            logger.warning(f"Failed to update vector for {item['uuid']}: {e}")
                            errors += 1
                else:
                    # Batch failed — try one by one
                    for item in pending_batch:
                        try:
                            vector = await generate_embedding(item["text"])
                            if vector:
                                collection.data.update(
                                    uuid=item["uuid"],
                                    vector=vector,
                                )
                                fixed += 1
                            else:
                                errors += 1
                        except Exception as e:
                            logger.warning(f"Single embed failed for {item['uuid']}: {e}")
                            errors += 1
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                errors += len(pending_batch)
            pending_batch.clear()

        for item in collection.iterator(
            include_vector=True,
            return_properties=["title", "content"],
        ):
            # Check if object has a vector
            has_vector = (
                item.vector
                and isinstance(item.vector, dict)
                and "default" in item.vector
                and len(item.vector["default"]) > 0
            ) if isinstance(item.vector, dict) else bool(item.vector)

            if has_vector:
                already_has_vector += 1
                continue

            missing += 1

            if dry_run:
                continue

            title = item.properties.get("title", "") or ""
            content = item.properties.get("content", "") or ""
            text_to_embed = f"{title} {content}".strip()

            if not text_to_embed:
                errors += 1
                continue

            pending_batch.append({"uuid": item.uuid, "text": text_to_embed})

            if len(pending_batch) >= batch_size:
                await flush_batch()

        # Flush remaining
        await flush_batch()

        result = {
            "collection": collection_name,
            "total_scanned": already_has_vector + missing,
            "already_has_vector": already_has_vector,
            "missing_vectors": missing,
            "fixed": fixed,
            "errors": errors,
            "dry_run": dry_run,
        }
        logger.info(f"Embedding backfill complete: {result}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Embedding backfill failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================
# Emma Agent Service Endpoints
# ========================================
# These endpoints are called by emma-agent-service via HTTP
# They provide SIL structural queries, RAG queries, and document access

class StructuralSummaryRequest(BaseModel):
    """Request for structural summary (terminology)"""
    tenant_id: str


class StructuralSummaryResponse(BaseModel):
    """Response with structural summary text"""
    summary: str = ""


@router.post("/structural/summary", response_model=StructuralSummaryResponse)
async def structural_summary(
    request: StructuralSummaryRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Get tenant structural summary (terminology) from SIL graph.
    """
    try:
        from app.clients.knowledge_tree_client import knowledge_tree_legal_client

        summary = await knowledge_tree_legal_client.get_structural_summary(
            tenant_id=request.tenant_id
        )
        return StructuralSummaryResponse(summary=summary or "")
    except Exception as e:
        logger.error(f"Structural summary failed: {e}", exc_info=True)
        return StructuralSummaryResponse(summary="")


class RAGQueryRequest(BaseModel):
    """Request for RAG query (from emma-agent-service)"""
    tenant_id: str
    query: str
    user_id: Optional[str] = None
    conversation_id: Optional[str] = None
    max_tokens: int = 4096
    include_sources: bool = True


class RAGQueryResponse(BaseModel):
    """Response from RAG query"""
    answer: str
    sources: List[Dict[str, Any]] = []
    confidence: float = 0.0
    metadata: Dict[str, Any] = {}


@router.post("/rag/query", response_model=RAGQueryResponse)
async def rag_query(
    request: RAGQueryRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Execute RAG query through the full pipeline.

    This endpoint is called by emma-agent-service for the analyze tool.
    It runs the complete 7-layer RAG pipeline.
    """
    try:
        from app.services.rag.rag_pipeline import RAGPipeline
        from app.core.security import get_tenant_collection_name

        pipeline = RAGPipeline()
        await pipeline.initialize()

        collection = get_tenant_collection_name(request.tenant_id)

        # Execute RAG pipeline
        result = await pipeline.answer_with_context(
            collection_name=collection,
            query=request.query,
            max_chunks=10,
        )

        sources = []
        if request.include_sources and result.get("sources"):
            sources = result["sources"]

        return RAGQueryResponse(
            answer=result.get("answer", ""),
            sources=sources,
            confidence=result.get("confidence", 0.8),
            metadata={
                "tokens_used": result.get("tokens_used", 0),
                "chunks_retrieved": len(result.get("sources", [])),
            }
        )

    except Exception as e:
        logger.error(f"❌ RAG query failed: {e}", exc_info=True)
        return RAGQueryResponse(
            answer=f"Error processing query: {e}",
            sources=[],
            confidence=0.0,
            metadata={"error": str(e)}
        )


class HybridSearchRequest(BaseModel):
    """Request for hybrid search (from emma-agent-service)"""
    tenant_id: str
    query: str
    limit: int = 10
    alpha: float = 0.5  # 0=keyword, 1=vector
    filters: Optional[Dict[str, Any]] = None
    # Enrichment filters for multi-signal retrieval
    person_filter: Optional[str] = None
    domain_filter: Optional[str] = None
    semantic_type_filter: Optional[str] = None
    min_quality: Optional[float] = None
    # Temporal filters
    date_from: Optional[str] = Field(default=None, description="Filter docs created on or after this date (ISO 8601)")
    date_to: Optional[str] = Field(default=None, description="Filter docs created on or before this date (ISO 8601)")


@router.post("/collections/documents/hybrid", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Execute hybrid search combining vector and keyword search.

    This endpoint is called by emma-agent-service for the search tool.
    Alpha controls the balance: 0=pure keyword, 1=pure vector, 0.5=balanced.
    """
    try:
        from app.core.security import get_tenant_collection_name
        from app.schemas.weaviate import SearchRequest as WeaviateSearchRequest

        collection = get_tenant_collection_name(request.tenant_id)

        # Build search request with enrichment filters
        search_request = WeaviateSearchRequest(
            query=request.query,
            limit=request.limit,
            tenant_id=request.tenant_id,
            search_type="hybrid",
            filters=request.filters,
            alpha=request.alpha,
            person_filter=request.person_filter,
            domain_filter=request.domain_filter,
            semantic_type_filter=request.semantic_type_filter,
            min_quality=request.min_quality,
            date_from=request.date_from,
            date_to=request.date_to,
        )

        # Execute search
        results = await weaviate_service.search_documents(collection, search_request)
        return results

    except Exception as e:
        logger.error(f"❌ Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{tenant_id}/{document_id}/chunks")
async def get_document_chunks(
    tenant_id: str,
    document_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _: bool = Depends(verify_api_key)
):
    """
    Get document chunks with pagination.

    This endpoint is called by emma-agent-service for document reading.
    """
    try:
        from app.core.security import get_tenant_collection_name

        collection = get_tenant_collection_name(tenant_id)

        # Get chunks from Weaviate
        chunks = await weaviate_service.get_document_chunks(
            collection_name=collection,
            document_id=document_id,
            offset=offset,
            limit=limit,
        )

        return {
            "chunks": chunks,
            "offset": offset,
            "limit": limit,
            "total": len(chunks),
        }

    except Exception as e:
        logger.error(f"❌ Get document chunks failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/knowledge/related")
async def get_related_entities(
    request: Dict[str, Any],
    _: bool = Depends(verify_api_key)
):
    """
    Get entities related to a given entity via knowledge graph.

    This endpoint is called by emma-agent-service for graph exploration.
    """
    try:
        tenant_id = request.get("tenant_id")
        entity_id = request.get("entity_id")
        relationship_types = request.get("relationship_types")
        depth = request.get("depth", 1)
        limit = request.get("limit", 20)

        if not tenant_id or not entity_id:
            raise HTTPException(
                status_code=400,
                detail="tenant_id and entity_id are required"
            )

        # Use knowledge-tree-service for entity relationships (via HTTP)
        from app.clients.knowledge_tree_client import knowledge_tree_legal_client

        neighbors = await knowledge_tree_legal_client.get_law_neighbors(
            boe_id=entity_id,
            max_depth=depth,
            relationship_types=relationship_types,
        )

        return {"entities": neighbors[:limit]}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Get related entities failed: {e}", exc_info=True)
        return {"entities": [], "error": str(e)}


@router.get("/collections/{tenant_id}/stats")
async def get_collection_stats(
    tenant_id: str,
    _: bool = Depends(verify_api_key)
):
    """
    Get collection statistics for a tenant.

    Returns document count, chunk count, and other metrics.
    """
    try:
        from app.core.security import get_tenant_collection_name

        collection = get_tenant_collection_name(tenant_id)

        # Get collection info
        info = await weaviate_service.get_collection_info(collection)

        return {
            "tenant_id": tenant_id,
            "collection": collection,
            "document_count": info.objects_count if info else 0,
            "status": "active" if info else "not_found",
        }

    except Exception as e:
        logger.error(f"❌ Get collection stats failed: {e}", exc_info=True)
        return {
            "tenant_id": tenant_id,
            "error": str(e),
            "status": "error",
        }
