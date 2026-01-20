"""
MCP Configuration Module.

Defines configuration models for MCP servers and their connections.
Supports loading from environment variables and YAML configuration files.

Configuration can be provided via:
1. Environment variables (MCP_SERVERS_CONFIG path)
2. YAML configuration file
3. Programmatic configuration

Example YAML configuration:
    servers:
      - name: storage
        transport: http
        url: http://mcp-storage:8000
        enabled: true
        timeout: 30

      - name: erp_api
        transport: http
        url: https://erp.company.com/mcp
        tenant_whitelist:
          - tenant-123
          - tenant-456
        auth:
          type: oauth2
          client_id: ${ERP_CLIENT_ID}
          client_secret: ${ERP_CLIENT_SECRET}

      - name: database
        transport: stdio
        command: python
        args:
          - -m
          - mcp_database_server
        env:
          DATABASE_URL: ${EXTERNAL_DB_URL}
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class MCPTransportType(str, Enum):
    """Supported MCP transport types."""
    STDIO = "stdio"  # Subprocess communication
    HTTP = "http"    # HTTP/SSE transport
    SSE = "sse"      # Server-Sent Events (alias for HTTP)


class MCPAuthType(str, Enum):
    """Supported authentication types for MCP servers."""
    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"
    BASIC = "basic"


class MCPAuthConfig(BaseModel):
    """Authentication configuration for MCP server."""
    type: MCPAuthType = Field(default=MCPAuthType.NONE)

    # API Key / Bearer
    api_key: Optional[str] = Field(default=None)
    api_key_header: str = Field(default="X-API-Key")

    # OAuth2
    client_id: Optional[str] = Field(default=None)
    client_secret: Optional[str] = Field(default=None)
    token_url: Optional[str] = Field(default=None)
    scopes: List[str] = Field(default_factory=list)

    # Basic Auth
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)

    @field_validator('api_key', 'client_id', 'client_secret', 'token_url', 'username', 'password', mode='before')
    @classmethod
    def expand_env_vars(cls, v: Optional[str]) -> Optional[str]:
        """Expand environment variables in config values."""
        if v and isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            env_var = v[2:-1]
            return os.getenv(env_var, "")
        return v


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    # Server identification
    name: str = Field(..., description="Unique server identifier")
    description: Optional[str] = Field(default=None, description="Human-readable description")

    # Transport configuration
    transport: MCPTransportType = Field(default=MCPTransportType.HTTP)

    # HTTP transport settings
    url: Optional[str] = Field(default=None, description="Server URL (for HTTP transport)")

    # STDIO transport settings
    command: Optional[str] = Field(default=None, description="Command to run (for STDIO)")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    cwd: Optional[str] = Field(default=None, description="Working directory")

    # Connection settings
    timeout: int = Field(default=30, description="Connection timeout in seconds")
    max_retries: int = Field(default=3, description="Max connection retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retries (seconds)")

    # Health check
    health_check_interval: int = Field(default=60, description="Health check interval (seconds)")
    health_check_enabled: bool = Field(default=True)

    # Access control
    enabled: bool = Field(default=True, description="Whether server is enabled")
    tenant_whitelist: Optional[List[str]] = Field(
        default=None,
        description="If set, only these tenants can access this server"
    )
    tenant_blacklist: List[str] = Field(
        default_factory=list,
        description="Tenants that cannot access this server"
    )

    # Authentication
    auth: MCPAuthConfig = Field(default_factory=MCPAuthConfig)

    # Tool filtering
    tool_whitelist: Optional[List[str]] = Field(
        default=None,
        description="If set, only expose these tools"
    )
    tool_blacklist: List[str] = Field(
        default_factory=list,
        description="Tools to hide from this server"
    )

    # Tool name prefix (for namespacing)
    tool_prefix: Optional[str] = Field(
        default=None,
        description="Prefix to add to tool names (e.g., 'storage_' for storage server)"
    )

    @field_validator('url', 'command', mode='before')
    @classmethod
    def expand_env_vars(cls, v: Optional[str]) -> Optional[str]:
        """Expand environment variables."""
        if v and isinstance(v, str) and v.startswith("${") and v.endswith("}"):
            env_var = v[2:-1]
            return os.getenv(env_var, "")
        return v

    @field_validator('env', mode='before')
    @classmethod
    def expand_env_dict(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Expand environment variables in env dict."""
        if not v:
            return {}
        result = {}
        for key, value in v.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                result[key] = os.getenv(env_var, "")
            else:
                result[key] = value
        return result

    def is_accessible_by_tenant(self, tenant_id: str) -> bool:
        """Check if tenant can access this server."""
        if not self.enabled:
            return False

        # Check blacklist first
        if tenant_id in self.tenant_blacklist:
            return False

        # If whitelist is set, tenant must be in it
        if self.tenant_whitelist is not None:
            return tenant_id in self.tenant_whitelist

        return True

    def get_tool_name(self, original_name: str) -> str:
        """Get the potentially prefixed tool name."""
        if self.tool_prefix:
            return f"{self.tool_prefix}{original_name}"
        return original_name

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool should be exposed."""
        if tool_name in self.tool_blacklist:
            return False
        if self.tool_whitelist is not None:
            return tool_name in self.tool_whitelist
        return True


class MCPConfig(BaseModel):
    """Root configuration for all MCP servers."""

    # Global settings
    enabled: bool = Field(default=True, description="Enable MCP integration")
    connection_timeout: int = Field(default=30, description="Default connection timeout")
    max_connections_per_server: int = Field(default=10, description="Max connections per server")

    # Server configurations
    servers: List[MCPServerConfig] = Field(default_factory=list)

    # Connection pool settings
    pool_min_size: int = Field(default=1, description="Minimum connections per server")
    pool_max_size: int = Field(default=10, description="Maximum connections per server")
    pool_idle_timeout: int = Field(default=300, description="Idle connection timeout (seconds)")

    # Retry settings
    global_max_retries: int = Field(default=3)
    global_retry_delay: float = Field(default=1.0)

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """Get server configuration by name."""
        for server in self.servers:
            if server.name == name:
                return server
        return None

    def get_servers_for_tenant(self, tenant_id: str) -> List[MCPServerConfig]:
        """Get all servers accessible by a tenant."""
        return [
            server for server in self.servers
            if server.is_accessible_by_tenant(tenant_id)
        ]

    def get_enabled_servers(self) -> List[MCPServerConfig]:
        """Get all enabled servers."""
        return [server for server in self.servers if server.enabled]


def load_config_from_yaml(path: str) -> MCPConfig:
    """
    Load MCP configuration from YAML file.

    Args:
        path: Path to YAML configuration file

    Returns:
        MCPConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"MCP config file not found: {path}")

    with open(config_path, 'r') as f:
        data = yaml.safe_load(f)

    if not data:
        return MCPConfig()

    return MCPConfig(**data)


