"""
Tool Call Adapters Package.

This package provides adapters for different LLM provider tool calling formats.
The adapters convert between our internal model-agnostic format and each
provider's specific format.

Usage:
    from app.tools.adapters import get_tool_adapter

    # Get adapter for current LLM provider
    adapter = get_tool_adapter("vllm")  # or "openai", "anthropic"

    # Convert tools for request
    provider_tools = adapter.format_tools_for_request(tools)

    # Parse tool calls from response
    tool_calls = adapter.parse_tool_calls(response)

    # Format results for next message
    result_messages = adapter.format_tool_results(results)

Supported Providers:
    - hermes/vllm: Hermes format for vLLM with Qwen3
    - openai/gpt-4/gpt-4o: OpenAI's native tool calling
    - anthropic (TODO): Claude's tool use format
    - ollama (TODO): Ollama's native format
"""

from typing import Optional

from .base import ToolCallAdapter, AdapterRegistry, register_adapter
from .hermes import HermesAdapter
from .openai import OpenAIAdapter


def get_tool_adapter(provider: str) -> ToolCallAdapter:
    """
    Get the appropriate adapter for an LLM provider.

    This is the main entry point for getting adapters. It handles
    provider name normalization and falls back to Hermes (vLLM)
    if the provider is unknown.

    Args:
        provider: LLM provider name (case-insensitive)
                 Examples: "vllm", "openai", "gpt-4o", "hermes"

    Returns:
        Appropriate ToolCallAdapter instance

    Raises:
        ValueError: If provider is not supported and no fallback available
    """
    # Normalize provider name
    provider_lower = provider.lower().strip()

    # Map common aliases
    alias_map = {
        "vllm": "hermes",
        "qwen": "hermes",
        "qwen3": "hermes",
        "llama": "hermes",
        "gpt4": "openai",
        "gpt-4": "openai",
        "gpt-4o": "openai",
        "gpt4o": "openai",
        "gpt-4o-mini": "openai",
        "gpt-3.5": "openai",
        "gpt-3.5-turbo": "openai",
    }

    provider_key = alias_map.get(provider_lower, provider_lower)

    # Try to get from registry
    adapter = AdapterRegistry.get(provider_key)

    if adapter:
        return adapter

    # Fallback to Hermes (default for local models)
    from ..base import logger
    logger.warning(
        f"Unknown provider '{provider}', falling back to Hermes adapter. "
        f"Registered providers: {AdapterRegistry.list_providers()}"
    )
    return HermesAdapter()


def get_adapter_for_model(model_name: str) -> ToolCallAdapter:
    """
    Infer the appropriate adapter from a model name.

    This is useful when you have a model name but not the provider.
    It attempts to determine the provider from the model name.

    Args:
        model_name: Full model name (e.g., "Qwen/Qwen3-14B", "gpt-4o")

    Returns:
        Appropriate ToolCallAdapter instance
    """
    model_lower = model_name.lower()

    # OpenAI models
    if any(x in model_lower for x in ["gpt-4", "gpt-3.5", "o1-", "o3-"]):
        return OpenAIAdapter()

    # Anthropic models
    if any(x in model_lower for x in ["claude", "anthropic"]):
        # TODO: Return AnthropicAdapter when implemented
        return HermesAdapter()  # Fallback for now

    # Default to Hermes for local/vLLM models
    return HermesAdapter()


__all__ = [
    # Base classes
    "ToolCallAdapter",
    "AdapterRegistry",
    "register_adapter",
    # Implementations
    "HermesAdapter",
    "OpenAIAdapter",
    # Factory functions
    "get_tool_adapter",
    "get_adapter_for_model",
]
