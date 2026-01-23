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
from app.services.document_acl_service import DocumentACLService
from app.services.queue_service import queue_service
from app.services.elasticsearch_client import elasticsearch_client
from app.services.storage_service import StorageService
from app.core.config import settings

from app.api.async_dependencies import (
    get_current_user_async,
    get_current_tenant_id_async,
    require_document_upload_permission_async,
    get_document_service,
    get_async_db
)
from app.db.models import User, Document as DBDocument, Tag
from app.schemas.document import (
    Document, DocumentDetail,
    UploadRequest, DocumentUpdate
)
from app.schemas.document_acl import Permission

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================================
# ACL CHECK HELPER
# ========================================

async def _check_document_permission(
    db: AsyncSession,
    doc_id: str,
    permission: Permission,
    current_user: User,
    tenant_id: str,
) -> None:
    """
    Check if user has the required permission on a document.

    Raises HTTPException 403 if permission is denied.
    """
    acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))
    has_permission = await acl_service.check_permission(
        db, UUID(doc_id), permission, current_user
    )
    if not has_permission:
        permission_name = permission.value
        raise HTTPException(
            status_code=403,
            detail=f"You don't have {permission_name} permission on this document"
        )


@router.get("", response_model=dict)
async def list_documents(
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
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
    # When searching with Weaviate, let Weaviate handle ACL filtering directly
    # (Weaviate receives user_id, user_role_ids, is_admin for filtering)
    # Only do PostgreSQL ACL check for non-search requests
    accessible_doc_ids = None
    if not search or not search.strip():
        acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))
        accessible_doc_ids = await acl_service.get_documents_user_can_access(
            db, permission=Permission.VIEW, user=current_user
        )

    return await document_service.get_documents(
        db=db,
        page=page,
        per_page=per_page,
        search=search,
        tags=tags,
        date_from=date_from,
        date_to=date_to,
        category=category,
        document_ids=accessible_doc_ids,  # None for search (Weaviate handles ACL)
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
    file: UploadFile = File(...),
    current_user: User = Depends(require_document_upload_permission_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    # Note: We manually create service here because require_document_upload_permission_async
    # might consume the body stream if not handled carefully, but here we use Form/File
    # We can use the factory manually or add a dependency that doesn't conflict.
    # For safety with UploadFile, we'll construct it manually to ensure strict control.
):
    """
    Sube un nuevo documento al sistema.

    Si se proporciona folder_path, el documento se guarda en esa carpeta
    y se marca como clasificación manual (auto_classified=False).
    """
    # Convertir tags de string separado por comas a lista
    tag_list = tags.split(",") if tags else []
    tag_list = [tag.strip() for tag in tag_list if tag.strip()]

    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id), db=db)
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
        folder_path=folder_path  # Pass folder for manual classification
    )
    
    # Proactive Preview Generation: Enqueue background task
    try:
        await queue_service.enqueue_preview_generation(
            document_id=str(new_doc.id),
            tenant_id=tenant_id,
            user_id=str(current_user.id),
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Obtiene detalles de un documento específico.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    doc = await document_service.get_document(db=db, doc_id=doc_id)
    
    # Convert to DocumentDetail schema
    # Note: Tags are already loaded via selectinload in the service
    tags_list = [
        Tag(id=tag.id, name=tag.name, tenant_id=tag.tenant_id, created_at=tag.created_at) 
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
        tenant_id=doc.tenant_id,
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Sirve documentos a través del proxy con cache Redis.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    # Obtener información del documento
    document = await document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Llamar al storage service proxy endpoint
    storage_url = f"{settings.STORAGE_SERVICE_URL}/api/v1/storage/proxy/{document.file_path}"
    
    headers = {
        "X-API-Key": settings.STORAGE_API_KEY,
        "X-Tenant-ID": tenant_id,
        "X-User-ID": str(current_user.id)
    }
    
    client = httpx.AsyncClient(timeout=60.0)
    try:
        request = client.build_request("GET", storage_url, headers=headers)
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
        
        # Preparar headers para el cliente
        content_headers = {
            "Content-Type": response.headers.get("content-type", "application/octet-stream"),
            "Content-Disposition": f'inline; filename="{document.filename}"'
        }
        
        # Añadir headers de cache info si están disponibles
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
                # Stop yielding to close the stream gracefully from client perspective
                # (although it will look truncated)
        
        return StreamingResponse(
            iterate_file(),
            headers=content_headers,
            media_type=response.headers.get("content-type", "application/octet-stream"),
            background=BackgroundTask(client.aclose)
        )
            
    except httpx.TimeoutException:
        await client.aclose()
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
        await client.aclose()
        logger.error(f"Error streaming document {doc_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error streaming document")


@router.get("/{doc_id}/pdf")
async def serve_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Sirve el PDF directamente para visualización en el navegador.
    Solo funciona para documentos que ya son PDF.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Sirve el PDF convertido para documentos no-PDF que han sido convertidos a PDF.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Actualiza los metadatos de un documento (título, descripción, tags, categoría).

    Requires: EDIT permission on the document.
    """
    # ACL Check: Verify user has edit permission
    await _check_document_permission(db, doc_id, Permission.EDIT, current_user, tenant_id)

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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Elimina un documento y sus datos asociados.

    Requires: DELETE permission on the document.
    """
    # ACL Check: Verify user has delete permission
    await _check_document_permission(db, doc_id, Permission.DELETE, current_user, tenant_id)

    return await document_service.delete_document(db=db, doc_id=doc_id)


@router.get("/{doc_id}/summary", response_model=dict)
async def get_document_summary(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Genera un resumen del documento utilizando LLM.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    return await document_service.generate_summary(db=db, doc_id=doc_id)


@router.post("/{doc_id}/tag", response_model=dict)
async def add_document_tag(
    doc_id: str,
    tag: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Añade una etiqueta a un documento.

    Requires: EDIT permission on the document.
    """
    # ACL Check: Verify user has edit permission
    await _check_document_permission(db, doc_id, Permission.EDIT, current_user, tenant_id)

    return await document_service.add_tag(db=db, doc_id=doc_id, tag_name=tag)


@router.delete("/{doc_id}/tag/{tag_name}", response_model=dict)
async def remove_document_tag(
    doc_id: str,
    tag_name: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Elimina una etiqueta de un documento.

    Requires: EDIT permission on the document.
    """
    # ACL Check: Verify user has edit permission
    await _check_document_permission(db, doc_id, Permission.EDIT, current_user, tenant_id)

    return await document_service.remove_tag(db=db, doc_id=doc_id, tag_name=tag_name)


@router.get("/{doc_id}/preview", response_model=dict)
async def get_document_preview(
    doc_id: str,
    force_regenerate: bool = Query(False, description="Force regeneration of preview"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Genera preview del documento usando Gotenberg.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Obtiene información de preview existente sin regenerar.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Get agents assigned to a specific document based on its type and tags.
    Logic delegated to service.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Recategoriza un documento específico.

    Requires: EDIT permission on the document (categorization modifies metadata).
    """
    # ACL Check: Verify user has edit permission (recategorization modifies the document)
    await _check_document_permission(db, doc_id, Permission.EDIT, current_user, tenant_id)

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
        tenant_id=tenant_id,
        user_id=str(current_user.id),
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service),
    only_uncategorized: bool = Query(True),
    batch_size: int = Query(10, ge=1, le=50)
):
    """
    Recategoriza todos los documentos del tenant.

    Requires: EDIT permission on each document (only processes documents user can edit).
    """
    # ACL: Get documents user has EDIT permission on
    acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))
    editable_doc_ids = await acl_service.get_documents_user_can_access(
        db, permission=Permission.EDIT, user=current_user
    )

    if not editable_doc_ids:
        return {"total_documents": 0, "message": "No editable documents found"}

    # Build query with ACL filter
    query = select(DBDocument).filter(
        DBDocument.tenant_id == tenant_id,
        DBDocument.indexed > 0,
        DBDocument.id.in_(editable_doc_ids)  # ACL filter
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
            tenant_id=tenant_id,
            user_id=str(current_user.id),
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Queue document preview generation.

    Requires: VIEW permission on the document.
    """
    # ACL Check: Verify user has view permission
    await _check_document_permission(db, doc_id, Permission.VIEW, current_user, tenant_id)

    # Verify document exists via service
    await document_service.get_document(db=db, doc_id=doc_id)
    
    job_id = await queue_service.enqueue_preview_generation(
        document_id=doc_id,
        tenant_id=tenant_id,
        user_id=str(current_user.id),
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Queue batch preview generation.

    Requires: VIEW permission on each document (checked per-document).
    """
    valid_ids = []
    acl_service = DocumentACLService(tenant_id=tenant_id, user_id=str(current_user.id))

    for doc_id in document_ids:
        try:
            # Verify document exists
            await document_service.get_document(db=db, doc_id=doc_id)
            # ACL Check: Verify user has view permission
            has_permission = await acl_service.check_permission(
                db, UUID(doc_id), Permission.VIEW, current_user
            )
            if has_permission:
                valid_ids.append(doc_id)
        except:
            pass

    if not valid_ids:
        return {"status": "failed", "error": "No accessible documents found"}
    
    job_id = await queue_service.enqueue_preview_batch(
        document_ids=valid_ids,
        tenant_id=tenant_id,
        user_id=str(current_user.id),
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
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get facets for document search results via Elasticsearch.
    """
    try:
        facets_data = await elasticsearch_client.get_facets(
            tenant_id=tenant_id,
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
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
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
        f"Identity document processing | user={current_user.id} tenant={tenant_id} "
        f"file={filename} size={file_size} type={document_type or 'auto'} purpose={purpose}"
    )

    # Audit log: PII access initiated
    audit_entry = {
        "action": "identity_extraction_started",
        "user_id": str(current_user.id),
        "tenant_id": tenant_id,
        "timestamp": datetime.utcnow().isoformat(),
        "purpose": purpose,
        "filename": filename,
        "ip_address": None,  # Would be extracted from request in production
    }
    logger.info(f"AUDIT: {audit_entry}")

    try:
        # Call langextract-service for identity document extraction
        langextract_url = os.getenv(
            "LANGEXTRACT_SERVICE_URL",
            "http://langextract-service:8000"
        )
        api_key = settings.MICROSERVICES_API_KEY

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{langextract_url}/api/v1/extraction/identity/extract",
                headers={
                    "X-API-Key": api_key,
                    "X-Tenant-ID": tenant_id,
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
                        tenant_id, document_type, issuing_country,
                        extracted_data, confidence_score, ocr_engine,
                        retention_until, consent_purpose, created_by
                    ) VALUES (
                        :tenant_id, :document_type, :issuing_country,
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
                        "tenant_id": tenant_id,
                        "document_type": result.get("document_type", "unknown"),
                        "issuing_country": result.get("issuing_country"),
                        "extracted_data": json.dumps(extracted_data),
                        "confidence_score": result.get("confidence_score", 0.0),
                        "ocr_engine": result.get("ocr_engine", "doctr"),
                        "retention_until": retention_until,
                        "consent_purpose": purpose,
                        "created_by": str(current_user.id),
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
            "user_id": str(current_user.id),
            "tenant_id": tenant_id,
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
