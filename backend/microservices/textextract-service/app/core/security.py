"""
Security helpers for the text extraction microservice.
"""
from typing import Optional
from fastapi import Depends, HTTPException, Security, Request
from fastapi.security import APIKeyHeader

from .config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> bool:
    """Validate the incoming API key."""
    if not api_key or api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return True


async def get_request_context(request: Request) -> dict:
    """
    Build a context dictionary from common headers.

    This is mainly used for logging and debugging purposes.
    """
    return {
        "tenant_id": request.headers.get("X-Tenant-ID"),
        "user_id": request.headers.get("X-User-ID"),
        "filename": request.headers.get("X-Original-Filename"),
    }
