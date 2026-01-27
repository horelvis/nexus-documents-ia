"""
Main API routes for MEN service.

Endpoints:
- POST /men/query - Full query pipeline
- POST /men/decide - Classification only
- GET /men/health - Health check
- GET /men/status - Detailed status
"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from ..core.config import settings, VRAM_ESTIMATES
from ..core.security import validate_tenant_access, verify_api_key
from ..services import get_men_system

from .schemas import (
    QueryRequest,
    QueryResponse,
    DecideRequest,
    DecideResponse,
    HealthResponse,
    StatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/men", tags=["MEN"])


@router.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Process a user query through the full MEN pipeline.

    Pipeline:
    1. Orchestrator classifies domain
    2. Expert provides technical data (if available)
    3. LLM Modeler synthesizes response with memory

    The session_id enables conversational memory - subsequent
    queries with the same session_id will have context from
    previous turns.
    """
    try:
        men_system = get_men_system()

        result = await men_system.query(
            user_input=request.query,
            tenant_id=request.tenant_id,
            session_id=request.session_id,
            tenant_schema=request.tenant_schema
        )

        return QueryResponse(**result)

    except Exception as e:
        logger.error(f"Query failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query processing failed: {str(e)}"
        )


@router.post("/decide", response_model=DecideResponse)
async def decide(
    request: DecideRequest,
    _: bool = Depends(verify_api_key)
):
    """
    Classify a query without generating a response.

    Useful for:
    - Routing decisions
    - Pre-filtering queries
    - Analytics on query types

    Returns domain classification and confidence score.
    """
    try:
        men_system = get_men_system()

        result = await men_system.decide(request.query)

        return DecideResponse(**result)

    except Exception as e:
        logger.error(f"Decision failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Decision processing failed: {str(e)}"
        )


@router.get("/health", response_model=HealthResponse)
async def health():
    """
    Health check endpoint.

    Returns service status and component availability.
    Used by container orchestration for readiness probes.
    """
    try:
        men_system = get_men_system()
        status = men_system.get_status()

        return HealthResponse(
            status="healthy" if status["loaded"] else "starting",
            service=settings.service_name,
            version=settings.service_version,
            loaded=status["loaded"],
            orchestrator_loaded=status["orchestrator_loaded"],
            modeler_loaded=status["modeler_loaded"],
            modeler_enabled=status["modeler_enabled"],
            experts_enabled=status["experts_enabled"],
        )

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service=settings.service_name,
            version=settings.service_version,
            loaded=False,
            orchestrator_loaded=False,
            modeler_loaded=False,
            modeler_enabled=settings.modeler_enabled,
            experts_enabled=settings.experts_enabled,
        )


@router.get("/status", response_model=StatusResponse)
async def status(_: bool = Depends(verify_api_key)):
    """
    Detailed status endpoint.

    Returns comprehensive system status including:
    - Loaded components
    - Active sessions
    - Available domains
    - VRAM estimates
    """
    try:
        men_system = get_men_system()
        sys_status = men_system.get_status()

        return StatusResponse(
            status="healthy" if sys_status["loaded"] else "starting",
            service=settings.service_name,
            version=settings.service_version,
            loaded=sys_status["loaded"],
            orchestrator_loaded=sys_status["orchestrator_loaded"],
            modeler_loaded=sys_status["modeler_loaded"],
            modeler_enabled=sys_status["modeler_enabled"],
            experts_enabled=sys_status["experts_enabled"],
            loaded_experts=sys_status["loaded_experts"],
            active_sessions=sys_status["active_sessions"],
            available_domains=sys_status["available_domains"],
            vram_estimate=VRAM_ESTIMATES,
        )

    except Exception as e:
        logger.error(f"Status check failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Status check failed: {str(e)}"
        )
