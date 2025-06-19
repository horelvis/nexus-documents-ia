from typing import List, Optional
import os
import datetime

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, Body, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.api.async_dependencies import (
    get_current_user_async, 
    get_current_active_user_async,
    get_current_tenant_id_async,
    require_document_upload_permission_async
)
from app.db.async_database import get_async_db
from app.db.models import User
from app.schemas.document import (
    Document, DocumentDetail,
    UploadRequest
)
from app.services.document_service import DocumentService
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=dict)
async def list_documents(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
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
    from app.services.async_document_service import AsyncDocumentService
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
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
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Sube un nuevo documento al sistema.
    """
    # Convertir tags de string separado por comas a lista
    tag_list = tags.split(",") if tags else []
    tag_list = [tag.strip() for tag in tag_list if tag.strip()]
    
    from app.services.async_document_service import AsyncDocumentService
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
    return await document_service.upload_document(
        db=db,
        file=file,
        title=title,
        description=description,
        tags=tag_list,
        category=category
    )


# Upload signed URL endpoint removed for security reasons
# Use direct upload via /upload endpoint instead


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Obtiene detalles de un documento específico.
    """
    from app.services.async_document_service import AsyncDocumentService
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
    doc = await document_service.get_document(db=db, doc_id=doc_id)
    
    # Convert to DocumentDetail schema
    return DocumentDetail(
        id=str(doc.id),
        title=doc.title,
        description=doc.description,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
        tags=[{"id": str(tag.id), "name": tag.name} for tag in doc.tags] if hasattr(doc, 'tags') else [],
        created_by={
            "id": str(doc.creator.id),
            "email": doc.creator.email,
            "full_name": doc.creator.full_name
        } if doc.creator else None,
        category=doc.category if hasattr(doc, 'category') else None,
        indexed=doc.indexed
    )


# Signed URL endpoint removed for security reasons
# Use /stream endpoint instead for all document access


@router.get("/{doc_id}/stream")
async def stream_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Sirve documentos a través del proxy con cache Redis.
    Reemplaza tanto /pdf como /download-url con una sola ruta optimizada.
    """
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    import httpx
    
    from app.services.async_document_service import AsyncDocumentService
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
    
    # Obtener información del documento
    document = await document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Llamar al storage service proxy endpoint
    from app.core.config import settings
    storage_url = f"{settings.STORAGE_SERVICE_URL}/api/v1/storage/proxy/{document.file_path}"
    
    headers = {
        "X-API-Key": settings.STORAGE_API_KEY,
        "X-Tenant-ID": tenant_id,
        "X-User-ID": str(current_user.id)
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(storage_url, headers=headers)
            
            if response.status_code == 404:
                logger.error(f"Storage 404: File not found in storage for path: {document.file_path}")
                raise HTTPException(status_code=404, detail="Document file not found in storage")
            elif response.status_code != 200:
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
            
            # Stream la respuesta
            async def stream_response():
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk
            
            return StreamingResponse(
                stream_response(),
                headers=content_headers,
                media_type=response.headers.get("content-type", "application/octet-stream")
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
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Sirve el PDF directamente para visualización en el navegador.
    Solo funciona para documentos que ya son PDF.
    """
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    
    from app.services.async_document_service import AsyncDocumentService
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
    
    # Obtener información del documento
    document = await document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verificar que sea un PDF
    if document.file_type.lower() != 'pdf':
        raise HTTPException(status_code=400, detail="Document is not a PDF")
    
    # Obtener el archivo desde storage
    from app.services.storage_service import StorageService
    storage_service = StorageService(tenant_id, str(current_user.id))
    
    try:
        # Descargar archivo como bytes
        file_content = storage_service.download_file(document.file_path)
        
        if not file_content:
            raise HTTPException(status_code=500, detail="Could not retrieve PDF")
        
        # Crear streaming response directamente desde bytes
        from io import BytesIO
        
        def iterfile():
            yield file_content
        
        response = StreamingResponse(
            iterfile(),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'inline; filename="{document.filename}"',
                'Content-Type': 'application/pdf'
            }
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error serving PDF {doc_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error serving PDF")


@router.get("/{doc_id}/converted-pdf")
async def serve_converted_pdf(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Sirve el PDF convertido para documentos no-PDF que han sido convertidos a PDF.
    """
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    from app.services.document_preview_service import DocumentPreviewService
    
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
    # Obtener información del documento
    document = document_service.get_document(db=db, doc_id=doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verificar que NO sea un PDF original (para PDFs originales usar /pdf endpoint)
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
        
        # Obtener el archivo PDF desde storage
        from app.services.storage_service import StorageService
        storage_service = StorageService(tenant_id, str(current_user.id))
        
        # Descargar archivo PDF convertido
        file_content = storage_service.download_file(pdf_storage_path)
        
        if not file_content:
            raise HTTPException(status_code=500, detail="Could not retrieve converted PDF")
        
        # Crear streaming response
        def iterfile():
            yield file_content
        
        response = StreamingResponse(
            iterfile(),
            media_type='application/pdf',
            headers={
                'Content-Disposition': f'inline; filename="{document.filename}_converted.pdf"',
                'Content-Type': 'application/pdf'
            }
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving converted PDF {doc_id}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error serving converted PDF")


@router.delete("/{doc_id}", response_model=dict)
async def delete_document(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Elimina un documento y sus datos asociados.
    """
    from app.services.async_document_service import AsyncDocumentService
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
    return await document_service.delete_document(db=db, doc_id=doc_id)


@router.get("/{doc_id}/summary", response_model=dict)
async def get_document_summary(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Genera un resumen del documento utilizando LLM.
    """
    # TODO: Implement async version of generate_summary
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.generate_summary(db=db,doc_id=doc_id)


@router.post("/{doc_id}/tag", response_model=dict)
async def add_document_tag(
    doc_id: str,
    tag: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Añade una etiqueta a un documento.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.add_tag(db=db, doc_id=doc_id, tag_name=tag) # Pass db


@router.delete("/{doc_id}/tag/{tag_name}", response_model=dict)
async def remove_document_tag(
    doc_id: str,
    tag_name: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Elimina una etiqueta de un documento.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.remove_tag(db=db, doc_id=doc_id, tag_name=tag_name) # Pass db


@router.get("/{doc_id}/preview", response_model=dict)
async def get_document_preview(
    doc_id: str,
    force_regenerate: bool = Query(False, description="Force regeneration of preview"),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Genera preview del documento usando Gotenberg.
    Soporta conversión de documentos Office, texto, markdown y más a PDF.
    """
    from app.services.document_preview_service import DocumentPreviewService
    
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
    try:
        # Obtener información del documento
        document = document_service.get_document(db=db, doc_id=doc_id)
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Descargar archivo para procesamiento
        from app.services.storage_service import StorageService
        storage_service = StorageService(tenant_id, str(current_user.id))
        
        import tempfile
        import os
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, document.filename or 'document')
        
        # Descargar archivo como bytes
        file_content = storage_service.download_file(document.file_path or '')
        
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
        # Cleanup preview service resources
        try:
            await preview_service.cleanup()
        except Exception as e:
            logger.warning(f"Preview service cleanup failed: {e}")
        
        # Cleanup temp directory
        try:
            import shutil
            if 'temp_dir' in locals():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Temp directory cleanup failed: {e}")


@router.get("/{doc_id}/preview/info", response_model=dict)
async def get_preview_info(
    doc_id: str,
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Obtiene información de preview existente sin regenerar.
    """
    from app.services.document_preview_service import DocumentPreviewService
    
    preview_service = DocumentPreviewService(tenant_id=tenant_id, user_id=str(current_user.id))
    
    try:
        preview_info = await preview_service.get_preview_info(doc_id)
        
        if preview_info:
            return {
                "has_preview": True,
                "preview_info": preview_info
            }
        else:
            return {
                "has_preview": False,
                "message": "No preview available. Generate one with /preview endpoint."
            }
            
    except Exception as e:
        logger.error(f"Preview info retrieval failed for document {doc_id}: {str(e)}")
        return {
            "has_preview": False,
            "error": "Could not retrieve preview information"
        }
    finally:
        # Cleanup preview service resources
        try:
            await preview_service.cleanup()
        except Exception as e:
            logger.warning(f"Preview service cleanup failed: {e}")

@router.get("/{doc_id}/agents")
async def get_document_agents(
    doc_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Get agents assigned to a specific document based on its type and tags.
    """
    try:
        # Get document details
        document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
        document = document_service.get_document(db, doc_id, include_content=False)
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Determine document type and tags
        doc_tags = document.get("tags", [])
        doc_type = document.get("category", "general")
        
        # Map document characteristics to agent types
        assigned_agents = []
        
        # Check if document is signable
        is_signable = any(tag in ["signable", "contract", "agreement"] for tag in doc_tags)
        if is_signable:
            assigned_agents.append({
                "id": f"sig-{doc_id}",
                "name": "Digital Signature Agent",
                "type": "digital_signature",
                "status": "ready",
                "description": "Manages digital signature workflows",
                "capabilities": ["signature_requests", "status_tracking", "signer_management"]
            })
        
        # Check if document needs legal compliance
        is_legal = any(tag in ["legal", "contract", "compliance"] for tag in doc_tags) or doc_type == "legal"
        if is_legal:
            assigned_agents.append({
                "id": f"legal-{doc_id}",
                "name": "Legal Compliance Agent",
                "type": "legal_compliance",
                "status": "ready",
                "description": "Validates legal requirements",
                "capabilities": ["compliance_check", "risk_assessment", "regulatory_analysis"]
            })
        
        # Check if document is financial
        is_financial = any(tag in ["financial", "invoice", "report"] for tag in doc_tags) or doc_type == "financial"
        if is_financial:
            assigned_agents.append({
                "id": f"fin-{doc_id}",
                "name": "Financial Analysis Agent",
                "type": "financial_analyzer",
                "status": "ready",
                "description": "Analyzes financial documents",
                "capabilities": ["financial_metrics", "trend_analysis", "report_generation"]
            })
        
        # Document analyzer is always available
        assigned_agents.append({
            "id": f"doc-{doc_id}",
            "name": "Document Analyzer",
            "type": "document_analyzer",
            "status": "ready",
            "description": "Analyzes document content and structure",
            "capabilities": ["content_analysis", "extraction", "summarization"]
        })
        
        # RAG assistant for Q&A
        assigned_agents.append({
            "id": f"rag-{doc_id}",
            "name": "RAG Assistant",
            "type": "rag_assistant",
            "status": "ready",
            "description": "Answers questions about the document",
            "capabilities": ["document_search", "context_qa", "knowledge_retrieval"]
        })
        
        return {
            "document_id": doc_id,
            "document_type": doc_type,
            "tags": doc_tags,
            "assigned_agents": assigned_agents,
            "total_agents": len(assigned_agents)
        }
        
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
    tenant_id: str = Depends(get_current_tenant_id_async)
):
    """
    Recategoriza un documento específico (lo agrega a la cola de procesamiento)
    """
    from app.services.async_document_service import AsyncDocumentService
    from app.services.queue_service import queue_service
    
    document_service = await AsyncDocumentService.create(tenant_id=tenant_id, user_id=str(current_user.id))
    doc = await document_service.get_document(db=db, doc_id=doc_id)
    
    # Check if document has content
    if not doc.content:
        return {
            "document_id": doc_id,
            "status": "failed",
            "error": "Document has no extracted content"
        }
    
    # Queue for categorization
    job_id = await queue_service.enqueue_document_categorization(
        document_id=doc_id,
        tenant_id=tenant_id,
        user_id=str(current_user.id),
        priority="high"  # High priority for manual requests
    )
    
    if job_id:
        return {
            "document_id": doc_id,
            "status": "queued",
            "job_id": job_id,
            "message": "Document queued for recategorization"
        }
    else:
        return {
            "document_id": doc_id,
            "status": "failed",
            "error": "Failed to queue document for categorization"
        }


@router.post("/recategorize-all")
async def recategorize_all_documents(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user_async),
    tenant_id: str = Depends(get_current_tenant_id_async),
    only_uncategorized: bool = Query(True, description="Only recategorize documents without category"),
    batch_size: int = Query(10, ge=1, le=50, description="Batch size for processing")
):
    """
    Recategoriza todos los documentos del tenant (los agrega a la cola por lotes)
    """
    from app.services.queue_service import queue_service
    from sqlalchemy import or_
    
    # Get documents to recategorize
    query = select(Document.id).filter(
        Document.tenant_id == tenant_id,
        Document.content.isnot(None)  # Only documents with content
    )
    
    if only_uncategorized:
        query = query.filter(
            or_(
                Document.category.is_(None),
                Document.category == "",
                Document.category == "general"
            )
        )
    
    result = await db.execute(query)
    document_ids = [str(row[0]) for row in result.fetchall()]
    
    if not document_ids:
        return {
            "total_documents": 0,
            "message": "No documents found to categorize"
        }
    
    # Queue in batches
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
            "job_id": job_id,
            "batch_size": batch_size,
            "message": f"Queued {len(document_ids)} documents for batch categorization"
        }
    else:
        return {
            "status": "failed",
            "error": "Failed to queue documents for categorization"
        }


@router.get("/categorization/job/{job_id}")
async def get_categorization_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user_async)
):
    """
    Obtiene el estado de un trabajo de categorización
    """
    from app.services.queue_service import queue_service
    
    status = await queue_service.get_job_status(job_id)
    
    if status:
        return status
    else:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )


@router.get("/categorization/queue-stats")
async def get_categorization_queue_stats(
    current_user: User = Depends(get_current_user_async)
):
    """
    Obtiene estadísticas de la cola de categorización
    """
    from app.services.queue_service import queue_service
    
    stats = await queue_service.get_queue_stats()
    
    return {
        "queues": stats,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }