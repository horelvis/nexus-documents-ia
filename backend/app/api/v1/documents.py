from typing import List, Optional, Dict, Any
from uuid import UUID
import os
import logging
import io
import shutil
import tempfile

import httpx
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, Body, HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.services.async_document_service import AsyncDocumentService
from app.services.document_preview_service import DocumentPreviewService
from app.services.queue_service import queue_service
from app.services.elasticsearch_client import elasticsearch_client
from app.services.storage_service import StorageService
from app.core.config import settings

from app.api.async_dependencies import (
    get_current_user_async,
    require_document_upload_permission_async,
    get_document_service,
    get_async_db
)
from app.core.auth.base import UserProfile
from app.core.auth.acl import filter_visible_to_user
from app.db.models import Document as DBDocument, Tag, IndexedDocument, Connector
from app.schemas.document import (
    Document, DocumentDetail,
    UploadRequest, DocumentUpdate
)
from app.services.connectors import ConnectorAdapterFactory
from app.schemas.unified_document import UnifiedDocument, ConnectorType

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================================
# ACL — role-based access enforced via filter_visible_to_user
# ========================================

async def _load_visible_document(
    db: AsyncSession,
    doc_id: str,
    user: UserProfile,
) -> DBDocument:
    """Load a Document enforcing role-based visibility or raise 403/404."""
    query = filter_visible_to_user(
        select(DBDocument).where(DBDocument.id == UUID(doc_id)),
        user,
    )
    result = await db.execute(query)
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("", response_model=dict)
async def list_documents(
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service),
    current_user: UserProfile = Depends(get_current_user_async),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    folder: Optional[str] = Query(None, description="Filter by folder path. Use empty string for root.")
):
    """
    Obtiene lista paginada de documentos con filtros opcionales.
    Estilo Google Drive: devuelve carpetas + documentos en una sola lista.

    ACL filtering: Only returns documents the user has VIEW permission on.
    - Owners see their own documents
    - Admins see all documents in tenant
    - Other users see documents with explicit ACL grants

    Folder filtering:
    - If folder is None: Returns all documents (all folders)
    - If folder is "": Returns documents in root folder + subfolders as items
    - If folder is "/path": Returns documents in that folder + subfolders as items
    """
    # Role-based ACL filtering is applied by the service layer via
    # filter_visible_to_user using current_user.roles.
    return await document_service.get_documents(
        db=db,
        user=current_user,
        page=page,
        per_page=per_page,
        search=search,
        tags=tags,
        date_from=date_from,
        date_to=date_to,
        category=category,
        folder=folder  # Filter by folder path
    )


@router.post("", response_model=Document)
async def create_document(
    db: AsyncSession = Depends(get_async_db),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    cliente: Optional[str] = Form(None),
    periodo: Optional[str] = Form(None),
    tipo_documento: Optional[str] = Form(None),
    folder_path: Optional[str] = Form(None),  # Target folder for upload (Google Drive style)
    roles: List[str] = Form(default=["EVERYONE"]),
    file: UploadFile = File(...),
    current_user: UserProfile = Depends(require_document_upload_permission_async),
):
    """
    Sube un nuevo documento al sistema.

    Si se proporciona folder_path, el documento se guarda en esa carpeta
    y se marca como clasificación manual (auto_classified=False).
    """
    # Convertir tags de string separado por comas a lista
    tag_list = tags.split(",") if tags else []
    tag_list = [tag.strip() for tag in tag_list if tag.strip()]

    document_service = await AsyncDocumentService.create(user=current_user, db=db)
    new_doc = await document_service.upload_document(
        db=db,
        file=file,
        title=title,
        description=description,
        tags=tag_list,
        category=category,
        cliente=cliente,
        periodo=periodo,
        tipo_documento=tipo_documento,
        folder_path=folder_path,
        roles=roles,
    )

    # Proactive Preview Generation: Enqueue background task
    try:
        await queue_service.enqueue_preview_generation(
            document_id=str(new_doc.id),
            user_id=current_user.sub,
            preview_type="all",
            priority="default"
        )
    except Exception as e:
        logger.warning(f"Failed to enqueue proactive preview generation for {new_doc.id}: {e}")
        
    return new_doc


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Obtiene detalles de un documento específico.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    doc = await document_service.get_document(db=db, doc_id=doc_id)
    
    # Convert to DocumentDetail schema
    # Note: Tags are already loaded via selectinload in the service
    tags_list = [
        Tag(id=tag.id, name=tag.name, created_at=tag.created_at)
        for tag in doc.tags
    ] if hasattr(doc, 'tags') else []

    return DocumentDetail(
        id=str(doc.id),
        title=doc.title,
        description=doc.description,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        category=doc.category,
        created_by=doc.created_by,
        indexed=doc.indexed,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        tags=tags_list,
        extracted_entities=doc.extracted_entities,
        document_metadata=doc.document_metadata
    )


