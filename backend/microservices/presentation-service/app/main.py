"""
NouxCube Presentation Service

Main FastAPI application for PowerPoint presentation generation from document notebooks.
Uses Qwen3-4B for outline generation and python-pptx for slide creation.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api import router as presentation_router

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
    logger.info(f"Storage Service URL: {settings.storage_service_url}")
    logger.info(f"Default language: {settings.default_language}")
    logger.info(f"Templates directory: {settings.templates_dir}")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.service_name}")


app = FastAPI(
    title="NouxCube Presentation Service",
    description="PowerPoint presentation generation service for NouxCube notebooks. "
                "Generates PPTX presentations from document sources using "
                "Qwen3-4B for outline generation and python-pptx for slide creation.",
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
app.include_router(presentation_router)


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "status": "running",
        "endpoints": {
            "generate": "/api/v1/presentation/generate",
            "status": "/api/v1/presentation/status/{presentation_id}",
            "health": "/api/v1/presentation/health",
        }
    }


@app.get("/ping")
async def ping():
    """Simple ping endpoint for liveness probes."""
    return {"status": "pong"}
