"""
Application middlewares configuration
"""
import logging
import time
from urllib.parse import urlparse
from typing import Callable

from fastapi import Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security_config import get_cors_origins, SECURITY_HEADERS
from app.core.rate_limiting import rate_limit_middleware
from app.core.compression import CompressionMiddleware
from app.core.metrics import performance_monitor
from app.core.prometheus_metrics import MetricsMiddleware
from app.core.structured_logging import RequestContextMiddleware, structured_logger

logger = logging.getLogger(__name__)


def configure_cors(app) -> None:
    """Configure CORS middleware with secure settings"""
    cors_origins = get_cors_origins()

    if settings.DEBUG:
        logger.info("🔧 DEBUG mode - allowing flexible development origins")
        logger.info(f"🌐 Configured origins: {len(cors_origins)} total")

        # Log a sample of origins for debugging
        if len(cors_origins) > 10:
            logger.info(f"📋 Sample origins: {cors_origins[:5]} ... and {len(cors_origins)-5} more")
        else:
            logger.info(f"📋 All origins: {cors_origins}")

        # In development, also allow localhost with any port as fallback
        if settings.ALLOW_ALL_CORS:
            logger.warning("🚨 ALLOW_ALL_CORS is enabled - allowing all origins!")
            cors_origins = ["*"]
    else:
        if not cors_origins:
            logger.error("❌ CRITICAL: No CORS origins configured for production!")
            logger.error("🔧 Set BACKEND_CORS_ORIGINS environment variable")
            cors_origins = []  # Fail securely

    logger.info(f"🌐 Final CORS configuration: {len(cors_origins)} origins")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False if cors_origins == ["*"] else True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=[
            "Accept",
            "Accept-Language",
            "Content-Language",
            "Content-Type",
            "Authorization",
            "X-Requested-With",
            "X-User-Id",
            "X-Tenant-Id",
            "X-Requested-With",
            "X-CSRF-Token"
        ],
    )
    logger.info("✅ CORS middleware configured with secure settings")


async def log_requests_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware for detailed request logging"""
    start_time = time.time()

    # Handle OPTIONS requests early (CORS preflight)
    if request.method == "OPTIONS":
        logger.info(f"🔄 OPTIONS: {request.url.path}")
        if settings.DEBUG:
            logger.info(f"🌐 Origin: {request.headers.get('origin')}")
            logger.debug("🔍 Request headers: %s", dict(request.headers))

        response = await call_next(request)
        process_time = time.time() - start_time

        if settings.DEBUG:
            logger.debug("📨 Response headers: %s", dict(response.headers))
        logger.info(f"✅ OPTIONS completed: {response.status_code} ({process_time:.3f}s)")

        if response.status_code != 200:
            logger.error(f"❌ OPTIONS failed with {response.status_code}")

        return response

    # Get request information
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    auth_header = request.headers.get("authorization")
    user_id = request.headers.get("x-user-id")
    content_type = request.headers.get("content-type")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    # Skip logging for health checks (Docker health check spam)
    is_health_check = request.url.path in ["/health", "/healthz"]

    # Log initial request (skip health checks)
    if not is_health_check:
        logger.info(f"📨 {request.method} {request.url.path} from {client_ip}")

    # Log headers for auth endpoints
    if request.url.path.startswith("/api/v1/auth"):
        logger.info(f"🔍 Auth endpoint: {request.url.path}")
        if settings.DEBUG:
            logger.info(f"🔗 Origin: {origin or 'None'}")
            logger.info(f"🎫 Auth header present: {'Yes' if auth_header else 'No'}")
            logger.debug("📋 All headers: %s", dict(request.headers))

    try:
        # Procesar la solicitud
        response = await call_next(request)

        # Calcular tiempo de procesamiento
        process_time = time.time() - start_time

        # Añadir cabecera de tiempo de procesamiento
        response.headers["X-Process-Time"] = str(process_time)

        # Monitorear rendimiento HTTP
        response_size = len(response.body) if hasattr(response, 'body') else 0
        performance_monitor.monitor_http_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration=process_time,
            response_size=response_size
        )

        # Log de respuesta exitosa (skip health checks)
        if not is_health_check:
            logger.info(f"✅ {response.status_code} {request.method} {request.url.path} ({process_time:.3f}s)")

        # Log adicional para endpoints de auth con errores
        if request.url.path.startswith("/api/v1/auth") and response.status_code >= 400:
            if response.status_code == 401:
                logger.error("🚫 Unauthorized - token validation failed")
            elif response.status_code == 403:
                logger.error("🚫 Forbidden - user authenticated but not authorized")
            elif response.status_code == 400:
                logger.error("⚠️ Bad Request - missing or malformed token")

        return response

    except Exception as e:
        process_time = time.time() - start_time
        # Log errors (skip health checks)
        if not is_health_check:
            logger.error(f"❌ {request.method} {request.url.path} failed: {str(e)} ({process_time:.3f}s)")

        # Log additional info for auth endpoint exceptions
        if request.url.path.startswith("/api/v1/auth"):
            logger.error(f"💥 Auth exception: {type(e).__name__}")
            if hasattr(e, 'status_code'):
                logger.error(f"📋 HTTP {e.status_code}: {getattr(e, 'detail', 'No detail')}")

        raise


async def security_headers_middleware(request: Request, call_next: Callable) -> Response:
    """Add security headers to all responses"""
    response = await call_next(request)

    # Add security headers
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value

    return response

def configure_trusted_hosts(app) -> None:
    """Configure trusted hosts middleware for production"""
    if not settings.DEBUG:
        def _host_from_url(url: str) -> str | None:
            try:
                parsed = urlparse(url)
                return parsed.hostname
            except Exception:
                return None

        # In production, only allow requests from trusted hosts.
        # Include configured frontend/backend hosts so deployments on custom domains don't break.
        configured_hosts = [
            _host_from_url(getattr(settings, "FRONTEND_URL", "") or ""),
            _host_from_url(getattr(settings, "API_BASE_URL", "") or ""),
            _host_from_url(str(getattr(settings, "SERVER_HOST", "") or "")),
        ]
        trusted_hosts = [
            "nouxcubeia.app",
            "www.nouxcubeia.app",
            "api.nouxcubeia.app",
            "nouxcube.local.es",
            "www.nouxcube.local.es",
            *[h for h in configured_hosts if h],
        ]
        trusted_hosts = sorted(set(trusted_hosts))
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=trusted_hosts
        )
        logger.info(f"🛡️ Trusted hosts configured: {trusted_hosts}")

def configure_middlewares(app) -> None:
    """Configure all application middlewares"""
    # Configure CORS
    configure_cors(app)

    # Configure trusted hosts (production only)
    configure_trusted_hosts(app)

    # Add compression middleware (must be first for response compression)
    app.add_middleware(CompressionMiddleware)

    # Add Prometheus metrics middleware
    app.add_middleware(MetricsMiddleware)

    # Add structured logging middleware
    app.add_middleware(RequestContextMiddleware, logger=structured_logger)

    # Add security headers middleware
    app.middleware("http")(security_headers_middleware)

    # Add rate limiting middleware
    app.middleware("http")(rate_limit_middleware)

    # Add request logging middleware
    app.middleware("http")(log_requests_middleware)
