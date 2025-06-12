"""
Security module for Storage Service
Unified implementation following common pattern
"""
import logging
from fastapi import HTTPException, Request, Depends
from typing import Optional

from .config import settings

logger = logging.getLogger(__name__)


def get_api_key_from_header(request: Request) -> str:
    """Extract API key from X-API-Key header"""
    api_key = request.headers.get("X-API-Key")
    logger.info(f"=== API KEY VALIDATION ===")
    logger.info(f"Received API key: {api_key[:10] if api_key else 'NONE'}...")
    logger.info(f"Expected API key: {settings.API_KEY[:10]}...")
    if not api_key:
        logger.error("Missing X-API-Key header")
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    return api_key


def get_tenant_id_from_header(request: Request) -> Optional[str]:
    """Extract tenant ID from X-Tenant-ID header (optional for routes with path param)"""
    logger.info(f"=== EXTRACTING HEADERS ===")
    logger.info(f"All headers: {dict(request.headers)}")
    tenant_id = request.headers.get("X-Tenant-ID")
    logger.info(f"Tenant ID: {tenant_id}")
    return tenant_id


def get_user_id_from_header(request: Request) -> Optional[str]:
    """Extract user ID from X-User-ID header (optional)"""
    return request.headers.get("X-User-ID")


def get_bucket_name_from_header(request: Request) -> Optional[str]:
    """Extract bucket name from X-Bucket-Name header (optional)"""
    return request.headers.get("X-Bucket-Name")


def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool:
    """Validate API key"""
    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def validate_service_access(
    tenant_id: Optional[str] = Depends(get_tenant_id_from_header),
    user_id: Optional[str] = Depends(get_user_id_from_header),
    bucket_name: Optional[str] = Depends(get_bucket_name_from_header),
    api_key_valid: bool = Depends(validate_api_key)
) -> dict:
    """Validate service access and return context"""
    
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "bucket_name": bucket_name,
        "authenticated": True,
        "api_key_valid": api_key_valid
    }


def validate_tenant_access(
    tenant_id: Optional[str] = Depends(get_tenant_id_from_header),
    user_id: Optional[str] = Depends(get_user_id_from_header),
    bucket_name: Optional[str] = Depends(get_bucket_name_from_header),
    api_key_valid: bool = Depends(validate_api_key)
) -> dict:
    """Legacy function - validate tenant access and return security context"""
    
    # Validate tenant_id if provided
    if tenant_id and not tenant_id.strip():
        raise HTTPException(status_code=400, detail="Invalid tenant ID")
    
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "bucket_name": bucket_name,
        "authenticated": True
    }


def validate_tenant_id(tenant_id: str, context: dict) -> str:
    """Validate tenant access and return validated tenant_id"""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID required")
    
    # If tenant_id is also in headers, validate they match
    header_tenant_id = context.get("tenant_id")
    if header_tenant_id and header_tenant_id != tenant_id:
        raise HTTPException(
            status_code=403, 
            detail="Tenant ID mismatch between path and header"
        )
    
    return tenant_id

def get_bucket_name(tenant_id: str, bucket_name: Optional[str] = None) -> str:
    """Genera nombre del bucket basado en tenant (un bucket por tenant para LGPD)"""
    # Siempre usar patrón tenant-specific para LGPD compliance
    # Un bucket por tenant, no bucket compartido
    base_name = f"{settings.GCS_BUCKET_NAME}-{tenant_id}"
    if settings.TESTING:
        final_name = f"{base_name}-test"
    else:
        final_name = base_name
    
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