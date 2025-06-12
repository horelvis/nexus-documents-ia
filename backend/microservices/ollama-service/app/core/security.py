"""
Security module for Ollama Service
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
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    return api_key


def get_tenant_id_from_header(request: Request) -> Optional[str]:
    """Extract tenant ID from X-Tenant-ID header (optional for routes with path param)"""
    return request.headers.get("X-Tenant-ID")


def get_user_id_from_header(request: Request) -> Optional[str]:
    """Extract user ID from X-User-ID header (optional)"""
    return request.headers.get("X-User-ID")


def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool:
    """Validate API key"""
    # For Ollama service, we might have a different API key or no API key requirement
    # This is a simplified implementation
    if hasattr(settings, 'API_KEY') and settings.API_KEY:
        if api_key != settings.API_KEY:
            logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
            raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def validate_service_access(
    tenant_id: Optional[str] = Depends(get_tenant_id_from_header),
    user_id: Optional[str] = Depends(get_user_id_from_header),
    api_key_valid: bool = Depends(validate_api_key)
) -> dict:
    """Validate service access and return context"""
    
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "authenticated": True,
        "api_key_valid": api_key_valid
    }


def validate_tenant_access(tenant_id: str, context: dict) -> str:
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