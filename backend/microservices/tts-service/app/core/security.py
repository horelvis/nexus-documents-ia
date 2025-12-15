"""
TTS Service Security

API key validation and authentication for the TTS microservice.
"""

import logging
from typing import Optional

from fastapi import HTTPException, Security, Header, status
from fastapi.security import APIKeyHeader

from app.core.config import settings

logger = logging.getLogger(__name__)

# API Key header security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: Optional[str] = Security(api_key_header)
) -> bool:
    """
    Verify the API key from request headers.

    Args:
        api_key: API key from X-API-Key header

    Returns:
        True if API key is valid

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not settings.microservices_api_key:
        logger.warning("MICROSERVICES_API_KEY not configured - allowing all requests")
        return True

    if not api_key:
        logger.warning("Missing API key in request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key"
        )

    if api_key != settings.microservices_api_key:
        logger.warning("Invalid API key provided")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key"
        )

    return True


async def get_tenant_context(
    tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    user_id: Optional[str] = Header(None, alias="X-User-ID"),
) -> dict:
    """
    Extract tenant context from request headers.

    Args:
        tenant_id: Tenant ID from header
        user_id: User ID from header

    Returns:
        Dictionary with tenant context
    """
    return {
        "tenant_id": tenant_id,
        "user_id": user_id
    }


def verify_websocket_api_key(api_key: Optional[str]) -> bool:
    """
    Verify API key for WebSocket connections.

    WebSocket doesn't support standard header-based auth in the same way,
    so we accept the API key as a query parameter or in the first message.

    Args:
        api_key: API key to verify

    Returns:
        True if valid, False otherwise
    """
    if not settings.microservices_api_key:
        return True

    if not api_key:
        return False

    return api_key == settings.microservices_api_key
