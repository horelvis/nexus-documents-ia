"""Weaviate API endpoints (single-org refactor)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.core.security import verify_api_key
from app.core.auth_headers import extract_user_roles, extract_user_id, EVERYONE_ROLE
from app.core.config import settings
from app.services.weaviate_service import (
    weaviate_service,
    DOCUMENTS_COLLECTION,
)
from app.schemas.weaviate import (
    DocumentCreate, DocumentResponse, SearchRequest, SearchResponse,
    CollectionInfo, VectorQuery,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================================
# Request Models
# ========================================

class DocumentACLUpdate(BaseModel):
    """Schema for updating document ACL (roles) on a document."""
    collection_name: str
    roles: List[str] = []


@router.get("/documents/count-by-type")
async def count_by_semantic_type(
    semantic_type: Optional[str] = Query(default=None, description="Specific semantic type to count"),
    _: bool = Depends(verify_api_key),
):
    """Count documents by semantic_type from Weaviate enrichment properties."""
    try:
        return await weaviate_service.count_by_semantic_type(semantic_type)
    except Exception as e:
        logger.error(f"count_by_semantic_type failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collections/{collection_name}/documents", response_model=DocumentResponse)
async def add_document(
    collection_name: str,
    document: DocumentCreate,
    _: bool = Depends(verify_api_key),
):
    """Add a document to a Weaviate collection."""
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
    user_roles: List[str] = Depends(extract_user_roles),
    _: bool = Depends(verify_api_key),
):
    """Search documents in a Weaviate collection with role-based ACL."""
    try:
        # Inject roles from header into the search request (allows callers to
        # pass additional filters in the body but not bypass ACL).
        try:
            setattr(search_request, "user_roles", user_roles)
        except Exception:
            pass
        results = await weaviate_service.search_documents(collection_name, search_request)
        return results
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections/{collection_name}/info", response_model=CollectionInfo)
async def get_collection_info(
    collection_name: str,
    _: bool = Depends(verify_api_key),
):
    """Get information about a Weaviate collection."""
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
    _: bool = Depends(verify_api_key),
):
    """Create a new Weaviate collection."""
    try:
        result = await weaviate_service.create_collection(collection_name, schema)
        return {"status": "success", "collection": collection_name, "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to create collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/collections/{collection_name}")
async def delete_collection(
    collection_name: str,
    _: bool = Depends(verify_api_key),
):
    """Delete a Weaviate collection."""
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
    _: bool = Depends(verify_api_key),
):
    """Delete a document from a Weaviate collection."""
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
    _: bool = Depends(verify_api_key),
):
    """Batch add multiple documents to Weaviate."""
    try:
        results = await weaviate_service.batch_add_documents(collection_name, documents)
        return {
            "status": "success",
            "collection": collection_name,
            "processed": len(documents),
            "results": results,
        }
    except Exception as e:
        logger.error(f"❌ Batch operation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/collections")
async def list_collections(_: bool = Depends(verify_api_key)):
    """List all Weaviate collections."""
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
    user_roles: List[str] = Depends(extract_user_roles),
    _: bool = Depends(verify_api_key),
):
    """Perform a raw vector query on a Weaviate collection."""
    try:
        try:
            setattr(query, "user_roles", user_roles)
        except Exception:
            pass
        results = await weaviate_service.vector_query(collection_name, query)
        return results
    except Exception as e:
        logger.error(f"❌ Vector query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/documents/{document_id}/acl")
async def update_document_acl(
    document_id: str,
    acl_update: DocumentACLUpdate,
    _: bool = Depends(verify_api_key),
):
    """Update document roles ACL in Weaviate."""
    try:
        result = await weaviate_service.update_document_acl(
            collection_name=acl_update.collection_name,
            document_id=document_id,
            roles=acl_update.roles,
        )
        return {"status": "success", "document_id": document_id, "result": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to update document ACL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Weaviate service health check."""
    try:
        status = await weaviate_service.health_check()
        return status
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


# ========================================
# Multimodal Embedding Endpoints
# ========================================

