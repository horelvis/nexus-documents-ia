"""
Tool Registry - Global and per-tenant tool management.

The ToolRegistry manages tool registration, discovery, and access control.
It supports both global tools (available to all tenants) and tenant-specific
tools (configured per organization).

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    ToolRegistry                              │
    │                                                              │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │              Global Tool Store                       │    │
    │  │  [rag_search, document_summarize, ...]              │    │
    │  └─────────────────────────────────────────────────────┘    │
    │                                                              │
    │  ┌─────────────────────────────────────────────────────┐    │
    │  │           Tenant-Specific Store                      │    │
    │  │  tenant_1: [search_emails, search_drive]            │    │
    │  │  tenant_2: [search_emails, search_slack]            │    │
    │  │  tenant_3: [search_salesforce]                      │    │
    │  └─────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────┘

Usage:
    registry = ToolRegistry()

    # Register global tools
    registry.register(RAGSearchTool())
    registry.register(DocumentSummarizeTool())

    # Register tenant-specific tools
    registry.register_for_tenant("tenant_123", SearchEmailsTool(config))

    # Get tools for a specific tenant
    tools = registry.get_tools_for_tenant("tenant_123")
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Set, Type

from .base import BaseTool, ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing tools across the system.

    Supports:
    - Global tool registration (available to all tenants)
    - Per-tenant tool registration (configured per organization)
    - Category-based filtering
    - Tool discovery for LLM requests
    """

    def __init__(self):
        """Initialize empty registry."""
        # Global tools available to all tenants
        self._global_tools: Dict[str, BaseTool] = {}

        # Per-tenant tool overrides/additions
        self._tenant_tools: Dict[str, Dict[str, BaseTool]] = defaultdict(dict)

        # Disabled tools per tenant
        self._disabled_tools: Dict[str, Set[str]] = defaultdict(set)

        # Tool factories for lazy instantiation
        self._factories: Dict[str, Callable[..., BaseTool]] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool globally (available to all tenants).

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

    def register_for_tenant(
        self,
        tenant_id: str,
        tool: BaseTool
    ) -> None:
        """
        Register a tool for a specific tenant.

        This can add new tools or override global tools for the tenant.

        Args:
            tenant_id: Tenant identifier
            tool: Tool instance to register
        """
        self._tenant_tools[tenant_id][tool.name] = tool
        logger.debug(f"Registered tool {tool.name} for tenant {tenant_id}")

    def disable_for_tenant(
        self,
        tenant_id: str,
        tool_name: str
    ) -> None:
        """
        Disable a global tool for a specific tenant.

        Args:
            tenant_id: Tenant identifier
            tool_name: Name of tool to disable
        """
        self._disabled_tools[tenant_id].add(tool_name)
        logger.debug(f"Disabled tool {tool_name} for tenant {tenant_id}")

    def enable_for_tenant(
        self,
        tenant_id: str,
        tool_name: str
    ) -> None:
        """
        Re-enable a previously disabled tool for a tenant.

        Args:
            tenant_id: Tenant identifier
            tool_name: Name of tool to enable
        """
        self._disabled_tools[tenant_id].discard(tool_name)
        logger.debug(f"Enabled tool {tool_name} for tenant {tenant_id}")

    def get_tool(
        self,
        name: str,
        tenant_id: Optional[str] = None
    ) -> Optional[BaseTool]:
        """
        Get a specific tool by name.

        Checks tenant-specific tools first, then falls back to global.
        Respects disabled tool settings.

        Args:
            name: Tool name
            tenant_id: Optional tenant for context

        Returns:
            Tool instance or None if not found/disabled
        """
        # Check if disabled for tenant
        if tenant_id and name in self._disabled_tools.get(tenant_id, set()):
            return None

        # Check tenant-specific tools first
        if tenant_id:
            tenant_tool = self._tenant_tools.get(tenant_id, {}).get(name)
            if tenant_tool:
                return tenant_tool

        # Check global tools
        if name in self._global_tools:
            return self._global_tools[name]

        # Try factory
        if name in self._factories:
            return self._factories[name]()

        return None

    def get_tools_for_tenant(
        self,
        tenant_id: str,
        category: Optional[str] = None,
        requires_auth: Optional[bool] = None
    ) -> List[BaseTool]:
        """
        Get all tools available for a specific tenant.

        Args:
            tenant_id: Tenant identifier
            category: Optional category filter
            requires_auth: Optional auth requirement filter

        Returns:
            List of available tools
        """
        disabled = self._disabled_tools.get(tenant_id, set())
        tools: Dict[str, BaseTool] = {}

        # Start with global tools
        for name, tool in self._global_tools.items():
            if name not in disabled:
                if category and tool.category != category:
                    continue
                if requires_auth is not None and tool.requires_auth != requires_auth:
                    continue
                tools[name] = tool

        # Add/override with tenant-specific tools
        for name, tool in self._tenant_tools.get(tenant_id, {}).items():
            if category and tool.category != category:
                continue
            if requires_auth is not None and tool.requires_auth != requires_auth:
                continue
            tools[name] = tool

        return list(tools.values())

    def get_definitions_for_tenant(
        self,
        tenant_id: str,
        category: Optional[str] = None
    ) -> List[ToolDefinition]:
        """
        Get tool definitions for LLM consumption.

        This is what gets passed to the adapter for formatting.

        Args:
            tenant_id: Tenant identifier
            category: Optional category filter

        Returns:
            List of ToolDefinition objects
        """
        tools = self.get_tools_for_tenant(tenant_id, category)
        return [tool.get_definition() for tool in tools]

    def get_all_global_tools(self) -> List[BaseTool]:
        """Get all globally registered tools."""
        return list(self._global_tools.values())

    def get_categories(self) -> Set[str]:
        """Get all unique tool categories."""
        categories = set()
        for tool in self._global_tools.values():
            if tool.category:
                categories.add(tool.category)
        for tenant_tools in self._tenant_tools.values():
            for tool in tenant_tools.values():
                if tool.category:
                    categories.add(tool.category)
        return categories

    def clear(self) -> None:
        """Clear all registrations (for testing)."""
        self._global_tools.clear()
        self._tenant_tools.clear()
        self._disabled_tools.clear()
        self._factories.clear()

    def __len__(self) -> int:
        """Total number of unique tools registered."""
        all_tools = set(self._global_tools.keys())
        for tenant_tools in self._tenant_tools.values():
            all_tools.update(tenant_tools.keys())
        return len(all_tools)

    def __contains__(self, name: str) -> bool:
        """Check if a tool is registered (globally or for any tenant)."""
        if name in self._global_tools:
            return True
        for tenant_tools in self._tenant_tools.values():
            if name in tenant_tools:
                return True
        return False


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
