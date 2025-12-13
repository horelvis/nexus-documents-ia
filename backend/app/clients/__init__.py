"""
HTTP Clients Module

Provides standardized HTTP clients for microservice communication.

Usage:
    from app.clients import BaseHTTPClient, ServiceUnavailableError

    class MyServiceClient(BaseHTTPClient):
        def __init__(self):
            super().__init__(
                service_name="my-service",
                base_url="http://my-service:8000",
                timeout_type="default"  # or 'fast', 'ai', 'document', 'long', 'upload'
            )

        async def get_item(self, item_id: str) -> dict:
            response = await self.get(f"/api/v1/items/{item_id}")
            return response.json()
"""

from app.clients.base import BaseHTTPClient
from app.clients.config import (
    TimeoutConfig,
    RetryConfig,
    ServiceConfig,
    SERVICE_TIMEOUTS,
    STANDARD_HEADERS,
    get_timeout_for_service,
    get_api_key,
)
from app.clients.exceptions import (
    HTTPClientError,
    ServiceUnavailableError,
    ServiceTimeoutError,
    UpstreamError,
    RateLimitError,
    AuthenticationError,
    AuthorizationError,
)

__all__ = [
    # Base client
    "BaseHTTPClient",
    # Config
    "TimeoutConfig",
    "RetryConfig",
    "ServiceConfig",
    "SERVICE_TIMEOUTS",
    "STANDARD_HEADERS",
    "get_timeout_for_service",
    "get_api_key",
    # Exceptions
    "HTTPClientError",
    "ServiceUnavailableError",
    "ServiceTimeoutError",
    "UpstreamError",
    "RateLimitError",
    "AuthenticationError",
    "AuthorizationError",
]
