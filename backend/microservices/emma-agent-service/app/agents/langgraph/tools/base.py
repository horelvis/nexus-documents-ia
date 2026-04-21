"""
Emma ReAct Agent — Tool Base Classes

Inspired by OpenManus ToolCollection pattern: each tool is a self-contained
object with schema definition, async execution, and structured results.

Design:
- EmmaTool: Abstract base with OpenAI function-calling schema generation
- ToolResult: Structured output (success or error) with optional sources
- ToolError: Rich error for tool failures with retry hints
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Structured result from tool execution.

    Attributes:
        output: The tool's textual output (what the LLM sees as observation)
        sources: Optional list of source references for citation
        data: Optional structured data (not sent to LLM, used by synthesize)
        success: Whether the tool executed successfully
        error: Error message if execution failed
    """
    output: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None

    @classmethod
    def from_error(cls, error: str, suggestion: str = "") -> "ToolResult":
        """Create an error result with optional retry suggestion."""
        msg = f"Error: {error}"
        if suggestion:
            msg += f"\nSuggestion: {suggestion}"
        return cls(output=msg, success=False, error=error)


class ToolError(Exception):
    """Rich error for tool failures."""

    def __init__(self, message: str, tool_name: str = "", retryable: bool = False):
        self.tool_name = tool_name
        self.retryable = retryable
        super().__init__(message)


class EmmaTool(ABC):
    """Abstract base class for Emma ReAct tools.

    Each tool declares:
    - name: Unique identifier used in tool_calls
    - description: What the tool does (shown to LLM)
    - parameters_schema: Pydantic model for input validation
    - execute(): Async execution with structured ToolResult

    The to_openai_param() method generates the OpenAI function-calling
    schema automatically from the Pydantic model, so adding a new tool
    only requires defining its schema and execute method.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool identifier (used in function calling)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description shown to the LLM."""
        ...

    @property
    @abstractmethod
    def parameters_schema(self) -> Type[BaseModel]:
        """Pydantic model defining the tool's input parameters."""
        ...

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Execute the tool with validated arguments.

        Args:
            arguments: Dict parsed from LLM tool_call arguments
            context: Current ReActState (user_roles, user_id, sector, etc.)

        Returns:
            ToolResult with output text, sources, and success status
        """
        ...

    def to_openai_param(self) -> Dict[str, Any]:
        """Generate OpenAI function-calling schema from the Pydantic model.

        Returns a dict compatible with the OpenAI tools API:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        schema = self.parameters_schema.model_json_schema()

        # Clean up Pydantic schema for OpenAI compatibility
        # Remove $defs, title, and other non-OpenAI fields
        properties = schema.get("properties", {})
        cleaned_properties = {}
        for prop_name, prop_schema in properties.items():
            cleaned = {k: v for k, v in prop_schema.items() if k not in ("title",)}
            cleaned_properties[prop_name] = cleaned

        required = schema.get("required", [])

        parameters: Dict[str, Any] = {
            "type": "object",
            "properties": cleaned_properties,
        }
        if required:
            parameters["required"] = required

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }

    async def safe_execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Execute with validation, error handling, and logging."""
        try:
            # Validate arguments via Pydantic
            validated = self.parameters_schema(**arguments)
            validated_args = validated.model_dump()
        except Exception as e:
            logger.warning(f"Tool {self.name}: invalid arguments: {e}")
            return ToolResult.from_error(
                f"Invalid arguments for {self.name}: {e}",
                suggestion="Check parameter types and required fields.",
            )

        try:
            result = await self.execute(validated_args, context)
            logger.debug(f"Tool {self.name}: success (output length={len(result.output)})")
            return result
        except ToolError as e:
            logger.warning(f"Tool {self.name}: {e}")
            return ToolResult.from_error(str(e))
        except Exception as e:
            logger.error(f"Tool {self.name}: unexpected error: {e}", exc_info=True)
            return ToolResult.from_error(
                f"Internal error in {self.name}: {type(e).__name__}",
                suggestion="Try a different approach or tool.",
            )

    def __repr__(self) -> str:
        return f"<EmmaTool: {self.name}>"
