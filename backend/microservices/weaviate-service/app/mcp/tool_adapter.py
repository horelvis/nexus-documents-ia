"""
MCP Tool Adapter - Bridge between MCP tools and BaseTool framework.

Converts MCP tool definitions to the internal BaseTool format used by
the agent framework, enabling seamless integration of MCP servers with
existing tools.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    MCP Server                                    │
    │  Tool: { name, description, inputSchema }                        │
    └────────────────────────┬────────────────────────────────────────┘
                             │ MCP Protocol
                             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                   MCPToolAdapter                                 │
    │  Converts inputSchema → ToolDefinition                          │
    │  Wraps call_tool() → BaseTool.execute()                         │
    └────────────────────────┬────────────────────────────────────────┘
                             │ Internal Format
                             ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                    BaseTool (Internal)                          │
    │  Used by agent framework for tool execution                      │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from pydantic import BaseModel, Field, create_model

from ..tools.base import (
    BaseTool,
    ToolCall,
    ToolDefinition,
    ToolExecutionContext,
    ToolParameter,
    ToolParameterType,
    ToolResult,
    ToolResultStatus,
)

if TYPE_CHECKING:
    from .client_manager import MCPClientManager, MCPToolInfo

logger = logging.getLogger(__name__)


def json_schema_type_to_tool_type(json_type: str) -> ToolParameterType:
    """Convert JSON Schema type to internal ToolParameterType."""
    mapping = {
        "string": ToolParameterType.STRING,
        "integer": ToolParameterType.INTEGER,
        "number": ToolParameterType.NUMBER,
        "boolean": ToolParameterType.BOOLEAN,
        "array": ToolParameterType.ARRAY,
        "object": ToolParameterType.OBJECT,
    }
    return mapping.get(json_type, ToolParameterType.STRING)


def input_schema_to_parameters(input_schema: Dict[str, Any]) -> List[ToolParameter]:
    """
    Convert MCP inputSchema (JSON Schema) to list of ToolParameter.

    Args:
        input_schema: JSON Schema dict from MCP tool

    Returns:
        List of ToolParameter objects
    """
    parameters = []

    if not input_schema or "properties" not in input_schema:
        return parameters

    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    for name, prop in properties.items():
        param_type = json_schema_type_to_tool_type(prop.get("type", "string"))

        # Handle array items
        items_type = None
        if param_type == ToolParameterType.ARRAY and "items" in prop:
            items_type = json_schema_type_to_tool_type(
                prop["items"].get("type", "string")
            )

        param = ToolParameter(
            name=name,
            type=param_type,
            description=prop.get("description", ""),
            required=name in required,
            default=prop.get("default"),
            enum=prop.get("enum"),
            items_type=items_type,
        )
        parameters.append(param)

    return parameters


def create_dynamic_params_model(
    tool_name: str,
    input_schema: Dict[str, Any]
) -> Type[BaseModel]:
    """
    Dynamically create a Pydantic model for tool parameters.

    Args:
        tool_name: Tool name (used for model naming)
        input_schema: JSON Schema dict

    Returns:
        Dynamically created Pydantic model class
    """
    if not input_schema or "properties" not in input_schema:
        # Empty params model
        return create_model(f"{tool_name}Params")

    properties = input_schema.get("properties", {})
    required = set(input_schema.get("required", []))

    # Build field definitions
    fields = {}
    for name, prop in properties.items():
        field_type = _json_type_to_python(prop.get("type", "string"))
        is_required = name in required

        if is_required:
            fields[name] = (field_type, Field(..., description=prop.get("description", "")))
        else:
            default = prop.get("default")
            fields[name] = (
                Optional[field_type],
                Field(default=default, description=prop.get("description", ""))
            )

    return create_model(f"{tool_name}Params", **fields)


def _json_type_to_python(json_type: str) -> type:
    """Map JSON Schema type to Python type."""
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    return mapping.get(json_type, str)


class MCPTool(BaseTool):
    """
    Wrapper that exposes an MCP tool as a BaseTool.

    This enables MCP tools to be used seamlessly within the agent
    framework alongside native tools.
    """

    def __init__(
        self,
        tool_info: "MCPToolInfo",
        client_manager: "MCPClientManager",
        category: Optional[str] = None
    ):
        """
        Initialize MCP tool wrapper.

        Args:
            tool_info: Tool metadata from MCP server
            client_manager: Manager for MCP connections
            category: Optional category override
        """
        self._tool_info = tool_info
        self._client_manager = client_manager
        self._category = category or "mcp"
        self._params_class = create_dynamic_params_model(
            tool_info.name,
            tool_info.input_schema
        )

    @property
    def name(self) -> str:
        """Tool name (with prefix if configured)."""
        return self._tool_info.name

    @property
    def category(self) -> Optional[str]:
        """Tool category."""
        return self._category

    @property
    def requires_auth(self) -> bool:
        """MCP tools handle their own auth."""
        return False

    @property
    def timeout_seconds(self) -> float:
        """Tool execution timeout."""
        return 60.0  # MCP calls may involve network latency

    def get_definition(self) -> ToolDefinition:
        """Get tool definition for LLM consumption."""
        return ToolDefinition(
            name=self.name,
            description=self._tool_info.description,
            parameters=input_schema_to_parameters(self._tool_info.input_schema),
            category=self._category,
            requires_auth=False,
        )

    def get_params_class(self) -> Type[BaseModel]:
        """Get dynamic params class."""
        return self._params_class

    async def execute(
        self,
        params: BaseModel,
        context: ToolExecutionContext
    ) -> ToolResult:
        """
        Execute the MCP tool.

        Args:
            params: Validated parameters
            context: Execution context

        Returns:
            ToolResult with execution outcome
        """
        start_time = datetime.utcnow()

        try:
            # Convert params to dict
            arguments = params.model_dump(exclude_none=True)

            # Execute via MCP
            result = await self._client_manager.execute_tool(
                tool_name=self._tool_info.name,
                arguments=arguments,
                server_name=self._tool_info.server_name,
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000

            return ToolResult(
                call_id=str(id(params)),
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data=result,
                execution_time_ms=execution_time,
                metadata={
                    "server": self._tool_info.server_name,
                    "original_tool": self._tool_info.original_name,
                },
            )

        except ValueError as e:
            # Access denied or tool not found
            return ToolResult(
                call_id=str(id(params)),
                tool_name=self.name,
                status=ToolResultStatus.UNAUTHORIZED,
                error=str(e),
                execution_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )

        except asyncio.TimeoutError:
            return ToolResult(
                call_id=str(id(params)),
                tool_name=self.name,
                status=ToolResultStatus.TIMEOUT,
                error=f"Tool execution timed out after {self.timeout_seconds}s",
                execution_time_ms=self.timeout_seconds * 1000,
            )

        except Exception as e:
            logger.error(f"MCP tool execution failed: {self.name} - {e}")
            return ToolResult(
                call_id=str(id(params)),
                tool_name=self.name,
                status=ToolResultStatus.ERROR,
                error=str(e),
                execution_time_ms=(datetime.utcnow() - start_time).total_seconds() * 1000,
            )


class MCPToolAdapter:
    """
    Adapter for converting MCP tools to BaseTool instances.

    Provides factory methods for creating tool wrappers and
    batch operations for tool discovery.
    """

    def __init__(self, client_manager: "MCPClientManager"):
        """
        Initialize the adapter.

        Args:
            client_manager: MCP connection manager
        """
        self._client_manager = client_manager
        self._tool_cache: Dict[str, MCPTool] = {}

    async def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        Get a tool wrapper by name.

        Args:
            tool_name: Tool name

        Returns:
            MCPTool instance or None if not found
        """
        if tool_name in self._tool_cache:
            return self._tool_cache[tool_name]

        # Find tool in connections
        conn = self._client_manager.get_connection_for_tool(tool_name)
        if not conn:
            return None

        for tool_info in conn.tools:
            if tool_info.name == tool_name:
                wrapper = MCPTool(tool_info, self._client_manager)
                self._tool_cache[tool_name] = wrapper
                return wrapper

        return None

    async def get_available_tools(
        self,
        category: Optional[str] = None
    ) -> List[MCPTool]:
        """
        Get all available MCP tools.

        Args:
            category: Optional category filter

        Returns:
            List of MCPTool instances
        """
        tool_infos = await self._client_manager.get_available_tools()
        tools = []

        for tool_info in tool_infos:
            if tool_info.name in self._tool_cache:
                tools.append(self._tool_cache[tool_info.name])
            else:
                wrapper = MCPTool(
                    tool_info,
                    self._client_manager,
                    category=category or _infer_category(tool_info.server_name)
                )
                self._tool_cache[tool_info.name] = wrapper
                tools.append(wrapper)

        return tools

    def clear_cache(self) -> None:
        """Clear the tool wrapper cache."""
        self._tool_cache.clear()


def _infer_category(server_name: str) -> str:
    """Infer tool category from server name."""
    category_map = {
        "storage": "storage",
        "database": "data",
        "rest_api": "api",
        "filesystem": "storage",
    }
    return category_map.get(server_name, "mcp")


def mcp_tool_to_base_tool(
    tool_info: "MCPToolInfo",
    client_manager: "MCPClientManager",
    category: Optional[str] = None
) -> BaseTool:
    """
    Convert an MCP tool to a BaseTool instance.

    Convenience function for creating a single tool wrapper.

    Args:
        tool_info: Tool metadata from MCP server
        client_manager: Manager for MCP connections
        category: Optional category override

    Returns:
        MCPTool instance (which is a BaseTool)
    """
    return MCPTool(tool_info, client_manager, category)
