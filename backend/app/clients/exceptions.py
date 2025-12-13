"""
HTTP Client Exceptions

Typed exceptions for microservice communication errors.
"""
from typing import Optional, Dict, Any


class HTTPClientError(Exception):
    """Base exception for HTTP client errors"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        service_name: Optional[str] = None,
        response_body: Optional[str] = None
    ):
        self.message = message
        self.status_code = status_code
        self.service_name = service_name
        self.response_body = response_body
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "status_code": self.status_code,
            "service": self.service_name,
        }


class ServiceUnavailableError(HTTPClientError):
    """Service is not reachable (connection refused, DNS error, etc.)"""

    def __init__(self, service_name: str, original_error: Optional[str] = None):
        super().__init__(
            message=f"Service '{service_name}' is unavailable",
            status_code=503,
            service_name=service_name,
            response_body=original_error
        )


class ServiceTimeoutError(HTTPClientError):
    """Request to service timed out"""

    def __init__(self, service_name: str, timeout_seconds: float):
        super().__init__(
            message=f"Request to '{service_name}' timed out after {timeout_seconds}s",
            status_code=504,
            service_name=service_name
        )
        self.timeout_seconds = timeout_seconds


class UpstreamError(HTTPClientError):
    """Service returned an error response (4xx, 5xx)"""

    def __init__(
        self,
        service_name: str,
        status_code: int,
        response_body: Optional[str] = None
    ):
        super().__init__(
            message=f"Service '{service_name}' returned error {status_code}",
            status_code=status_code,
            service_name=service_name,
            response_body=response_body
        )


class RateLimitError(HTTPClientError):
    """Service rate limit exceeded (429)"""

    def __init__(
        self,
        service_name: str,
        retry_after: Optional[int] = None
    ):
        super().__init__(
            message=f"Rate limit exceeded for '{service_name}'",
            status_code=429,
            service_name=service_name
        )
        self.retry_after = retry_after


class AuthenticationError(HTTPClientError):
    """Authentication failed (401)"""

    def __init__(self, service_name: str):
        super().__init__(
            message=f"Authentication failed for '{service_name}'",
            status_code=401,
            service_name=service_name
        )


class AuthorizationError(HTTPClientError):
    """Authorization failed (403)"""

    def __init__(self, service_name: str):
        super().__init__(
            message=f"Access forbidden for '{service_name}'",
            status_code=403,
            service_name=service_name
        )
