"""
Security configuration and constants
"""
import os
from typing import List

from app.core.config import settings


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
    "https://nexusdocs360.app",
    "https://www.nexusdocs360.app",
    "https://api.nexusdocs360.app",
]

# Development CORS origins (more permissive but still secure)
DEVELOPMENT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://localhost:5173",  # Vite
    "http://localhost:4000",  # Common dev port
    "http://localhost:8080",  # Common dev port
]

def get_cors_origins() -> List[str]:
    """Get appropriate CORS origins based on environment"""
    if settings.DEBUG:
        return DEVELOPMENT_CORS_ORIGINS
    else:
        # In production, use configured origins or fallback to secure defaults
        configured_origins = [str(origin) for origin in settings.BACKEND_CORS_ORIGINS]
        return configured_origins if configured_origins else PRODUCTION_CORS_ORIGINS

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