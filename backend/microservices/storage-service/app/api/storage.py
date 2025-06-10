import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.security import (
    validate_tenant_access, 
    get_bucket_name, 
    get_object_path,
    validate_file_extension,
    validate_file_size
)
from app.core.config import settings
from app.services.gcs_service import GCSService

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/storage", tags=["storage"])

# Pydantic models
class UploadResponse(BaseModel):
    object_name: str
    size: int
    bucket: str
    uploaded_at: str
    metadata: dict

class FileInfo(BaseModel):
    name: str
    size: int
    content_type: Optional[str]
    created: Optional[str]
    updated: Optional[str]
    metadata: dict

class SignedUrlRequest(BaseModel):
    filename: str
    content_type: Optional[str] = None
    expiration: Optional[int] = None

class SignedUrlResponse(BaseModel):
    url: str
    expires_at: str
    object_name: str

class ListResponse(BaseModel):
    files: List[FileInfo]
    count: int
    prefix: str

class DeleteResponse(BaseModel):
    message: str
    object_name: str

class CleanupResponse(BaseModel):
    message: str
    files_deleted: int
    bucket: str

def get_gcs_service(auth_context: dict = Depends(validate_tenant_access)) -> GCSService:
    """Dependency que retorna el servicio GCS configurado para el tenant"""
    bucket_name = get_bucket_name(
        auth_context["tenant_id"], 
        auth_context.get("bucket_name")
    )
    return GCSService(bucket_name)

@router.post("/upload", response_model=UploadResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    metadata: Optional[str] = None,
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Sube un archivo al storage.
    
    - **file**: Archivo a subir
    - **metadata**: Metadatos JSON opcionales (como string)
    """
    logger.info(f"=== UPLOAD ENDPOINT REACHED ===")
    logger.info(f"Auth context: {auth_context}")
    logger.info(f"File: {file.filename}")
    logger.info(f"=== END UPLOAD ENDPOINT ===")
    
    # Validaciones
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File extension not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    if not validate_file_size(file.size):
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE} bytes"
        )
    
    # Generar path del objeto
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        file.filename
    )
    
    # Procesar metadatos
    file_metadata = {
        "tenant_id": auth_context["tenant_id"],
        "user_id": auth_context["user_id"] or "system",
        "original_filename": file.filename,
        "content_type": file.content_type or "application/octet-stream"
    }
    
    if metadata:
        try:
            import json
            custom_metadata = json.loads(metadata)
            file_metadata.update(custom_metadata)
        except json.JSONDecodeError:
            logger.warning("Invalid metadata JSON provided")
    
    # Subir archivo
    result = gcs_service.upload_file(
        file=file,
        object_name=object_name,
        metadata=file_metadata
    )
    
    logger.info(f"File uploaded: {object_name} by tenant {auth_context['tenant_id']}")
    
    return UploadResponse(**result)

@router.get("/download/{path:path}")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def download_file(
    request: Request,
    path: str,
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Descarga un archivo del storage.
    
    - **path**: Path del archivo (sin prefijo de tenant/user)
    """
    
    # Construir path completo
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        path
    )
    
    content = gcs_service.download_file(object_name)
    
    if content is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Obtener info del archivo para headers
    file_info = gcs_service.get_file_info(object_name)
    content_type = file_info.get("content_type") if file_info else "application/octet-stream"
    
    logger.info(f"File downloaded: {object_name} by tenant {auth_context['tenant_id']}")
    
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename={path.split('/')[-1]}"
        }
    )

