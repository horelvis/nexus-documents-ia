"""
Emma ReAct Agent — Tool Registry

Inspired by OpenManus ToolCollection: a dynamic registry that provides
context-aware tool sets based on tenant configuration, sector, and features.

The registry is a singleton that lazily initializes all tools on first access.
Tools are filtered per-request based on:
- Sector config (which agents/capabilities are enabled)
- Tenant features (web search, connectors, etc.)
- Available services (knowledge tree, weaviate)

Usage:
    registry = get_tool_registry()
    tools = registry.get_tools_for_context(tenant_id, sector, features)
    result = await registry.execute("smart_search", args, context)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from app.core.config import settings
from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies — tools are registered on first access
_tool_registry: Optional["ToolRegistry"] = None
_tool_registry_lock = asyncio.Lock()


class ToolRegistry:
    """Dynamic tool registry with context-aware filtering.

    Tools are registered once at startup and filtered per-request
    based on tenant config, sector, and enabled features.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, EmmaTool] = {}
        self._initialized = False

    def register(self, tool: EmmaTool) -> None:
        """Register a tool by its name."""
        if tool.name in self._tools:
            logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        self._tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name}")

    def _ensure_initialized(self) -> None:
        """Lazy initialization of all tools on first access."""
        if self._initialized:
            return

        from .terminate import TerminateTool
        from .smart_search import SmartSearchTool
        from .search import GetDocumentContentTool
        from .graph import StructuralQueryTool
        from .specialists import AnalyzeDomainTool
        from .web import WebSearchTool
        from .discovery import ListSourcesTool
        from .connectors import QueryConnectorTool
        from .cendoj import CendojSearchTool

        tools: List[EmmaTool] = [
            SmartSearchTool(),         # Replaces SearchDocuments + SearchLegislation
            GetDocumentContentTool(),
            StructuralQueryTool(),
            AnalyzeDomainTool(),
            WebSearchTool(),
            CendojSearchTool(),
            ListSourcesTool(),
            QueryConnectorTool(),
            TerminateTool(),  # Always last — the agent's "I'm done" signal
        ]

        for tool in tools:
            self.register(tool)

        self._initialized = True
        logger.info(f"Tool registry initialized with {len(self._tools)} tools")

    def get_tool(self, name: str) -> Optional[EmmaTool]:
        """Get a tool by name."""
        self._ensure_initialized()
        return self._tools.get(name)

    def get_all_tools(self) -> List[EmmaTool]:
        """Get all registered tools."""
        self._ensure_initialized()
        return list(self._tools.values())

    def get_tools_for_context(
        self,
        tenant_id: str,
        sector: Optional[str] = None,
        features: Optional[Dict[str, bool]] = None,
    ) -> List[EmmaTool]:
        """Get tools available for the current request context.

        Filtering rules:
        - terminate: always included
        - smart_search: always included (unified documents + legislation)
        - get_document_content: always included
        - structural_query: always included (enables count/list/filter queries)
        - analyze_domain: included if sector has specialist agents
        - web_search: included if feature is enabled
        - list_sources: always included (discovery)
        - query_connector: included if feature is enabled
        """
        self._ensure_initialized()
        features = features or {}

        # Determine which tools are available
        available: List[EmmaTool] = []
        excluded: Set[str] = set()

        # Check sector agent availability
        has_specialists = True  # Default: all sectors have at least general analysis

        if sector:
            from ..sectors.registry import SECTOR_CONFIGS
            sector_config = SECTOR_CONFIGS.get(sector)
            if sector_config:
                sector_agents = set(sector_config.agents)
                has_specialists = len(sector_agents) > 0

        for tool in self._tools.values():
            name = tool.name

            # Always include these
            if name in ("terminate", "smart_search", "get_document_content",
                        "structural_query", "list_sources"):
                available.append(tool)
                continue

            # Conditional tools
            if name == "analyze_domain" and has_specialists:
                available.append(tool)
            elif name == "web_search" and features.get("web_search_enabled", False):
                available.append(tool)
            elif name == "search_jurisprudence" and features.get("cendoj_enabled", False):
                available.append(tool)
            elif name == "query_connector" and features.get("connectors_enabled", False):
                available.append(tool)
            elif name not in ("analyze_domain",
                              "web_search", "search_jurisprudence", "query_connector"):
                # Unknown tool — include by default
                available.append(tool)
            else:
                excluded.add(name)

        if excluded:
            logger.debug(f"Tools excluded for context: {excluded}")

        return available

    def get_openai_params(
        self,
        tenant_id: str,
        sector: Optional[str] = None,
        features: Optional[Dict[str, bool]] = None,
    ) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool schemas for the current context."""
        tools = self.get_tools_for_context(tenant_id, sector, features)
        return [t.to_openai_param() for t in tools]

    def get_tools_description(
        self,
        tenant_id: str,
        sector: Optional[str] = None,
        features: Optional[Dict[str, bool]] = None,
        max_desc_chars: int = 0,
    ) -> str:
        """Generate human-readable tool descriptions for the system prompt.

        Args:
            max_desc_chars: Truncate each description to this length (0 = unlimited).
        """
        tools = self.get_tools_for_context(tenant_id, sector, features)
        lines = []
        for tool in tools:
            desc = tool.description
            if max_desc_chars and len(desc) > max_desc_chars:
                desc = desc[:max_desc_chars - 3] + "..."
            lines.append(f"- **{tool.name}**: {desc}")
        return "\n".join(lines)

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ToolResult:
        """Execute a tool by name with safe error handling.

        Args:
            name: Tool name from the LLM's tool_call
            arguments: Parsed arguments dict
            context: Current ReActState as dict

        Returns:
            ToolResult (always — errors are wrapped, never raised)
        """
        self._ensure_initialized()

        tool = self._tools.get(name)
        if not tool:
            available = ", ".join(self._tools.keys())
            return ToolResult.from_error(
                f"Unknown tool: '{name}'",
                suggestion=f"Available tools: {available}",
            )

        try:
            return await asyncio.wait_for(
                tool.safe_execute(arguments, context),
                timeout=settings.react_tool_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Tool '{name}' timed out after {settings.react_tool_timeout_seconds}s")
            return ToolResult.from_error(
                f"Tool '{name}' timed out after {settings.react_tool_timeout_seconds}s",
                suggestion="Try a simpler query or a different tool.",
            )

    def __repr__(self) -> str:
        return f"<ToolRegistry: {len(self._tools)} tools>"


def get_tool_registry() -> ToolRegistry:
    """Get the singleton ToolRegistry instance (sync — init is cheap, no I/O)."""
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ToolRegistry()
    return _tool_registry


async def get_tool_registry_async() -> ToolRegistry:
    """Get the singleton ToolRegistry instance (async — race-safe)."""
    global _tool_registry
    if _tool_registry is None:
        async with _tool_registry_lock:
            if _tool_registry is None:
                _tool_registry = ToolRegistry()
    return _tool_registry
