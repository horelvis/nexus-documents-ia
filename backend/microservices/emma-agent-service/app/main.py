"""
Emma Agent Service - Intelligent Query Orchestration

Provides AI agent capabilities:
- Emma v2 agent with LLM-based reasoning
- LangGraph multi-agent orchestration
- Session and conversation management

Separated from weaviate-service to enable:
- Independent scaling (agents vs retrieval)
- Fault isolation (LLM errors don't affect vector search)
- Faster iteration on agent logic
"""
import warnings

# Suppress httpx deprecation warning from litellm (transitive dep via semantic-router, not used directly)
warnings.filterwarnings(
    "ignore",
    message="Use 'content=<...>' to upload raw bytes/text content.",
    category=DeprecationWarning,
    module="httpx._models"
)

# Suppress pydantic v2 deprecation warnings
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

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time

from app.core.config import settings
from app.api import emma_router, uploads_router, training_router, background_router, triggers_router, notifications_router, channels_router, heartbeat_router, prompts_router, diagnostics_router, generated_documents_router
from app.api.explainability import router as explainability_router
from app.api.langgraph_protocol import router as langgraph_protocol_router
from app.api.report_downloads import router as report_downloads_router
from app.clients import get_weaviate_client

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce verbosity of noisy logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


async def _validate_required_prompts():
    """Verify critical prompts exist in Langfuse at startup.

    Checks a representative subset of prompts (one per section) to catch
    configuration issues early. Full validation happens via seed script --diff.
    """
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client

    # Representative prompts — one per section, covering critical paths
    critical_prompts = [
        "emma_react_system",
        "emma_fast_conversational_system",
        "emma_swarm_decompose",
        "emma_context_root",
    ]

    client = get_langfuse_prompt_client()
    missing = []

    for name in critical_prompts:
        try:
            prompt = await client.get_prompt(name, fallback="__check__")
            if prompt and prompt.content == "__check__":
                missing.append(name)
        except Exception:
            missing.append(name)

    if missing:
        logger.error(
            f"Missing {len(missing)} critical prompts in Langfuse: {missing}. "
            f"Create them via Langfuse UI or a migration script."
        )
    else:
        logger.info("Langfuse prompt validation passed (critical prompts present)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("Starting Emma Agent Service...")
    logger.info(f"Service Port: {settings.service_port}")
    logger.info(f"Weaviate Service URL: {settings.weaviate_service_url}")
    logger.info(f"Agents enabled: {settings.agents_enabled}")

    # Initialize connections
    try:
        # Verify weaviate-service connection
        client = get_weaviate_client()
        health = await client.health_check()
        if health.get("status") == "healthy":
            logger.info("Weaviate Service connection verified")
        else:
            logger.warning(f"Weaviate Service health check: {health}")

        # Initialize Emma AI — LangGraph is the primary orchestration engine.
        # Legacy orchestration routers (SemanticPatternRouter, NexusRouter) are
        # no longer preloaded; LangGraph's IntentRouter handles classification.
        if settings.agents_enabled:
            logger.info("Emma AI ready (LangGraph orchestration)")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")

    # Validate Langfuse prompts — fail fast if any are missing
    if settings.langfuse_enabled:
        try:
            await _validate_required_prompts()
        except Exception as e:
            logger.warning(f"Langfuse prompt validation skipped: {e}")

    # Initialize Event Bus (Emma Reactive)
    if settings.event_bus_enabled:
        try:
            from app.services.event_bus import event_bus
            health = await event_bus.health_check()
            logger.info(f"Event Bus: {health.get('status', 'unknown')}")
        except Exception as e:
            logger.warning(f"Event Bus initialization skipped: {e}")

    yield

    # Cleanup
    logger.info("Shutting down Emma Agent Service...")

    # Close HTTP clients
    try:
        from app.clients.weaviate_client import close_weaviate_client
        from app.clients.text_extraction_client import close_text_extraction_client
        await close_weaviate_client()
        await close_text_extraction_client()
        logger.info("HTTP clients closed")
    except Exception:
        pass

    # Close LangGraph checkpointer
    try:
        from app.core.checkpointer import close_checkpointer
        await close_checkpointer()
    except Exception:
        pass

    # Close reactive services
    try:
        from app.services.event_bus import event_bus
        from app.services.trigger_engine import trigger_engine
        from app.services.notification_service import notification_service
        from app.services.heartbeat import heartbeat_service
        await event_bus.close()
        await trigger_engine.close()
        await notification_service.close()
        await heartbeat_service.close()
    except Exception:
        pass


# Create FastAPI app
app = FastAPI(
    title="Emma Agent Service",
    description="Intelligent AI agent service for document analysis and question answering",
    version="1.0.0",
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

    skip_log = request.url.path == "/health" or request.url.path.startswith("/diagnostics")
    if not skip_log:
        logger.info(f"{request.method} {request.url.path}")

    response = await call_next(request)
    process_time = time.time() - start_time

    if not skip_log:
        logger.info(f"{response.status_code} completed in {process_time:.3f}s")

    return response


# Include routers
app.include_router(emma_router, prefix="/emma", tags=["emma"])
app.include_router(uploads_router, prefix="/emma", tags=["uploads"])
# verified_router and predictive_router removed — absorbed by /emma/query (sub-graph tools)
app.include_router(training_router, tags=["training"])
app.include_router(background_router, prefix="/emma", tags=["background"])
app.include_router(triggers_router, tags=["triggers"])
app.include_router(notifications_router, prefix="/emma", tags=["notifications"])
app.include_router(channels_router, tags=["channels"])
app.include_router(heartbeat_router, prefix="/emma", tags=["heartbeat"])
app.include_router(prompts_router, tags=["prompts"])
app.include_router(diagnostics_router, prefix="/diagnostics", tags=["diagnostics"])
app.include_router(generated_documents_router, tags=["generated-documents"])
app.include_router(explainability_router, prefix="/emma", tags=["explainability"])
app.include_router(langgraph_protocol_router, tags=["langgraph-protocol"])
app.include_router(report_downloads_router, tags=["reports"])


# Health check
@app.get("/health")
async def health_check():
    """Service health check"""
    # Check weaviate-service connection
    weaviate_status = "unknown"
    try:
        client = get_weaviate_client()
        health = await client.health_check()
        weaviate_status = health.get("status", "unknown")
    except Exception as e:
        weaviate_status = f"error: {str(e)[:50]}"

    return {
        "status": "healthy",
        "service": "emma-agent-service",
        "version": "1.0.0",
        "weaviate_service": weaviate_status,
        "agents_enabled": settings.agents_enabled,
    }


# Service info
@app.get("/info")
async def service_info():
    """Service information and capabilities"""
    return {
        "service": "emma-agent-service",
        "description": "Intelligent AI agent service for document analysis",
        "capabilities": [
            "Natural language query processing",
            "Multi-agent orchestration (Emma)",
            "LangGraph multi-agent workflows",
            "LLM-based query understanding and routing",
            "Domain-specific routing",
            "Conversation memory",
            "Session management",
            "Multi-provider LLM support (SGLang, OpenAI, Anthropic)",
        ],
        "agents": [
            "Emma (main orchestrator)",
            "Domain specialists (labor, fiscal, contract, privacy, etc.)",
        ],
        "endpoints": {
            "emma": "/emma/* (AI chat)",
            "health": "/health",
            "docs": "/docs" if settings.debug else None
        },
        "dependencies": {
            "weaviate_service": settings.weaviate_service_url,
            "sglang": settings.sglang_base_url if settings.sglang_enabled else None,
        },
        "note": "Query planning handled by LLM reasoning"
    }


# Agent status endpoint
@app.get("/agents/status")
async def agents_status():
    """Emma AI agents status"""
    try:
        return {
            "status": "available",
            "version": "2.0",
            "orchestration": "LangGraph",
            "config": {
                "enabled": settings.agents_enabled,
                "model": settings.sglang_model,
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=settings.service_port,
        reload=settings.debug
    )
