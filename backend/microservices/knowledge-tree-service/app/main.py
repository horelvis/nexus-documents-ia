"""
Knowledge Tree Service - Structural context for Emma

Provides tenant structural summaries and tree context from FalkorDB.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.api.tree import tree_router
from app.api.entities import router as entities_router
from app.api.memory_bank import router as memory_bank_router
from app.api.claims import router as claims_router
from app.api.legal_links import router as legal_links_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Knowledge Tree Service...")
    logger.info(f"Service Port: {settings.service_port}")

    # Bootstrap sector graph on startup
    from app.services.graph_bootstrap import bootstrap_sector_graph
    graph_name = await bootstrap_sector_graph()
    if graph_name:
        logger.info(f"Graph ready: {graph_name} (sector={settings.active_sector})")

    # Initialize entity graph bridge
    from app.services.entity_graph_bridge import entity_graph_bridge
    await entity_graph_bridge.initialize()

    # Initialize memory bank
    from app.services.memory_bank_service import memory_bank
    await memory_bank.initialize()

    # Initialize claim extractor
    from app.services.claim_extractor import claim_extractor
    logger.info("Claim extractor ready")

    yield
    logger.info("Shutting down Knowledge Tree Service...")


app = FastAPI(
    title="Knowledge Tree Service",
    description="Structural context service for Emma (FalkorDB)",
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
app.include_router(entities_router, tags=["entity-graph"])
app.include_router(memory_bank_router, tags=["memory-bank"])
app.include_router(claims_router, tags=["claims"])
app.include_router(legal_links_router, prefix="/tree/legal-links", tags=["legal-links"])
