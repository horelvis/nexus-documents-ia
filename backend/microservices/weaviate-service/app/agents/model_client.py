"""
Multi-Provider Model Client for Qwen-Agent Framework

Provides factory functions for creating LLM configurations and clients:
- vLLM (PRIMARY - Qwen3-VL-4B-Instruct with vision + tool calling)
- OpenAI (GPT-4o, GPT-4o-mini - fallback)

IMPORTANT: vLLM uses OpenAI-compatible API. Qwen-Agent handles tool parsing
internally (no --tool-call-parser needed in vLLM).

FRAMEWORK: Qwen-Agent
All agents use get_llm_config() to obtain their LLM configuration dict.

MULTIMODAL SUPPORT:
Qwen3-VL-4B-Instruct supports vision (images) alongside text. Use build_multimodal_message()
to construct messages with images in OpenAI Vision API format.

References:
- https://github.com/QwenLM/Qwen-Agent
- https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
- https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct
"""

import base64
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import httpx

from .config import agent_config, AgentConfig

logger = logging.getLogger(__name__)

# Type alias for LLM config (Qwen-Agent uses dict configuration)
LLMConfig = Dict[str, Any]


# =============================================================================
# Multimodal Message Support (Qwen3-VL Vision)
# =============================================================================

@dataclass
class ImageContent:
    """Represents an image for multimodal input."""
    data: bytes  # Raw image bytes
    media_type: str = "image/png"  # image/png, image/jpeg, image/webp, image/gif
    detail: str = "auto"  # auto, low, high (controls resolution for vision processing)

    def to_base64_url(self) -> str:
        """Convert to data URL for OpenAI Vision API format."""
        b64_data = base64.b64encode(self.data).decode("utf-8")
        return f"data:{self.media_type};base64,{b64_data}"

    def to_content_block(self) -> dict:
        """Convert to OpenAI Vision API content block."""
        return {
            "type": "image_url",
            "image_url": {
                "url": self.to_base64_url(),
                "detail": self.detail,
            }
        }


@dataclass
class MultimodalMessage:
    """
    A message that can contain text and/or images.

    Supports the OpenAI Vision API format used by vLLM with Qwen3-VL.
    """
    role: str  # "user", "assistant", "system"
    text: Optional[str] = None
    images: List[ImageContent] = field(default_factory=list)

    def to_api_format(self) -> dict:
        """
        Convert to OpenAI-compatible API message format.

        Returns:
            Message dict in OpenAI Vision API format
        """
        if not self.images:
            # Text-only message (simple format)
            return {
                "role": self.role,
                "content": self.text or ""
            }

        # Multimodal message (array content format)
        content = []

        # Add text first if present
        if self.text:
            content.append({
                "type": "text",
                "text": self.text
            })

        # Add images
        for img in self.images:
            content.append(img.to_content_block())

        return {
            "role": self.role,
            "content": content
        }


def build_multimodal_message(
    text: str,
    images: Optional[List[Union[bytes, str, ImageContent]]] = None,
    role: str = "user",
    image_detail: str = "auto",
) -> dict:
    """
    Build a multimodal message for the Vision API.

    Args:
        text: The text content of the message
        images: List of images (bytes, base64 strings, or ImageContent objects)
        role: Message role (user, assistant, system)
        image_detail: Image detail level (auto, low, high)

    Returns:
        Message dict in OpenAI Vision API format

    Example:
        >>> msg = build_multimodal_message(
        ...     text="What's in this diagram?",
        ...     images=[diagram_bytes],
        ... )
        >>> # Returns: {"role": "user", "content": [{"type": "text", ...}, {"type": "image_url", ...}]}
    """
    image_contents = []

    if images:
        for img in images:
            if isinstance(img, ImageContent):
                image_contents.append(img)
            elif isinstance(img, bytes):
                # Detect media type from magic bytes
                media_type = _detect_image_type(img)
                image_contents.append(ImageContent(
                    data=img,
                    media_type=media_type,
                    detail=image_detail
                ))
            elif isinstance(img, str):
                # Assume base64 string
                image_contents.append(ImageContent(
                    data=base64.b64decode(img),
                    media_type="image/png",
                    detail=image_detail
                ))

    message = MultimodalMessage(
        role=role,
        text=text,
        images=image_contents
    )

    return message.to_api_format()


