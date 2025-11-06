"""
Rate limiting middleware for API protection
"""
import logging
import time
from collections import defaultdict
from typing import Dict, Tuple

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from app.core.security_config import RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW

logger = logging.getLogger(__name__)

# In-memory storage for rate limiting (use Redis in production)
_rate_limit_storage: Dict[str, list] = defaultdict(list)


def _get_client_key(request: Request) -> str:
    """Generate a unique key for the client based on IP and path"""
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    return f"{client_ip}:{path}"


def _is_rate_limited(client_key: str) -> bool:
    """Check if client has exceeded rate limit"""
    current_time = time.time()
    request_times = _rate_limit_storage[client_key]

    # Remove old requests outside the window
    request_times[:] = [t for t in request_times if current_time - t < RATE_LIMIT_WINDOW]

    # Check if limit exceeded
    if len(request_times) >= RATE_LIMIT_REQUESTS:
        return True

    # Add current request
    request_times.append(current_time)
    return False


def _get_remaining_requests(client_key: str) -> int:
    """Get remaining requests for client"""
    current_time = time.time()
    request_times = _rate_limit_storage[client_key]

    # Clean old requests
    request_times[:] = [t for t in request_times if current_time - t < RATE_LIMIT_WINDOW]

    return max(0, RATE_LIMIT_REQUESTS - len(request_times))


async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware"""
    # Skip rate limiting for health checks and static files
    if request.url.path in ["/health", "/healthz"] or request.url.path.startswith("/static"):
        return await call_next(request)

    client_key = _get_client_key(request)

    if _is_rate_limited(client_key):
        logger.warning(f"🚫 Rate limit exceeded for {client_key}")
        return JSONResponse(
            status_code=429,
            content={
                "detail": "Too many requests",
                "retry_after": RATE_LIMIT_WINDOW
            },
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)}
        )

    # Add rate limit headers to response
    response = await call_next(request)

    remaining = _get_remaining_requests(client_key)
    response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_REQUESTS)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(int(time.time()) + RATE_LIMIT_WINDOW)

    return response