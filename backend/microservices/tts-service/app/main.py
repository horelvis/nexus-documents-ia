"""
TTS Service - Text-to-Speech Microservice

FastAPI application for text-to-speech synthesis using Microsoft VibeVoice
or Google Cloud TTS as fallback.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.tts import router as tts_router
from app.services.tts_provider_factory import TTSProviderFactory
from app.services.audio_utils import get_audio_cache
from app.services.vibevoice_service import cleanup_vibevoice_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown tasks including model loading and cache initialization.
    """
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"TTS Provider: {settings.tts_provider}")

    # Initialize TTS provider (this loads the model)
    try:
        provider = await TTSProviderFactory.get_provider()
        logger.info(f"TTS provider initialized: {TTSProviderFactory.get_provider_name()}")
        logger.info(f"GPU available: {provider.check_gpu_available()}")
    except Exception as e:
        logger.error(f"Failed to initialize TTS provider: {e}")
        logger.warning("Service starting without TTS provider - will try again on first request")

    # Initialize audio cache
    try:
        cache = await get_audio_cache()
        logger.info("Audio cache initialized")
    except Exception as e:
        logger.warning(f"Audio cache not available: {e}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")

    # Unload TTS model and release GPU memory
    try:
        logger.info("Releasing GPU resources...")
        # Use factory cleanup which handles both VibeVoice and Google TTS
        await TTSProviderFactory.cleanup()
        # Also call vibevoice-specific cleanup for global singleton
        await cleanup_vibevoice_service()
        logger.info("GPU resources released successfully")
    except Exception as e:
        logger.error(f"Error releasing GPU resources: {e}")

    # Close cache connection
    try:
        cache = await get_audio_cache()
        await cache.close()
    except Exception:
        pass


# Create FastAPI application
app = FastAPI(
    title="TTS Service",
    description="Text-to-Speech microservice using Microsoft VibeVoice",
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tts_router)


# Health check endpoint (no auth required for Docker health checks)
@app.get("/health")
async def health():
    """
    Simple health check for Docker/Kubernetes.

    Returns basic service status without authentication.
    """
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version
    }


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "provider": settings.tts_provider,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
        reload_dirs=["/app/app"]
    )
