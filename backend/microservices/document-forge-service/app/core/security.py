"""API key validation for inter-service communication."""

from fastapi import Header, HTTPException

from app.core.config import get_settings


async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    settings = get_settings()
    if not settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key
