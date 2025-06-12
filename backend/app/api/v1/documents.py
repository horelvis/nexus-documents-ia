from typing import List, Optional
import os

from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, Body, HTTPException
from app.api.dependencies import get_current_user, get_current_tenant_id, require_document_upload_permission
from app.db.models import User
from app.schemas.document import (
    Document, DocumentDetail,
    SignedUrlResponse, UploadRequest
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


@router.get("/upload-url", response_model=SignedUrlResponse)
async def get_upload_url(
    request: UploadRequest,
    current_user: User = Depends(require_document_upload_permission),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Genera una URL firmada para subir un documento directamente a GCS.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.get_signed_upload_url(
        filename=request.filename,
        content_type=request.content_type
    )


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


@router.get("/{doc_id}/download-url", response_model=SignedUrlResponse)
async def get_download_url(
    doc_id: str,
    db: Session = Depends(get_db), # Added db session
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id)
):
    """
    Genera una URL firmada para descargar un documento específico.
    """
    document_service = DocumentService(tenant_id=tenant_id, user_id=str(current_user.id))
    return document_service.get_signed_download_url(db=db, doc_id=doc_id) # Pass db


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
        storage_service = StorageService(tenant_id)
        
        import tempfile
        temp_dir = tempfile.mkdtemp()
        temp_file_path = os.path.join(temp_dir, document.filename or 'document')
        
        download_success = await storage_service.download_file(
            document.file_path or '', 
            temp_file_path
        )
        
        if not download_success:
            raise HTTPException(status_code=500, detail="Could not download document for preview")
        
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