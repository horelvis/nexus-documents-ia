"""
MCP (Model Context Protocol) Integration for Weaviate Service.

This module provides MCP client infrastructure for connecting to external
data sources through standardized MCP servers.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    Emma Agent Framework                          │
    │  ┌──────────────────────────────────────────────────────────┐   │
    │  │  Native Tools          │   MCP Tools (Dynamic)           │   │
    │  │  (emma_v2_tools)       │   (from MCP servers)            │   │
    │  └──────────────────────────────────────────────────────────┘   │
    └────────────────────────────────┬────────────────────────────────┘
                                     │
    ┌────────────────────────────────▼────────────────────────────────┐
    │                    MCPClientManager                              │
    │  ┌────────────────────────────────────────────────────────────┐ │
    │  │  Connection Pool       │  Tool Discovery  │  Health Check  │ │
    │  │  (per tenant)          │  & Registration  │  & Reconnect   │ │
    │  └────────────────────────────────────────────────────────────┘ │
    └────────────────────────────────┬────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │                           │                           │
         ▼                           ▼                           ▼
    ┌─────────────┐         ┌──────────────┐         ┌─────────────┐
    │ MCP-Storage │         │ MCP-REST-API │         │ MCP-Database│
    │   Server    │         │    Server    │         │   Server    │
    │             │         │              │         │             │
    │ Tools:      │         │ Tools:       │         │ Tools:      │
    │ - upload    │         │ - rest_get   │         │ - db_query  │
    │ - download  │         │ - rest_post  │         │ - db_list   │
    │ - list      │         │              │         │             │
    └─────────────┘         └──────────────┘         └─────────────┘

Usage:
    from app.mcp import MCPClientManager, MCPConfig

    # Initialize manager
    manager = MCPClientManager()
    await manager.initialize()

    # Get tools for a tenant
    tools = await manager.get_tools_for_tenant("tenant-123")

    # Execute a tool
    result = await manager.execute_tool(
        server_name="storage",
        tool_name="storage_upload",
        arguments={"file_path": "doc.pdf", "content": b"..."},
        tenant_id="tenant-123"
    )
"""

from .config import (
    MCPConfig,
    MCPServerConfig,
    MCPTransportType,
    MCPAuthConfig,
    get_mcp_config,
)
from .client_manager import (
    MCPClientManager,
    MCPConnection,
    get_mcp_manager,
)
from .tool_adapter import (
    MCPToolAdapter,
    MCPTool,
    mcp_tool_to_base_tool,
)

__all__ = [
    # Config
    "MCPConfig",
    "MCPServerConfig",
    "MCPTransportType",
    "MCPAuthConfig",
    "get_mcp_config",
    # Client Manager
    "MCPClientManager",
    "MCPConnection",
    "get_mcp_manager",
    # Tool Adapter
    "MCPToolAdapter",
    "MCPTool",
    "mcp_tool_to_base_tool",
]
