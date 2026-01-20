"""
Qwen-Agent Integration for MCP Tools.

This module provides seamless integration between MCP servers and the
Qwen-Agent framework, enabling MCP tools to be used as native Qwen-Agent
tools with the @register_tool decorator pattern.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    MCP Server                                    │
    │  Tools: [upload, download, list_files, ...]                     │
    └────────────────────────┬────────────────────────────────────────┘
                             │ MCP Protocol
                             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │             MCPQwenToolFactory                                   │
    │  Creates dynamic Qwen-Agent tool classes from MCP tools          │
    └────────────────────────┬────────────────────────────────────────┘
                             │ @register_tool
                             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │             Qwen-Agent Assistant                                 │
    │  function_list=['mcp_storage_upload', 'mcp_storage_download']   │
    └─────────────────────────────────────────────────────────────────┘

Usage:
    from app.mcp import get_mcp_manager
    from app.mcp.qwen_integration import (
        register_mcp_tools_for_tenant,
        get_mcp_tool_names_for_tenant,
    )

    # At startup
    manager = get_mcp_manager()
    await manager.initialize()

    # Register tools for a tenant
    await register_mcp_tools_for_tenant("tenant-123", manager)

    # Get tool names for Assistant
    tool_names = get_mcp_tool_names_for_tenant("tenant-123")
    agent = Assistant(llm=llm_cfg, function_list=tool_names)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set, Type, Union, TYPE_CHECKING

from qwen_agent.tools.base import BaseTool as QwenBaseTool, register_tool

if TYPE_CHECKING:
    from .client_manager import MCPClientManager, MCPToolInfo

logger = logging.getLogger(__name__)

# Registry of dynamically created MCP tool classes
_mcp_tool_classes: Dict[str, Type[QwenBaseTool]] = {}
_tenant_tool_registry: Dict[str, Set[str]] = {}  # tenant_id → set of tool names


def _run_async(coro):
    """
    Run an async coroutine from sync context.

    Handles the case where we might already be in an async context (FastAPI)
    or need to create a new event loop.
    """
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=120)
    except RuntimeError:
        return asyncio.run(coro)


def _json_schema_to_qwen_params(input_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert JSON Schema to Qwen-Agent parameter format.

    Args:
        input_schema: JSON Schema dict from MCP tool

    Returns:
        List of parameter definitions in Qwen-Agent format
    """
    params = []

    if not input_schema or "properties" not in input_schema:
        return params

    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    for name, prop in properties.items():
        param = {
            "name": name,
            "type": prop.get("type", "string"),
            "description": prop.get("description", ""),
            "required": name in required,
        }

        # Add enum if present
        if "enum" in prop:
            param["enum"] = prop["enum"]

        # Add default if present
        if "default" in prop:
            param["default"] = prop["default"]

        params.append(param)

    return params


def create_mcp_tool_class(
    tool_info: "MCPToolInfo",
    client_manager: "MCPClientManager",
) -> Type[QwenBaseTool]:
    """
    Dynamically create a Qwen-Agent tool class for an MCP tool.

    This creates a class that:
    1. Has the MCP tool's description and parameters
    2. Calls the MCP server when executed
    3. Handles async/sync conversion

    Args:
        tool_info: Tool metadata from MCP server
        client_manager: Manager for MCP connections

    Returns:
        Dynamically created tool class
    """
    tool_name = tool_info.name
    tool_desc = tool_info.description
    tool_params = _json_schema_to_qwen_params(tool_info.input_schema)
    server_name = tool_info.server_name
    original_name = tool_info.original_name

    # Store manager reference in closure
    _manager = client_manager

    class MCPDynamicTool(QwenBaseTool):
        """Dynamically generated Qwen-Agent tool for MCP."""

        description = tool_desc
        parameters = tool_params

        def call(self, params: Union[str, dict], **kwargs) -> str:
            """Execute the MCP tool."""
            if isinstance(params, str):
                try:
                    params = json.loads(params)
                except json.JSONDecodeError:
                    return json.dumps({"error": f"Invalid JSON params: {params}"})

            # Get tenant_id from params or context
            tenant_id = params.pop("tenant_id", None)
            if not tenant_id:
                # Try to get from execution context
                try:
                    from app.core.execution_context import resolve_tenant_id
                    tenant_id = resolve_tenant_id(None)
                except Exception:
                    return json.dumps({"error": "tenant_id is required"})

            return _run_async(self._execute_mcp(params, tenant_id))

        async def _execute_mcp(self, params: dict, tenant_id: str) -> str:
            """Async execution of MCP tool."""
            try:
                logger.info(f"MCP tool call: {tool_name}, server={server_name}, tenant={tenant_id}")

                result = await _manager.execute_tool(
                    tool_name=tool_name,
                    arguments=params,
                    tenant_id=tenant_id,
                    server_name=server_name,
                )

                # Format result
                if isinstance(result, dict):
                    return json.dumps(result, ensure_ascii=False, indent=2)
                elif isinstance(result, (list, tuple)):
                    return json.dumps(list(result), ensure_ascii=False, indent=2)
                else:
                    return str(result)

            except Exception as e:
                logger.exception(f"MCP tool error: {tool_name} - {e}")
                return json.dumps({
                    "error": str(e),
                    "tool": tool_name,
                    "server": server_name,
                })

    # Set class name for debugging
    MCPDynamicTool.__name__ = f"MCP_{tool_name}"
    MCPDynamicTool.__qualname__ = f"MCP_{tool_name}"

    return MCPDynamicTool