class MultimodalHealthResponse(BaseModel):
    """Response model for multimodal health check."""
    tei: Dict[str, Any]
    multimodal: Dict[str, Any]


class VisualSearchRequest(BaseModel):
    """Request model for visual content search."""
    query: str
    content_types: Optional[List[str]] = None  # image, table_image, diagram
    document_ids: Optional[List[str]] = None
    limit: int = 10


class VisualSearchResult(BaseModel):
    """Single visual search result."""
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
    """Response model for visual content search."""
    results: List[Dict[str, Any]]
    total: int
    query: str
    multimodal_enabled: bool


@router.get("/multimodal/health", response_model=MultimodalHealthResponse)
async def multimodal_health_check(
    _: bool = Depends(verify_api_key),
):
    """Check health of multimodal embedding services."""
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
    user_roles: List[str] = Depends(extract_user_roles),
    _: bool = Depends(verify_api_key),
):
    """Search visual content (images, tables, diagrams) using text query."""
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

        embedding_result = await multimodal_embedding_service.embed_texts(
            texts=[request.query],
            use_multimodal=True,
        )

        if not embedding_result.success or not embedding_result.vectors:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate query embedding: {embedding_result.error}",
            )

        results = await weaviate_service.search_visual_content(
            query_vector=embedding_result.vectors[0],
            user_roles=user_roles,
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


@router.post("/visual/create-collection")
async def create_visual_collection(
    _: bool = Depends(verify_api_key),
):
    """Create the visual content collection (single-org)."""
    try:
        result = await weaviate_service.create_visual_collection()
        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"❌ Failed to create visual collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/visual/documents/{document_id}")
async def delete_visual_by_document(
    document_id: str,
    _: bool = Depends(verify_api_key),
):
    """Delete all visual content from a specific document."""
    try:
        deleted_count = await weaviate_service.delete_visual_by_document(
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
    """Learned context from Data Learning System."""
    folder_semantics: Dict[str, Any] = {}
    property_weights: Dict[str, float] = {}
    normalized_properties: Dict[str, Any] = {}
    relationships: List[Dict[str, Any]] = []
    semantic_type: Optional[str] = None
    folder_pattern_id: Optional[str] = None
    folder_confidence: Optional[float] = None


class IndexingStrategySchema(BaseModel):
    """Indexing strategy from Data Learning System."""
    chunking_type: str = "semantic"
    chunking_config: Dict[str, Any] = {}
    embedding_fields: List[str] = []
    extract_entities: bool = True
    entity_types: List[str] = []
    priority_score: float = 1.0


class ConnectorIndexRequest(BaseModel):
    """Request to index a document from an external connector."""
    document_id: str
    file_bytes_base64: str
    filename: str
    mime_type: Optional[str] = None
    owner_id: str
    metadata: Dict[str, Any] = {}
    # roles are authoritative ACL. When missing we default to [EVERYONE].
    roles: Optional[List[str]] = None
    learned_context: Optional[LearnedContextSchema] = None
    indexing_strategy: Optional[IndexingStrategySchema] = None


class ConnectorIndexResponse(BaseModel):
    """Response from connector document indexing."""
    success: bool
    document_id: str
    weaviate_id: Optional[str] = None
    collection: Optional[str] = None
    chunk_count: int = 0
    entities_count: int = 0
    error: Optional[str] = None
    processing_time_ms: float = 0.0
    extracted_text_preview: Optional[str] = None
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

VALID_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".txt", ".html", ".htm", ".csv", ".rtf", ".xml",
    ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".gif",
    ".odt", ".ods", ".odp", ".epub", ".md", ".markdown",
}


