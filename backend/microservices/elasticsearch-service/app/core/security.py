"""Security utilities for Elasticsearch microservice"""
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer()

async def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> bool:
    """Verify API key for microservice authentication"""
    try:
        if credentials.credentials != settings.MICROSERVICES_API_KEY:
            logger.warning("Invalid API key provided")
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        return True
    except Exception as e:
        logger.error(f"API key verification failed: {e}")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed"
        )