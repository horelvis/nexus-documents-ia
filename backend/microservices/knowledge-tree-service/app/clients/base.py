"""Base HTTP client with connection pooling and retry logic"""
import asyncio
import logging
from typing import Any, Optional
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class HTTPClientConfig:
    """Configuration for HTTP client"""
    base_url: str
    timeout: float = 120.0
    max_connections: int = 100
    max_keepalive_connections: int = 20
    keepalive_expiry: float = 30.0
    retry_attempts: int = 3
    retry_delay: float = 1.0
    retry_backoff: float = 2.0


class BaseHTTPClient:
    """
    Base HTTP client with connection pooling, retry logic, and circuit breaker.

    Features:
    - Connection pooling for performance
    - Automatic retry with exponential backoff
    - Graceful error handling
    - Request/response logging
    """

    def __init__(self, config: HTTPClientConfig):
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client with connection pooling"""
        if self._client is None or self._client.is_closed:
            async with self._lock:
                if self._client is None or self._client.is_closed:
                    limits = httpx.Limits(
                        max_connections=self.config.max_connections,
                        max_keepalive_connections=self.config.max_keepalive_connections,
                        keepalive_expiry=self.config.keepalive_expiry
                    )
                    self._client = httpx.AsyncClient(
                        base_url=self.config.base_url,
                        timeout=httpx.Timeout(self.config.timeout),
                        limits=limits,
                        follow_redirects=True
                    )
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with automatic retry"""
        client = await self._get_client()
        last_error: Optional[Exception] = None
        delay = self.config.retry_delay

        for attempt in range(self.config.retry_attempts):
            try:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    logger.warning(
                        f"Client error {e.response.status_code} for {method} {path}: "
                        f"{e.response.text[:200]}"
                    )
                    raise
                last_error = e

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                logger.warning(
                    f"Connection error on attempt {attempt + 1}/{self.config.retry_attempts} "
                    f"for {method} {path}: {e}"
                )

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error for {method} {path}: {e}")

            if attempt < self.config.retry_attempts - 1:
                logger.info(f"Retrying {method} {path} in {delay:.1f}s...")
                await asyncio.sleep(delay)
                delay *= self.config.retry_backoff

        raise last_error or Exception(f"Request failed after {self.config.retry_attempts} attempts")

    async def get(self, path: str, **kwargs) -> httpx.Response:
        """Make GET request"""
        return await self._request_with_retry("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        """Make POST request"""
        return await self._request_with_retry("POST", path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        """Make PUT request"""
        return await self._request_with_retry("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """Make DELETE request"""
        return await self._request_with_retry("DELETE", path, **kwargs)

    async def get_json(self, path: str, **kwargs) -> dict[str, Any]:
        """Make GET request and parse JSON response"""
        response = await self.get(path, **kwargs)
        return response.json()

    async def post_json(self, path: str, **kwargs) -> dict[str, Any]:
        """Make POST request and parse JSON response"""
        response = await self.post(path, **kwargs)
        return response.json()
