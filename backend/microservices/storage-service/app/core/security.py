import logging
from fastapi import HTTPException, Request, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

def get_api_key_from_header(request: Request) -> str:
    """Extrae API key del header X-API-Key"""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header"
        )
    return api_key

def get_tenant_id_from_header(request: Request) -> str:
    """Extrae tenant ID del header X-Tenant-ID"""
    tenant_id = request.headers.get("X-Tenant-ID")
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Tenant-ID header"
        )
    return tenant_id

def get_user_id_from_header(request: Request) -> Optional[str]:
    """Extrae user ID del header X-User-ID (opcional)"""
    return request.headers.get("X-User-ID")

def get_bucket_name_from_header(request: Request) -> Optional[str]:
    """Extrae bucket name del header X-Bucket-Name (opcional)"""
    return request.headers.get("X-Bucket-Name")

def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool:
    """Valida la API key"""
    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return True

def validate_tenant_access(
    tenant_id: str = Depends(get_tenant_id_from_header),
    user_id: Optional[str] = Depends(get_user_id_from_header),
    bucket_name: Optional[str] = Depends(get_bucket_name_from_header),
    api_key_valid: bool = Depends(validate_api_key)
) -> dict:
    """Valida acceso del tenant y retorna contexto de seguridad"""
    
    # Validaciones básicas
    if not tenant_id.strip():
        raise HTTPException(
            status_code=400,
            detail="Invalid tenant ID"
        )
    
    # Log del acceso para auditoria y debugging
    logger.info(f"=== TENANT ACCESS ===")
    logger.info(f"Tenant ID: {tenant_id}")
    logger.info(f"User ID: {user_id or 'system'}")
    logger.info(f"Bucket Name from header: {bucket_name or 'NOT_PROVIDED'}")
    logger.info(f"=== END TENANT ACCESS ===")
    
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "bucket_name": bucket_name,
        "authenticated": True
    }

def get_bucket_name(tenant_id: str, bucket_name: Optional[str] = None) -> str:
    """Genera nombre del bucket basado en tenant y modo, o usa el proporcionado"""
    logger.info(f"=== BUCKET NAME GENERATION ===")
    logger.info(f"Tenant ID: {tenant_id}")
    logger.info(f"Provided bucket name: {bucket_name or 'NONE'}")
    logger.info(f"TESTING mode: {settings.TESTING}")
    
    if bucket_name:
        # Usar bucket name proporcionado en header
        if settings.TESTING:
            final_name = f"{bucket_name}-test"
        else:
            final_name = bucket_name
        logger.info(f"Using provided bucket: {final_name}")
        return final_name
    else:
        # Fallback al patrón anterior
        base_name = f"{settings.GCS_BUCKET_NAME}-{tenant_id}"
        if settings.TESTING:
            final_name = f"{base_name}-test"
        else:
            final_name = base_name
        logger.info(f"Using fallback bucket: {final_name}")
        return final_name

def get_object_path(tenant_id: str, user_id: Optional[str], filename: str) -> str:
    """Genera path del objeto con aislamiento por tenant/usuario"""
    if user_id:
        return f"tenant-{tenant_id}/user-{user_id}/{filename}"
    else:
        return f"tenant-{tenant_id}/system/{filename}"

def validate_file_extension(filename: str) -> bool:
    """Valida que la extensión del archivo sea permitida"""
    if "." not in filename:
        return False
    
    extension = filename.rsplit(".", 1)[1].lower()
    return extension in settings.ALLOWED_EXTENSIONS

def validate_file_size(content_length: Optional[int]) -> bool:
    """Valida el tamaño del archivo"""
    if content_length is None:
        return True  # Si no se puede determinar, permitir
    
    return content_length <= settings.MAX_UPLOAD_SIZE