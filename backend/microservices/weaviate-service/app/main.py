"""
Weaviate Microservice - Vector Search & Indexing

This service provides:
- Weaviate vector database operations
- Document indexing and chunking
- Semantic and hybrid search

Note: RAG query pipeline, agent orchestration, and knowledge graph
have been separated into emma-agent-service and knowledge-tree-service.
"""
import warnings

# Suppress httpx deprecation warning from litellm (transitive dep via semantic-router, not used directly)
warnings.filterwarnings(
    "ignore",
    message="Use 'content=<...>' to upload raw bytes/text content.",
    category=DeprecationWarning,
    module="httpx._models"
)

# Suppress pydantic v2 deprecation warnings (class Config -> model_config)
try:
    from pydantic import PydanticDeprecatedSince20
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)
except ImportError:
    pass
warnings.filterwarnings(
    "ignore",
    message=".*class-based `config` is deprecated.*",
    category=DeprecationWarning
)

# Suppress FastAPI regex deprecation warning
warnings.filterwarnings(
    "ignore",
    message="`regex` has been deprecated.*",
    category=DeprecationWarning
)

# Suppress Click shell_completion deprecation from spacy
warnings.filterwarnings(
    "ignore",
    message=".*Importing 'parser.split_arg_string' is deprecated.*",
    category=DeprecationWarning
)

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time

from app.core.config import settings
from app.core.security import verify_api_key
from app.api import (
    weaviate_router,
    knowledge_router,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce verbosity of noisy logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("Starting Weaviate Service (Vector Search & Indexing)...")
    logger.info(f"Service Port: {settings.service_port}")
    logger.info(f"Weaviate URL: {settings.weaviate_url}")

    # Initialize connections
    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.initialize()
        logger.info("Weaviate connection established")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        # Continue startup but log error

    yield

    # Cleanup
    logger.info("Shutting down Weaviate Service...")

    try:
        from app.clients.intelligence_client import close_client
        await close_client()
    except Exception:
        pass

    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.cleanup()
        logger.info("Weaviate connections closed")
    except Exception:
        pass


# Create FastAPI app
app = FastAPI(
    title="Weaviate Service - Vector Search & Indexing",
    description="Vector database operations and document indexing",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if not settings.request_logging_enabled:
        return await call_next(request)

    start_time = time.time()

    # Skip health check spam
    if request.url.path != "/health":
        logger.info(f"{request.method} {request.url.path}")

    response = await call_next(request)
    process_time = time.time() - start_time

    if request.url.path != "/health":
        logger.info(f"{response.status_code} completed in {process_time:.3f}s")

    return response


# Include routers
app.include_router(weaviate_router, prefix="/weaviate", tags=["weaviate"])
app.include_router(knowledge_router, tags=["knowledge"])


# Health check
@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "weaviate-service",
        "version": "2.0.0",
        "weaviate_url": settings.weaviate_url,
        "capabilities": ["vector-search", "hybrid-search", "indexing"]
    }


# ── Embedding endpoint (used by emma-agent-service for few-shot retrieval) ──

class EmbedRequest(BaseModel):
    """Request for text embedding generation."""
    text: str = ""
    texts: list[str] = []
    task: str = "retrieval.passage"  # Jina v3 task adapter (ignored by BGE-M3)


@app.post("/embed")
async def generate_embedding_endpoint(request: EmbedRequest):
    """Generate embeddings via intelligence-docs-service (proxy).

    Supports both single text and batch:
    - {"text": "..."} → {"embedding": [...]}
    - {"texts": ["...", "..."]} → {"embeddings": [[...], [...]]}
    """
    from app.clients import intelligence_client

    if request.text and not request.texts:
        embedding = await intelligence_client.embed(request.text, task=request.task)
        if embedding is None:
            raise HTTPException(status_code=500, detail="Embedding generation failed")
        return {"embedding": embedding}
    else:
        texts = request.texts or [request.text]
        embeddings = await intelligence_client.embed_batch(texts, task=request.task)
        if embeddings is None:
            raise HTTPException(status_code=500, detail="Embedding generation failed")
        return {"embeddings": embeddings}


# Service info
@app.get("/info")
async def service_info():
    """Service information and capabilities"""
    return {
        "service": "weaviate-service",
        "description": "Vector Search and Indexing service using Weaviate",
        "capabilities": [
            "Vector storage and retrieval",
            "Semantic search",
            "Hybrid search (vector + keyword)",
            "Document indexing and chunking",
        ],
        "endpoints": {
            "weaviate": "/weaviate/* (vector operations)",
            "knowledge": "/knowledge/* (knowledge endpoints)",
            "health": "/health",
            "docs": "/docs" if settings.debug else None
        },
        "note": "RAG query pipeline moved to emma-agent-service (port 8009)"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug
    )
