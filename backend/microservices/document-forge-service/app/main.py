"""Document Forge Service — template-based document generation with LLM field detection."""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.analyze import router as analyze_router
from app.api.convert import router as convert_router
from app.api.persist import router as persist_router
from app.api.render import router as render_router
from app.api.sessions import router as sessions_router
from app.clients.gotenberg_client import get_gotenberg_client
from app.clients.llm_client import get_llm_client
from app.core.config import get_settings
from app.services.session_store import get_session_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify dependencies. Shutdown: close connections."""
    settings = get_settings()
    logger.info(
        "Starting %s on port %d", settings.service_name, settings.service_port
    )

    # Verify gotenberg-service connectivity
    gotenberg = get_gotenberg_client()
    if await gotenberg.health():
        logger.info("gotenberg-service: healthy")
    else:
        logger.warning("gotenberg-service: unreachable (PDF conversion unavailable)")

    yield

    # Shutdown
    store = get_session_store()
    await store.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Document Forge Service",
    description="Template-based document generation with LLM-powered field detection",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    if request.url.path in ("/health",):
        return await call_next(request)
    start = time.time()
    response = await call_next(request)
    elapsed = (time.time() - start) * 1000
    logger.info(
        "%s %s → %d (%.0fms)", request.method, request.url.path, response.status_code, elapsed
    )
    return response


# Routes
app.include_router(analyze_router, tags=["analyze"])
app.include_router(render_router, tags=["render"])
app.include_router(convert_router, tags=["convert"])
app.include_router(persist_router, tags=["persist"])
app.include_router(sessions_router, tags=["sessions"])


@app.get("/health")
async def health():
    """Service health check."""
    checks = {}

    # Redis
    try:
        store = get_session_store()
        r = await store._get_redis()
        await r.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {e}"

    # vLLM/SGLang
    try:
        import httpx

        settings = get_settings()
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.vllm_base_url}/models")
            checks["vllm"] = "healthy" if resp.status_code == 200 else f"status={resp.status_code}"
    except Exception as e:
        checks["vllm"] = f"unhealthy: {e}"

    # Gotenberg
    gotenberg = get_gotenberg_client()
    checks["gotenberg"] = "healthy" if await gotenberg.health() else "unhealthy"

    all_healthy = all(v == "healthy" for v in checks.values())
    # Degrade gracefully — vLLM and gotenberg are optional at startup
    critical = checks.get("redis", "").startswith("healthy")

    return {
        "status": "healthy" if all_healthy else ("degraded" if critical else "critical"),
        "service": "document-forge-service",
        "checks": checks,
    }
