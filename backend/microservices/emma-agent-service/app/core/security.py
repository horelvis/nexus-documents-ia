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
