"""
Security utilities for Template Editor Service
"""
from fastapi import HTTPException, status
from app.core.config import settings


def verify_api_key(api_key: str) -> bool:
    """Verify microservices API key"""
    return api_key == settings.microservices_api_key


def require_api_key(api_key: str) -> None:
    """Raise exception if API key is invalid"""
    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )