"""
Podcast Generation API Endpoints

Endpoints for generating podcast audio from notebook sources.
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import StreamingResponse

from app.core.security import verify_api_key, get_tenant_context
from app.schemas import (
    GeneratePodcastRequest, GeneratePodcastResponse,
    PodcastStatusResponse, AudioStatus,
)
from app.services.podcast_generator import PodcastGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/podcast", tags=["podcast"])

# Singleton generator instance
_generator: Optional[PodcastGenerator] = None


def get_generator() -> PodcastGenerator:
    """Get or create the podcast generator instance."""
    global _generator
    if _generator is None:
        _generator = PodcastGenerator()
    return _generator


@router.post("/generate", response_model=GeneratePodcastResponse)
async def generate_podcast(
    request: GeneratePodcastRequest,
    background_tasks: BackgroundTasks,
    _: bool = Depends(verify_api_key),
    tenant_context: dict = Depends(get_tenant_context),
):
    """
    Start podcast generation for a notebook.

    This endpoint queues the podcast generation as a background task.
    Use the /status endpoint to poll for progress.

    Args:
        request: Generation request with sources and configuration

    Returns:
        Generation response with audio_id and initial status
    """
    logger.info(f"Starting podcast generation for audio_id: {request.audio_id}")

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
        audio_id=request.audio_id,
        notebook_id=request.notebook_id,
        tenant_id=request.tenant_id,
        sources=request.sources,
        config=request.config,
    )

    return GeneratePodcastResponse(
        audio_id=request.audio_id,
        status=AudioStatus.PENDING,
        message="Podcast generation queued"
    )


@router.get("/status/{audio_id}", response_model=PodcastStatusResponse)
async def get_status(
    audio_id: UUID,
    _: bool = Depends(verify_api_key),
):
    """
    Get the status of a podcast generation.

    Args:
        audio_id: ID of the audio being generated

    Returns:
        Current status, progress, and any error messages
    """
    generator = get_generator()

    status_info = await generator.get_status(audio_id)

    if status_info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio generation not found"
        )

    return PodcastStatusResponse(**status_info)


@router.post("/cancel/{audio_id}")
async def cancel_generation(
    audio_id: UUID,
    _: bool = Depends(verify_api_key),
):
    """
    Cancel an ongoing podcast generation.

    Args:
        audio_id: ID of the audio generation to cancel

    Returns:
        Cancellation confirmation
    """
    generator = get_generator()

    cancelled = await generator.cancel(audio_id)

    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio generation not found or already completed"
        )

    return {"message": "Generation cancelled", "audio_id": str(audio_id)}


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns service status and dependencies health.
    """
    generator = get_generator()
    health = await generator.health_check()

    return {
        "status": "healthy" if health["vllm_healthy"] and health["tts_healthy"] else "degraded",
        "service": "podcast-service",
        "version": "1.0.0",
        "dependencies": health,
    }
