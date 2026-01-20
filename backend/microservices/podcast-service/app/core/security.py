"""
Security utilities for the Podcast Service.
"""
from fastapi import Header, HTTPException, status
from .config import settings


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> bool:
    """Verify the API key from request header."""
    if not settings.api_key:
        # No API key configured, allow all requests (development mode)
        return True

    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    return True


def get_tenant_context(
    x_tenant_id: str = Header(None, alias="X-Tenant-ID"),
    x_user_id: str = Header(None, alias="X-User-ID"),
) -> dict:
    """Extract tenant context from headers."""
    return {
        "tenant_id": x_tenant_id,
        "user_id": x_user_id,
    }
