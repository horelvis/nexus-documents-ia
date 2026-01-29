"""
Knowledge Tree Service - Structural context for Emma

Provides tenant structural summaries and tree context from Apache AGE.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.api.tree import tree_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Knowledge Tree Service...")
    logger.info(f"Service Port: {settings.service_port}")
    yield
    logger.info("Shutting down Knowledge Tree Service...")


app = FastAPI(
    title="Knowledge Tree Service",
    description="Structural context service for Emma (Apache AGE)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "knowledge-tree-service",
        "version": "1.0.0",
    }


app.include_router(tree_router, prefix="/tree", tags=["tree"])