def load_config_from_env() -> MCPConfig:
    """
    Load MCP configuration from environment variables.

    Environment variables:
        MCP_ENABLED: Enable/disable MCP (default: true)
        MCP_SERVERS_CONFIG: Path to YAML config file
        MCP_CONNECTION_TIMEOUT: Default timeout (default: 30)
        MCP_MAX_CONNECTIONS: Max connections per server (default: 10)

        # Per-server config (for simple setups without YAML):
        MCP_STORAGE_URL: Storage server URL
        MCP_STORAGE_ENABLED: Enable storage server

    Returns:
        MCPConfig instance
    """
    config = MCPConfig(
        enabled=os.getenv("MCP_ENABLED", "true").lower() == "true",
        connection_timeout=int(os.getenv("MCP_CONNECTION_TIMEOUT", "30")),
        max_connections_per_server=int(os.getenv("MCP_MAX_CONNECTIONS", "10")),
    )

    # Check for YAML config file
    yaml_path = os.getenv("MCP_SERVERS_CONFIG")
    if yaml_path and Path(yaml_path).exists():
        yaml_config = load_config_from_yaml(yaml_path)
        # Merge: YAML servers + env overrides
        config.servers = yaml_config.servers
        logger.info(f"Loaded MCP config from {yaml_path} with {len(config.servers)} servers")
    else:
        # Build config from individual env vars
        servers = []

        # Storage server
        storage_url = os.getenv("MCP_STORAGE_URL")
        if storage_url:
            servers.append(MCPServerConfig(
                name="storage",
                description="MCP Storage Server (GCS/NFS/SMB)",
                transport=MCPTransportType.HTTP,
                url=storage_url,
                enabled=os.getenv("MCP_STORAGE_ENABLED", "true").lower() == "true",
                tool_prefix="storage_",
            ))

        # REST API server
        rest_api_url = os.getenv("MCP_REST_API_URL")
        if rest_api_url:
            servers.append(MCPServerConfig(
                name="rest_api",
                description="MCP REST API Server (External APIs)",
                transport=MCPTransportType.HTTP,
                url=rest_api_url,
                enabled=os.getenv("MCP_REST_API_ENABLED", "true").lower() == "true",
                tool_prefix="api_",
            ))

        # Database server
        db_url = os.getenv("MCP_DATABASE_URL")
        if db_url:
            servers.append(MCPServerConfig(
                name="database",
                description="MCP Database Server (External DBs)",
                transport=MCPTransportType.HTTP,
                url=db_url,
                enabled=os.getenv("MCP_DATABASE_ENABLED", "true").lower() == "true",
                tool_prefix="db_",
            ))

        # Filesystem server (STDIO)
        fs_command = os.getenv("MCP_FILESYSTEM_COMMAND")
        if fs_command:
            servers.append(MCPServerConfig(
                name="filesystem",
                description="MCP Filesystem Server (NFS/SMB/FTP)",
                transport=MCPTransportType.STDIO,
                command=fs_command,
                args=os.getenv("MCP_FILESYSTEM_ARGS", "").split(),
                enabled=os.getenv("MCP_FILESYSTEM_ENABLED", "true").lower() == "true",
                tool_prefix="fs_",
            ))

        config.servers = servers
        if servers:
            logger.info(f"Configured {len(servers)} MCP servers from environment")

    return config


# Global config singleton
_config: Optional[MCPConfig] = None


def get_mcp_config() -> MCPConfig:
    """
    Get the global MCP configuration singleton.

    Loads from environment/YAML on first call.

    Returns:
        MCPConfig instance
    """
    global _config
    if _config is None:
        _config = load_config_from_env()
    return _config


def set_mcp_config(config: MCPConfig) -> None:
    """
    Set the global MCP configuration.

    Useful for testing or programmatic configuration.

    Args:
        config: MCPConfig instance to use
    """
    global _config
    _config = config
