"""
Configuration for MCP REST API Server.

External API endpoints can be configured via:
1. Environment variables
2. YAML configuration file
"""

import os
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import yaml


class APIEndpointConfig(BaseModel):
    """Configuration for a single API endpoint."""
    name: str
    base_url: str
    description: Optional[str] = None

    # Authentication
    auth_type: str = "none"  # none, api_key, bearer, basic, oauth2
    api_key: Optional[str] = None
    api_key_header: str = "X-API-Key"
    bearer_token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

    # OAuth2
    oauth2_token_url: Optional[str] = None
    oauth2_client_id: Optional[str] = None
    oauth2_client_secret: Optional[str] = None
    oauth2_scopes: List[str] = Field(default_factory=list)

    # Rate limiting
    rate_limit_requests: int = 100
    rate_limit_period: int = 60  # seconds

    # Access control
    tenant_whitelist: Optional[List[str]] = None
    tenant_blacklist: List[str] = Field(default_factory=list)

    # Timeouts
    timeout_seconds: int = 30

    def is_accessible_by_tenant(self, tenant_id: str) -> bool:
        """Check if tenant can access this endpoint."""
        if tenant_id in self.tenant_blacklist:
            return False
        if self.tenant_whitelist is not None:
            return tenant_id in self.tenant_whitelist
        return True


class Settings(BaseSettings):
    """MCP REST API Server settings."""

    service_name: str = "mcp-rest-api-server"
    service_port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Configuration file path
    config_file: str = os.getenv("API_CONFIG_FILE", "/app/config/apis.yaml")

    # Default timeout
    default_timeout: int = int(os.getenv("DEFAULT_TIMEOUT", "30"))

    # Rate limiting
    global_rate_limit: int = int(os.getenv("GLOBAL_RATE_LIMIT", "1000"))

    class Config:
        env_file = ".env"


settings = Settings()


def load_api_endpoints() -> Dict[str, APIEndpointConfig]:
    """
    Load API endpoint configurations from YAML file.

    Returns:
        Dict mapping endpoint names to their configurations
    """
    endpoints = {}

    if os.path.exists(settings.config_file):
        try:
            with open(settings.config_file, 'r') as f:
                config = yaml.safe_load(f)

            if config and 'endpoints' in config:
                for ep in config['endpoints']:
                    # Expand environment variables
                    for key in ['api_key', 'bearer_token', 'password', 'oauth2_client_secret']:
                        if key in ep and isinstance(ep[key], str):
                            if ep[key].startswith("${") and ep[key].endswith("}"):
                                env_var = ep[key][2:-1]
                                ep[key] = os.getenv(env_var, "")

                    endpoint = APIEndpointConfig(**ep)
                    endpoints[endpoint.name] = endpoint

        except Exception as e:
            import logging
            logging.error(f"Failed to load API config: {e}")

    return endpoints


# Global endpoints registry
_endpoints: Optional[Dict[str, APIEndpointConfig]] = None


def get_endpoints() -> Dict[str, APIEndpointConfig]:
    """Get the loaded API endpoints."""
    global _endpoints
    if _endpoints is None:
        _endpoints = load_api_endpoints()
    return _endpoints
