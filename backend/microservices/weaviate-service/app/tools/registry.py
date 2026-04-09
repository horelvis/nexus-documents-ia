"""
Tool Registry - Global tool management.

The ToolRegistry manages tool registration, discovery, and category-based
filtering for LLM tool calling.

Usage:
    registry = ToolRegistry()

    # Register global tools
    registry.register(RAGSearchTool())
    registry.register(DocumentSummarizeTool())

    # Get tools (optionally filtered by category)
    tools = registry.get_tools()
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Set, Type

from .base import BaseTool, ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing tools across the system.

    Supports:
    - Global tool registration
    - Category-based filtering
    - Tool discovery for LLM requests
    """

    def __init__(self):
        """Initialize empty registry."""
        # Global tools available everywhere
        self._global_tools: Dict[str, BaseTool] = {}

        # Tool factories for lazy instantiation
        self._factories: Dict[str, Callable[..., BaseTool]] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool globally.

        Args:
            tool: Tool instance to register
        """
        if tool.name in self._global_tools:
            logger.warning(f"Overwriting existing global tool: {tool.name}")

        self._global_tools[tool.name] = tool
        logger.debug(f"Registered global tool: {tool.name}")

    def register_factory(
        self,
        name: str,
        factory: Callable[..., BaseTool]
    ) -> None:
        """
        Register a factory for lazy tool instantiation.

        Useful for tools that need per-request configuration
        (e.g., tools that need OAuth credentials).

        Args:
            name: Tool name
            factory: Callable that creates tool instances
        """
        self._factories[name] = factory
        logger.debug(f"Registered tool factory: {name}")

    def get_tool(
        self,
        name: str,
    ) -> Optional[BaseTool]:
        """
        Get a specific tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        # Check global tools
        if name in self._global_tools:
            return self._global_tools[name]

        # Try factory
        if name in self._factories:
            return self._factories[name]()

        return None

    def get_tools(
        self,
        category: Optional[str] = None,
        requires_auth: Optional[bool] = None,
    ) -> List[BaseTool]:
        """
        Get all registered tools, optionally filtered.

        Args:
            category: Optional category filter
            requires_auth: Optional auth requirement filter

        Returns:
            List of available tools
        """
        tools: List[BaseTool] = []
        for tool in self._global_tools.values():
            if category and tool.category != category:
                continue
            if requires_auth is not None and tool.requires_auth != requires_auth:
                continue
            tools.append(tool)
        return tools

    def get_definitions(
        self,
        category: Optional[str] = None,
    ) -> List[ToolDefinition]:
        """
        Get tool definitions for LLM consumption.

        This is what gets passed to the adapter for formatting.

        Args:
            category: Optional category filter

        Returns:
            List of ToolDefinition objects
        """
        return [tool.get_definition() for tool in self.get_tools(category=category)]

    def get_all_global_tools(self) -> List[BaseTool]:
        """Get all globally registered tools."""
        return list(self._global_tools.values())

    def get_categories(self) -> Set[str]:
        """Get all unique tool categories."""
        categories: Set[str] = set()
        for tool in self._global_tools.values():
            if tool.category:
                categories.add(tool.category)
        return categories

    def clear(self) -> None:
        """Clear all registrations (for testing)."""
        self._global_tools.clear()
        self._factories.clear()

    def __len__(self) -> int:
        """Total number of unique tools registered."""
        return len(self._global_tools)

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered globally."""
        return name in self._global_tools


# Global registry instance
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """
    Get the global tool registry singleton.

    Creates the registry on first call.

    Returns:
        The global ToolRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def register_tool(tool: BaseTool) -> BaseTool:
    """
    Decorator/function to register a tool globally.

    Can be used as a decorator on tool classes or called directly.

    Usage:
        @register_tool
        class MyTool(BaseTool):
            ...

        # Or:
        register_tool(MyTool())
    """
    get_registry().register(tool)
    return tool


def register_tool_class(cls: Type[BaseTool]) -> Type[BaseTool]:
    """
    Decorator to register a tool class (instantiates it).

    Usage:
        @register_tool_class
        class MyTool(BaseTool):
            ...
    """
    get_registry().register(cls())
    return cls
