"""
Security module for LangGraph Service
Independent implementation without external dependencies
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
        logger.error("Missing X-API-Key header")
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    return api_key


def get_tenant_id_from_header(request: Request) -> Optional[str]:
    """Extract tenant ID from X-Tenant-ID header"""
    return request.headers.get("X-Tenant-ID")


def get_user_id_from_header(request: Request) -> Optional[str]:
    """Extract user ID from X-User-ID header"""
    return request.headers.get("X-User-ID")


def validate_api_key(api_key: str = Depends(get_api_key_from_header)) -> bool:
    """Validate API key"""
    if api_key != settings.service_api_key:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def validate_service_access(
    api_key_valid: bool = Depends(validate_api_key)
) -> bool:
    """Validate service access with API key"""
    return api_key_valid


def validate_tenant_access(
    tenant_id: Optional[str] = Depends(get_tenant_id_from_header),
    user_id: Optional[str] = Depends(get_user_id_from_header),
    api_key_valid: bool = Depends(validate_api_key)
) -> dict:
    """Validate tenant access and return security context"""
    
    # Validate tenant_id if provided
    if tenant_id and not tenant_id.strip():
        raise HTTPException(status_code=400, detail="Invalid tenant ID")
    
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "authenticated": True
    }