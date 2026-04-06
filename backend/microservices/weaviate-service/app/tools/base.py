"""
Tool Framework Base Classes - Model Agnostic Abstractions.

This module provides the foundational abstractions for the Tool Framework,
designed to be completely independent of any specific LLM provider's tool
calling format (Hermes, OpenAI, Anthropic, etc.).

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    LLM Provider                              │
    │  (SGLang/Qwen3, OpenAI GPT-4, Anthropic Claude, etc.)        │
    └────────────────────────┬────────────────────────────────────┘
                             │ Provider-specific format
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                  ToolCallAdapter                             │
    │  Converts provider format ←→ internal ToolCall format        │
    └────────────────────────┬────────────────────────────────────┘
                             │ Internal format (ToolCall)
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                    ToolExecutor                              │
    │  Executes tools with timeout, retry, and error handling      │
    └────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
    ┌─────────────────────────────────────────────────────────────┐
    │                 BaseTool Implementations                     │
    │  SearchEmailsTool, SearchDriveTool, RAGSearchTool, etc.     │
    └─────────────────────────────────────────────────────────────┘

This design ensures that:
1. Switching LLM providers requires only a new adapter
2. Tools remain unchanged regardless of provider
3. Business logic is decoupled from LLM specifics
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

# Type variable for tool parameter schemas
TParams = TypeVar("TParams", bound=BaseModel)


class ToolParameterType(str, Enum):
    """Supported parameter types for tool definitions."""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolParameter(BaseModel):
    """
    Definition of a single tool parameter.

    This is the internal, model-agnostic representation that gets
    converted to provider-specific formats by adapters.
    """
    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(..., description="Parameter name")
    type: ToolParameterType = Field(..., description="Parameter type")
    description: str = Field(..., description="Parameter description")
    required: bool = Field(default=True, description="Whether parameter is required")
    default: Optional[Any] = Field(default=None, description="Default value if not provided")
    enum: Optional[List[Any]] = Field(default=None, description="Allowed values (for enums)")
    items_type: Optional[ToolParameterType] = Field(
        default=None,
        description="Type of items in array (when type=array)"
    )


class ToolDefinition(BaseModel):
    """
    Internal model-agnostic tool definition.

    This represents a tool's metadata and capabilities independent
    of any specific LLM provider's format.

    Example:
        tool_def = ToolDefinition(
            name="search_emails",
            description="Search emails in the user's inbox",
            parameters=[
                ToolParameter(
                    name="query",
                    type=ToolParameterType.STRING,
                    description="Search query",
                    required=True
                ),
                ToolParameter(
                    name="limit",
                    type=ToolParameterType.INTEGER,
                    description="Maximum results",
                    required=False,
                    default=10
                )
            ]
        )
    """
    model_config = ConfigDict(use_enum_values=True)

    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="What the tool does (for LLM)")
    parameters: List[ToolParameter] = Field(
        default_factory=list,
        description="Tool parameters"
    )
    # Metadata for registry/filtering
    category: Optional[str] = Field(
        default=None,
        description="Tool category (e.g., 'email', 'drive', 'rag')"
    )
    requires_auth: bool = Field(
        default=False,
        description="Whether tool requires OAuth/credentials"
    )
    tenant_specific: bool = Field(
        default=True,
        description="Whether tool operates on tenant data"
    )

    def to_json_schema(self) -> Dict[str, Any]:
        """
        Convert to JSON Schema format (used by most providers).

        Returns:
            Dict representing the tool as JSON Schema
        """
        properties = {}
        required = []

        for param in self.parameters:
            prop: Dict[str, Any] = {
                "type": param.type,
                "description": param.description
            }

            if param.enum:
                prop["enum"] = param.enum

            if param.type == ToolParameterType.ARRAY and param.items_type:
                prop["items"] = {"type": param.items_type}

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }


class ToolCall(BaseModel):
    """
    Internal model-agnostic tool call representation.

    This is what we receive after the adapter converts provider-specific
    formats. The tool executor uses this to invoke the actual tool.

    Attributes:
        id: Unique identifier for this call (for tracking/logging)
        name: Name of the tool to invoke
        arguments: Parsed arguments as dictionary
        raw_arguments: Original string arguments (for debugging)
        metadata: Additional context (tenant_id, user_id, etc.)
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(..., description="Tool name to invoke")
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parsed tool arguments"
    )
    raw_arguments: Optional[str] = Field(
        default=None,
        description="Original string arguments (before parsing)"
    )
    # Execution context
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for execution"
    )

    def get_argument(self, name: str, default: Any = None) -> Any:
        """Safely get an argument with optional default."""
        return self.arguments.get(name, default)


