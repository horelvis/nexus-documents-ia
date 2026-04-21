"""Security utilities for Weaviate service"""
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


def get_tenant_collection_name(tenant_id: str = "", collection_type: str = "documents") -> str:
    """Return the fixed collection name.

    Kept for backward-compatibility with callers that still pass a
    tenant_id parameter. The tenant_id is ignored -- a single shared
    collection is used for all users.
    """
    return f"{settings.collection_prefix}{collection_type}"