async def register_mcp_tools_for_tenant(
    tenant_id: str,
    client_manager: "MCPClientManager",
) -> List[str]:
    """
    Register all available MCP tools for a tenant with Qwen-Agent.

    This discovers tools from all accessible MCP servers and creates
    Qwen-Agent tool classes for them.

    Args:
        tenant_id: Tenant identifier
        client_manager: MCP connection manager

    Returns:
        List of registered tool names
    """
    registered_names = []

    # Get all tools for this tenant
    tool_infos = await client_manager.get_tools_for_tenant(tenant_id)

    for tool_info in tool_infos:
        tool_name = tool_info.name

        # Skip if already registered
        if tool_name in _mcp_tool_classes:
            registered_names.append(tool_name)
            continue

        # Create and register the tool class
        tool_class = create_mcp_tool_class(tool_info, client_manager)

        # Register with Qwen-Agent
        try:
            register_tool(tool_name)(tool_class)
            _mcp_tool_classes[tool_name] = tool_class
            registered_names.append(tool_name)
            logger.info(f"Registered MCP tool: {tool_name} (server: {tool_info.server_name})")
        except Exception as e:
            logger.error(f"Failed to register MCP tool {tool_name}: {e}")

    # Update tenant registry
    _tenant_tool_registry[tenant_id] = set(registered_names)

    return registered_names


def get_mcp_tool_names_for_tenant(tenant_id: str) -> List[str]:
    """
    Get list of MCP tool names available for a tenant.

    Use this in Qwen-Agent Assistant's function_list.

    Args:
        tenant_id: Tenant identifier

    Returns:
        List of tool names for this tenant
    """
    return list(_tenant_tool_registry.get(tenant_id, set()))


def get_all_mcp_tool_names() -> List[str]:
    """
    Get all registered MCP tool names.

    Returns:
        List of all registered tool names
    """
    return list(_mcp_tool_classes.keys())


def is_mcp_tool(tool_name: str) -> bool:
    """
    Check if a tool name is an MCP tool.

    Args:
        tool_name: Tool name to check

    Returns:
        True if it's an MCP tool
    """
    return tool_name in _mcp_tool_classes


def clear_mcp_tool_registry() -> None:
    """
    Clear all registered MCP tools.

    Useful for testing or when MCP servers change.
    """
    _mcp_tool_classes.clear()
    _tenant_tool_registry.clear()
    logger.info("Cleared MCP tool registry")


class MCPQwenToolFactory:
    """
    Factory for creating and managing MCP tools in Qwen-Agent format.

    Provides a high-level interface for MCP tool integration.
    """

    def __init__(self, client_manager: "MCPClientManager"):
        """
        Initialize the factory.

        Args:
            client_manager: MCP connection manager
        """
        self._manager = client_manager
        self._initialized_tenants: Set[str] = set()

    async def initialize_for_tenant(self, tenant_id: str) -> List[str]:
        """
        Initialize MCP tools for a tenant.

        Should be called when a tenant starts using the system.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of registered tool names
        """
        if tenant_id in self._initialized_tenants:
            return get_mcp_tool_names_for_tenant(tenant_id)

        tool_names = await register_mcp_tools_for_tenant(tenant_id, self._manager)
        self._initialized_tenants.add(tenant_id)
        return tool_names

    def get_tool_names(self, tenant_id: str) -> List[str]:
        """
        Get tool names for a tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of tool names
        """
        return get_mcp_tool_names_for_tenant(tenant_id)

    async def refresh_tools(self, tenant_id: str) -> List[str]:
        """
        Refresh MCP tools for a tenant.

        Re-discovers tools from MCP servers.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Updated list of tool names
        """
        self._initialized_tenants.discard(tenant_id)
        return await self.initialize_for_tenant(tenant_id)


# Global factory instance
_factory: Optional[MCPQwenToolFactory] = None


def get_mcp_tool_factory(client_manager: "MCPClientManager") -> MCPQwenToolFactory:
    """
    Get or create the global MCP tool factory.

    Args:
        client_manager: MCP connection manager

    Returns:
        MCPQwenToolFactory instance
    """
    global _factory
    if _factory is None:
        _factory = MCPQwenToolFactory(client_manager)
    return _factory
