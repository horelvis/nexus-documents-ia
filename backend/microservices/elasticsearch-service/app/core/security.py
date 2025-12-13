"""Security utilities for Elasticsearch microservice"""
from typing import Optional
from fastapi import HTTPException, Depends, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> bool:
    """
    Verify API key for microservice authentication.

    Accepts both:
    - X-API-Key header (preferred, new standard)
    - Authorization: Bearer <key> (legacy, for backward compatibility)
    """
    api_key = None

    # Prefer X-API-Key header
    if x_api_key:
        api_key = x_api_key
    elif credentials:
        api_key = credentials.credentials

    if not api_key:
        logger.warning("No API key provided in X-API-Key or Authorization header")
        raise HTTPException(
            status_code=401,
            detail="API key required. Use X-API-Key header."
        )

    if api_key != settings.MICROSERVICES_API_KEY:
        logger.warning(f"Invalid API key provided: {api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return True