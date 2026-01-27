"""
Security utilities for MEN service.

Provides API key validation and tenant context extraction.
"""

import logging
from typing import Optional

from fastapi import Header, HTTPException, Request

from .config import settings

logger = logging.getLogger(__name__)


def get_api_key_from_header(request: Request) -> str:
    """Extract API key from request headers."""
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header"
        )
    return api_key


def get_tenant_id_from_header(request: Request) -> Optional[str]:
    """Extract tenant ID from request headers (optional)."""
    return request.headers.get("X-Tenant-ID")


def get_user_id_from_header(request: Request) -> Optional[str]:
    """Extract user ID from request headers (optional)."""
    return request.headers.get("X-User-ID")


def get_session_id_from_header(request: Request) -> Optional[str]:
    """Extract session ID from request headers (optional)."""
    return request.headers.get("X-Session-ID")


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key")
) -> bool:
    """
    Verify the API key from request header.

    Used as a FastAPI dependency for protected endpoints.

    Args:
        x_api_key: The API key from X-API-Key header

    Returns:
        True if valid

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not settings.MICROSERVICES_API_KEY:
        # No API key configured, allow all requests (dev mode)
        logger.warning("No MICROSERVICES_API_KEY configured - allowing request")
        return True

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header"
        )

    if x_api_key != settings.MICROSERVICES_API_KEY:
        logger.warning(f"Invalid API key attempt")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return True


async def validate_tenant_access(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
) -> dict:
    """
    Validate API key and extract tenant context.

    Returns a context dict with tenant_id, user_id, and session_id.

    Args:
        request: FastAPI request object
        x_api_key: API key header
        x_tenant_id: Tenant ID header
        x_user_id: User ID header
        x_session_id: Session ID header

    Returns:
        Dict with context: {tenant_id, user_id, session_id}

    Raises:
        HTTPException: If authentication fails
    """
    # Verify API key
    await verify_api_key(x_api_key)

    # Build context
    context = {
        "tenant_id": x_tenant_id or "default",
        "user_id": x_user_id,
        "session_id": x_session_id or "default",
    }

    logger.debug(f"Tenant context: {context}")
    return context