def _detect_image_type(data: bytes) -> str:
    """Detect image MIME type from magic bytes."""
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    elif data[:2] == b'\xff\xd8':
        return "image/jpeg"
    elif data[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    elif data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return "image/webp"
    else:
        # Default to PNG
        return "image/png"


# =============================================================================
# Thinking Mode Support (Qwen3-VL Thinking models)
# =============================================================================

@dataclass
class ThinkingResponse:
    """
    Parsed response from a thinking-enabled model.

    The model uses <think>...</think> tags to show its reasoning process.
    """
    thinking: Optional[str] = None  # Content inside <think> tags (reasoning)
    content: str = ""  # Final answer (content outside <think> tags)
    raw_response: str = ""  # Original full response

    @property
    def has_thinking(self) -> bool:
        """Check if response contains thinking content."""
        return self.thinking is not None and len(self.thinking) > 0


def parse_thinking_response(response: str) -> ThinkingResponse:
    """
    Parse a response from a thinking-enabled model.

    Extracts content from <think>...</think> tags and separates it from
    the final answer.

    Args:
        response: Raw response from the model

    Returns:
        ThinkingResponse with separated thinking and content

    Example:
        >>> response = "<think>Let me analyze this...</think>The answer is 42."
        >>> parsed = parse_thinking_response(response)
        >>> parsed.thinking  # "Let me analyze this..."
        >>> parsed.content   # "The answer is 42."
    """
    # Pattern to match <think>...</think> content (non-greedy, handles multiline)
    think_pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)

    thinking_matches = think_pattern.findall(response)
    thinking_content = "\n".join(match.strip() for match in thinking_matches) if thinking_matches else None

    # Remove thinking tags to get final content
    final_content = think_pattern.sub('', response).strip()

    return ThinkingResponse(
        thinking=thinking_content,
        content=final_content,
        raw_response=response
    )


def build_thinking_prompt(
    query: str,
    enable_thinking: bool = True,
    thinking_budget: Optional[int] = None,
) -> str:
    """
    Build a prompt with thinking mode control.

    Args:
        query: The user's query
        enable_thinking: Whether to enable extended reasoning
        thinking_budget: Optional token budget for thinking (soft limit)

    Returns:
        Formatted query with thinking control

    Example:
        >>> build_thinking_prompt("What is 25*4?", enable_thinking=True)
        '/think What is 25*4?'
    """
    if enable_thinking:
        prefix = "/think"
        if thinking_budget:
            # Some models support budget hints
            prefix = f"/think budget={thinking_budget}"
        return f"{prefix} {query}"
    else:
        return f"/no_think {query}"


class ModelClientError(Exception):
    """Error creating or using a model client."""
    pass


# =============================================================================
# Qwen-Agent LLM Configuration
# =============================================================================

