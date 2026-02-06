"""
LLM Router with Automatic Fallback

Provides unified access to multiple LLM providers with automatic fallback
when the primary provider fails. Inspired by OpenRouter's gateway pattern.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                      LLMRouter                               │
    │                                                              │
    │  Primary (vLLM) ──fail──> Fallback (OpenRouter) ──fail──>   │
    │                           Fallback (OpenAI)                  │
    │                                                              │
    │  Each provider uses LLMClient with appropriate LLMConfig    │
    └─────────────────────────────────────────────────────────────┘

Usage:
    >>> router = LLMRouter()
    >>> response = await router.chat(messages, tools)
    >>> # Uses primary provider, falls back automatically if it fails

Environment Variables:
    LLM_PROVIDER: Primary provider (vllm, openrouter, openai)
    LLM_FALLBACK_ENABLED: Enable automatic fallback (true/false)
    LLM_FALLBACK_CHAIN: Comma-separated provider order (e.g., "vllm,openrouter,openai")
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.agents.llm_client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    StreamEvent,
    create_llm_config_for_provider,
)
from app.core.langfuse_config import langfuse_context, observe

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Router with automatic fallback between LLM providers.

    The router maintains a pool of LLM clients and routes requests
    to the primary provider. If the primary fails, it automatically
    tries fallback providers in order.

    Features:
    - Lazy client initialization (created on first use)
    - Automatic fallback on provider failure
    - Provider override per request
    - Configurable fallback chain
    - Langfuse observability integration

    Example:
        >>> router = LLMRouter()
        >>> # Uses primary provider with automatic fallback
        >>> response = await router.chat(messages)
        >>> # Force specific provider (no fallback)
        >>> response = await router.chat(messages, provider_override="openrouter")
    """

    def __init__(self):
        """Initialize the router with empty client pool."""
        self._clients: Dict[LLMProvider, LLMClient] = {}
        self._fallback_chain: List[LLMProvider] = self._parse_fallback_chain()
        self._fallback_enabled: bool = self._is_fallback_enabled()

        logger.info(
            f"LLMRouter initialized: primary={self._fallback_chain[0].value if self._fallback_chain else 'none'}, "
            f"fallback_enabled={self._fallback_enabled}, chain={[p.value for p in self._fallback_chain]}"
        )

    def _parse_fallback_chain(self) -> List[LLMProvider]:
        """
        Parse fallback chain from settings.

        Returns:
            List of providers in fallback order
        """
        from app.core.config import settings

        chain_str = settings.llm_fallback_chain
        providers = []

        for provider_name in chain_str.split(","):
            provider_name = provider_name.strip().lower()
            try:
                providers.append(LLMProvider(provider_name))
            except ValueError:
                logger.warning(f"Unknown provider in fallback chain: {provider_name}")

        # If no valid providers, default to primary only
        if not providers:
            primary = settings.llm_provider.lower()
            try:
                providers = [LLMProvider(primary)]
            except ValueError:
                providers = [LLMProvider.VLLM]

        return providers

    def _is_fallback_enabled(self) -> bool:
        """Check if fallback is enabled in settings."""
        from app.core.config import settings
        return settings.llm_fallback_enabled

    def _get_or_create_client(self, provider: LLMProvider) -> LLMClient:
        """
        Get existing client or create new one for provider.

        Args:
            provider: The LLM provider

        Returns:
            LLMClient instance for the provider
        """
        if provider not in self._clients:
            config = create_llm_config_for_provider(provider)
            self._clients[provider] = LLMClient(config)
            logger.debug(f"Created LLM client for provider: {provider.value}")

        return self._clients[provider]

    def _get_providers_to_try(self, provider_override: Optional[str] = None) -> List[LLMProvider]:
        """
        Get list of providers to try in order.

        Args:
            provider_override: If set, only try this provider (no fallback)

        Returns:
            List of providers to attempt
        """
        if provider_override:
            try:
                return [LLMProvider(provider_override.lower())]
            except ValueError:
                logger.warning(f"Unknown provider override: {provider_override}, using fallback chain")

        if self._fallback_enabled:
            return self._fallback_chain
        else:
            # Only try primary (first in chain)
            return [self._fallback_chain[0]] if self._fallback_chain else [LLMProvider.VLLM]

    @observe(as_type="span", name="llm_router.chat")
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        provider_override: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Send chat completion request with automatic fallback.

        Args:
            messages: Conversation history
            tools: Available tools (OpenAI function format)
            provider_override: Force specific provider (disables fallback)
            **kwargs: Override config (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with content and/or tool calls

        Raises:
            Exception: If all providers fail
        """
        providers = self._get_providers_to_try(provider_override)
        last_error: Optional[Exception] = None

        for i, provider in enumerate(providers):
            is_fallback = i > 0

            try:
                client = self._get_or_create_client(provider)

                if is_fallback:
                    logger.info(f"Fallback attempt {i}: trying provider {provider.value}")

                response = await client.chat(messages, tools, **kwargs)

                # Log success
                if is_fallback:
                    logger.info(f"Fallback to {provider.value} succeeded")

                # Update Langfuse with provider info
                langfuse_context.update_current_observation(
                    metadata={
                        "provider": provider.value,
                        "is_fallback": is_fallback,
                        "fallback_attempt": i if is_fallback else 0,
                    }
                )

                return response

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider {provider.value} failed: {type(e).__name__}: {str(e)[:200]}"
                )

                # Update Langfuse with failure
                langfuse_context.update_current_observation(
                    metadata={
                        f"provider_{provider.value}_error": str(e)[:200],
                    }
                )

                # Continue to next provider
                continue

        # All providers failed
        error_msg = f"All LLM providers failed. Last error: {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        provider_override: Optional[str] = None,
        **kwargs,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream chat completion response with automatic fallback.

        Note: Fallback only happens before streaming starts. Once streaming
        begins, errors are yielded as StreamEvent(event_type="error").

        Args:
            messages: Conversation history
            tools: Available tools
            provider_override: Force specific provider (disables fallback)
            **kwargs: Override config

        Yields:
            StreamEvent objects
        """
        providers = self._get_providers_to_try(provider_override)
        last_error: Optional[Exception] = None

        for i, provider in enumerate(providers):
            is_fallback = i > 0

            try:
                client = self._get_or_create_client(provider)

                if is_fallback:
                    logger.info(f"Fallback attempt {i}: trying provider {provider.value} for streaming")

                # Start streaming - if this succeeds, we're committed to this provider
                async for event in client.chat_stream(messages, tools, **kwargs):
                    yield event

                # Stream completed successfully
                if is_fallback:
                    logger.info(f"Fallback streaming from {provider.value} succeeded")

                return

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider {provider.value} failed to start stream: {type(e).__name__}: {str(e)[:200]}"
                )
                continue

        # All providers failed to start streaming
        yield StreamEvent(
            event_type="error",
            error=f"All LLM providers failed. Last error: {last_error}"
        )

    async def validate_connection(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate connection to one or all providers.

        Args:
            provider: Specific provider to check, or None for all in chain

        Returns:
            Dict with provider status information
        """
        results = {}

        if provider:
            providers_to_check = [LLMProvider(provider.lower())]
        else:
            providers_to_check = self._fallback_chain

        for p in providers_to_check:
            try:
                client = self._get_or_create_client(p)
                is_connected, message = await client.validate_connection()
                results[p.value] = {
                    "connected": is_connected,
                    "message": message,
                    "model": client.config.model,
                }
            except Exception as e:
                results[p.value] = {
                    "connected": False,
                    "message": f"Error: {str(e)}",
                    "model": None,
                }

        return results

    async def close(self) -> None:
        """Close all LLM clients."""
        for provider, client in self._clients.items():
            try:
                await client.close()
                logger.debug(f"Closed LLM client for provider: {provider.value}")
            except Exception as e:
                logger.warning(f"Error closing client for {provider.value}: {e}")

        self._clients.clear()

    @property
    def primary_provider(self) -> LLMProvider:
        """Get the primary (first) provider in the chain."""
        return self._fallback_chain[0] if self._fallback_chain else LLMProvider.VLLM

    @property
    def fallback_chain(self) -> List[str]:
        """Get the fallback chain as list of provider names."""
        return [p.value for p in self._fallback_chain]

    @property
    def is_fallback_enabled(self) -> bool:
        """Check if fallback is enabled."""
        return self._fallback_enabled


# =============================================================================
# Global Router Instance (Lazy Initialization)
# =============================================================================

_llm_router: Optional[LLMRouter] = None
_llm_router_lock = asyncio.Lock()


async def get_llm_router() -> LLMRouter:
    """
    Get global LLM router instance (thread-safe with double-check locking).

    Returns:
        Shared LLMRouter instance
    """
    global _llm_router
    if _llm_router is None:
        async with _llm_router_lock:
            if _llm_router is None:
                _llm_router = LLMRouter()
    return _llm_router


async def close_llm_router() -> None:
    """Close global LLM router and all its clients."""
    global _llm_router
    if _llm_router:
        await _llm_router.close()
        _llm_router = None
