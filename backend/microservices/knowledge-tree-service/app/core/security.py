"""Security utilities for Knowledge Tree Service"""
from typing import Optional

from fastapi import HTTPException, Header
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> bool:
    """Verify the API key for microservice communication."""
    if not settings.MICROSERVICES_API_KEY:
        # If not configured, allow for internal usage (dev)
        return True

    if not x_api_key:
        logger.warning("No API key provided in X-API-Key header")
        raise HTTPException(status_code=401, detail="Missing API key")

    if x_api_key != settings.MICROSERVICES_API_KEY:
        logger.warning("Invalid API key provided")
        raise HTTPException(status_code=401, detail="Invalid API key")

    return True
