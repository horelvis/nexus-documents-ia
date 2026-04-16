"""
MCP Client Manager - Connection Pool and Server Management.

Manages connections to MCP servers, including:
- Connection pooling (per server)
- Health checks and automatic reconnection
- Tool discovery and caching
- Request routing

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    MCPClientManager                              │
    │                                                                  │
    │  ┌─────────────────────────────────────────────────────────┐    │
    │  │              Connection Pool (per server)                │    │
    │  │  ┌─────────┐  ┌─────────┐  ┌─────────┐                  │    │
    │  │  │ Conn 1  │  │ Conn 2  │  │ Conn N  │  (reusable)     │    │
    │  │  └─────────┘  └─────────┘  └─────────┘                  │    │
    │  └─────────────────────────────────────────────────────────┘    │
    │                                                                  │
    │  ┌─────────────────────────────────────────────────────────┐    │
    │  │              Tool Cache (TTL-based)                      │    │
    │  │  server_name → [tool_1, tool_2, ...]                    │    │
    │  └─────────────────────────────────────────────────────────┘    │
    │                                                                  │
    │  ┌─────────────────────────────────────────────────────────┐    │
    │  │              Health Monitor (background task)            │    │
    │  │  Periodic health checks + automatic reconnection         │    │
    │  └─────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import httpx
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.sse import sse_client

from .config import (
    MCPConfig,
    MCPServerConfig,
    MCPTransportType,
    MCPAuthType,
    get_mcp_config,
)

logger = logging.getLogger(__name__)


@dataclass
class MCPToolInfo:
    """Cached information about an MCP tool."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str
    original_name: str  # Name before prefix
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class MCPConnection:
    """
    Represents a connection to an MCP server.

    Wraps the MCP ClientSession with connection metadata.
    """
    server_config: MCPServerConfig
    session: Optional[ClientSession] = None
    connected: bool = False
    last_health_check: Optional[datetime] = None
    health_check_failures: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used: datetime = field(default_factory=datetime.utcnow)

    # Cached tools from this server
    tools: List[MCPToolInfo] = field(default_factory=list)
    tools_cache_expires: Optional[datetime] = None

    async def connect(self) -> bool:
        """
        Establish connection to the MCP server.

        Returns:
            True if connection successful, False otherwise
        """
        config = self.server_config

        try:
            if config.transport == MCPTransportType.STDIO:
                return await self._connect_stdio()
            else:  # HTTP or SSE
                return await self._connect_http()

        except Exception as e:
            logger.error(f"Failed to connect to MCP server {config.name}: {e}")
            self.connected = False
            return False

    async def _connect_stdio(self) -> bool:
        """Connect via STDIO transport."""
        config = self.server_config

        if not config.command:
            logger.error(f"STDIO transport requires 'command' for server {config.name}")
            return False

        server_params = StdioServerParameters(
            command=config.command,
            args=config.args,
            env={**config.env} if config.env else None,
        )

        # Create STDIO client
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                self.session = session
                self.connected = True
                logger.info(f"Connected to MCP server {config.name} via STDIO")
                return True

    async def _connect_http(self) -> bool:
        """Connect via HTTP/SSE transport."""
        config = self.server_config

        if not config.url:
            logger.error(f"HTTP transport requires 'url' for server {config.name}")
            return False

        # Build headers for authentication
        headers = self._build_auth_headers()

        # Use SSE client for HTTP transport
        async with sse_client(config.url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                self.session = session
                self.connected = True
                logger.info(f"Connected to MCP server {config.name} via HTTP/SSE")
                return True

    def _build_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers based on config."""
        headers = {}
        auth = self.server_config.auth

        if auth.type == MCPAuthType.API_KEY and auth.api_key:
            headers[auth.api_key_header] = auth.api_key

        elif auth.type == MCPAuthType.BEARER and auth.api_key:
            headers["Authorization"] = f"Bearer {auth.api_key}"

        elif auth.type == MCPAuthType.BASIC and auth.username and auth.password:
            import base64
            credentials = base64.b64encode(
                f"{auth.username}:{auth.password}".encode()
            ).decode()
            headers["Authorization"] = f"Basic {credentials}"

        return headers

    async def disconnect(self) -> None:
        """Close the connection."""
        if self.session:
            try:
                # MCP sessions auto-close via context manager
                self.session = None
            except Exception as e:
                logger.warning(f"Error disconnecting from {self.server_config.name}: {e}")

        self.connected = False

    async def health_check(self) -> bool:
        """
        Perform a health check on the connection.

        Returns:
            True if healthy, False otherwise
        """
        if not self.connected or not self.session:
            return False

        try:
            # Try to list tools as a health check
            await self.session.list_tools()
            self.last_health_check = datetime.utcnow()
            self.health_check_failures = 0
            return True

        except Exception as e:
            logger.warning(f"Health check failed for {self.server_config.name}: {e}")
            self.health_check_failures += 1
            return False

    async def list_tools(self, force_refresh: bool = False) -> List[MCPToolInfo]:
        """
        Get available tools from this server.

        Uses caching to avoid repeated requests.

        Args:
            force_refresh: Force refresh from server

        Returns:
            List of tool information
        """
        # Check cache
        if not force_refresh and self.tools and self.tools_cache_expires:
            if datetime.utcnow() < self.tools_cache_expires:
                return self.tools

        if not self.connected or not self.session:
            return []

        try:
            result = await self.session.list_tools()
            config = self.server_config

            self.tools = []
            for tool in result.tools:
                # Check if tool is allowed
                if not config.is_tool_allowed(tool.name):
                    continue

                tool_info = MCPToolInfo(
                    name=config.get_tool_name(tool.name),
                    description=tool.description or "",
                    input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {},
                    server_name=config.name,
                    original_name=tool.name,
                )
                self.tools.append(tool_info)

            # Cache for 5 minutes
            self.tools_cache_expires = datetime.utcnow() + timedelta(minutes=5)
            logger.debug(f"Loaded {len(self.tools)} tools from {config.name}")

            return self.tools

        except Exception as e:
            logger.error(f"Failed to list tools from {self.server_config.name}: {e}")
            return []

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """
        Execute a tool on this server.

        Args:
            tool_name: Tool name (with or without prefix)
            arguments: Tool arguments

        Returns:
            Tool execution result

        Raises:
            RuntimeError: If not connected
            Exception: On tool execution failure
        """
        if not self.connected or not self.session:
            raise RuntimeError(f"Not connected to {self.server_config.name}")

        # Strip prefix if present
        config = self.server_config
        original_name = tool_name
        if config.tool_prefix and tool_name.startswith(config.tool_prefix):
            original_name = tool_name[len(config.tool_prefix):]

        self.last_used = datetime.utcnow()

        result = await self.session.call_tool(original_name, arguments)
        return result


class MCPClientManager:
    """
    Central manager for MCP server connections.

    Handles:
    - Connection lifecycle (create, health check, reconnect)
    - Connection pooling
    - Tool discovery and registration
    - Request routing to appropriate servers
    """

    def __init__(self, config: Optional[MCPConfig] = None):
        """
        Initialize the MCP client manager.

        Args:
            config: MCP configuration (uses global config if not provided)
        """
        self.config = config or get_mcp_config()
        self._connections: Dict[str, MCPConnection] = {}
        self._tool_server_map: Dict[str, str] = {}  # tool_name → server_name
        self._lock = asyncio.Lock()
        self._initialized = False
        self._health_task: Optional[asyncio.Task] = None

    async def initialize(self) -> None:
        """
        Initialize all configured MCP server connections.

        Should be called at application startup.
        """
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            logger.info("Initializing MCP Client Manager...")

            for server_config in self.config.get_enabled_servers():
                await self._create_connection(server_config)

            # Start background health check task
            if self.config.enabled:
                self._health_task = asyncio.create_task(self._health_check_loop())

            self._initialized = True
            logger.info(f"MCP Client Manager initialized with {len(self._connections)} connections")

    async def shutdown(self) -> None:
        """
        Shutdown all connections.

        Should be called at application shutdown.
        """
        logger.info("Shutting down MCP Client Manager...")

        # Cancel health check task
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

        # Disconnect all servers
        async with self._lock:
            for conn in self._connections.values():
                await conn.disconnect()
            self._connections.clear()
            self._tool_server_map.clear()
            self._initialized = False

    async def _create_connection(self, config: MCPServerConfig) -> Optional[MCPConnection]:
        """Create and connect to an MCP server."""
        if config.name in self._connections:
            return self._connections[config.name]

        conn = MCPConnection(server_config=config)

        # Try to connect
        if await conn.connect():
            self._connections[config.name] = conn

            # Discover and cache tools
            tools = await conn.list_tools()
            for tool in tools:
                self._tool_server_map[tool.name] = config.name

            return conn

        return None

    async def _health_check_loop(self) -> None:
        """Background task for periodic health checks."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute

                for server_name, conn in list(self._connections.items()):
                    if not conn.server_config.health_check_enabled:
                        continue

                    healthy = await conn.health_check()

                    if not healthy and conn.health_check_failures >= 3:
                        logger.warning(f"Reconnecting to {server_name} after 3 failures")
                        await conn.disconnect()
                        await conn.connect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    def get_connection(self, server_name: str) -> Optional[MCPConnection]:
        """Get a connection by server name."""
        return self._connections.get(server_name)

    def get_connection_for_tool(self, tool_name: str) -> Optional[MCPConnection]:
        """Get the connection that provides a specific tool."""
        server_name = self._tool_server_map.get(tool_name)
        if server_name:
            return self._connections.get(server_name)
        return None

    async def get_available_tools(
        self,
        category: Optional[str] = None
    ) -> List[MCPToolInfo]:
        """
        Get all available MCP tools.

        Args:
            category: Optional tool category filter

        Returns:
            List of available tools
        """
        tools = []

        for server_config in self.config.get_enabled_servers():
            conn = self._connections.get(server_config.name)
            if conn and conn.connected:
                server_tools = await conn.list_tools()
                tools.extend(server_tools)

        return tools

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        server_name: Optional[str] = None
    ) -> Any:
        """
        Execute an MCP tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            server_name: Optional specific server to use

        Returns:
            Tool execution result

        Raises:
            ValueError: If tool not found
            RuntimeError: If execution fails
        """
        # Get connection
        if server_name:
            conn = self._connections.get(server_name)
        else:
            conn = self.get_connection_for_tool(tool_name)

        if not conn:
            raise ValueError(f"Tool not found: {tool_name}")

        if not conn.server_config.enabled:
            raise ValueError(f"Server for tool {tool_name} is disabled")

        # Execute tool
        return await conn.call_tool(tool_name, arguments)

    def get_all_tool_names(self) -> List[str]:
        """Get all registered tool names."""
        return list(self._tool_server_map.keys())

    def get_server_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get status of all MCP servers.

        Returns:
            Dictionary with server status information
        """
        status = {}
        for name, conn in self._connections.items():
            status[name] = {
                "connected": conn.connected,
                "last_health_check": conn.last_health_check.isoformat() if conn.last_health_check else None,
                "health_failures": conn.health_check_failures,
                "tools_count": len(conn.tools),
                "created_at": conn.created_at.isoformat(),
                "last_used": conn.last_used.isoformat(),
            }
        return status


# Global manager singleton
_manager: Optional[MCPClientManager] = None


def get_mcp_manager() -> MCPClientManager:
    """
    Get the global MCP client manager singleton.

    Creates the manager on first call.

    Returns:
        MCPClientManager instance
    """
    global _manager
    if _manager is None:
        _manager = MCPClientManager()
    return _manager


async def initialize_mcp() -> MCPClientManager:
    """
    Initialize the global MCP client manager.

    Should be called at application startup.

    Returns:
        Initialized MCPClientManager
    """
    manager = get_mcp_manager()
    await manager.initialize()
    return manager


async def shutdown_mcp() -> None:
    """
    Shutdown the global MCP client manager.

    Should be called at application shutdown.
    """
    global _manager
    if _manager:
        await _manager.shutdown()
        _manager = None
