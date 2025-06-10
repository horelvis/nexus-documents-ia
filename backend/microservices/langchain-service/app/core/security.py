"""
Security module for LangChain Service
"""
import logging
from fastapi import HTTPException, Header, Depends

from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_api_key(api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Extract and validate API key from headers"""
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    
    if api_key != settings.API_KEY:
        logger.warning(f"Invalid API key attempted: {api_key[:10]}...")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return api_key


async def get_tenant_id(tenant_id: str = Header(..., alias="X-Tenant-ID")) -> str:
    """Extract tenant ID from headers"""
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Tenant ID required")
    return tenant_id


async def get_user_id(user_id: str = Header(None, alias="X-User-ID")) -> str:
    """Extract user ID from headers (optional)"""
    return user_id


async def verify_service_access(
    api_key: str = Depends(get_api_key),
    tenant_id: str = Depends(get_tenant_id),
    user_id: str = Depends(get_user_id)
) -> dict:
    """Verify service access with API key and tenant isolation"""
    
    return {
        "api_key_valid": True,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "authenticated": True
    }