"""
Security configuration and constants
"""
import os
import logging
from typing import List

from app.core.config import settings

logger = logging.getLogger(__name__)


# Security headers
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}

# Rate limiting
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "100"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

# File upload security
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(50 * 1024 * 1024)))  # 50MB default
ALLOWED_EXTENSIONS = [
    'pdf', 'docx', 'txt', 'md', 'csv', 'xlsx', 'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff', 'webp', 'json'
]

# Password security
MIN_PASSWORD_LENGTH = int(os.getenv("MIN_PASSWORD_LENGTH", "8"))
PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]"

# JWT security
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", settings.SECRET_KEY)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Encryption
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
if not ENCRYPTION_KEY and not settings.DEBUG:
    raise ValueError("ENCRYPTION_KEY environment variable is required in production")

# CORS security - strict origins for production
PRODUCTION_CORS_ORIGINS = [
    # SaaS domain
    "https://nouxcubeia.app",
    "https://www.nouxcubeia.app",
    "https://api.nouxcubeia.app",
    # On-premise (DDNS)
    "https://nouxcubeai.ddns.net",
    "https://nouxcubeai.ddns.net:8000",   # API (tls-proxy)
    "https://nouxcubeai.ddns.net:8009",   # Emma agent (tls-proxy)
    "https://nouxcubeai.ddns.net:8007",   # Weaviate (tls-proxy)
    "https://nouxcubeai.ddns.net:8085",   # KeyCloak
    # Legacy local domain
    "https://nouxcube.local.es",
    "https://www.nouxcube.local.es",
    "https://nouxcube.local.es:3000",
    "https://www.nouxcube.local.es:3000",
]

# Development CORS origins (more permissive but still secure)
# NOTE: In DEBUG mode, we now use "*" (allow all) for maximum flexibility
# with dynamic ports. This can be changed back to specific origins if needed.
DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://192.168.1.58:3000",  # Frontend IP
    "http://localhost:5173",  # Vite
    "http://localhost:4000",  # Common dev port
    "http://localhost:8080",  # Common dev port
]

def get_cors_origins() -> List[str]:
    """Get appropriate CORS origins based on environment"""
    if settings.DEBUG:
        # In development, allow all origins for flexibility with dynamic ports
        # This solves the "origin-when-cross-origin" issue when frontend ports change
        logger.info("🔧 DEBUG mode - allowing ALL origins (*) for development flexibility")
        logger.info("💡 This allows any localhost port to connect (solves dynamic port issues)")
        return ["*"]
    else:
        # In production, use configured origins or fallback to secure defaults
        configured_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
        origins = configured_origins if configured_origins else PRODUCTION_CORS_ORIGINS
        # Strip trailing slashes — Pydantic v2 AnyHttpUrl adds "/" but browsers
        # send Origin without it, and Starlette does exact string comparison.
        return [o.rstrip("/") for o in origins]


def get_dynamic_cors_origins() -> List[str]:
    """Alternative: Get CORS origins with dynamic localhost port detection"""
    if not settings.DEBUG:
        return get_cors_origins()

    # For development, detect and allow localhost with any port
    base_origins = DEVELOPMENT_CORS_ORIGINS.copy()

    # Add localhost with a wide range of ports
    for port in range(3000, 3010):  # 3000-3009
        base_origins.extend([
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        ])

    for port in [4000, 5000, 8000, 8080, 5173, 5174]:  # Common dev ports
        base_origins.extend([
            f"http://localhost:{port}",
            f"http://127.0.0.1:{port}",
        ])

    # Remove duplicates
    return list(set(base_origins))

def is_secure_environment() -> bool:
    """Check if running in a secure environment"""
    return not settings.DEBUG and os.getenv("SECURE_ENV", "false").lower() == "true"

def get_security_middleware_config():
    """Get security middleware configuration"""
    return {
        "ssl_redirect": not settings.DEBUG,
        "session_cookie_secure": not settings.DEBUG,
        "session_cookie_httponly": True,
        "session_cookie_samesite": "Lax",
    }