@router.delete("/delete/{path:path}", response_model=DeleteResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def delete_file(
    request: Request,
    path: str,
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Elimina un archivo del storage.
    
    - **path**: Path del archivo (sin prefijo de tenant/user)
    """
    
    # Construir path completo
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        path
    )
    
    success = gcs_service.delete_file(object_name)
    
    logger.info(f"File deleted: {object_name} by tenant {auth_context['tenant_id']}")
    
    return DeleteResponse(
        message="File deleted successfully",
        object_name=object_name
    )

@router.get("/info/{path:path}", response_model=FileInfo)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def get_file_info(
    request: Request,
    path: str,
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Obtiene información de un archivo.
    
    - **path**: Path del archivo (sin prefijo de tenant/user)
    """
    
    # Construir path completo
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        path
    )
    
    file_info = gcs_service.get_file_info(object_name)
    
    if file_info is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileInfo(**file_info)

@router.get("/list", response_model=ListResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def list_files(
    request: Request,
    prefix: str = Query("", description="Prefijo para filtrar archivos"),
    limit: int = Query(100, ge=1, le=1000, description="Límite de archivos"),
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Lista archivos del tenant.
    
    - **prefix**: Prefijo para filtrar archivos
    - **limit**: Número máximo de archivos a retornar
    """
    
    # Construir prefijo completo para el tenant
    tenant_prefix = f"tenant-{auth_context['tenant_id']}/"
    if auth_context["user_id"]:
        full_prefix = f"{tenant_prefix}user-{auth_context['user_id']}/{prefix}"
    else:
        full_prefix = f"{tenant_prefix}{prefix}"
    
    files = gcs_service.list_files(prefix=full_prefix, limit=limit)
    
    # Remover el prefijo del tenant/user de los nombres para simplificar
    for file_info in files:
        # Remover prefijo tenant-{id}/user-{id}/ o tenant-{id}/system/
        name_parts = file_info["name"].split("/", 2)
        if len(name_parts) >= 3:
            file_info["name"] = name_parts[2]  # Solo el nombre del archivo
    
    logger.info(f"Listed {len(files)} files for tenant {auth_context['tenant_id']}")
    
    return ListResponse(
        files=[FileInfo(**f) for f in files],
        count=len(files),
        prefix=prefix
    )

@router.post("/signed-url/upload", response_model=SignedUrlResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def generate_upload_signed_url(
    request: Request,
    data: SignedUrlRequest,
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Genera una URL firmada para subir un archivo.
    
    - **filename**: Nombre del archivo a subir
    - **content_type**: Tipo de contenido MIME
    - **expiration**: Tiempo de expiración en segundos (opcional)
    """
    
    # Validaciones
    if not validate_file_extension(data.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File extension not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Generar path del objeto
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        data.filename
    )
    
    url, expires_at = gcs_service.generate_signed_url(
        object_name=object_name,
        method="PUT",
        expiration=data.expiration,
        content_type=data.content_type
    )
    
    logger.info(f"Generated upload signed URL for: {object_name}")
    
    return SignedUrlResponse(
        url=url,
        expires_at=expires_at.isoformat(),
        object_name=object_name
    )

@router.post("/signed-url/download/{path:path}", response_model=SignedUrlResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def generate_download_signed_url(
    request: Request,
    path: str,
    expiration: Optional[int] = Query(None, description="Tiempo de expiración en segundos"),
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Genera una URL firmada para descargar un archivo.
    
    - **path**: Path del archivo (sin prefijo de tenant/user)
    - **expiration**: Tiempo de expiración en segundos (opcional)
    """
    
    # Construir path completo
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        path
    )
    
    # Verificar que el archivo existe
    if not gcs_service.file_exists(object_name):
        raise HTTPException(status_code=404, detail="File not found")
    
    url, expires_at = gcs_service.generate_signed_url(
        object_name=object_name,
        method="GET",
        expiration=expiration
    )
    
    logger.info(f"Generated download signed URL for: {object_name}")
    
    return SignedUrlResponse(
        url=url,
        expires_at=expires_at.isoformat(),
        object_name=object_name
    )

# Endpoint solo para testing
@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_test_bucket(
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Limpia el bucket de test. Solo disponible en modo testing.
    """
    
    if not settings.TESTING:
        raise HTTPException(
            status_code=403,
            detail="Cleanup endpoint only available in testing mode"
        )
    
    result = gcs_service.cleanup_bucket()
    
    logger.info(f"Test bucket cleaned for tenant {auth_context['tenant_id']}")
    
    return CleanupResponse(**result)

# Health check
@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION
    }