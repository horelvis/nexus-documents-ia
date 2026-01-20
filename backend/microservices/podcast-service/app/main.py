"""
NexusLM Podcast Service

Main FastAPI application for podcast generation from document notebooks.
Uses Qwen3-4B-Thinking for script generation and VibeVoice for TTS.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import router as podcast_router

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info(f"vLLM URL: {settings.vllm_base_url}")
    logger.info(f"TTS Service URL: {settings.tts_service_url}")
    logger.info(f"Default language: {settings.default_language}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")


app = FastAPI(
    title="NexusLM Podcast Service",
    description="Podcast generation service for NexusLM notebooks. "
                "Generates two-host podcasts from document sources using "
                "Qwen3-4B-Thinking for script generation and VibeVoice for TTS.",
    version=settings.service_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(podcast_router)


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "generate": "/api/v1/podcast/generate",
            "status": "/api/v1/podcast/status/{audio_id}",
            "health": "/api/v1/podcast/health",
        }
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint for liveness probes."""
    return {"status": "pong"}
