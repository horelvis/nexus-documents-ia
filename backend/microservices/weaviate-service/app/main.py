"""
Weaviate Microservice - RAG and Vector Search

This service provides:
- Weaviate vector database operations
- RAG Pipeline (7-layer retrieval-augmented generation)
- Document indexing and chunking
- Semantic and hybrid search
- Knowledge graph operations (Apache AGE)
- Cache management (retrieval, context, semantic)

Note: Agent orchestration (Emma v2, LangGraph) has been separated into
emma-agent-service for independent scaling. Query understanding is now
handled by LLM-based reasoning via Multi-Pipeline RAG sectors.
"""
import warnings

# Suppress httpx deprecation warning from litellm (uses data= instead of content=)
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
    public_knowledge_router,
    knowledge_router,
    learning_router,
)
from app.api.boe_legislation import router as boe_router
from app.api.legal_graph import router as legal_graph_router
from app.cag.api.cag import router as cag_router
from app.cag.api.vector import router as cag_vector_router

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
    logger.info("Starting Weaviate Service (RAG & Vector Search)...")
    logger.info(f"Service Port: {settings.service_port}")
    logger.info(f"Weaviate URL: {settings.weaviate_url}")

    # Initialize connections
    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.initialize()
        logger.info("Weaviate connection established")

        # Initialize integrated CAG engine
        try:
            from app.cag.services.cag_service import cag_service
            await cag_service.initialize()
            logger.info("CAG engine initialized")
        except Exception as cag_error:
            logger.error(f"Failed to initialize CAG engine: {cag_error}")
            raise cag_error

        # Initialize RAG Pipeline
        try:
            from app.services.rag.rag_pipeline import RAGPipeline
            pipeline = RAGPipeline()
            await pipeline.initialize()
            logger.info("RAG Pipeline initialized")
        except Exception as rag_error:
            logger.warning(f"RAG Pipeline initialization skipped: {rag_error}")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")
        # Continue startup but log error

    yield

    # Cleanup
    logger.info("Shutting down Weaviate Service...")

    try:
        from app.services.weaviate_service import weaviate_service
        await weaviate_service.cleanup()
        logger.info("Weaviate connections closed")
    except Exception:
        pass


# Create FastAPI app
app = FastAPI(
    title="Weaviate Service - RAG & Vector Search",
    description="Vector database operations, RAG pipeline, and knowledge graph queries",
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
app.include_router(public_knowledge_router, tags=["public-knowledge"])
app.include_router(boe_router, tags=["boe-legislation"])
app.include_router(knowledge_router, tags=["knowledge"])
app.include_router(learning_router, tags=["learning"])
app.include_router(legal_graph_router, tags=["legal-knowledge-graph"])
app.include_router(cag_router)
app.include_router(cag_vector_router)


# Health check
@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "weaviate-service",
        "version": "2.0.0",
        "weaviate_url": settings.weaviate_url,
        "capabilities": ["vector-search", "rag-pipeline", "indexing", "caching"]
    }


# ── Embedding endpoint (used by emma-agent-service for few-shot retrieval) ──

class EmbedRequest(BaseModel):
    """Request for text embedding generation."""
    text: str = ""
    texts: list[str] = []
    task: str = "retrieval.passage"  # Jina v3 task adapter (ignored by BGE-M3)


@app.post("/embed")
async def generate_embedding_endpoint(request: EmbedRequest):
    """Generate embeddings using the loaded model (BGE-M3 or Jina v3).

    Supports both single text and batch:
    - {"text": "..."} → {"embedding": [...]}
    - {"texts": ["...", "..."]} → {"embeddings": [[...], [...]]}

    The `task` parameter selects Jina v3 LoRA adapters:
    - "retrieval.query": for search queries
    - "retrieval.passage": for document chunks (default)
    - "classification": for semantic type classification
    """
    from app.services.weaviate_service import get_embedding_model
    import asyncio

    model = await get_embedding_model()
    if model is None or model == "tei":
        from app.services.weaviate_service import get_tei_embedding
        texts = request.texts if request.texts else [request.text]
        embeddings = await get_tei_embedding(texts)
        if embeddings is None:
            raise HTTPException(status_code=500, detail="Embedding generation failed")
        if request.text and not request.texts:
            return {"embedding": embeddings[0]}
        return {"embeddings": embeddings}

    texts = request.texts if request.texts else [request.text]
    task = request.task

    loop = asyncio.get_event_loop()

    def _encode():
        kwargs = {"convert_to_numpy": True}
        try:
            return model.encode(texts, prompt_name=task, **kwargs).tolist()
        except (TypeError, ValueError, KeyError):
            # BGE-M3 only accepts prompt_name in ['query', 'document']
            return model.encode(texts, **kwargs).tolist()

    embeddings = await loop.run_in_executor(None, _encode)

    if request.text and not request.texts:
        return {"embedding": embeddings[0]}
    return {"embeddings": embeddings}


# Service info
@app.get("/info")
async def service_info():
    """Service information and capabilities"""
    return {
        "service": "weaviate-service",
        "description": "RAG and Vector Search service using Weaviate",
        "capabilities": [
            "Vector storage and retrieval",
            "Semantic search",
            "Hybrid search (vector + keyword)",
            "RAG Pipeline (7 layers)",
            "Document indexing and chunking",
            "Multi-tier caching",
        ],
        "endpoints": {
            "weaviate": "/weaviate/* (vector operations)",
            "rag": "/weaviate/rag/* (RAG queries)",
            "knowledge": "/knowledge/* (knowledge graph)",
            "learning": "/learning/* (user learning)",
            "legal": "/legal/* (legal knowledge graph)",
            "verified": "Moved to emma-agent-service (port 8009)",
            "cag": "/cag/*",
            "health": "/health",
            "docs": "/docs" if settings.debug else None
        },
        "note": "Agent orchestration moved to emma-agent-service (port 8009)"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug
    )
