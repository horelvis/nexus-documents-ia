"""
Tool Framework Integration for EmmaService.

This module bridges the Tool Framework with Emma's existing architecture.
It provides:
1. Initialization at application startup
2. Tool execution during conversation flow
3. Adapter selection based on LLM provider
4. Context management for multi-turn conversations

Usage in EmmaService:
    from app.services.tool_integration import ToolIntegration

    class EmmaService:
        def __init__(self):
            self.tool_integration = ToolIntegration()

        async def initialize(self):
            await self.tool_integration.initialize()

        async def execute_query(self, query):
            # Use tools when needed
            if needs_tool_execution:
                results = await self.tool_integration.execute_tools(
                    tool_calls=parsed_tool_calls,
                    user_id=query.user_id,
                    user_roles=query.user_roles,
                )
"""

import logging
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.tools import (
    ToolRegistry,
    ToolExecutor,
    ToolExecutionContext,
    ToolCall,
    ToolResult,
    ToolDefinition,
    get_registry,
    get_tool_adapter,
    initialize_tools,
    ExecutorConfig,
)
from app.tools.adapters import ToolCallAdapter

logger = logging.getLogger(__name__)


class ToolIntegration:
    """
    Integration layer between EmmaService and the Tool Framework.

    Handles:
    - Tool registry initialization
    - LLM provider adapter selection
    - Tool execution with proper context
    - Result formatting for LLM consumption
    """

    def __init__(self):
        """Initialize the tool integration layer."""
        self._registry: Optional[ToolRegistry] = None
        self._executor: Optional[ToolExecutor] = None
        self._adapter: Optional[ToolCallAdapter] = None
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize tools and adapter.

        Call this during EmmaService initialization.
        """
        if self._initialized:
            return

        try:
            # Initialize registry with all built-in tools
            self._registry = initialize_tools()
            logger.info(f"✅ Initialized tool registry with {len(self._registry)} tools")

            # Create executor with config
            config = ExecutorConfig(
                default_timeout=30.0,
                max_timeout=120.0,
                default_retries=2,
                parallel_execution=True,
                max_concurrency=5
            )
            self._executor = ToolExecutor(self._registry, config)

            # Select adapter based on configured LLM provider
            provider = getattr(settings, 'llm_provider', 'sglang')
            self._adapter = get_tool_adapter(provider)
            logger.info(f"✅ Using {self._adapter.provider_name} adapter for tool calls")

            self._initialized = True
            logger.info("✅ Tool integration layer initialized")

        except Exception as e:
            logger.error(f"❌ Failed to initialize tool integration: {e}")
            raise

    @property
    def is_initialized(self) -> bool:
        """Check if tool integration is initialized."""
        return self._initialized

    @property
    def registry(self) -> Optional[ToolRegistry]:
        """Get the tool registry."""
        return self._registry

    @property
    def adapter(self) -> Optional[ToolCallAdapter]:
        """Get the current adapter."""
        return self._adapter

    def get_tools(
        self,
        category: Optional[str] = None
    ) -> List[ToolDefinition]:
        """
        Get available tool definitions.

        Args:
            category: Optional category filter

        Returns:
            List of ToolDefinition objects
        """
        if not self._registry:
            return []

        return self._registry.get_definitions(category=category)

    def format_tools_for_request(
        self,
        category: Optional[str] = None
    ) -> Any:
        """
        Get tools formatted for the current LLM provider.

        Args:
            category: Optional category filter

        Returns:
            Provider-formatted tools for LLM request
        """
        if not self._adapter or not self._registry:
            return []

        definitions = self._registry.get_definitions(category=category)
        return self._adapter.format_tools_for_request(definitions)

    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Parse tool calls from LLM response.

        Args:
            response: Raw LLM response

        Returns:
            List of ToolCall objects
        """
        if not self._adapter:
            return []

        return self._adapter.parse_tool_calls(response)

    def has_tool_calls(self, response: Any) -> bool:
        """
        Check if response contains tool calls.

        Args:
            response: Raw LLM response

        Returns:
            True if tool calls are present
        """
        if not self._adapter:
            return False

        return self._adapter.has_tool_calls(response)

    async def execute_tool(
        self,
        tool_call: ToolCall,
        user_id: Optional[str] = None,
        user_roles: Optional[List[str]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None
    ) -> ToolResult:
        """
        Execute a single tool call.

        Args:
            tool_call: The tool call to execute
            user_id: Optional user identifier (from authenticated context)
            user_roles: Optional list of user roles for ACL scoping
            credentials: Optional OAuth credentials
            conversation_id: Optional conversation ID

        Returns:
            ToolResult from execution

        Note:
            user_id and user_roles are automatically injected into tool_call.arguments
            to ensure proper ACL scoping regardless of what the LLM passes.
        """
        if not self._executor:
            raise RuntimeError("Tool integration not initialized")

        # === Automatic injection of user_id and user_roles ===
        if tool_call.arguments is None:
            tool_call.arguments = {}

        # Inject user_id if available
        if user_id and 'user_id' not in tool_call.arguments:
            tool_call.arguments['user_id'] = user_id

        # Inject user_roles for ACL scoping
        if user_roles is not None and 'user_roles' not in tool_call.arguments:
            tool_call.arguments['user_roles'] = list(user_roles)
        # === End automatic injection ===

        context = ToolExecutionContext(
            user_id=user_id,
            user_roles=list(user_roles) if user_roles is not None else None,
            credentials=credentials,
            conversation_id=conversation_id,
            metadata={"call_id": tool_call.id}
        )

        return await self._executor.execute(tool_call, context)

    async def execute_tools(
        self,
        tool_calls: List[ToolCall],
        user_id: Optional[str] = None,
        user_roles: Optional[List[str]] = None,
        credentials: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None
    ) -> List[ToolResult]:
        """
        Execute multiple tool calls.

        Executes in parallel if the adapter supports it.

        Args:
            tool_calls: List of tool calls to execute
            user_id: Optional user identifier
            user_roles: Optional list of user roles for ACL scoping
            credentials: Optional OAuth credentials
            conversation_id: Optional conversation ID

        Returns:
            List of ToolResult in same order as calls
        """
        if not self._executor:
            raise RuntimeError("Tool integration not initialized")

        # === Automatic injection of user_id and user_roles for each tool_call ===
        for tool_call in tool_calls:
            if tool_call.arguments is None:
                tool_call.arguments = {}

            # Inject user_id if available
            if user_id and 'user_id' not in tool_call.arguments:
                tool_call.arguments['user_id'] = user_id

            # Inject user_roles for ACL scoping
            if user_roles is not None and 'user_roles' not in tool_call.arguments:
                tool_call.arguments['user_roles'] = list(user_roles)
        # === End automatic injection ===

        context = ToolExecutionContext(
            user_id=user_id,
            user_roles=list(user_roles) if user_roles is not None else None,
            credentials=credentials,
            conversation_id=conversation_id
        )

        return await self._executor.execute_many(tool_calls, context)

    def format_results_for_llm(
        self,
        results: List[ToolResult]
    ) -> Any:
        """
        Format tool results for the next LLM message.

        Args:
            results: List of ToolResult from execution

        Returns:
            Provider-formatted results for LLM
        """
        if not self._adapter:
            return []

        return self._adapter.format_tool_results(results)

    def get_text_content(self, response: Any) -> Optional[str]:
        """
        Get text content from LLM response (excluding tool calls).

        Args:
            response: Raw LLM response

        Returns:
            Text content if present
        """
        if not self._adapter:
            return None

        return self._adapter.get_text_content(response)

    def get_tool_info(self) -> List[Dict[str, Any]]:
        """
        Get tool information for UI display.

        Returns:
            List of tool info dicts with name, description, category
        """
        if not self._registry:
            return []

        tools = self._registry.get_all_global_tools()
        return [
            {
                "name": tool.name,
                "description": tool.get_definition().description,
                "category": tool.category,
                "requires_auth": tool.requires_auth
            }
            for tool in tools
        ]


# Singleton instance for application-wide use
_tool_integration: Optional[ToolIntegration] = None


def get_tool_integration() -> ToolIntegration:
    """
    Get the global ToolIntegration singleton.

    Returns:
        The application-wide ToolIntegration instance
    """
    global _tool_integration
    if _tool_integration is None:
        _tool_integration = ToolIntegration()
    return _tool_integration


async def initialize_tool_integration() -> ToolIntegration:
    """
    Initialize and return the global tool integration.

    Call this at application startup.

    Returns:
        Initialized ToolIntegration instance
    """
    integration = get_tool_integration()
    await integration.initialize()
    return integration
