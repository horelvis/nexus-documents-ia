"""
Emma Agent Service - Intelligent Query Orchestration

Provides AI agent capabilities:
- Emma v2 agent with domain routing and LLM-based reasoning
- LangGraph multi-agent orchestration
- Session and conversation management

Note: Query planning and classification is now handled by LLM reasoning
directly, replacing the previous rule-based SIL and SLM Router systems.

Separated from weaviate-service to enable:
- Independent scaling (agents vs retrieval)
- Fault isolation (LLM errors don't affect vector search)
- Faster iteration on agent logic
"""
import warnings

# Suppress httpx deprecation warning from litellm
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
from app.api import emma_router, learning_router, uploads_router, verified_router, predictive_router, training_router, background_router, triggers_router, notifications_router, channels_router, heartbeat_router
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

        # Preload Semantic Routers (downloads HuggingFace model if needed)
        try:
            from app.agents.orchestration import preload_semantic_routers, _SEMANTIC_ROUTER_AVAILABLE
            if _SEMANTIC_ROUTER_AVAILABLE and preload_semantic_routers:
                preload_semantic_routers()
            else:
                logger.warning("Semantic Router not available, skipping preload")
        except Exception as router_error:
            logger.warning(f"Semantic Router preload failed: {router_error}")

        # Initialize Emma AI
        if settings.agents_enabled:
            try:
                from app.services.emma_service import emma_service
                await emma_service.initialize()
                logger.info("Emma AI initialized (Emma orchestration with LLM-based reasoning)")
            except Exception as emma_error:
                logger.warning(f"Emma AI initialization skipped: {emma_error}")

    except Exception as e:
        logger.error(f"Service initialization failed: {e}")

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

    if request.url.path != "/health":
        logger.info(f"{request.method} {request.url.path}")

    response = await call_next(request)
    process_time = time.time() - start_time

    if request.url.path != "/health":
        logger.info(f"{response.status_code} completed in {process_time:.3f}s")

    return response


# Include routers
app.include_router(emma_router, prefix="/emma", tags=["emma"])
app.include_router(learning_router, prefix="/learning", tags=["learning"])
app.include_router(uploads_router, prefix="/emma", tags=["uploads"])
app.include_router(verified_router, tags=["verified-generation"])
app.include_router(predictive_router, tags=["predictive-analysis"])
app.include_router(training_router, tags=["training"])
app.include_router(background_router, prefix="/emma", tags=["background"])
app.include_router(triggers_router, tags=["triggers"])
app.include_router(notifications_router, prefix="/emma", tags=["notifications"])
app.include_router(channels_router, tags=["channels"])
app.include_router(heartbeat_router, prefix="/emma", tags=["heartbeat"])


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
            "Multi-provider LLM support (vLLM, OpenAI, Anthropic)",
        ],
        "agents": [
            "Emma (main orchestrator)",
            "Domain specialists (labor, fiscal, contract, privacy, etc.)",
        ],
        "endpoints": {
            "emma": "/emma/* (AI chat)",
            "learning": "/learning/* (feedback)",
            "health": "/health",
            "docs": "/docs" if settings.debug else None
        },
        "dependencies": {
            "weaviate_service": settings.weaviate_service_url,
            "vllm": settings.vllm_base_url if settings.vllm_enabled else None,
        },
        "note": "Query planning handled by LLM reasoning (SIL/SLM Router removed)"
    }


# Agent status endpoint
@app.get("/agents/status")
async def agents_status():
    """Emma AI agents status"""
    try:
        from app.agents import agent_config, get_emma
        from app.agents.langgraph import is_langgraph_enabled

        # Check if Emma is available
        emma_available = False
        try:
            emma = await get_emma()
            emma_available = emma is not None
        except Exception:
            pass

        return {
            "status": "available" if emma_available else "disabled",
            "version": "2.0",
            "emma": {
                "available": emma_available,
                "model_provider": agent_config.model_provider,
            },
            "langgraph": {
                "enabled": is_langgraph_enabled(),
                "specialists": ["privacy_agent", "legal_agent", "general_agent"],
            },
            "config": {
                "enabled": agent_config.enabled,
                "max_turns": agent_config.max_turns,
                "timeout_seconds": agent_config.timeout_seconds,
                "fallback_to_rag": agent_config.fallback_to_rag,
                "model_provider": agent_config.model_provider,
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