def normalize_filename_extension(filename: str, mime_type: str | None) -> str:
    """Ensure filename has a valid extension for text extraction (MIME first)."""
    import os

    _, current_ext = os.path.splitext(filename)
    current_ext_lower = current_ext.lower()

    if mime_type:
        mime_type_lower = mime_type.lower()
        expected_ext = MIME_TO_EXTENSION.get(mime_type_lower)

        if expected_ext:
            if current_ext_lower != expected_ext:
                logger.info(
                    f"📎 Filename extension mismatch: '{filename}' has '{current_ext}' "
                    f"but MIME type '{mime_type}' indicates '{expected_ext}'. "
                    f"Using MIME-based extension."
                )
                if current_ext_lower in VALID_EXTENSIONS:
                    base_name = filename[:-len(current_ext)] if current_ext else filename
                    return f"{base_name}{expected_ext}"
                else:
                    return f"{filename}{expected_ext}"
            else:
                return filename

    if current_ext_lower in VALID_EXTENSIONS:
        return filename

    logger.warning(
        f"⚠️ Cannot determine extension for '{filename}' (mime={mime_type}). "
        "Will attempt extraction anyway - Tika may auto-detect."
    )

    return filename


def _extract_folder_path(external_path: str) -> str:
    """Extract folder path from external_path (remove filename)."""
    if not external_path:
        return ""

    path = external_path.replace("\\", "/").strip()

    if "/" in path:
        folder_path = path.rsplit("/", 1)[0]
        return folder_path if folder_path else "/"

    return ""


def _generate_folder_hierarchy(folder_path: str) -> list:
    """Generate folder hierarchy array from folder path."""
    if not folder_path:
        return []

    path = folder_path.replace("\\", "/").strip()
    if not path.startswith("/"):
        path = "/" + path

    hierarchy = ["/"]

    parts = [p for p in path.split("/") if p]
    current = ""

    for part in parts:
        current = f"{current}/{part}"
        hierarchy.append(current)

    return hierarchy


def _extract_person_from_path(folder_path: str) -> str:
    """Heuristic: extract person name from folder path."""
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
    document_id: str,
    document_text: str,
    filename: str,
    semantic_type: str,
) -> None:
    """Fire-and-forget call to emma-agent-service to generate a document memory."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.emma_agent_service_url}/emma/memory/generate",
                json={
                    "document_id": document_id,
                    "document_text": document_text[:8000],
                    "filename": filename,
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
    document_id: str,
    document_text: str,
    filename: str,
    semantic_type: str,
) -> None:
    """Fire-and-forget call to emma-agent-service MemoRAG memorize endpoint."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.emma_agent_service_url}/emma/memorag/memorize",
                json={
                    "document_id": document_id,
                    "document_text": document_text[:8000],
                    "filename": filename,
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
    document_id: str, filename: str, file_bytes: bytes,
) -> Optional[str]:
    """Cache original file in storage-service (MinIO) for offline access."""
    import httpx
    try:
        object_name = f"originals/{document_id}/{filename}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.storage_service_url}/files/{object_name}",
                content=file_bytes,
            )
            response.raise_for_status()
        return object_name
    except Exception as e:
        logger.warning(f"Content cache failed for {document_id}: {e}")
        return None


async def _cache_extracted_text(
    document_id: str, extracted_text: str,
) -> Optional[str]:
    """Cache extracted text for database connector documents (no file bytes)."""
    import httpx
    try:
        object_name = f"originals/{document_id}/extracted.txt"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.storage_service_url}/files/{object_name}",
                content=extracted_text.encode("utf-8"),
            )
            response.raise_for_status()
        return object_name
    except Exception as e:
        logger.warning(f"Text cache failed for {document_id}: {e}")
        return None


async def _update_cached_path(document_id: str, cached_path: str) -> None:
    """Direct DB update for cached_path using asyncpg."""
    try:
        import asyncpg
        import uuid as _uuid
        dsn = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        conn = await asyncpg.connect(dsn)
        await conn.execute(
            "UPDATE indexed_documents SET cached_path = $1 WHERE id = $2",
            cached_path, _uuid.UUID(document_id),
        )
        await conn.close()
    except Exception as e:
        logger.debug(f"Failed to update cached_path for {document_id}: {e}")


