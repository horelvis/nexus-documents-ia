"""
Presentation Generation API Endpoints

Endpoints for generating PowerPoint presentations from notebook sources.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status

from app.core.security import verify_api_key, get_tenant_context
from app.schemas import (
    GeneratePresentationRequest, GeneratePresentationResponse,
    PresentationStatusResponse, PresentationStatus,
)
from app.services.presentation_generator import PresentationGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/presentation", tags=["presentation"])

# Singleton generator instance
_generator: Optional[PresentationGenerator] = None


def get_generator() -> PresentationGenerator:
    """Get or create the presentation generator instance."""
    global _generator
    if _generator is None:
        _generator = PresentationGenerator()
    return _generator


@router.post("/generate", response_model=GeneratePresentationResponse)
async def generate_presentation(
    request: GeneratePresentationRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key),
    tenant_context: dict = Depends(get_tenant_context),
):
    """
    Start presentation generation for a notebook.

    This endpoint queues the presentation generation as a background task.
    Use the /status endpoint to poll for progress.

    Args:
        request: Generation request with sources and configuration

    Returns:
        Generation response with presentation_id and initial status
    """
    logger.info(f"Starting presentation generation for presentation_id: {request.presentation_id}")

    generator = get_generator()

    # Validate request
    if not request.sources:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one source is required"
        )

    # Queue generation task
    background_tasks.add_task(
        generator.generate,
        presentation_id=request.presentation_id,
        notebook_id=request.notebook_id,
        tenant_id=request.tenant_id,
        sources=request.sources,
        config=request.config,
    )

    return GeneratePresentationResponse(
        presentation_id=request.presentation_id,
        status=PresentationStatus.PENDING,
        message="Presentation generation queued"
    )


@router.get("/status/{presentation_id}", response_model=PresentationStatusResponse)
async def get_status(
    presentation_id: str,
    _: bool = Depends(verify_api_key),
):
    """
    Get the status of a presentation generation.

    Args:
        presentation_id: ID of the presentation being generated

    Returns:
        Current status, progress, and any error messages
    """
    generator = get_generator()

    status_info = await generator.get_status(presentation_id)

    if status_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation generation not found"
        )

    return PresentationStatusResponse(**status_info)


@router.post("/cancel/{presentation_id}")
async def cancel_generation(
    presentation_id: str,
    _: bool = Depends(verify_api_key),
):
    """
    Cancel an ongoing presentation generation.

    Args:
        presentation_id: ID of the presentation generation to cancel

    Returns:
        Cancellation confirmation
    """
    generator = get_generator()

    cancelled = await generator.cancel(presentation_id)

    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Presentation generation not found or already completed"
        )

    return {"message": "Generation cancelled", "presentation_id": presentation_id}


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns service status and dependencies health.
    """
    generator = get_generator()
    health = await generator.health_check()

    return {
        "status": "healthy" if health["sglang_healthy"] else "degraded",
        "service": "presentation-service",
        "version": "1.0.0",
        "dependencies": health,
    }