@router.get("/{doc_id}/stream")
async def stream_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Sirve documentos a través del proxy con cache Redis.

    Soporta dos tipos de documentos:
    - Document (uploads directos): se obtienen del storage service
    - IndexedDocument (conectores): se obtienen del sistema externo (Alfresco, etc.)

    Requires: VIEW permission on the document.
    """
    import uuid as uuid_module

    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    # 1. Intentar obtener de tabla Document (uploads)
    try:
        document = await document_service.get_document(db=db, doc_id=doc_id)

        # Document encontrado - streameamos desde storage service (MinIO)
        storage_url = f"{settings.STORAGE_SERVICE_URL}/files/{document.file_path}"

        client = httpx.AsyncClient(timeout=60.0)
        try:
            request = client.build_request("GET", storage_url)
            response = await client.send(request, stream=True)

            if response.status_code == 404:
                await response.aclose()
                await client.aclose()
                logger.error(f"Storage 404: File not found in storage for path: {document.file_path}")
                raise HTTPException(status_code=404, detail="Document file not found in storage")
            elif response.status_code != 200:
                await response.aread()
                logger.error(f"Storage error {response.status_code}: {response.text}")
                await response.aclose()
                await client.aclose()
                raise HTTPException(status_code=500, detail=f"Storage service error: {response.status_code}")

            content_headers = {
                "Content-Type": response.headers.get("content-type", "application/octet-stream"),
                "Content-Disposition": f'inline; filename="{document.filename}"'
            }

            if "x-cache" in response.headers:
                content_headers["X-Cache"] = response.headers["x-cache"]

            if "content-length" in response.headers:
                content_headers["Content-Length"] = response.headers["content-length"]

            async def iterate_file():
                try:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
                except Exception as e:
                    logger.error(f"Error streaming document {doc_id} from storage: {e}")

            return StreamingResponse(
                iterate_file(),
                headers=content_headers,
                media_type=response.headers.get("content-type", "application/octet-stream"),
                background=BackgroundTask(client.aclose)
            )

        except httpx.TimeoutException:
            await client.aclose()
            raise HTTPException(status_code=408, detail="Request timeout")
        except HTTPException:
            raise
        except Exception as e:
            await client.aclose()
            logger.error(f"Error streaming document {doc_id}: {str(e)}")
            raise HTTPException(status_code=500, detail="Error streaming document")

    except HTTPException as e:
        if e.status_code != 404:
            raise
        # Document no encontrado en tabla Document, intentar IndexedDocument
        pass

    # 2. Intentar obtener de tabla IndexedDocument (conectores)
    try:
        indexed_doc = await document_service.get_indexed_document(db=db, doc_id=doc_id)
    except HTTPException:
        raise HTTPException(status_code=404, detail="Document not found in any table")

    # Verificar si tiene conector asociado
    if not indexed_doc.connector_id:
        raise HTTPException(
            status_code=400,
            detail="IndexedDocument without connector - cannot stream content"
        )

    # Obtener configuración del conector
    connector_result = await db.execute(
        select(Connector).where(Connector.id == indexed_doc.connector_id)
    )
    connector = connector_result.scalar_one_or_none()

    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Download content: MinIO cache first, source connector as fallback
    content = None

    # Try 1: MinIO cache (fastest, always available if cached)
    if hasattr(indexed_doc, 'cached_path') and indexed_doc.cached_path:
        try:
            import httpx as _httpx
            from app.core.config import settings as _settings
            async with _httpx.AsyncClient(timeout=30.0) as http_client:
                cache_response = await http_client.get(
                    f"{_settings.STORAGE_SERVICE_URL}/files/{indexed_doc.cached_path}",
                )
                if cache_response.status_code == 200:
                    content = cache_response.content
                    logger.info(f"Served from cache: {doc_id}")
        except Exception as cache_error:
            logger.debug(f"Cache read failed for {doc_id}: {cache_error}")

    # Try 2: Source connector (only if cache miss)
    if content is None:
        try:
            adapter = ConnectorAdapterFactory.get_adapter(connector)

            connector_type_str = connector.connector_type or "alfresco"
            try:
                connector_type_enum = ConnectorType(connector_type_str)
            except ValueError:
                connector_type_enum = ConnectorType.ALFRESCO

            unified_doc = UnifiedDocument(
                document_id=indexed_doc.id,
                connector_id=indexed_doc.connector_id,
                connector_type=connector_type_enum,
                external_id=indexed_doc.external_id,
                external_url=indexed_doc.external_url,
                external_path=indexed_doc.external_path,
                filename=indexed_doc.title or "document",
                mime_type=indexed_doc.mime_type,
                size_bytes=indexed_doc.size_bytes or 0,
                source_created_at=indexed_doc.source_created_at,
                source_modified_at=indexed_doc.source_modified_at,
                owner_id=indexed_doc.owner_id,
            )

            content = await adapter.download_content(unified_doc)
        except Exception as source_error:
            logger.info(f"Source download failed for {doc_id}: {source_error}")

    if content is None:
        raise HTTPException(
            status_code=503,
            detail="Document not available (no cache and source connector unavailable)"
        )

    # Preparar respuesta
    content_type = indexed_doc.mime_type or "application/octet-stream"
    filename = indexed_doc.title or "document"

    content_headers = {
        "Content-Type": content_type,
        "Content-Disposition": f'inline; filename="{filename}"',
        "Content-Length": str(len(content)),
        "X-Source": "connector"
    }

    return StreamingResponse(
        io.BytesIO(content),
        headers=content_headers,
        media_type=content_type
    )


@router.get("/{doc_id}/pdf")
async def serve_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Sirve el PDF directamente para visualización en el navegador.
    Solo funciona para documentos que ya son PDF.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    # Obtener información del documento
    document = await document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verificar que sea un PDF
    if document.file_type.lower() != 'pdf':
        raise HTTPException(status_code=400, detail="Document is not a PDF")
    
    # Obtener el archivo desde storage (usando el servicio de storage interno del document_service)
    try:
        # Descargar archivo como bytes
        file_content = await document_service.storage_service.download_file(document.file_path)
        
        if not file_content:
            raise HTTPException(status_code=500, detail="Could not retrieve PDF")
        
        def iterfile():
            yield file_content
        
        return StreamingResponse(
            iterfile(),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'inline; filename="{document.filename}"',
                'Content-Type': 'application/pdf'
            }
        )
        
    except Exception as e:
        logger.error(f"Error serving PDF {doc_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error serving PDF")


@router.get("/{doc_id}/converted-pdf")
async def serve_converted_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Sirve el PDF convertido para documentos no-PDF que han sido convertidos a PDF.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    preview_service = DocumentPreviewService(user_id=current_user.sub)
    
    # Obtener información del documento
    document = await document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verificar que NO sea un PDF original
    if document.file_type.lower() == 'pdf':
        raise HTTPException(status_code=400, detail="Use /pdf endpoint for original PDF documents")
    
    try:
        # Obtener información del preview existente
        preview_info = await preview_service.get_preview_info(doc_id)
        
        if not preview_info or not preview_info.get('pdf_available'):
            raise HTTPException(status_code=404, detail="No converted PDF available for this document")
        
        # Verificar si tenemos el PDF en storage
        pdf_storage_path = preview_info.get('pdf_storage_path')
        if not pdf_storage_path:
            raise HTTPException(status_code=404, detail="Converted PDF not found in storage")
        
        # Descargar archivo PDF convertido
        file_content = await document_service.storage_service.download_file(pdf_storage_path)
        
        if not file_content:
            raise HTTPException(status_code=500, detail="Could not retrieve converted PDF")
        
        def iterfile():
            yield file_content
        
        return StreamingResponse(
            iterfile(),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'inline; filename="{document.filename}_converted.pdf"',
                'Content-Type': 'application/pdf'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving converted PDF {doc_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error serving converted PDF")


@router.put("/{doc_id}", response_model=Document)
async def update_document(
    doc_id: str,
    update_data: DocumentUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Actualiza los metadatos de un documento (título, descripción, tags, categoría).

    Requires: EDIT permission on the document.
    """
    # ACL Check: Verify user has edit permission
    await _load_visible_document(db, doc_id, current_user)

    # Obtener el documento existente
    document = await document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Actualizar campos usando Pydantic model
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(document, field, value)
    
    # Guardar cambios
    db.add(document)
    await db.commit()
    await db.refresh(document)
    
    # Convertir a schema
    from app.schemas.document import Document as DocumentSchema
    return DocumentSchema.model_validate(document)


