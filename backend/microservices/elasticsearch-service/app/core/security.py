"""Security utilities for Elasticsearch microservice"""
from typing import Optional
from fastapi import HTTPException, Depends, Request, Header
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> bool:
    """
    Verify API key for microservice authentication.
    """
    if not x_api_key:
        logger.warning("No API key provided in X-API-Key header")
        raise HTTPException(
            status_code=401,
            detail="API key required. Use X-API-Key header."
        )

    if x_api_key != settings.MICROSERVICES_API_KEY:
        logger.warning(f"Invalid API key provided: {x_api_key[:10]}...")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return True
