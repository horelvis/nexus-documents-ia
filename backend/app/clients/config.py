"""
HTTP Client Configuration

Centralized configuration for microservice communication.
Standardizes timeouts, retries, and headers across all clients.
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
import os


@dataclass
class TimeoutConfig:
    """Timeout configuration for HTTP requests"""
    connect: float = 5.0      # Connection timeout
    read: float = 30.0        # Read timeout (default)
    write: float = 30.0       # Write timeout
    pool: float = 5.0         # Connection pool timeout


@dataclass
class RetryConfig:
    """Retry configuration with exponential backoff"""
    max_attempts: int = 3
    base_delay: float = 1.0           # Initial delay in seconds
    max_delay: float = 30.0           # Maximum delay between retries
    exponential_base: float = 2.0     # Exponential backoff multiplier
    retry_on_status: tuple = (429, 500, 502, 503, 504)  # Status codes to retry


# Service-specific timeout presets
SERVICE_TIMEOUTS: Dict[str, TimeoutConfig] = {
    # Fast services (health checks, simple queries)
    "fast": TimeoutConfig(connect=3.0, read=10.0, write=10.0),

    # Default for most microservices
    "default": TimeoutConfig(connect=5.0, read=30.0, write=30.0),

    # Services that process documents (text extraction, indexing)
    "document": TimeoutConfig(connect=5.0, read=60.0, write=60.0),

    # AI/LLM services (CAG, Weaviate RAG, Emma)
    "ai": TimeoutConfig(connect=5.0, read=120.0, write=30.0),

    # Long-running operations (migrations, batch processing)
    "long": TimeoutConfig(connect=10.0, read=300.0, write=60.0),

    # File uploads (storage service)
    "upload": TimeoutConfig(connect=5.0, read=60.0, write=120.0),
}


@dataclass
class ServiceConfig:
    """Configuration for a specific microservice"""
    name: str
    base_url: str
    timeout: TimeoutConfig = field(default_factory=lambda: SERVICE_TIMEOUTS["default"])
    retry: RetryConfig = field(default_factory=RetryConfig)

    # Standard headers for internal communication
    # X-API-Key is the preferred method for microservice auth
    api_key_header: str = "X-API-Key"


# Standard headers for microservice communication
STANDARD_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# Context headers to propagate
CONTEXT_HEADERS = [
    "X-Tenant-ID",
    "X-User-ID",
    "X-Request-ID",
    "X-Correlation-ID",
]


def get_timeout_for_service(service_type: str) -> TimeoutConfig:
    """
    Get timeout configuration for a service type.

    Args:
        service_type: One of 'fast', 'default', 'document', 'ai', 'long', 'upload'

    Returns:
        TimeoutConfig for the service type
    """
    return SERVICE_TIMEOUTS.get(service_type, SERVICE_TIMEOUTS["default"])


def get_api_key() -> str:
    """Get the microservice API key from settings"""
    from app.core.config import settings
    return settings.MICROSERVICES_API_KEY