def get_llm_config(
    config: AgentConfig = None,
    provider: str = None,
    model: str = None,
    agent_name: str = None,
) -> LLMConfig:
    """
    Get LLM configuration dict for Qwen-Agent.

    This is the main entry point for getting LLM configuration.
    All agents should use this function to obtain their LLM config.

    Args:
        config: Agent configuration (uses global if None)
        provider: Override provider (vllm, openai)
        model: Override model name
        agent_name: Name of the agent (for per-agent temperature)

    Returns:
        LLM configuration dict for Qwen-Agent

    Example:
        >>> llm_cfg = get_llm_config(agent_name="SearchAgent")
        >>> agent = Assistant(llm=llm_cfg, system_message="...", function_list=[...])
    """
    cfg = config or agent_config
    selected_provider = (provider or cfg.model_provider).lower()

    # Get temperature for this specific agent
    temperature = cfg.get_temperature_for_agent(agent_name) if agent_name else cfg.default_temperature

    logger.info(f"Creating Qwen-Agent LLM config for provider: {selected_provider}")
    logger.info(f"LLM config for {agent_name or 'default'}: temperature={temperature}")

    if selected_provider == "vllm":
        # vLLM with OpenAI-compatible API
        logger.info(f"Using vLLM: model={model or cfg.vllm_model}, base_url={cfg.vllm_base_url}")
        logger.info(f"vLLM thinking mode: {cfg.vllm_enable_thinking}")

        # Build generate config with thinking mode control
        # For Qwen3 models, use chat_template_kwargs to control thinking mode
        generate_cfg = {
            "temperature": temperature,
            "top_p": 0.9,
            # Pass enable_thinking via extra_body for vLLM/SGLang compatibility
            "extra_body": {
                "chat_template_kwargs": {
                    "enable_thinking": cfg.vllm_enable_thinking
                }
            },
        }

        return {
            "model": model or cfg.vllm_model,
            "model_server": cfg.vllm_base_url,
            "api_key": "not-needed-for-vllm",
            "generate_cfg": generate_cfg
        }
    elif selected_provider == "openai":
        api_key = cfg.openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ModelClientError("OPENAI_API_KEY not set")
        logger.info(f"Using OpenAI: model={model or cfg.openai_model}")
        return {
            "model": model or cfg.openai_model,
            "model_type": "openai",
            "api_key": api_key,
            "generate_cfg": {
                "temperature": temperature,
                "top_p": 0.9,
            }
        }
    else:
        raise ModelClientError(
            f"Provider '{selected_provider}' not supported. "
            f"Supported: vllm, openai"
        )


def get_chat_model(
    config: AgentConfig = None,
    provider: str = None,
    model: str = None,
    agent_name: str = None,
):
    """
    Get a Qwen-Agent BaseChatModel instance.

    This creates an actual chat model object that can be used directly
    for making LLM calls without an agent wrapper.

    Args:
        config: Agent configuration (uses global if None)
        provider: Override provider (vllm, openai)
        model: Override model name
        agent_name: Name of the agent (for per-agent temperature)

    Returns:
        BaseChatModel instance from Qwen-Agent

    Example:
        >>> chat_model = get_chat_model()
        >>> response = chat_model.chat(messages=[{"role": "user", "content": "Hello"}])
    """
    try:
        from qwen_agent.llm import get_chat_model as qwen_get_chat_model
    except ImportError as e:
        raise ModelClientError(
            "qwen-agent not installed. "
            "Run: pip install qwen-agent"
        ) from e

    llm_cfg = get_llm_config(config, provider, model, agent_name)
    return qwen_get_chat_model(llm_cfg)


# Legacy alias for backwards compatibility during migration
def get_chat_client(
    config: AgentConfig = None,
    provider: str = None,
    model: str = None,
    agent_name: str = None,
) -> LLMConfig:
    """
    Legacy function - returns LLM config dict.

    DEPRECATED: Use get_llm_config() instead.
    This function is kept for backwards compatibility during migration.
    """
    logger.warning("get_chat_client() is deprecated. Use get_llm_config() instead.")
    return get_llm_config(config, provider, model, agent_name)


def get_available_providers() -> list[str]:
    """
    Get list of available providers.

    Returns:
        List of provider names that are available
    """
    available = []

    try:
        from qwen_agent.llm import get_chat_model
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
                logger.info(f"vLLM connection validated. Available models: {models}")
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
                logger.info(f"vLLM connection validated. Available models: {models}")
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
        "name": "vLLM (Qwen3-VL-4B-Instruct)",
        "description": "High-throughput GPU inference with vision + tool calling",
        "requires_api_key": False,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,  # Can process images
        "supports_thinking": False,  # Use Thinking variant for this
        "primary": True,
        "framework": "qwen-agent",
    },
    "openai": {
        "name": "OpenAI",
        "description": "OpenAI GPT models (GPT-4, GPT-4o)",
        "requires_api_key": True,
        "supports_tools": True,
        "supports_streaming": True,
        "supports_vision": True,  # GPT-4V supports vision
        "supports_thinking": False,
        "primary": False,
        "framework": "qwen-agent",
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
