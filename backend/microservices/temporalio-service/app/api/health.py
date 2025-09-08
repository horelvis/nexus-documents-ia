"""Health check endpoints"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any
import logging

from app.core.temporalio_client import temporalio_client
from app.workers.worker_manager import worker_manager

logger = logging.getLogger(__name__)
router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    components: Dict[str, Any]


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Main health check endpoint"""
    
    # Check Temporalio client
    temporalio_health = await temporalio_client.health_check()
    
    # Check worker manager
    worker_health = await worker_manager.health_check()
    
    # Determine overall status
    components_healthy = (
        temporalio_health.get("status") == "healthy" and
        worker_health.get("status") == "healthy"
    )
    
    overall_status = "healthy" if components_healthy else "degraded"
    
    return HealthResponse(
        status=overall_status,
        service="temporalio-workflows-service",
        version="1.0.0",
        components={
            "temporalio_client": temporalio_health,
            "worker_manager": worker_health
        }
    )


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    temporalio_health = await temporalio_client.health_check()
    worker_health = await worker_manager.health_check()
    
    if (temporalio_health.get("status") == "healthy" and 
        worker_health.get("status") == "healthy"):
        return {"status": "ready"}
    else:
        return {"status": "not_ready"}, 503


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    return {"status": "alive"}