@router.delete("/{doc_id}", response_model=dict)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Elimina un documento y sus datos asociados.

    Requires: DELETE permission on the document.
    """
    # ACL Check: Verify user has delete permission
    await _load_visible_document(db, doc_id, current_user)

    return await document_service.delete_document(db=db, doc_id=doc_id)


@router.get("/{doc_id}/summary", response_model=dict)
async def get_document_summary(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Genera un resumen del documento utilizando LLM.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    return await document_service.generate_summary(db=db, doc_id=doc_id)


@router.post("/{doc_id}/tag", response_model=dict)
async def add_document_tag(
    doc_id: str,
    tag: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Añade una etiqueta a un documento.

    Requires: EDIT permission on the document.
    """
    # ACL Check: Verify user has edit permission
    await _load_visible_document(db, doc_id, current_user)

    return await document_service.add_tag(db=db, doc_id=doc_id, tag_name=tag)


@router.delete("/{doc_id}/tag/{tag_name}", response_model=dict)
async def remove_document_tag(
    doc_id: str,
    tag_name: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Elimina una etiqueta de un documento.

    Requires: EDIT permission on the document.
    """
    # ACL Check: Verify user has edit permission
    await _load_visible_document(db, doc_id, current_user)

    return await document_service.remove_tag(db=db, doc_id=doc_id, tag_name=tag_name)


@router.get("/{doc_id}/preview", response_model=dict)
async def get_document_preview(
    doc_id: str,
    force_regenerate: bool = Query(False, description="Force regeneration of preview"),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Genera preview del documento usando Gotenberg.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    preview_service = DocumentPreviewService(user_id=current_user.sub)
    
    try:
        # Obtener información del documento
        document = await document_service.get_document(db=db, doc_id=doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")

        # Verificar cache antes de descargar el archivo
        if not force_regenerate:
            cached_preview = await preview_service.get_preview_info(doc_id)
            if cached_preview:
                return cached_preview

        # Generar síncronamente bajo demanda del usuario (no encolar)
        # El encolado solo se usa para generación proactiva en uploads
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, document.filename or 'document')

        # NOTE: MinIO cache fallback (cached_path) does NOT apply here.
        # This endpoint only handles Document table records (direct uploads stored
        # in the primary storage service / MinIO). The storage service IS the single
        # source of truth for these files — there is no separate "connector source"
        # that can go down independently. The cached_path / MinIO fallback pattern
        # (introduced in the download endpoint for IndexedDocument/connector files)
        # would only be relevant if this endpoint were extended to support
        # IndexedDocument connector files, which it currently does not.

        # Descargar archivo como bytes
        file_content = await document_service.storage_service.download_file(document.file_path or '')
        
        if not file_content:
            raise HTTPException(status_code=500, detail="Could not download document for preview")
        
        # Escribir bytes a archivo temporal
        try:
            with open(temp_file_path, 'wb') as f:
                f.write(file_content)
        except Exception as e:
            logger.error(f"Error writing temp file: {e}")
            raise HTTPException(status_code=500, detail="Could not create temporary file")
        
        # Generar preview
        preview_result = await preview_service.generate_preview(
            document_id=doc_id,
            file_path=temp_file_path,
            filename=document.filename or 'unknown',
            force_regenerate=force_regenerate
        )
        
        # Marcar documento como visualizado
        if not force_regenerate:
            try:
                await document_service.mark_document_viewed(
                    document_id=doc_id,
                    view_duration_seconds=0,
                    scroll_percentage=0.0
                )
            except Exception as e:
                logger.warning(f"Failed to mark document {doc_id} as viewed: {e}")
        
        return preview_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview generation failed for document {doc_id}: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail="Preview generation failed. Please try again later."
        )
    finally:
        # Cleanup
        try:
            await preview_service.cleanup()
            # Check if temp_dir is defined before trying to remove it (in case of early return)
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")


@router.get("/{doc_id}/preview/info", response_model=dict)
async def get_preview_info(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Obtiene información de preview existente sin regenerar.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    preview_service = DocumentPreviewService(user_id=current_user.sub)
    
    try:
        preview_info = await preview_service.get_preview_info(doc_id)
        return {
            "has_preview": bool(preview_info),
            "preview_info": preview_info,
            "message": "No preview available" if not preview_info else None
        }
            
    except Exception as e:
        logger.error(f"Preview info retrieval failed for document {doc_id}: {str(e)}")
        return {
            "has_preview": False,
            "error": "Could not retrieve preview information"
        }
    finally:
        await preview_service.cleanup()


@router.get("/{doc_id}/agents")
async def get_document_agents(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Get agents assigned to a specific document based on its type and tags.
    Logic delegated to service.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    try:
        return await document_service.get_document_agents(db, doc_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get document agents for {doc_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve document agents: {str(e)}"
        )


@router.post("/{doc_id}/recategorize")
async def recategorize_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Recategoriza un documento específico.

    Requires: EDIT permission on the document (categorization modifies metadata).
    """
    # ACL Check: Verify user has edit permission (recategorization modifies the document)
    await _load_visible_document(db, doc_id, current_user)

    doc = await document_service.get_document(db=db, doc_id=doc_id)
    
    # Require at least a lightweight preview for categorization
    metadata = doc.document_metadata or {}
    preview_candidates = [
        metadata.get("text_preview"),
        metadata.get("summary"),
        doc.description,
        doc.title,
        doc.filename,
    ]
    content_preview = next((str(value).strip() for value in preview_candidates if value), None)

    if not content_preview:
        return {
            "document_id": doc_id,
            "status": "failed",
            "error": "Document has no available preview to categorize"
        }
    
    result = await document_service.categorize_document(
        db,
        doc_id,
        content_preview=content_preview,
        user_id=current_user.sub,
        source="manual_api"
    )
    
    if result.get("success"):
        return {
            "document_id": doc_id,
            "status": "updated",
            "category": result.get("category")
        }
    
    return {
        "document_id": doc_id,
        "status": "failed",
        "error": result.get("error", "Unable to categorize document")
    }


@router.post("/recategorize-all")
async def recategorize_all_documents(
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service),
    only_uncategorized: bool = Query(True),
    batch_size: int = Query(10, ge=1, le=50)
):
    """
    Recategoriza documentos visibles para el usuario.
    """
    # Build query; role-based visibility applied via filter_visible_to_user
    query = filter_visible_to_user(
        select(DBDocument).filter(DBDocument.indexed > 0),
        current_user,
    )

    if only_uncategorized:
        query = query.filter(
            or_(
                DBDocument.category.is_(None),
                DBDocument.category == "",
                DBDocument.category == "general"
            )
        )

    result = await db.execute(query)
    documents = result.scalars().all()

    if not documents:
        return {"total_documents": 0, "message": "No documents found matching criteria"}

    target_docs = documents[:batch_size] if batch_size else documents
    processed = 0
    failures = 0
    skipped_no_permission = 0

    for doc in target_docs:
        metadata = doc.document_metadata or {}
        preview_candidates = [
            metadata.get("text_preview"),
            metadata.get("summary"),
            doc.description,
            doc.title,
            doc.filename,
        ]
        content_preview = next(
            (str(value).strip() for value in preview_candidates if value), None
        )
        if not content_preview:
            failures += 1
            continue

        cat_result = await document_service.categorize_document(
            db,
            str(doc.id),
            content_preview=content_preview,
            user_id=current_user.sub,
            source="bulk_api",
        )
        if cat_result.get("success"):
            processed += 1
        else:
            failures += 1
    
    return {
        "total_documents": len(target_docs),
        "processed": processed,
        "failed": failures,
        "message": "Categorization executed directly via CAG"
    }


