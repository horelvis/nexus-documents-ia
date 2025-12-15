"""
Base HTTP Client for Microservice Communication

Provides:
- Standardized headers (X-API-Key)
- Retry with exponential backoff
- Configurable timeouts
- Context propagation (tenant, user, request IDs)
- Proper error handling with typed exceptions
"""
import logging
import asyncio
from typing import Dict, Any, Optional, Union
from contextlib import asynccontextmanager

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from app.clients.config import (
    TimeoutConfig,
    RetryConfig,
    ServiceConfig,
    STANDARD_HEADERS,
    get_api_key,
    get_timeout_for_service,
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

logger = logging.getLogger(__name__)


class RetryableError(Exception):
    """Marker exception for errors that should be retried"""
    pass


class BaseHTTPClient:
    """
    Base async HTTP client for microservice communication.

    Features:
    - Uses X-API-Key header (standard for internal services)
    - Retry with exponential backoff for transient errors
    - Configurable timeouts per service type
    - Request/Response logging
    - Context header propagation

    Example:
        class StorageClient(BaseHTTPClient):
            def __init__(self):
                super().__init__(
                    service_name="storage",
                    base_url="http://storage-service:8001",
                    timeout_type="upload"
                )

            async def upload_file(self, file_data: bytes) -> dict:
                return await self.post("/api/v1/storage/upload", data=file_data)
    """

    def __init__(
        self,
        service_name: str,
        base_url: str,
        timeout_type: str = "default",
        timeout_config: Optional[TimeoutConfig] = None,
        retry_config: Optional[RetryConfig] = None,
        api_key: Optional[str] = None,
    ):
        """
        Initialize the HTTP client.

        Args:
            service_name: Name for logging and error messages
            base_url: Base URL of the service (e.g., http://service:8000)
            timeout_type: Preset timeout type ('fast', 'default', 'document', 'ai', 'long', 'upload')
            timeout_config: Custom timeout config (overrides timeout_type)
            retry_config: Custom retry config
            api_key: API key (defaults to MICROSERVICES_API_KEY)
        """
        self.service_name = service_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_config or get_timeout_for_service(timeout_type)
        self.retry_config = retry_config or RetryConfig()
        self._api_key = api_key

        logger.debug(
            f"Initialized {service_name} client | base_url={self.base_url} "
            f"timeout_read={self.timeout.read}s retry_attempts={self.retry_config.max_attempts}"
        )

    @property
    def api_key(self) -> str:
        """Get API key lazily to allow settings to be loaded"""
        if self._api_key is None:
            self._api_key = get_api_key()
        return self._api_key

    def _build_headers(
        self,
        extra_headers: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build request headers with API key and context"""
        headers = {
            **STANDARD_HEADERS,
            "X-API-Key": self.api_key,
        }

        # Add context headers
        if tenant_id:
            headers["X-Tenant-ID"] = str(tenant_id)
        if user_id:
            headers["X-User-ID"] = str(user_id)
        if request_id:
            headers["X-Request-ID"] = str(request_id)
            headers.setdefault("X-Correlation-ID", str(request_id))

        # Merge extra headers
        if extra_headers:
            headers.update(extra_headers)

        return headers

    def _build_timeout(self) -> httpx.Timeout:
        """Build httpx Timeout from config"""
        return httpx.Timeout(
            connect=self.timeout.connect,
            read=self.timeout.read,
            write=self.timeout.write,
            pool=self.timeout.pool,
        )

    def _handle_response_error(self, response: httpx.Response) -> None:
        """Convert HTTP error responses to typed exceptions"""
        status = response.status_code

        if status == 401:
            raise AuthenticationError(self.service_name)
        elif status == 403:
            raise AuthorizationError(self.service_name)
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                self.service_name,
                retry_after=int(retry_after) if retry_after else None
            )
        elif status >= 500 or status in self.retry_config.retry_on_status:
            # Server errors that might be retried
            raise RetryableError(f"Service returned {status}")
        elif status >= 400:
            # Client errors (not retryable)
            raise UpstreamError(
                self.service_name,
                status_code=status,
                response_body=response.text[:500] if response.text else None
            )

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> httpx.Response:
        """
        Execute HTTP request with retry logic.

        Retries on:
        - Connection errors
        - Timeout errors
        - Server errors (500, 502, 503, 504)
        - Rate limits (429) with exponential backoff
        """
        retry_decorator = retry(
            stop=stop_after_attempt(self.retry_config.max_attempts),
            wait=wait_exponential(
                multiplier=self.retry_config.base_delay,
                max=self.retry_config.max_delay,
                exp_base=self.retry_config.exponential_base,
            ),
            retry=retry_if_exception_type((RetryableError, httpx.TransportError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )

        @retry_decorator
        async def _execute():
            async with httpx.AsyncClient(timeout=self._build_timeout()) as client:
                response = await client.request(method, url, **kwargs)

                if response.status_code >= 400:
                    self._handle_response_error(response)

                return response

        return await _execute()

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> httpx.Response:
        """
        Make an HTTP request to the service.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., /api/v1/documents)
            tenant_id: Tenant ID for X-Tenant-ID header
            user_id: User ID for X-User-ID header
            request_id: Request ID for X-Request-ID header
            headers: Additional headers
            **kwargs: Additional httpx request arguments (json, data, params, etc.)

        Returns:
            httpx.Response

        Raises:
            ServiceUnavailableError: Service not reachable
            ServiceTimeoutError: Request timed out
            UpstreamError: Service returned error response
            RateLimitError: Rate limit exceeded
            AuthenticationError: API key invalid
            AuthorizationError: Access forbidden
        """
        url = f"{self.base_url}{endpoint}"
        request_headers = self._build_headers(headers, tenant_id, user_id, request_id)
        if "json" in kwargs and "Content-Type" not in request_headers:
            request_headers["Content-Type"] = "application/json"

        # Log request (without sensitive data)
        log_kwargs = {k: v for k, v in kwargs.items() if k not in ('data', 'content', 'files')}
        logger.debug(
            f"HTTP {method} {url} | service={self.service_name} "
            f"tenant={tenant_id} user={user_id[:8] if user_id else None}... "
            f"kwargs={list(log_kwargs.keys())}"
        )

        try:
            response = await self._request_with_retry(
                method,
                url,
                headers=request_headers,
                **kwargs
            )

            logger.debug(
                f"HTTP {method} {url} -> {response.status_code} | "
                f"service={self.service_name} elapsed={response.elapsed.total_seconds():.3f}s"
            )

            return response

        except httpx.ConnectError as e:
            logger.error(f"Connection error to {self.service_name}: {e}")
            raise ServiceUnavailableError(self.service_name, str(e))

        except httpx.TimeoutException as e:
            logger.error(f"Timeout to {self.service_name}: {e}")
            raise ServiceTimeoutError(self.service_name, self.timeout.read)

        except RetryableError:
            # All retries exhausted
            logger.error(f"All retries exhausted for {self.service_name}")
            raise ServiceUnavailableError(
                self.service_name,
                f"Service unavailable after {self.retry_config.max_attempts} retries"
            )

    # Convenience methods

    async def get(
        self,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> httpx.Response:
        """HTTP GET request"""
        return await self.request("GET", endpoint, params=params, **kwargs)

    async def post(
        self,
        endpoint: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        **kwargs
    ) -> httpx.Response:
        """HTTP POST request"""
        return await self.request("POST", endpoint, json=json, data=data, **kwargs)

    async def put(
        self,
        endpoint: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> httpx.Response:
        """HTTP PUT request"""
        return await self.request("PUT", endpoint, json=json, **kwargs)

    async def delete(
        self,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """HTTP DELETE request"""
        return await self.request("DELETE", endpoint, **kwargs)

    async def health_check(self) -> Dict[str, Any]:
        """
        Check service health.

        Returns:
            Dict with status and optional details
        """
        try:
            response = await self.get("/health")
            if response.status_code == 200:
                return {"status": "healthy", "service": self.service_name}
            return {"status": "degraded", "service": self.service_name, "code": response.status_code}
        except HTTPClientError as e:
            return {"status": "unhealthy", "service": self.service_name, "error": str(e)}

    # JSON convenience methods

    async def get_json(
        self,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """GET request returning JSON"""
        response = await self.get(endpoint, **kwargs)
        return response.json()

    async def post_json(
        self,
        endpoint: str,
        *,
        json: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """POST request returning JSON"""
        response = await self.post(endpoint, json=json, **kwargs)
        return response.json()
