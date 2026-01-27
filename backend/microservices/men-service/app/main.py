"""
MEN Service - Mixture of Experts Network for Document Intelligence.

A microservice that provides intelligent document querying using:
- Orchestrator (1.5B): Domain classification
- Experts (0.5B + LoRA): Tenant-specific knowledge
- LLM Modeler (3B): Response synthesis with conversational memory

Architecture benefits:
- Low VRAM footprint (~4.5 GB vs 16GB for single large model)
- Dynamic expert loading/unloading
- Conversational memory per session
- Tenant-specific customization via LoRA adapters

Endpoints:
- POST /men/query - Full query pipeline
- POST /men/decide - Classification only
- GET /men/health - Health check
- GET /men/status - Detailed status
- GET /men/sessions/{id}/history - Get conversation history
- POST /men/sessions/{id}/clear - Clear session memory
- GET /men/tenants/{id}/experts - List tenant experts
- POST /men/tenants/{id}/experts/train - Train new expert
"""

import logging
import sys
import warnings
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Suppress warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message=".*torch.cuda.amp.autocast.*")

from .core.config import settings, VRAM_ESTIMATES
from .api import main_router, tenant_router, session_router

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Reduce noise from transformers and torch
logging.getLogger("transformers").setLevel(logging.WARNING)
logging.getLogger("torch").setLevel(logging.WARNING)
logging.getLogger("accelerate").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown of MEN components.
    """
    # Startup
    logger.info("=" * 60)
    logger.info(f"Starting {settings.service_name} v{settings.service_version}")
    logger.info("=" * 60)

    logger.info(f"Configuration:")
    logger.info(f"  Service Port: {settings.service_port}")
    logger.info(f"  MEN Enabled: {settings.men_enabled}")
    logger.info(f"  Modeler Enabled: {settings.modeler_enabled}")
    logger.info(f"  Experts Enabled: {settings.experts_enabled}")
    logger.info(f"  Orchestrator Model: {settings.orchestrator_model}")
    logger.info(f"  Modeler Model: {settings.llm_modeler_model}")
    logger.info(f"  Expert Base Model: {settings.expert_base_model}")
    logger.info(f"  Experts Directory: {settings.experts_dir}")

    if settings.men_enabled:
        try:
            from .services import initialize_men_system
            men_system = initialize_men_system()

            logger.info("=" * 60)
            logger.info("MEN System initialized successfully!")
            logger.info(f"  Estimated VRAM usage:")
            logger.info(f"    - Base (Orchestrator + Modeler): ~{VRAM_ESTIMATES['base_total']} GB")
            logger.info(f"    - Peak (with Expert): ~{VRAM_ESTIMATES['peak_total']} GB")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Failed to initialize MEN System: {e}", exc_info=True)
            logger.warning("Service will start but MEN queries will fail")
    else:
        logger.info("MEN System disabled by configuration")

    yield

    # Shutdown
    logger.info("Shutting down MEN Service...")

    try:
        from .services import get_men_system
        men_system = get_men_system()
        if men_system.is_loaded:
            men_system.unload()
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

    logger.info("MEN Service stopped")


# Create FastAPI application
app = FastAPI(
    title="MEN Service",
    description="Mixture of Experts Network for Document Intelligence",
    version=settings.service_version,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log incoming requests."""
    logger.debug(f"{request.method} {request.url.path}")
    response = await call_next(request)
    return response


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "type": str(type(exc).__name__)}
    )


# Include routers
app.include_router(main_router)
app.include_router(session_router)
app.include_router(tenant_router)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": settings.service_name,
        "version": settings.service_version,
        "description": "Mixture of Experts Network for Document Intelligence",
        "endpoints": {
            "query": "/men/query",
            "decide": "/men/decide",
            "health": "/men/health",
            "status": "/men/status",
            "sessions": "/men/sessions/{session_id}",
            "tenants": "/men/tenants/{tenant_id}/experts",
            "docs": "/docs",
        }
    }


# Direct health endpoint (no auth required)
@app.get("/health")
async def root_health():
    """Simple health check at root."""
    try:
        from .services import get_men_system
        men_system = get_men_system()
        return {
            "status": "healthy" if men_system.is_loaded else "starting",
            "service": settings.service_name,
        }
    except Exception:
        return {
            "status": "starting",
            "service": settings.service_name,
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug,
    )
