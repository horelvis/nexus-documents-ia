"""
Knowledge Tree Service - Structural context for Emma

Provides tenant structural summaries and tree context from Apache AGE.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.core.config import settings
from app.api.tree import tree_router
from app.api.legal_graph import router as legal_graph_router
from app.api.ontology import router as ontology_router
from app.api.entities import router as entities_router
from app.api.memory_bank import router as memory_bank_router
from app.api.legal_sync import router as legal_sync_router

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

    # Sync legal proxy nodes from knowledge_graph_public
    if graph_name:
        from app.services.legal_proxy_sync import legal_proxy_sync
        await legal_proxy_sync.initialize()
        sync_result = await legal_proxy_sync.sync(graph_name)
        if sync_result["synced_laws"] > 0:
            logger.info(
                f"Legal proxy sync: {sync_result['synced_laws']} laws, "
                f"{sync_result['synced_edges']} edges ({sync_result['elapsed_ms']}ms)"
            )

    # Initialize legal graph service
    from app.services.legal_graph_service import legal_graph
    await legal_graph.initialize()

    # Initialize business ontology
    from app.services.ontology_service import ontology_service
    await ontology_service.initialize()

    # Initialize entity graph bridge
    from app.services.entity_graph_bridge import entity_graph_bridge
    await entity_graph_bridge.initialize()

    # Initialize memory bank
    from app.services.memory_bank_service import memory_bank
    await memory_bank.initialize()

    # Initialize legal reference bridge
    from app.services.legal_reference_bridge import legal_reference_bridge
    await legal_reference_bridge.initialize()

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
app.include_router(legal_graph_router, tags=["legal-knowledge-graph"])
app.include_router(ontology_router, tags=["business-ontology"])
app.include_router(entities_router, tags=["entity-graph"])
app.include_router(memory_bank_router, tags=["memory-bank"])
app.include_router(legal_sync_router, tags=["legal-proxy-sync"])

