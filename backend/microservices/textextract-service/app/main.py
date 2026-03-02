"""
Main application entry point for the text extraction microservice.
Supports pluggable backends: Apache Tika (default) and IBM Docling.
"""
from contextlib import asynccontextmanager
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api import text_extraction
from app.core.config import settings
from app.schemas.text_extraction import HealthResponse

# Configure loguru
logger.remove()
# Normalize log level and fallback to INFO if invalid
configured_level = (settings.log_level or "INFO").upper()
try:
    logger.level(configured_level)
except ValueError:
    configured_level = "INFO"

logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | "
           "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=configured_level,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting {} v{}", settings.service_name, settings.service_version)
    logger.info(
        "Extraction backend: {} | fallback: {} | Tika: {} | Docling: {}",
        settings.extraction_backend,
        "tika" if (settings.extraction_fallback_enabled and settings.extraction_backend != "tika") else "none",
        settings.tika_url,
        settings.docling_url if settings.extraction_backend == "docling" else "not configured",
    )
    logger.info("Allowed extensions: {}", ", ".join(settings.allowed_extensions))
    yield
    logger.info("Shutting down {}", settings.service_name)


app = FastAPI(
    title=settings.service_name,
    version=settings.service_version,
    description="Document text extraction microservice with pluggable backends (Tika, Docling).",
    lifespan=lifespan,
)

# CORS configuration (open for internal network use)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(text_extraction.router)


@app.get("/", response_model=dict)
async def root():
    """Root endpoint with service metadata."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "backend": settings.extraction_backend,
        "fallback_enabled": settings.extraction_fallback_enabled,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health endpoint without authentication (used by orchestrators)."""
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.service_version,
        backend=settings.extraction_backend,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
