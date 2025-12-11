"""Health check endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.camunda_client import get_camunda_client
from app.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    camunda_status: str = "unknown"


class CamundaHealthResponse(BaseModel):
    status: str
    engines: list[dict] = []


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    settings = get_settings()
    client = get_camunda_client()

    camunda_status = "unhealthy"
    try:
        engines = await client.get_engine_info()
        if engines:
            camunda_status = "healthy"
    except Exception:
        camunda_status = "unhealthy"

    return HealthResponse(
        status="healthy",
        service=settings.SERVICE_NAME,
        version=settings.VERSION,
        camunda_status=camunda_status
    )


@router.get("/health/camunda", response_model=CamundaHealthResponse)
async def camunda_health_check():
    """Detailed Camunda health check."""
    client = get_camunda_client()

    try:
        engines = await client.get_engine_info()
        return CamundaHealthResponse(
            status="healthy",
            engines=engines
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Camunda is not available: {str(e)}"
        )