@router.post("/index/from-connector", response_model=ConnectorIndexResponse)
async def index_from_connector(
    request: ConnectorIndexRequest,
    _: bool = Depends(verify_api_key),
):
    """Index a document from an external connector."""
    import base64
    import time

    start_time = time.time()

    try:
        try:
            file_bytes = base64.b64decode(request.file_bytes_base64)
        except Exception as e:
            logger.error(f"Failed to decode base64 content: {e}")
            return ConnectorIndexResponse(
                success=False,
                document_id=request.document_id,
                error=f"Invalid base64 content: {e}",
            )

        cached_path = await _cache_original_file(
            document_id=request.document_id,
            filename=request.filename,
            file_bytes=file_bytes,
        )

        normalized_filename = normalize_filename_extension(
            request.filename,
            request.mime_type,
        )

        has_learned_context = request.learned_context is not None
        has_strategy = request.indexing_strategy is not None
        logger.info(
            f"📥 Indexing connector document: {normalized_filename} "
            f"({len(file_bytes)} bytes) "
            f"[learned_context={has_learned_context}, strategy={has_strategy}]"
        )

        from app.services.rag.indexing_pipeline import IndexingPipeline

        pipeline = IndexingPipeline()

        doc_roles = request.roles or [EVERYONE_ROLE]

        metadata = {
            **request.metadata,
            "source": "connector",
            "owner_id": request.owner_id,
            "mime_type": request.mime_type,
            "roles": doc_roles,
        }

        strategy_config = None
        if request.indexing_strategy:
            strategy_config = request.indexing_strategy.model_dump()
            logger.info(
                f"📋 Using indexing strategy: chunking_type={request.indexing_strategy.chunking_type}, "
                f"extract_entities={request.indexing_strategy.extract_entities}"
            )

        result = await pipeline.process_file(
            document_id=request.document_id,
            file_bytes=file_bytes,
            filename=normalized_filename,
            metadata=metadata,
            indexing_strategy=strategy_config,
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

        from app.schemas.weaviate import DocumentCreate

        collection_name = DOCUMENTS_COLLECTION

        await weaviate_service.ensure_collection_exists(collection_name)

        external_path = request.metadata.get("external_path", "") if request.metadata else ""
        folder_path = _extract_folder_path(external_path)
        folder_hierarchy = _generate_folder_hierarchy(folder_path)
        connector_id = request.metadata.get("connector_id", "") if request.metadata else ""

        if folder_path:
            logger.info(f"📁 Folder hierarchy: {folder_path} → {folder_hierarchy}")

        learned_context_dict = None
        if request.learned_context:
            learned_context_dict = request.learned_context.model_dump()
            logger.info(
                f"🧠 Storing learned context: semantic_type={request.learned_context.semantic_type}, "
                f"folder_semantics={list(request.learned_context.folder_semantics.keys())}"
            )

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

        doc_create = DocumentCreate(
            id=request.document_id,
            title=request.filename,
            document_type=doc_type,
            content=result.extracted_text[:2000] if result.chunks else (result.extracted_text or ""),
            roles=doc_roles,
            owner_user_id=request.owner_id,
            external_id=request.metadata.get("external_id", "") if request.metadata else "",
            source_type="connector",
            folder_path=folder_path,
            folder_hierarchy=folder_hierarchy,
            connector_id=connector_id,
            semantic_type=(
                (request.learned_context.semantic_type if request.learned_context and request.learned_context.semantic_type else None)
                or inferred_semantic_type
                or ""
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
                "learned_context": learned_context_dict,
                "semantic_type": (request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                "folder_semantics": request.learned_context.folder_semantics if request.learned_context else {},
                "property_weights": request.learned_context.property_weights if request.learned_context else {},
            },
            chunks=[
                {
                    "content": chunk.content,
                    "metadata": {
                        **chunk.metadata,
                        "semantic_type": (request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                        "quality_score": result.analysis.confidence if result.analysis else 0.0,
                        "folder_path": folder_path,
                        "folder_hierarchy": folder_hierarchy,
                        "connector_id": connector_id,
                    },
                    "chunk_index": i,
                }
                for i, chunk in enumerate(result.chunks)
            ],
        )

        weaviate_result = await weaviate_service.add_document(collection_name, doc_create)

        processing_time = (time.time() - start_time) * 1000

        logger.info(
            f"✅ Indexed connector document: {request.filename} → "
            f"Weaviate ID: {weaviate_result.id}, "
            f"{len(result.chunks)} chunks, {processing_time:.0f}ms"
        )

        text_preview = None
        if result.extracted_text:
            text_preview = result.extracted_text[:5000]

        if cached_path:
            import asyncio
            asyncio.create_task(
                _update_cached_path(request.document_id, cached_path)
            )

        # Fire-and-forget structural indexing + legal reference extraction
        if True:
            import asyncio
            try:
                from app.clients.knowledge_tree_client import knowledge_tree_legal_client
                asyncio.create_task(
                    knowledge_tree_legal_client.index_structural(
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

        if result.extracted_text:
            import asyncio
            if settings.memorag_enabled:
                asyncio.create_task(
                    _memorize_document(
                        document_id=request.document_id,
                        document_text=result.extracted_text,
                        filename=request.filename,
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                    )
                )
            elif settings.memory_bank_enabled:
                asyncio.create_task(
                    _generate_document_memory(
                        document_id=request.document_id,
                        document_text=result.extracted_text,
                        filename=request.filename,
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
                    )
                )
            try:
                from app.clients.knowledge_tree_client import knowledge_tree_legal_client
                asyncio.create_task(
                    knowledge_tree_legal_client.extract_and_link_legal(
                        document_id=request.document_id,
                        text_sample=result.extracted_text[:2000] if result.extracted_text else "",
                        semantic_type=(request.learned_context.semantic_type if request.learned_context else None) or inferred_semantic_type or "",
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
    """Response with full document content from all chunks."""
    document_id: str
    title: str
    content: str
    chunk_count: int
    word_count: int
    source_type: Optional[str] = None


@router.get("/documents/{document_id}/content", response_model=DocumentContentResponse)
async def get_document_full_content(
    document_id: str,
    _: bool = Depends(verify_api_key),
):
    """Get the full content of a document by concatenating all its chunks."""
    try:
        result = await weaviate_service.get_document_full_content(
            document_id=document_id,
        )

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Document {document_id} not found",
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
    force: bool = Query(default=False, description="Re-classify ALL objects"),
    _: bool = Depends(verify_api_key),
):
    """Backfill semantic_type for all objects in a collection using embedding classification."""
    from app.services.rag.semantic_type_classifier import classify_semantic_type

    _FORMAT_TYPES = {"pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt",
                     "txt", "html", "markdown", "csv", "json", "xml",
                     "image", "document", ""}

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
        classifications: Dict[str, int] = {}
        doc_cache: Dict[str, Any] = {}

        for item in collection.iterator(
            include_vector=False,
            return_properties=["title", "content", "semantic_type", "document_id"],
        ):
            current_type = (item.properties.get("semantic_type") or "").strip()

            if not force and current_type and current_type not in _FORMAT_TYPES:
                skipped += 1
                continue

            title = item.properties.get("title", "") or ""
            content = item.properties.get("content", "") or ""
            doc_id = item.properties.get("document_id", "") or ""

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
                        properties={"semantic_type": inferred_type},
                    )
                    updated += 1
                    classifications[inferred_type] = classifications.get(inferred_type, 0) + 1
                except Exception as e:
                    logger.warning(f"Failed to update {item.uuid}: {e}")
                    errors += 1
            else:
                if force and current_type:
                    try:
                        collection.data.update(
                            uuid=item.uuid,
                            properties={"semantic_type": ""},
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
    dry_run: bool = Query(default=False, description="Only count objects missing vectors"),
    _: bool = Depends(verify_api_key),
):
    """Backfill vector embeddings for objects that were indexed without vectors."""
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

        pending_batch: list[dict] = []

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

class StructuralSummaryRequest(BaseModel):
    """Request for structural summary (terminology)."""
    # No body fields — single-org deployment


class StructuralSummaryResponse(BaseModel):
    """Response with structural summary text."""
    summary: str = ""


@router.post("/structural/summary", response_model=StructuralSummaryResponse)
async def structural_summary(
    request: StructuralSummaryRequest,
    _: bool = Depends(verify_api_key),
):
    """Get structural summary (terminology) from SIL graph."""
    try:
        from app.clients.knowledge_tree_client import knowledge_tree_legal_client

        summary = await knowledge_tree_legal_client.get_structural_summary()
        return StructuralSummaryResponse(summary=summary or "")
    except Exception as e:
        logger.error(f"Structural summary failed: {e}", exc_info=True)
        return StructuralSummaryResponse(summary="")



class HybridSearchRequest(BaseModel):
    """Request for hybrid search (from emma-agent-service)."""
    query: str
    limit: int = 10
    alpha: float = 0.5
    filters: Optional[Dict[str, Any]] = None
    person_filter: Optional[str] = None
    semantic_type_filter: Optional[str] = None
    min_quality: Optional[float] = None
    date_from: Optional[str] = Field(default=None, description="Filter docs created on or after this date (ISO 8601)")
    date_to: Optional[str] = Field(default=None, description="Filter docs created on or before this date (ISO 8601)")


@router.post("/collections/documents/hybrid", response_model=SearchResponse)
async def hybrid_search(
    request: HybridSearchRequest,
    user_roles: List[str] = Depends(extract_user_roles),
    _: bool = Depends(verify_api_key),
):
    """Execute hybrid search combining vector and keyword search with role ACL."""
    try:
        from app.schemas.weaviate import SearchRequest as WeaviateSearchRequest

        collection = DOCUMENTS_COLLECTION

        search_request = WeaviateSearchRequest(
            query=request.query,
            limit=request.limit,
            user_roles=user_roles,
            search_type="hybrid",
            filters=request.filters,
            alpha=request.alpha,
            person_filter=request.person_filter,
            semantic_type_filter=request.semantic_type_filter,
            min_quality=request.min_quality,
            date_from=request.date_from,
            date_to=request.date_to,
        )

        results = await weaviate_service.search_documents(collection, search_request)
        return results

    except Exception as e:
        logger.error(f"❌ Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _: bool = Depends(verify_api_key),
):
    """Get document chunks with pagination."""
    try:
        collection = DOCUMENTS_COLLECTION

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
    _: bool = Depends(verify_api_key),
):
    """Get entities related to a given entity via knowledge graph."""
    try:
        entity_id = request.get("entity_id")
        relationship_types = request.get("relationship_types")
        depth = request.get("depth", 1)
        limit = request.get("limit", 20)

        if not entity_id:
            raise HTTPException(
                status_code=400,
                detail="entity_id is required",
            )

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


@router.get("/collections/stats")
async def get_collection_stats(
    _: bool = Depends(verify_api_key),
):
    """Get collection statistics for the main documents collection.

    Returns status=empty when the collection has not been provisioned yet
    (fresh install, pre-indexing). The absence of a collection is a
    legitimate zero-state, not an error.
    """
    collection = DOCUMENTS_COLLECTION
    try:
        if not weaviate_service.client.collections.exists(collection):
            return {
                "collection": collection,
                "document_count": 0,
                "status": "empty",
            }

        info = await weaviate_service.get_collection_info(collection)
        return {
            "collection": collection,
            "document_count": info.objects_count if info else 0,
            "status": "active" if info else "not_found",
        }

    except Exception as e:
        logger.error(f"❌ Get collection stats failed: {e}", exc_info=True)
        return {
            "collection": collection,
            "document_count": 0,
            "error": str(e),
            "status": "error",
        }


# ============================================================================
# TrustGraph Entity Embeddings — Graph RAG
# ============================================================================

class EntitySearchRequest(BaseModel):
    """Search TrustGraphEntities by text query."""
    query: str
    collection: Optional[str] = None
    limit: int = 50


class EntitySearchByEmbeddingRequest(BaseModel):
    """Search TrustGraphEntities by pre-computed embedding."""
    query_embedding: List[float]
    collection: Optional[str] = None
    limit: int = 50


class EntityBatchUpsertRequest(BaseModel):
    """Batch upsert entities with their embeddings."""
    entities: List[Dict[str, Any]]
    embeddings: List[List[float]]


@router.post("/entities/search")
async def search_entities(
    request: EntitySearchRequest,
    user_roles: List[str] = Depends(extract_user_roles),
    _: bool = Depends(verify_api_key),
):
    """Search TrustGraphEntities by text query."""
    try:
        from app.services.weaviate_service import generate_embedding

        query_embedding = await generate_embedding(request.query, task="retrieval.query")
        if not query_embedding:
            raise HTTPException(status_code=503, detail="Embedding service unavailable")

        entities = await weaviate_service.search_trustgraph_entities(
            query_embedding=query_embedding,
            user_roles=user_roles,
            collection=request.collection,
            limit=request.limit,
        )
        return {"entities": entities, "count": len(entities)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Entity search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entities/search-by-embedding")
async def search_entities_by_embedding(
    request: EntitySearchByEmbeddingRequest,
    user_roles: List[str] = Depends(extract_user_roles),
    _: bool = Depends(verify_api_key),
):
    """Search TrustGraphEntities by pre-computed embedding."""
    try:
        entities = await weaviate_service.search_trustgraph_entities(
            query_embedding=request.query_embedding,
            user_roles=user_roles,
            collection=request.collection,
            limit=request.limit,
        )
        return {"entities": entities, "count": len(entities)}

    except Exception as e:
        logger.error(f"Entity search-by-embedding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/entities/batch-upsert")
async def batch_upsert_entities(
    request: EntityBatchUpsertRequest,
    _: bool = Depends(verify_api_key),
):
    """Batch upsert TrustGraph entity embeddings.

    The service layer always tags them with ``roles=[EVERYONE]`` because
    TrustGraph is shared org-wide.
    """
    try:
        if len(request.entities) != len(request.embeddings):
            raise HTTPException(
                status_code=422,
                detail="entities and embeddings must have the same length",
            )

        count = await weaviate_service.upsert_trustgraph_entities_batch(
            entities=request.entities,
            embeddings=request.embeddings,
        )
        return {"count": count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Entity batch-upsert failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/entities/delete")
async def delete_entities(
    _: bool = Depends(verify_api_key),
):
    """Delete all TrustGraphEntities (single-org full wipe)."""
    try:
        deleted = await weaviate_service.delete_trustgraph_entities()
        return {"deleted": deleted}

    except Exception as e:
        logger.error(f"Entity delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# OntologyTerms — Ontology RAG Phase 3a
# ============================================================================

class OntologyTermSearchRequest(BaseModel):
    """Search OntologyTerms by pre-computed embedding."""
    embedding: List[float]
    limit: int = 3
    namespace: Optional[str] = None


class OntologyTermUpsertRequest(BaseModel):
    """Insert a single OntologyTerm."""
    predicate_name: str
    namespace: str
    description: str
    domain_type: str
    range_type: str
    embed_text: str
    embedding: List[float]


@router.post("/trustgraph/ensure-ontology-terms")
async def ensure_ontology_terms(
    _: bool = Depends(verify_api_key),
):
    """Ensure OntologyTerms collection exists."""
    ok = await weaviate_service.ensure_ontology_terms_collection()
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to create OntologyTerms collection")
    return {"status": "ok"}


@router.post("/trustgraph/ontology-terms/search")
async def search_ontology_terms(
    request: OntologyTermSearchRequest,
    _: bool = Depends(verify_api_key),
):
    """Vector search over OntologyTerms."""
    results = await weaviate_service.search_ontology_terms(
        query_embedding=request.embedding,
        limit=request.limit,
        namespace=request.namespace,
    )
    return {"results": results}


@router.post("/trustgraph/ontology-terms")
async def upsert_ontology_term(
    request: OntologyTermUpsertRequest,
    _: bool = Depends(verify_api_key),
):
    """Insert a single OntologyTerm with embedding."""
    ok = await weaviate_service.upsert_ontology_term(
        predicate_name=request.predicate_name,
        namespace=request.namespace,
        description=request.description,
        domain_type=request.domain_type,
        range_type=request.range_type,
        embed_text=request.embed_text,
        embedding=request.embedding,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to upsert OntologyTerm")
    return {"status": "ok"}