class ToolResultStatus(str, Enum):
    """Possible outcomes of tool execution."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    NOT_FOUND = "not_found"
    UNAUTHORIZED = "unauthorized"
    RATE_LIMITED = "rate_limited"


class ToolResult(BaseModel):
    """
    Standardized result from tool execution.

    This provides a consistent format for all tool results,
    regardless of what the underlying tool returns.

    Attributes:
        call_id: Reference to the ToolCall that produced this result
        tool_name: Name of the tool that was executed
        status: Execution status
        data: The actual result data (type depends on tool)
        error: Error message if status != SUCCESS
        execution_time_ms: How long the tool took to execute
        metadata: Additional result metadata
    """
    call_id: str = Field(..., description="ID of the originating ToolCall")
    tool_name: str = Field(..., description="Name of executed tool")
    status: ToolResultStatus = Field(..., description="Execution status")
    data: Optional[Any] = Field(default=None, description="Result data")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    execution_time_ms: Optional[float] = Field(
        default=None,
        description="Execution time in milliseconds"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional result metadata"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the result was produced"
    )

    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.status == ToolResultStatus.SUCCESS

    def to_llm_content(self) -> str:
        """
        Format result for LLM consumption.

        This produces a clean string that the LLM can use in its response.
        """
        if self.is_success:
            if isinstance(self.data, str):
                return self.data
            elif isinstance(self.data, (list, dict)):
                import json
                return json.dumps(self.data, ensure_ascii=False, indent=2)
            else:
                return str(self.data) if self.data is not None else "Success (no data)"
        else:
            return f"Error ({self.status.value}): {self.error or 'Unknown error'}"


class BaseTool(ABC, Generic[TParams]):
    """
    Abstract base class for all tools.

    To create a new tool:
    1. Define a Pydantic model for parameters
    2. Subclass BaseTool with the parameter type
    3. Implement get_definition() and execute()

    Example:
        class SearchEmailsParams(BaseModel):
            query: str
            limit: int = 10

        class SearchEmailsTool(BaseTool[SearchEmailsParams]):
            @property
            def name(self) -> str:
                return "search_emails"

            def get_definition(self) -> ToolDefinition:
                return ToolDefinition(
                    name=self.name,
                    description="Search emails",
                    parameters=[...]
                )

            async def execute(
                self,
                params: SearchEmailsParams,
                context: ToolExecutionContext
            ) -> ToolResult:
                # Implementation
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this tool."""
        pass

    @property
    def category(self) -> Optional[str]:
        """Tool category for filtering/organization."""
        return None

    @property
    def requires_auth(self) -> bool:
        """Whether this tool requires OAuth/credentials."""
        return False

    @property
    def timeout_seconds(self) -> float:
        """Default timeout for this tool's execution."""
        return 30.0

    @property
    def max_retries(self) -> int:
        """Maximum retry attempts on transient failures."""
        return 2

    @abstractmethod
    def get_definition(self) -> ToolDefinition:
        """
        Return the tool's definition for LLM consumption.

        This is used by adapters to format the tool for the specific
        LLM provider being used.
        """
        pass

    @abstractmethod
    def get_params_class(self) -> Type[TParams]:
        """
        Return the Pydantic class for parameter validation.

        Used by the executor to validate arguments before execution.
        """
        pass

    @abstractmethod
    async def execute(
        self,
        params: TParams,
        context: "ToolExecutionContext"
    ) -> ToolResult:
        """
        Execute the tool with validated parameters.

        Args:
            params: Validated parameters as Pydantic model
            context: Execution context (tenant, user, credentials, etc.)

        Returns:
            ToolResult with execution outcome
        """
        pass

    def validate_params(self, arguments: Dict[str, Any]) -> TParams:
        """
        Validate and parse arguments into the params model.

        Args:
            arguments: Raw arguments dictionary

        Returns:
            Validated params model

        Raises:
            ValidationError: If arguments are invalid
        """
        params_class = self.get_params_class()
        return params_class(**arguments)


class ToolExecutionContext(BaseModel):
    """
    Context passed to tools during execution.

    Contains all the information a tool might need to execute,
    including tenant isolation, user identity, and credentials.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Tenant isolation
    tenant_id: str = Field(..., description="Current tenant ID")
    user_id: Optional[str] = Field(default=None, description="Current user ID")

    # Credentials (for OAuth tools)
    credentials: Optional[Dict[str, Any]] = Field(
        default=None,
        description="OAuth credentials or API keys"
    )

    # Session context
    conversation_id: Optional[str] = Field(
        default=None,
        description="Current conversation/session ID"
    )

    # Feature flags
    features: Dict[str, bool] = Field(
        default_factory=dict,
        description="Enabled features for this context"
    )

    # Additional context
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context data"
    )

    def get_credential(self, key: str) -> Optional[Any]:
        """Safely retrieve a credential value."""
        if self.credentials:
            return self.credentials.get(key)
        return None


# Type alias for tool function signature
ToolFunction = Callable[[Dict[str, Any], ToolExecutionContext], ToolResult]
