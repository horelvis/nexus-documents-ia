"""
Basic application routes (health, cors test, etc.)
"""
from typing import Dict, Any

from fastapi import APIRouter, Request

from app.core.config import settings

# Create router for basic endpoints
basic_router = APIRouter()


@basic_router.get("/health", tags=["health"])
async def health_check() -> Dict[str, str]:
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}


@basic_router.get("/cors-test", tags=["health"])
async def cors_test(request: Request) -> Dict[str, Any]:
    """Test CORS configuration"""
    return {
        "status": "ok",
        "origin": request.headers.get("origin"),
        "method": request.method,
        "cors_configured": len(settings.BACKEND_CORS_ORIGINS) > 0,
        "allowed_origins": [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
    }


@basic_router.get("/direct-auth-test", tags=["debug"])
async def direct_auth_test() -> Dict[str, str]:
    """Direct auth test endpoint"""
    return {"status": "direct_endpoint_working", "message": "This endpoint works without router"}


@basic_router.get("/test-connection", tags=["health"])
async def test_connection(request: Request) -> Dict[str, Any]:
    """Test connection and headers"""
    client_ip = request.client.host if request.client else "unknown"
    headers = dict(request.headers)

    return {
        "status": "connected",
        "client_ip": client_ip,
        "headers": headers,
        "cors_origins": [str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
        "api_prefix": settings.API_PREFIX,
        "server_host": str(settings.SERVER_HOST)
    }