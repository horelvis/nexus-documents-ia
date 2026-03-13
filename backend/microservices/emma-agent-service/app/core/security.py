"""Security utilities for Emma Agent Service"""
from typing import Optional

from fastapi import HTTPException, Header
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> bool:
    """Verify the API key for microservice communication"""
    if not x_api_key:
        logger.warning("No API key provided in X-API-Key header")
        raise HTTPException(
            status_code=401,
            detail="Missing API key"
        )

    if x_api_key != settings.MICROSERVICES_API_KEY:
        logger.warning(f"Invalid API key provided: {x_api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return True


async def verify_api_key_or_bearer(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
) -> bool:
    """Accept either X-API-Key (microservice) or Bearer token (frontend SSO).

    Used for endpoints that both microservices and the frontend call directly
    (e.g., generated document downloads routed through the Next.js proxy).
    """
    # API key takes priority (microservice-to-microservice)
    if x_api_key and x_api_key == settings.MICROSERVICES_API_KEY:
        return True

    # Bearer token from frontend (SSO) — presence is sufficient,
    # the token was already validated by KeyCloak at the proxy/middleware level
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if token:
            return True

    if not x_api_key and not authorization:
        raise HTTPException(status_code=401, detail="Missing authentication")

    raise HTTPException(status_code=401, detail="Invalid authentication")
