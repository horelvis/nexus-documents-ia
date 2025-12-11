"""
Tool Call Adapter Abstract Base Class.

This module defines the interface that all LLM-specific adapters must implement.
Each adapter handles the conversion between the LLM's native tool calling format
and our internal model-agnostic format.

Design Philosophy:
    The adapter pattern allows us to support multiple LLM providers without
    changing any business logic. When switching from vLLM to OpenAI (or vice versa),
    only the adapter needs to change - all tools remain exactly the same.

Provider-Specific Formats:
    - Hermes (vLLM, Qwen3): Uses <tool_call> XML tags in assistant messages
    - OpenAI: Uses structured tool_calls array in API response
    - Anthropic: Uses tool_use content blocks in API response
    - Ollama: Similar to Hermes but may vary by model

Each adapter must handle:
    1. Converting ToolDefinition → Provider's tool format (for requests)
    2. Parsing provider's response → List[ToolCall] (from responses)
    3. Formatting ToolResult → Provider's result format (for follow-up)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..base import ToolCall, ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


class ToolCallAdapter(ABC):
    """
    Abstract base class for LLM-specific tool call adapters.

    Subclasses must implement all abstract methods to handle the
    specific format used by their target LLM provider.

    Example usage:
        adapter = HermesAdapter()

        # Convert our tools to provider format
        provider_tools = adapter.format_tools_for_request(our_tools)

        # Parse tool calls from LLM response
        tool_calls = adapter.parse_tool_calls(llm_response)

        # Format results for next message
        result_message = adapter.format_tool_results(results)
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """
        Identifier for this adapter's provider.

        Returns:
            String like "hermes", "openai", "anthropic"
        """
        pass

    @abstractmethod
    def format_tools_for_request(
        self,
        tools: List[ToolDefinition]
    ) -> Any:
        """
        Convert internal tool definitions to provider's format.

        This is used when making requests to the LLM to tell it
        what tools are available.

        Args:
            tools: List of our internal ToolDefinition objects

        Returns:
            Provider-specific format (varies by provider)
            - OpenAI: List of tool objects with type="function"
            - Anthropic: List of tool objects for the tools parameter
            - Hermes: Tools description for system prompt
        """
        pass

    @abstractmethod
    def parse_tool_calls(
        self,
        response: Any
    ) -> List[ToolCall]:
        """
        Parse tool calls from LLM response.

        This extracts any tool calls made by the LLM and converts
        them to our internal ToolCall format.

        Args:
            response: The raw response from the LLM API
                     (format varies by provider)

        Returns:
            List of ToolCall objects (may be empty if no tools called)
        """
        pass

    @abstractmethod
    def format_tool_results(
        self,
        results: List[ToolResult]
    ) -> Any:
        """
        Format tool results for the next LLM request.

        After executing tools, we need to send the results back
        to the LLM in its expected format.

        Args:
            results: List of ToolResult from tool execution

        Returns:
            Provider-specific format for tool results
            - OpenAI: List of tool message objects
            - Anthropic: List of tool_result content blocks
            - Hermes: Formatted text with <tool_result> tags
        """
        pass

    @abstractmethod
    def has_tool_calls(self, response: Any) -> bool:
        """
        Check if the response contains tool calls.

        This is a quick check without full parsing, useful for
        determining the next step in the conversation loop.

        Args:
            response: The raw response from the LLM API

        Returns:
            True if response contains tool calls
        """
        pass

    @abstractmethod
    def get_text_content(self, response: Any) -> Optional[str]:
        """
        Extract text content from response (excluding tool calls).

        Used to get the LLM's textual response for final output.

        Args:
            response: The raw response from the LLM API

        Returns:
            Text content if present, None otherwise
        """
        pass

    def format_system_prompt_with_tools(
        self,
        base_prompt: str,
        tools: List[ToolDefinition]
    ) -> str:
        """
        Optionally augment system prompt with tool information.

        Some providers (like Hermes) require tools in the system prompt.
        Others (like OpenAI) use a separate tools parameter.

        Default implementation returns base prompt unchanged.
        Override in adapters that need prompt augmentation.

        Args:
            base_prompt: The original system prompt
            tools: Available tools

        Returns:
            System prompt (possibly augmented with tool info)
        """
        return base_prompt

    def supports_parallel_tool_calls(self) -> bool:
        """
        Whether this provider supports multiple tool calls in one response.

        OpenAI and Anthropic support this; Hermes typically does not.

        Returns:
            True if parallel tool calls are supported
        """
        return False

    def get_tool_choice_param(
        self,
        mode: str = "auto"
    ) -> Optional[Any]:
        """
        Get provider-specific tool choice parameter.

        Args:
            mode: One of "auto", "none", "required", or a specific tool name

        Returns:
            Provider-specific tool_choice value, or None if not supported
        """
        return None


class AdapterRegistry:
    """
    Registry for tool call adapters.

    Maintains a mapping of provider names to adapter instances,
    allowing easy lookup and instantiation.
    """

    _adapters: Dict[str, type[ToolCallAdapter]] = {}

    @classmethod
    def register(cls, provider: str, adapter_class: type[ToolCallAdapter]) -> None:
        """Register an adapter class for a provider."""
        cls._adapters[provider.lower()] = adapter_class
        logger.debug(f"Registered adapter for provider: {provider}")

    @classmethod
    def get(cls, provider: str) -> Optional[ToolCallAdapter]:
        """
        Get an adapter instance for a provider.

        Args:
            provider: Provider name (case-insensitive)

        Returns:
            Adapter instance, or None if not registered
        """
        adapter_class = cls._adapters.get(provider.lower())
        if adapter_class:
            return adapter_class()
        logger.warning(f"No adapter registered for provider: {provider}")
        return None

    @classmethod
    def list_providers(cls) -> List[str]:
        """List all registered provider names."""
        return list(cls._adapters.keys())


def register_adapter(provider: str):
    """
    Decorator to register an adapter class.

    Usage:
        @register_adapter("hermes")
        class HermesAdapter(ToolCallAdapter):
            ...
    """
    def decorator(cls: type[ToolCallAdapter]) -> type[ToolCallAdapter]:
        AdapterRegistry.register(provider, cls)
        return cls
    return decorator
