"""
Application middlewares configuration
"""
import logging
import time
from typing import Any, Callable
from urllib.parse import urlparse

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

    # Define critical origins that must always be allowed for this deployment
    critical_origins = [
        "http://nexus-docs360.es:3000",
        "http://nexus-docs360.es:3001",
        "http://192.168.1.58:3000",
        "http://192.168.1.58:3001",
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:8000"
    ]

    # Ensure critical origins are present
    for origin in critical_origins:
        if origin not in cors_origins:
            cors_origins.append(origin)

    # Log initial state
    logger.info(f"🔧 CORS Configuration Starting...")
    logger.info(f"🌐 DEBUG mode: {settings.DEBUG}")
    logger.info(f"✅ Final Allowed Origins: {cors_origins}")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],  # Allow all methods
        allow_headers=["*"],  # Allow all headers
        expose_headers=["*"]
    )
    logger.info("✅ CORS middleware configured with explicit origins and credentials=True")


async def log_requests_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware for detailed request logging"""
    start_time = time.time()

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
        logger.info(f"🔗 Origin: {origin or 'None'}")
        logger.info(f"🎫 Auth header: {'Yes' if auth_header else 'No'}")

        if auth_header and len(auth_header.split(' ')) == 2:
            auth_type, token = auth_header.split(' ')
            logger.info(f"🔐 Token: {auth_type} {token[:20]}...")

        # Log all headers for debugging when there's an auth problem
        logger.debug(f"📋 All headers: {dict(request.headers)}")

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
        # In production, only allow requests from trusted hosts
        trusted_hosts = {
            "nexusdocs360.app",
            "www.nexusdocs360.app",
            "api.nexusdocs360.app",
        }

        def _add_host(value: str | Any) -> None:
            if not value:
                return
            value_str = str(value)
            if not value_str:
                return
            parsed = urlparse(value_str if "://" in value_str else f"http://{value_str}")
            host = parsed.hostname or value_str.split(":")[0]
            if host:
                trusted_hosts.add(host)

        # Automatically trust hosts referenced by configuration/allowed origins
        _add_host(settings.SERVER_HOST)
        _add_host(settings.FRONTEND_URL)
        _add_host(settings.API_BASE_URL)

        for origin in settings.BACKEND_CORS_ORIGINS:
            _add_host(str(origin))

        # Common local/dev hosts
        trusted_hosts.update({"localhost", "127.0.0.1"})

        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=sorted(trusted_hosts)
        )
        logger.info(f"🛡️ Trusted hosts configured: {sorted(trusted_hosts)}")

def configure_middlewares(app) -> None:
    """Configure all application middlewares"""
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

    # Configure CORS - Must be added LAST to be the outermost middleware
    # This ensures it handles OPTIONS requests before any other middleware
    configure_cors(app)
