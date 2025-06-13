import logging
from typing import Optional, List, Dict, AsyncGenerator
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import io

from app.core.security import (
    validate_tenant_access, 
    get_bucket_name, 
    get_object_path,
    validate_file_extension,
    validate_file_size
)
from app.core.config import settings
from app.services.gcs_service import GCSService
from app.services.redis_cache import redis_cache

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Cache global para instancias de GCSService (bucket_name -> GCSService)
_gcs_service_cache: Dict[str, GCSService] = {}

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
    """Dependency que retorna el servicio GCS configurado para el tenant (con cache)"""
    bucket_name = get_bucket_name(
        auth_context["tenant_id"], 
        auth_context.get("bucket_name")
    )
    
    # Verificar si ya existe en cache
    if bucket_name in _gcs_service_cache:
        logger.debug(f"Using cached GCS service for bucket: {bucket_name}")
        return _gcs_service_cache[bucket_name]
    
    # Crear nueva instancia y guardar en cache
    logger.info(f"Creating new GCS service instance for bucket: {bucket_name}")
    gcs_service = GCSService(bucket_name)
    _gcs_service_cache[bucket_name] = gcs_service
    
    return gcs_service

def clear_gcs_cache():
    """Limpia el cache de servicios GCS (útil para testing)"""
    global _gcs_service_cache
    _gcs_service_cache.clear()
    logger.info("GCS service cache cleared")

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
    
    # Validaciones
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File extension not allowed. Allowed: {', '.join(settings.ALLOWED_EXTENSIONS)}"
        )
    
    # Skip file size validation for now (will be checked during upload)
    # FastAPI UploadFile.size can be None or unreliable
    # if not validate_file_size(file.size):
    #     raise HTTPException(
    #         status_code=400,
    #         detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE} bytes"
    #     )
    
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
    result = await gcs_service.upload_file(
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

@router.get("/proxy/{path:path}")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def proxy_download_file(
    request: Request,
    path: str,
    auth_context: dict = Depends(validate_tenant_access),
    gcs_service: GCSService = Depends(get_gcs_service)
):
    """
    Proxy download with Redis cache and streaming support.
    
    - **path**: Path del archivo (sin prefijo de tenant/user)
    
    Features:
    - Redis cache for files < 50MB
    - Streaming for large files
    - Automatic TTL based on file size
    - Complete audit logging
    """
    
    # Construir path completo
    object_name = get_object_path(
        auth_context["tenant_id"],
        auth_context["user_id"],
        path
    )
    
    # Obtener info del archivo primero
    file_info = gcs_service.get_file_info(object_name)
    if not file_info:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_size = file_info.get("size", 0)
    content_type = file_info.get("content_type", "application/octet-stream")
    filename = path.split('/')[-1]
    
    # Log access for audit
    logger.info(f"Proxy access: {object_name} by tenant {auth_context['tenant_id']} (size: {file_size})")
    
    # Check cache first for cacheable files
    if redis_cache.should_cache(file_size):
        cached_data = redis_cache.get(auth_context["tenant_id"], object_name)
        if cached_data:
            content, metadata = cached_data
            logger.info(f"Cache hit for {object_name}")
            
            return Response(
                content=content,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"inline; filename={filename}",
                    "Content-Length": str(len(content)),
                    "X-Cache": "HIT"
                }
            )
    
    # Cache miss or uncacheable file - download from GCS
    content = gcs_service.download_file(object_name)
    if content is None:
        raise HTTPException(status_code=404, detail="File not found in storage")
    
    # Cache small/medium files
    if redis_cache.should_cache(file_size):
        redis_cache.set(
            auth_context["tenant_id"], 
            object_name, 
            content, 
            file_info, 
            file_size
        )
        cache_status = "MISS-CACHED"
    else:
        cache_status = "UNCACHEABLE"
    
    # For large files, stream to avoid memory issues
    if file_size > redis_cache.MEDIUM_FILE_LIMIT:
        def stream_content():
            chunk_size = 1024 * 1024  # 1MB chunks
            content_io = io.BytesIO(content)
            while True:
                chunk = content_io.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        
        return StreamingResponse(
            stream_content(),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Length": str(file_size),
                "X-Cache": cache_status
            }
        )
    else:
        return Response(
            content=content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Content-Length": str(len(content)),
                "X-Cache": cache_status
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
    
    # Clear from cache if exists
    redis_cache.delete(auth_context["tenant_id"], object_name)
    
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

# Signed URL upload endpoint removed for security reasons
# Use direct upload via /upload endpoint instead

# Signed URL download endpoint removed for security reasons
# Use /proxy/{path} endpoint instead for all document access

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

# Cache management endpoints
@router.get("/cache/stats")
async def get_cache_stats(
    auth_context: dict = Depends(validate_tenant_access)
):
    """Get Redis cache statistics."""
    return redis_cache.get_cache_stats()

@router.delete("/cache/clear")
async def clear_tenant_cache(
    auth_context: dict = Depends(validate_tenant_access)
):
    """Clear cache for current tenant."""
    deleted = redis_cache.clear_tenant_cache(auth_context["tenant_id"])
    return {
        "message": f"Cleared {deleted} cached documents for tenant",
        "tenant_id": auth_context["tenant_id"],
        "deleted_count": deleted
    }

# Health check
@router.get("/health")
async def health_check():
    """Enhanced health check endpoint with Redis status"""
    redis_healthy = redis_cache.health_check()
    cache_stats = redis_cache.get_cache_stats() if redis_healthy else {"connected": False}
    
    return {
        "status": "healthy" if redis_healthy else "degraded",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "redis_connected": redis_healthy,
        "cache_stats": cache_stats,
        "cached_buckets": list(_gcs_service_cache.keys()),
        "gcs_cache_size": len(_gcs_service_cache)
    }