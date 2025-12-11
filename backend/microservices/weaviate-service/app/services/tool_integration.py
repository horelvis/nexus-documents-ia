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
                    tenant_id=query.tenant_id,
                    user_id=query.user_id
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
            provider = getattr(settings, 'llm_provider', 'vllm')
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

    def get_tools_for_tenant(
        self,
        tenant_id: str,
        category: Optional[str] = None
    ) -> List[ToolDefinition]:
        """
        Get available tools for a tenant.

        Args:
            tenant_id: Tenant identifier
            category: Optional category filter

        Returns:
            List of ToolDefinition objects
        """
        if not self._registry:
            return []

        return self._registry.get_definitions_for_tenant(tenant_id, category)

    def format_tools_for_request(
        self,
        tenant_id: str,
        category: Optional[str] = None
    ) -> Any:
        """
        Get tools formatted for the current LLM provider.

        Args:
            tenant_id: Tenant identifier
            category: Optional category filter

        Returns:
            Provider-formatted tools for LLM request
        """
        if not self._adapter or not self._registry:
            return []

        definitions = self._registry.get_definitions_for_tenant(tenant_id, category)
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
        tenant_id: str,
        user_id: Optional[str] = None,
        credentials: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None
    ) -> ToolResult:
        """
        Execute a single tool call.

        Args:
            tool_call: The tool call to execute
            tenant_id: Tenant identifier (from authenticated context)
            user_id: Optional user identifier
            credentials: Optional OAuth credentials
            conversation_id: Optional conversation ID

        Returns:
            ToolResult from execution

        Note:
            tenant_id and user_id are automatically injected into tool_call.arguments
            to ensure proper data isolation regardless of what the LLM passes.
        """
        if not self._executor:
            raise RuntimeError("Tool integration not initialized")

        # === Automatic injection of tenant_id and user_id ===
        # This ensures proper tenant isolation even if the LLM doesn't pass these correctly
        if tool_call.arguments is None:
            tool_call.arguments = {}

        # Security: Log if LLM tried to pass a different tenant_id
        if 'tenant_id' in tool_call.arguments:
            llm_tenant = tool_call.arguments['tenant_id']
            if llm_tenant != tenant_id:
                logger.warning(
                    f"🔒 tenant_id override in {tool_call.name}: "
                    f"LLM passed '{llm_tenant}', using authenticated '{tenant_id}'"
                )

        # Always override with the authenticated tenant_id
        tool_call.arguments['tenant_id'] = tenant_id

        # Inject user_id if available (for user-level isolation within tenant)
        if user_id and 'user_id' not in tool_call.arguments:
            tool_call.arguments['user_id'] = user_id
        # === End automatic injection ===

        context = ToolExecutionContext(
            tenant_id=tenant_id,
            user_id=user_id,
            credentials=credentials,
            conversation_id=conversation_id,
            metadata={"call_id": tool_call.id}
        )

        return await self._executor.execute(tool_call, context)

    async def execute_tools(
        self,
        tool_calls: List[ToolCall],
        tenant_id: str,
        user_id: Optional[str] = None,
        credentials: Optional[Dict[str, Any]] = None,
        conversation_id: Optional[str] = None
    ) -> List[ToolResult]:
        """
        Execute multiple tool calls.

        Executes in parallel if the adapter supports it.

        Args:
            tool_calls: List of tool calls to execute
            tenant_id: Tenant identifier
            user_id: Optional user identifier
            credentials: Optional OAuth credentials
            conversation_id: Optional conversation ID

        Returns:
            List of ToolResult in same order as calls
        """
        if not self._executor:
            raise RuntimeError("Tool integration not initialized")

        # === Automatic injection of tenant_id and user_id for each tool_call ===
        for tool_call in tool_calls:
            if tool_call.arguments is None:
                tool_call.arguments = {}

            # Security: Log if LLM tried to pass a different tenant_id
            if 'tenant_id' in tool_call.arguments:
                llm_tenant = tool_call.arguments['tenant_id']
                if llm_tenant != tenant_id:
                    logger.warning(
                        f"🔒 tenant_id override in {tool_call.name}: "
                        f"LLM passed '{llm_tenant}', using authenticated '{tenant_id}'"
                    )

            # Always override with the authenticated tenant_id
            tool_call.arguments['tenant_id'] = tenant_id

            # Inject user_id if available
            if user_id and 'user_id' not in tool_call.arguments:
                tool_call.arguments['user_id'] = user_id
        # === End automatic injection ===

        context = ToolExecutionContext(
            tenant_id=tenant_id,
            user_id=user_id,
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
