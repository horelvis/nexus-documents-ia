"""
Camunda Workflow Service

Microservice for managing BPMN workflows using Camunda 7 BPM Platform.
Provides REST API for:
- Deploying BPMN process definitions
- Starting and managing process instances
- Managing user tasks (approval workflows)
- Correlating messages between processes
- External task workers for async operations
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os

from app.core.config import get_settings
from app.api import health, deployments, processes, tasks
from app.workers import (
    get_worker_manager,
    create_signature_worker,
    create_email_worker,
    create_approval_status_worker,
    create_store_signed_document_worker
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info(f"Starting {settings.SERVICE_NAME} v{settings.VERSION}")
    logger.info(f"Camunda URL: {settings.CAMUNDA_URL}")

    # Start workers if enabled
    workers_enabled = os.getenv("CAMUNDA_WORKERS_ENABLED", "true").lower() == "true"

    if workers_enabled:
        logger.info("Starting external task workers...")
        worker_manager = get_worker_manager()

        # Register all workers
        worker_manager.register(create_signature_worker())
        worker_manager.register(create_email_worker())
        worker_manager.register(create_approval_status_worker())
        worker_manager.register(create_store_signed_document_worker())

        # Start workers
        await worker_manager.start_all()
        logger.info(f"Started {len(worker_manager.workers)} external task workers")
    else:
        logger.info("External task workers disabled (CAMUNDA_WORKERS_ENABLED=false)")

    yield

    # Shutdown
    logger.info(f"Shutting down {settings.SERVICE_NAME}")

    if workers_enabled:
        logger.info("Stopping external task workers...")
        worker_manager = get_worker_manager()
        await worker_manager.stop_all()
        logger.info("All workers stopped")


# Create FastAPI app with lifespan
app = FastAPI(
    title="Camunda Workflow Service",
    description="REST API for managing BPMN workflows with Camunda 7",
    version=settings.VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)}
    )


# Include routers
app.include_router(health.router)
app.include_router(deployments.router, prefix="/api/v1")
app.include_router(processes.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")


# Root endpoint
@app.get("/")
async def root():
    """Service information."""
    return {
        "service": settings.SERVICE_NAME,
        "version": settings.VERSION,
        "description": "Camunda Workflow Service for NouxCubeIA",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "deployments": "/api/v1/deployments",
            "processes": "/api/v1/processes",
            "tasks": "/api/v1/tasks"
        }
    }
