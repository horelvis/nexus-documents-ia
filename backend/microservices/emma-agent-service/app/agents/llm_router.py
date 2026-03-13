"""
LLM Router with Automatic Fallback and Dual-Model Architecture

Provides unified access to multiple LLM providers with automatic fallback
when the primary provider fails. Supports dual-model routing where a fast
planner model handles tool calling/routing and a quality chat model handles
final response generation.

Architecture (Dual-Model):
    ┌─────────────────────────────────────────────────────────────┐
    │                      LLMRouter                               │
    │                                                              │
    │  role=PLANNER → vLLM-Planner (4B, fast tool calling)        │
    │  role=CHAT    → vLLM-Chat (9B, quality generation)          │
    │                                                              │
    │  Each role+provider combo has its own LLMClient instance     │
    │  Fallback chain works per-role                               │
    └─────────────────────────────────────────────────────────────┘

Architecture (Single-Model, backwards compatible):
    ┌─────────────────────────────────────────────────────────────┐
    │  VLLM_DUAL_MODEL=false (default)                            │
    │  Both PLANNER and CHAT use the same vLLM endpoint/model     │
    └─────────────────────────────────────────────────────────────┘

Usage:
    >>> router = await get_llm_router()
    >>> # Tool calling (uses planner if dual-model enabled)
    >>> response = await router.chat(messages, tools=tools, role=ModelRole.PLANNER)
    >>> # Final response (uses chat model)
    >>> response = await router.chat(messages, role=ModelRole.CHAT)

Environment Variables:
    LLM_PROVIDER: Primary provider (vllm, openrouter, openai)
    VLLM_DUAL_MODEL: Enable dual-model routing (true/false)
    VLLM_PLANNER_URL: Planner vLLM endpoint (defaults to VLLM_BASE_URL)
    VLLM_PLANNER_MODEL: Planner model name (defaults to VLLM_MODEL)
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.agents.llm_client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    ModelRole,
    StreamEvent,
    create_llm_config_for_provider,
)
from app.core.langfuse_config import langfuse_context, observe

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Router with automatic fallback between LLM providers.

    Supports dual-model architecture where PLANNER role uses a fast model
    for tool calling and CHAT role uses a quality model for generation.

    Features:
    - Lazy client initialization (created on first use)
    - Automatic fallback on provider failure
    - Provider and role override per request
    - Configurable fallback chain
    - Langfuse observability integration
    """

    def __init__(self):
        """Initialize the router with empty client pool."""
        # Client pool keyed by (provider, role) for dual-model support
        self._clients: Dict[Tuple[LLMProvider, ModelRole], LLMClient] = {}
        self._fallback_chain: List[LLMProvider] = self._parse_fallback_chain()
        self._fallback_enabled: bool = self._is_fallback_enabled()
        self._dual_model: bool = self._is_dual_model()

        logger.info(
            f"LLMRouter initialized: primary={self._fallback_chain[0].value if self._fallback_chain else 'none'}, "
            f"dual_model={self._dual_model}, "
            f"fallback_enabled={self._fallback_enabled}, chain={[p.value for p in self._fallback_chain]}"
        )

    def _parse_fallback_chain(self) -> List[LLMProvider]:
        """Parse fallback chain from settings."""
        from app.core.config import settings

        primary_name = settings.llm_provider.lower()
        try:
            primary = LLMProvider(primary_name)
        except ValueError:
            logger.warning(f"Unknown primary provider: {primary_name}, defaulting to vllm")
            primary = LLMProvider.VLLM

        chain_str = settings.llm_fallback_chain
        providers = [primary]

        for provider_name in chain_str.split(","):
            provider_name = provider_name.strip().lower()
            try:
                provider = LLMProvider(provider_name)
                if provider != primary:
                    providers.append(provider)
            except ValueError:
                logger.warning(f"Unknown provider in fallback chain: {provider_name}")

        return providers

    def _is_fallback_enabled(self) -> bool:
        """Check if fallback is enabled in settings."""
        from app.core.config import settings
        return settings.llm_fallback_enabled

    def _is_dual_model(self) -> bool:
        """Check if dual-model architecture is enabled."""
        from app.core.config import settings
        return settings.vllm_dual_model

    def _get_or_create_client(
        self,
        provider: LLMProvider,
        role: ModelRole = ModelRole.CHAT,
    ) -> LLMClient:
        """
        Get existing client or create new one for provider+role combo.

        In single-model mode, both roles share the same client.
        In dual-model mode, each role gets its own client with different config.
        """
        # In single-model mode, normalize role to CHAT to share client
        effective_role = role if self._dual_model else ModelRole.CHAT
        key = (provider, effective_role)

        if key not in self._clients:
            config = create_llm_config_for_provider(provider, effective_role)
            self._clients[key] = LLMClient(config)
            logger.debug(
                f"Created LLM client: provider={provider.value}, role={effective_role.value}, "
                f"model={config.model}"
            )

        return self._clients[key]

    def _get_providers_to_try(self, provider_override: Optional[str] = None) -> List[LLMProvider]:
        """Get list of providers to try in order."""
        if provider_override:
            try:
                return [LLMProvider(provider_override.lower())]
            except ValueError:
                logger.warning(f"Unknown provider override: {provider_override}, using fallback chain")

        if self._fallback_enabled:
            return self._fallback_chain
        else:
            return [self._fallback_chain[0]] if self._fallback_chain else [LLMProvider.VLLM]

    @observe(as_type="span", name="llm_router.chat")
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        provider_override: Optional[str] = None,
        role: ModelRole = ModelRole.CHAT,
        **kwargs,
    ) -> LLMResponse:
        """
        Send chat completion request with automatic fallback.

        Args:
            messages: Conversation history
            tools: Available tools (OpenAI function format)
            provider_override: Force specific provider (disables fallback)
            role: Model role — PLANNER for tool calling, CHAT for generation
            **kwargs: Override config (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with content and/or tool calls

        Raises:
            Exception: If all providers fail
        """
        providers = self._get_providers_to_try(provider_override)
        last_error: Optional[Exception] = None

        from app.core.config import settings
        retry_delay = settings.llm_retry_delay_seconds

        for i, provider in enumerate(providers):
            is_fallback = i > 0

            client = self._get_or_create_client(provider, role)

            if is_fallback:
                logger.info(f"Fallback attempt {i}: trying provider {provider.value}")

            for attempt in range(2):
                try:
                    response = await client.chat(messages, tools, **kwargs)

                    if is_fallback:
                        logger.info(f"Fallback to {provider.value} succeeded")

                    langfuse_context.update_current_observation(
                        metadata={
                            "provider": provider.value,
                            "model_role": role.value,
                            "model": client.config.model,
                            "is_fallback": is_fallback,
                            "fallback_attempt": i if is_fallback else 0,
                            "retry_attempt": attempt,
                        }
                    )

                    return response

                except Exception as e:
                    last_error = e
                    logger.warning(
                        f"Provider {provider.value} (role={role.value}) attempt {attempt}: "
                        f"{type(e).__name__}: {str(e)[:200]}"
                    )

                    if attempt == 0:
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        langfuse_context.update_current_observation(
                            metadata={
                                f"provider_{provider.value}_error": str(e)[:200],
                            }
                        )
                        break

        error_msg = f"All LLM providers failed. Last error: {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        provider_override: Optional[str] = None,
        role: ModelRole = ModelRole.CHAT,
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
            role: Model role — PLANNER for tool calling, CHAT for generation
            **kwargs: Override config

        Yields:
            StreamEvent objects
        """
        providers = self._get_providers_to_try(provider_override)
        last_error: Optional[Exception] = None

        for i, provider in enumerate(providers):
            is_fallback = i > 0

            try:
                client = self._get_or_create_client(provider, role)

                if is_fallback:
                    logger.info(f"Fallback attempt {i}: trying provider {provider.value} for streaming")

                async for event in client.chat_stream(messages, tools, **kwargs):
                    yield event

                if is_fallback:
                    logger.info(f"Fallback streaming from {provider.value} succeeded")

                return

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider {provider.value} (role={role.value}) failed to start stream: "
                    f"{type(e).__name__}: {str(e)[:200]}"
                )
                continue

        yield StreamEvent(
            event_type="error",
            error=f"All LLM providers failed. Last error: {last_error}"
        )

    async def validate_connection(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Validate connection to one or all providers."""
        results = {}

        if provider:
            providers_to_check = [LLMProvider(provider.lower())]
        else:
            providers_to_check = self._fallback_chain

        for p in providers_to_check:
            # Validate chat model
            try:
                client = self._get_or_create_client(p, ModelRole.CHAT)
                is_connected, message = await client.validate_connection()
                results[f"{p.value}:chat"] = {
                    "connected": is_connected,
                    "message": message,
                    "model": client.config.model,
                    "role": "chat",
                }
            except Exception as e:
                results[f"{p.value}:chat"] = {
                    "connected": False,
                    "message": f"Error: {str(e)}",
                    "model": None,
                    "role": "chat",
                }

            # Validate planner model (only if dual-model and vLLM)
            if self._dual_model and p == LLMProvider.VLLM:
                try:
                    planner_client = self._get_or_create_client(p, ModelRole.PLANNER)
                    is_connected, message = await planner_client.validate_connection()
                    results[f"{p.value}:planner"] = {
                        "connected": is_connected,
                        "message": message,
                        "model": planner_client.config.model,
                        "role": "planner",
                    }
                except Exception as e:
                    results[f"{p.value}:planner"] = {
                        "connected": False,
                        "message": f"Error: {str(e)}",
                        "model": None,
                        "role": "planner",
                    }

        return results

    async def close(self) -> None:
        """Close all LLM clients."""
        for key, client in self._clients.items():
            try:
                await client.close()
                logger.debug(f"Closed LLM client: provider={key[0].value}, role={key[1].value}")
            except Exception as e:
                logger.warning(f"Error closing client for {key}: {e}")

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

    @property
    def is_dual_model(self) -> bool:
        """Check if dual-model architecture is active."""
        return self._dual_model


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
