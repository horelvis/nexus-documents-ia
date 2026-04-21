"""
Emma Tool Framework - Model-Agnostic Tool Calling System.

This package provides a complete tool framework for Emma that is independent
of any specific LLM provider. It allows seamless switching between SGLang,
OpenAI, Anthropic, or any other provider without changing tool implementations.

Quick Start:
    from app.tools import (
        get_registry,
        ToolExecutor,
        ToolExecutionContext,
        get_tool_adapter
    )

    # Setup
    registry = get_registry()
    executor = ToolExecutor(registry)
    adapter = get_tool_adapter("sglang")

    # Get tools (single-tenant: no per-tenant overrides)
    tools = registry.get_tools()
    provider_tools = adapter.format_tools_for_request(
        [t.get_definition() for t in tools]
    )

    # After LLM response
    tool_calls = adapter.parse_tool_calls(llm_response)

    # Execute tools
    context = ToolExecutionContext(user_id=user_id, user_roles=user_roles)
    results = await executor.execute_many(tool_calls, context)

    # Format results for next LLM message
    result_messages = adapter.format_tool_results(results)

Package Structure:
    app/tools/
    ├── __init__.py          # This file - exports public API
    ├── base.py              # Core abstractions (ToolDefinition, BaseTool, etc.)
    ├── executor.py          # ToolExecutor with async/retry logic
    ├── registry.py          # Global tool management (single-tenant deployment)
    └── adapters/            # LLM-specific format adapters
        ├── __init__.py
        ├── base.py          # ToolCallAdapter ABC
        ├── hermes.py        # SGLang/Qwen3 adapter
        └── openai.py        # GPT-4/GPT-4o adapter

Creating New Tools:
    from app.tools import BaseTool, ToolDefinition, ToolParameter, ToolResult
    from pydantic import BaseModel

    class MyToolParams(BaseModel):
        query: str
        limit: int = 10

    class MyTool(BaseTool[MyToolParams]):
        @property
        def name(self) -> str:
            return "my_tool"

        @property
        def category(self) -> str:
            return "custom"

        def get_definition(self) -> ToolDefinition:
            return ToolDefinition(
                name=self.name,
                description="Description for LLM",
                parameters=[
                    ToolParameter(
                        name="query",
                        type=ToolParameterType.STRING,
                        description="Search query",
                        required=True
                    )
                ]
            )

        def get_params_class(self):
            return MyToolParams

        async def execute(self, params, context):
            # Implementation
            return ToolResult(
                call_id=context.metadata.get("call_id", ""),
                tool_name=self.name,
                status=ToolResultStatus.SUCCESS,
                data={"result": "..."}
            )
"""

# Base types
from .base import (
    # Enums
    ToolParameterType,
    ToolResultStatus,
    # Core models
    ToolParameter,
    ToolDefinition,
    ToolCall,
    ToolResult,
    ToolExecutionContext,
    # Base class
    BaseTool,
)

# Executor
from .executor import (
    ToolExecutor,
    BatchToolExecutor,
    ExecutorConfig,
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
    ToolTimeoutError,
)

# Registry
from .registry import (
    ToolRegistry,
    get_registry,
    register_tool,
    register_tool_class,
)

# Adapters
from .adapters import (
    ToolCallAdapter,
    AdapterRegistry,
    HermesAdapter,
    OpenAIAdapter,
    get_tool_adapter,
    get_adapter_for_model,
)

# Tool implementations
from .channel_tools import (
    SearchEmailsTool,
    SearchDriveTool,
    SearchChannelTool,
    register_channel_tools,
)

from .rag_tools import (
    SearchDocumentsTool,
    HybridSearchTool,
    RAGQueryTool,
    register_rag_tools,
)


def initialize_tools(registry: ToolRegistry = None) -> ToolRegistry:
    """
    Initialize all built-in tools.

    Call this at application startup to register all available tools.

    Args:
        registry: Optional existing registry. Creates new one if not provided.

    Returns:
        The initialized ToolRegistry
    """
    if registry is None:
        registry = get_registry()

    # Register all tool modules
    register_rag_tools(registry)
    register_channel_tools(registry)

    return registry


__all__ = [
    # Enums
    "ToolParameterType",
    "ToolResultStatus",
    # Core models
    "ToolParameter",
    "ToolDefinition",
    "ToolCall",
    "ToolResult",
    "ToolExecutionContext",
    # Base class
    "BaseTool",
    # Executor
    "ToolExecutor",
    "BatchToolExecutor",
    "ExecutorConfig",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolValidationError",
    "ToolTimeoutError",
    # Registry
    "ToolRegistry",
    "get_registry",
    "register_tool",
    "register_tool_class",
    # Adapters
    "ToolCallAdapter",
    "AdapterRegistry",
    "HermesAdapter",
    "OpenAIAdapter",
    "get_tool_adapter",
    "get_adapter_for_model",
    # Channel tools
    "SearchEmailsTool",
    "SearchDriveTool",
    "SearchChannelTool",
    "register_channel_tools",
    # RAG tools
    "SearchDocumentsTool",
    "HybridSearchTool",
    "RAGQueryTool",
    "register_rag_tools",
    # Initialization
    "initialize_tools",
]
