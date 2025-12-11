"""
Multi-Provider Model Client for Agent Framework

Provides factory function for creating chat clients for different LLM providers:
- vLLM (PRIMARY - high-throughput GPU inference with Ministral 14B)
- OpenAI (GPT-4o, GPT-4o-mini - fallback)

IMPORTANT: vLLM uses OpenAI-compatible API, so we use the same client with different base_url.
This provides seamless switching between vLLM and OpenAI.

FRAMEWORK: Microsoft Agent Framework
All agents use get_chat_client() to obtain their LLM client.

References:
- https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
- https://learn.microsoft.com/en-us/agent-framework/
"""

import logging
import os
from typing import Any

import httpx

from .config import agent_config, AgentConfig

logger = logging.getLogger(__name__)

# Type alias for chat client
ChatClient = Any  # Agent Framework chat client type


class ModelClientError(Exception):
    """Error creating or using a model client."""
    pass


def get_chat_client(
    config: AgentConfig = None,
    provider: str = None,
    model: str = None,
    agent_name: str = None,
) -> ChatClient:
    """
    Factory to create Agent Framework ChatClient for ChatAgent.

    This is the main entry point for getting a chat client.
    All agents should use this function to obtain their LLM client.

    Args:
        config: Agent configuration (uses global if None)
        provider: Override provider (vllm, openai)
        model: Override model name
        agent_name: Name of the agent (for per-agent temperature)

    Returns:
        Configured OpenAIChatClient for Agent Framework

    Example:
        >>> client = get_chat_client(agent_name="LaborAgent")  # Uses per-agent temperature
        >>> agent = ChatAgent(chat_client=client, instructions="...", tools=[...])
    """
    cfg = config or agent_config
    selected_provider = (provider or cfg.model_provider).lower()

    # Get temperature for this specific agent
    temperature = cfg.get_temperature_for_agent(agent_name) if agent_name else cfg.default_temperature

    logger.info(f"Creating Agent Framework chat client for provider: {selected_provider}")

    try:
        from agent_framework.openai import OpenAIChatClient
    except ImportError as e:
        raise ModelClientError(
            "agent-framework not installed. "
            "Run: pip install 'agent-framework --pre'"
        ) from e

    # Log temperature for debugging (actual temperature is set at generation time)
    logger.info(f"Creating chat client for {agent_name or 'default'}: temperature={temperature}")

    if selected_provider == "vllm":
        # vLLM uses OpenAI-compatible API
        logger.info(f"Using vLLM: model={model or cfg.vllm_model}, base_url={cfg.vllm_base_url}")
        return OpenAIChatClient(
            model_id=model or cfg.vllm_model,
            base_url=cfg.vllm_base_url,
            api_key="not-needed-for-vllm",  # vLLM doesn't require API key
        )
    elif selected_provider == "openai":
        api_key = cfg.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ModelClientError("OPENAI_API_KEY not set")
        logger.info(f"Using OpenAI: model={model or cfg.openai_model}")
        return OpenAIChatClient(
            model_id=model or cfg.openai_model,
            api_key=api_key,
        )
    else:
        raise ModelClientError(
            f"Provider '{selected_provider}' not supported. "
            f"Supported: vllm, openai"
        )


def get_available_providers() -> list[str]:
    """
    Get list of available providers.

    Returns:
        List of provider names that are available
    """
    available = []

    try:
        from agent_framework.openai import OpenAIChatClient
        available.append("vllm")
        available.append("openai")
    except ImportError:
        pass

    return available


async def validate_vllm_connection(config: AgentConfig = None) -> tuple[bool, str]:
    """
    Validate that vLLM server is available and responding.

    Args:
        config: Agent configuration (uses global if None)

    Returns:
        Tuple of (is_available, message)
    """
    cfg = config or agent_config

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{cfg.vllm_base_url}/models")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("id", "unknown") for m in data.get("data", [])]
                logger.info(f"✅ vLLM connection validated. Available models: {models}")
                return True, f"Connected. Models: {', '.join(models)}"
            else:
                return False, f"vLLM responded with status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to vLLM at {cfg.vllm_base_url}"
    except httpx.TimeoutException:
        return False, f"Connection to vLLM timed out"
    except Exception as e:
        return False, f"vLLM validation error: {str(e)}"


def validate_vllm_connection_sync(config: AgentConfig = None) -> tuple[bool, str]:
    """
    Synchronous version of vLLM validation for use during startup.

    Args:
        config: Agent configuration (uses global if None)

    Returns:
        Tuple of (is_available, message)
    """
    cfg = config or agent_config

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{cfg.vllm_base_url}/models")
            if response.status_code == 200:
                data = response.json()
                models = [m.get("id", "unknown") for m in data.get("data", [])]
                logger.info(f"✅ vLLM connection validated. Available models: {models}")
                return True, f"Connected. Models: {', '.join(models)}"
            else:
                return False, f"vLLM responded with status {response.status_code}"
    except httpx.ConnectError:
        return False, f"Cannot connect to vLLM at {cfg.vllm_base_url}"
    except httpx.TimeoutException:
        return False, f"Connection to vLLM timed out"
    except Exception as e:
        return False, f"vLLM validation error: {str(e)}"


def validate_provider_config(provider: str, config: AgentConfig = None) -> tuple[bool, str]:
    """
    Validate that a provider is properly configured.

    Args:
        provider: Provider name to validate
        config: Configuration to check (uses global if None)

    Returns:
        Tuple of (is_valid, error_message)
    """
    cfg = config or agent_config
    provider = provider.lower()

    if provider not in get_available_providers():
        return False, f"Provider '{provider}' not available"

    if provider == "vllm":
        # vLLM doesn't require API key, just needs server running
        return True, ""

    if provider == "openai":
        if not cfg.openai_api_key:
            return False, "OPENAI_API_KEY not set"
        return True, ""

    return False, f"Unknown provider: {provider}"


# Provider information (models list is dynamic, set from config)
PROVIDER_INFO = {
    "vllm": {
        "name": "vLLM",
        "description": "High-throughput GPU inference with continuous batching",
        "requires_api_key": False,
        "supports_tools": True,
        "supports_streaming": True,
        "primary": True,
    },
    "openai": {
        "name": "OpenAI",
        "description": "OpenAI GPT models (GPT-4, GPT-4o)",
        "requires_api_key": True,
        "supports_tools": True,
        "supports_streaming": True,
        "primary": False,
    },
}


def get_provider_info(provider: str = None, config: AgentConfig = None) -> dict:
    """
    Get information about a provider or all providers.

    Args:
        provider: Specific provider name, or None for all
        config: Agent configuration to get current model from

    Returns:
        Provider info dict or dict of all providers
    """
    cfg = config or agent_config

    # Build info with dynamic model from config
    info = {}
    for name, data in PROVIDER_INFO.items():
        info[name] = dict(data)
        if name == "vllm":
            info[name]["model"] = cfg.vllm_model
        elif name == "openai":
            info[name]["model"] = cfg.openai_model

    if provider:
        return info.get(provider.lower(), {})
    return info
