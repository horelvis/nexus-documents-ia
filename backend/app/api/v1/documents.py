from typing import List, Optional
import os

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, Body, HTTPException
from app.api.dependencies import get_current_user, get_current_tenant_id, require_document_upload_permission
from app.db.models import User
from app.schemas.document import (
    Document, DocumentDetail,
    UploadRequest
)
from app.services.document_service import DocumentService
import logging
from sqlalchemy.orm import Session
from app.db.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("", response_model=dict)
async def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    search: Optional[str] = Query(None),
    tags: Optional[List[str]] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    """
    Obtiene lista paginada de documentos con filtros opcionales.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.get_documents(
        db=db,
        page=page,
        per_page=per_page,
        search=search,
        tags=tags,
        date_from=date_from,
        date_to=date_to
    )


@router.post("", response_model=Document)
async def create_document(
    db: Session = Depends(get_db),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(require_document_upload_permission),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Sube un nuevo documento al sistema.
    """
    # Convertir tags de string separado por comas a lista
    tag_list = tags.split(",") if tags else []
    tag_list = [tag.strip() for tag in tag_list if tag.strip()]
    
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return await document_service.process_document(
        db=db,
        file=file,
        title=title,
        description=description,
        tags=tag_list
    )


# Upload signed URL endpoint removed for security reasons
# Use direct upload via /upload endpoint instead


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Obtiene detalles de un documento específico.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.get_document(db=db, doc_id=doc_id)


# Signed URL endpoint removed for security reasons
# Use /stream endpoint instead for all document access


@router.get("/{doc_id}/stream")
async def stream_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Sirve documentos a través del proxy con cache Redis.
    Reemplaza tanto /pdf como /download-url con una sola ruta optimizada.
    """
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    import httpx
    
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    
    # Obtener información del documento
    document = document_service.get_document(db=db, doc_id=doc_id)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Sirve el PDF directamente para visualización en el navegador.
    Solo funciona para documentos que ya son PDF.
    """
    from fastapi.responses import StreamingResponse
    from fastapi import HTTPException
    
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    
    # Obtener información del documento
    document = document_service.get_document(db=db, doc_id=doc_id)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Elimina un documento y sus datos asociados.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return await document_service.delete_document(db=db, doc_id=doc_id)


@router.get("/{doc_id}/summary", response_model=dict)
async def get_document_summary(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Genera un resumen del documento utilizando LLM.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.generate_summary(db=db,doc_id=doc_id)


@router.post("/{doc_id}/tag", response_model=dict)
async def add_document_tag(
    doc_id: str,
    tag: str = Body(..., embed=True),
    db: Session = Depends(get_db), # Added db session
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    db: Session = Depends(get_db), # Added db session
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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


@router.get("/{doc_id}/preview/info", response_model=dict)
async def get_preview_info(
    doc_id: str,
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
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