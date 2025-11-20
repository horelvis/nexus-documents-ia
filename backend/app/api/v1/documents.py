from typing import List, Optional, Dict, Any
import os
import datetime
import logging
import io
import shutil
import tempfile

import httpx
from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, Body, HTTPException
from fastapi.responses import StreamingResponse
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

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=dict)
async def list_documents(
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    category: Optional[str] = Query(None)
):
    """
    Obtiene lista paginada de documentos con filtros opcionales.
    """
    return await document_service.get_documents(
        db=db,
        page=page,
        per_page=per_page,
        search=search,
        tags=tags,
        date_from=date_from,
        date_to=date_to,
        category=category
    )


@router.post("", response_model=Document)
async def create_document(
    db: AsyncSession = Depends(get_async_db),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
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
    """
    # Convertir tags de string separado por comas a lista
    tag_list = tags.split(",") if tags else []
    tag_list = [tag.strip() for tag in tag_list if tag.strip()]
    
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id), db=db)
    return await document_service.upload_document(
        db=db,
        file=file,
        title=title,
        description=description,
        tags=tag_list,
        category=category
    )


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Obtiene detalles de un documento específico.
    """
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
        tenant_id=doc.tenant_id,
        created_by=doc.created_by,
        indexed=doc.indexed,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        tags=tags_list,
        extracted_entities=doc.extracted_entities
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
    """
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
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            request = client.build_request("GET", storage_url, headers=headers)
            response = await client.send(request, stream=True)
            
            if response.status_code == 404:
                await response.aclose()
                logger.error(f"Storage 404: File not found in storage for path: {document.file_path}")
                raise HTTPException(status_code=404, detail="Document file not found in storage")
            elif response.status_code != 200:
                await response.aclose()
                logger.error(f"Storage error {response.status_code}: {response.text}")
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
            
            return StreamingResponse(
                response.aiter_bytes(chunk_size=8192),
                headers=content_headers,
                media_type=response.headers.get("content-type", "application/octet-stream"),
                background=None  # Let FastAPI handle closing the response
            )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
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
    """
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
    """
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
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Actualiza los metadatos de un documento (título, descripción, tags, categoría).
    """
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
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Elimina un documento y sus datos asociados.
    """
    return await document_service.delete_document(db=db, doc_id=doc_id)


@router.get("/{doc_id}/summary", response_model=dict)
async def get_document_summary(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Genera un resumen del documento utilizando LLM.
    """
    return await document_service.generate_summary(db=db, doc_id=doc_id)


@router.post("/{doc_id}/tag", response_model=dict)
async def add_document_tag(
    doc_id: str,
    tag: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Añade una etiqueta a un documento.
    """
    return await document_service.add_tag(db=db, doc_id=doc_id, tag_name=tag)


@router.delete("/{doc_id}/tag/{tag_name}", response_model=dict)
async def remove_document_tag(
    doc_id: str,
    tag_name: str,
    db: AsyncSession = Depends(get_async_db),
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Elimina una etiqueta de un documento.
    """
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
    """
    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
    try:
        # Obtener información del documento
        document = await document_service.get_document(db=db, doc_id=doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Descargar archivo para procesamiento usando el storage interno del servicio
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
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")


@router.get("/{doc_id}/preview/info", response_model=dict)
async def get_preview_info(
    doc_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Obtiene información de preview existente sin regenerar.
    """
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
    document_service: AsyncDocumentService = Depends(get_document_service)
):
    """
    Get agents assigned to a specific document based on its type and tags.
    Logic delegated to service.
    """
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
    """
    doc = await document_service.get_document(db=db, doc_id=doc_id)
    
    # Check if document has content
    if not doc.content:
        return {
            "document_id": doc_id,
            "status": "failed",
            "error": "Document has no extracted content"
        }
    
    job_id = await queue_service.enqueue_document_categorization(
        document_id=doc_id,
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        priority="high"
    )
    
    if job_id:
        return {
            "document_id": doc_id,
            "status": "queued",
            "job_id": job_id,
            "message": "Document queued for recategorization"
        }
    else:
        return {"status": "failed", "error": "Failed to queue document"}


@router.post("/recategorize-all")
async def recategorize_all_documents(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    only_uncategorized: bool = Query(True),
    batch_size: int = Query(10, ge=1, le=50)
):
    """
    Recategoriza todos los documentos del tenant.
    """
    query = select(DBDocument.id).filter(
        DBDocument.tenant_id == tenant_id,
        DBDocument.indexed > 0
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
    document_ids = [str(row[0]) for row in result.fetchall()]
    
    if not document_ids:
        return {"total_documents": 0, "message": "No documents found"}
    
    job_id = await queue_service.enqueue_batch_categorization(
        document_ids=document_ids,
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        batch_size=batch_size,
        priority="default"
    )
    
    if job_id:
        return {
            "total_documents": len(document_ids),
            "status": "queued",
            "job_id": job_id
        }
    else:
        return {"status": "failed", "error": "Failed to queue documents"}


@router.get("/categorization/job/{job_id}")
async def get_categorization_job_status(job_id: str):
    """
    Obtiene el estado de un trabajo de categorización.
    """
    status = await queue_service.get_job_status(job_id)
    if status:
        return status
    raise HTTPException(status_code=404, detail="Job not found")


@router.get("/categorization/queue-stats")
async def get_categorization_queue_stats():
    """
    Obtiene estadísticas de la cola de categorización.
    """
    stats = await queue_service.get_queue_stats()
    return {
        "queues": stats,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
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
    """
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
    """
    valid_ids = []
    for doc_id in document_ids:
        try:
            await document_service.get_document(db=db, doc_id=doc_id)
            valid_ids.append(doc_id)
        except:
            pass
    
    if not valid_ids:
        return {"status": "failed", "error": "No valid documents found"}
    
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