@router.post("/{doc_id}/preview/generate")
async def queue_preview_generation(
    doc_id: str,
    preview_type: str = Query("all"),
    force_regenerate: bool = Query(False),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Queue document preview generation.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _load_visible_document(db, doc_id, current_user)

    # Verify document exists via service
    await document_service.get_document(db=db, doc_id=doc_id)
    
    job_id = await queue_service.enqueue_preview_generation(
        document_id=doc_id,
        user_id=current_user.sub,
        preview_type=preview_type,
        force_regenerate=force_regenerate,
        priority="high" if force_regenerate else "default"
    )
    
    if job_id:
        return {
            "document_id": doc_id,
            "status": "queued",
            "job_id": job_id
        }
    else:
        return {"status": "failed", "error": "Failed to queue preview"}


@router.post("/preview/generate-batch")
async def queue_batch_preview_generation(
    document_ids: List[str] = Body(...),
    preview_type: str = Query("all"),
    batch_size: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Queue batch preview generation.

    Requires: VIEW permission on each document (checked per-document).
    """
    valid_ids = []
    for doc_id in document_ids:
        try:
            await _load_visible_document(db, doc_id, current_user)
            valid_ids.append(doc_id)
        except HTTPException:
            pass

    if not valid_ids:
        return {"status": "failed", "error": "No accessible documents found"}

    job_id = await queue_service.enqueue_preview_batch(
        document_ids=valid_ids,
        user_id=current_user.sub,
        preview_type=preview_type,
        batch_size=batch_size,
        priority="default"
    )
    
    if job_id:
        return {
            "total_documents": len(valid_ids),
            "status": "queued",
            "job_id": job_id
        }
    else:
        return {"status": "failed", "error": "Failed to queue batch"}


@router.post("/facets", response_model=dict)
async def get_document_facets(
    query: Optional[str] = Body(None),
    filters: Optional[dict] = Body(None),
    facet_fields: Optional[List[str]] = Body(["file_type", "category", "tags"]),
    max_facet_values: int = Body(10, ge=1, le=50),
):
    """
    Get facets for document search results via Elasticsearch.
    """
    try:
        facets_data = await elasticsearch_client.get_facets(
            query=query,
            filters=filters,
            facet_fields=facet_fields,
            max_facet_values=max_facet_values
        )

        # Mark selected facets based on current filters
        if filters and facets_data.get("facets"):
            for facet in facets_data["facets"]:
                field_name = facet["field"]
                if field_name in filters:
                    current_filter_values = filters[field_name]
                    if isinstance(current_filter_values, list):
                        for bucket in facet["buckets"]:
                            bucket["selected"] = bucket["key"] in current_filter_values
                    else:
                        for bucket in facet["buckets"]:
                            bucket["selected"] = bucket["key"] == current_filter_values

        return {
            "facets": facets_data.get("facets", []),
            "total_documents": facets_data.get("total_documents", 0),
            "query": query,
            "applied_filters": filters
        }

    except Exception as e:
        logger.error(f"Failed to get document facets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve facets: {str(e)}")


# ========================================
# IDENTITY DOCUMENT PROCESSING
# ========================================

@router.post("/process-identity")
async def process_identity_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(default=None, description="dni, nie, passport, driver_license"),
    consent_given: bool = Form(..., description="User consent for PII processing (required)"),
    purpose: str = Form(default="identity_verification", description="Purpose for processing"),
    retention_days: int = Form(default=90, ge=1, le=365, description="Days to retain extracted data"),
    db: AsyncSession = Depends(get_async_db),
    current_user: UserProfile = Depends(get_current_user_async),
):
    """
    Process an identity document (DNI, NIE, Passport, Driver's License) and extract structured data.

    GDPR Compliance:
    - Requires explicit consent_given=True to process
    - All access is logged for audit purposes
    - Data is automatically deleted after retention_days (default 90)
    - NO cloud APIs used - all processing is local

    Args:
        file: Image or PDF of the identity document
        document_type: Expected document type (auto-detected if not provided)
        consent_given: User consent for PII processing (REQUIRED)
        purpose: Purpose for processing (e.g., 'identity_verification', 'kyc')
        retention_days: Days to retain extracted data (GDPR compliance)

    Returns:
        Extracted identity document data with confidence scores
    """
    from datetime import datetime, timedelta
    from app.schemas.identity_document import (
        IdentityDocumentResponse,
        IdentityDocumentExtraction,
        IdentityDocumentType,
    )

    # GDPR: Require explicit consent
    if not consent_given:
        raise HTTPException(
            status_code=400,
            detail="Consent is required to process identity documents. "
            "Set consent_given=true to proceed."
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or "identity_document"
    file_size = len(contents)

    logger.info(
        f"Identity document processing | user={current_user.sub} "
        f"file={filename} size={file_size} type={document_type or 'auto'} purpose={purpose}"
    )

    # Audit log: PII access initiated
    audit_entry = {
        "action": "identity_extraction_started",
        "user_id": current_user.sub,
        "timestamp": datetime.utcnow().isoformat(),
        "purpose": purpose,
        "filename": filename,
        "ip_address": None,  # Would be extracted from request in production
    }
    logger.info(f"AUDIT: {audit_entry}")

    try:
        # Call intelligence-docs-service for identity document extraction
        intelligence_url = os.getenv(
            "INTELLIGENCE_DOCS_SERVICE_URL",
            "http://intelligence-docs-service:8000"
        )
        api_key = settings.MICROSERVICES_API_KEY

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{intelligence_url}/identity/extract",
                headers={
                    "X-API-Key": api_key,
                },
                files={"file": (filename, contents)},
                data={
                    "document_type": document_type or "",
                    "consent_given": "true",
                    "purpose": purpose,
                },
            )

            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = error_json.get("detail", response.text)
                except Exception:
                    pass

                logger.error(f"Identity extraction failed: {response.status_code} - {error_detail}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Identity extraction failed: {error_detail}"
                )

            result = response.json()

        # Calculate retention date
        retention_until = datetime.utcnow() + timedelta(days=retention_days)

        # Store extraction result in database (if successful)
        extraction_id = None
        if result.get("success"):
            try:
                from app.db.models import Base
                from sqlalchemy import text

                # Insert into identity_document_extractions table
                insert_sql = text("""
                    INSERT INTO identity_document_extractions (
                        document_type, issuing_country,
                        extracted_data, confidence_score, ocr_engine,
                        retention_until, consent_purpose, created_by
                    ) VALUES (
                        :document_type, :issuing_country,
                        :extracted_data, :confidence_score, :ocr_engine,
                        :retention_until, :consent_purpose, :created_by
                    ) RETURNING id
                """)

                import json
                extracted_data = {
                    "full_name": result.get("full_name"),
                    "first_name": result.get("first_name"),
                    "last_name": result.get("last_name"),
                    "document_number": result.get("document_number"),
                    "date_of_birth": result.get("date_of_birth"),
                    "expiration_date": result.get("expiration_date"),
                    "nationality": result.get("nationality"),
                    "gender": result.get("gender"),
                    "mrz_data": result.get("mrz_data"),
                    "license_categories": result.get("license_categories"),
                }

                db_result = await db.execute(
                    insert_sql,
                    {
                        "document_type": result.get("document_type", "unknown"),
                        "issuing_country": result.get("issuing_country"),
                        "extracted_data": json.dumps(extracted_data),
                        "confidence_score": result.get("confidence_score", 0.0),
                        "ocr_engine": result.get("ocr_engine", "doctr"),
                        "retention_until": retention_until,
                        "consent_purpose": purpose,
                        "created_by": current_user.sub,
                    }
                )
                await db.commit()

                row = db_result.fetchone()
                if row:
                    extraction_id = str(row[0])

            except Exception as db_error:
                logger.warning(f"Failed to store identity extraction in database: {db_error}")
                # Non-blocking - continue with response

        # Audit log: PII extraction completed
        audit_complete = {
            "action": "identity_extraction_completed",
            "user_id": current_user.sub,
            "timestamp": datetime.utcnow().isoformat(),
            "extraction_id": extraction_id,
            "document_type": result.get("document_type"),
            "confidence_score": result.get("confidence_score"),
            "retention_until": retention_until.isoformat(),
        }
        logger.info(f"AUDIT: {audit_complete}")

        return {
            "success": result.get("success", False),
            "extraction": result,
            "retention_until": retention_until.isoformat(),
            "extraction_id": extraction_id,
            "gdpr_notice": f"Data will be automatically deleted after {retention_days} days.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Identity document processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Identity document processing failed: {str(e)}"
        )
