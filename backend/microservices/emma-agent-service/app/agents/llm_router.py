"""
DEPRECATED: LLM Router compat wrapper.

This module is a thin compatibility layer that delegates chat() to ChatOpenAI
instances in llm_models.py. Streaming (chat_stream) still uses the old LLMClient
until the SSE migration sub-project.

Migrate consumers to use get_planner_model()/get_chat_model() directly.
"""

import logging
import warnings
from typing import Any, AsyncGenerator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agents.llm_client import (
    LLMClient,
    LLMProvider,
    LLMResponse,
    StreamEvent,
    ToolCall,
    create_llm_config_for_provider,
)
from app.agents.llm_models import get_chat_model, get_planner_model
from app.agents.llm_types import ModelRole

logger = logging.getLogger(__name__)


def _convert_dict_messages(messages):
    """Convert dict messages to LangChain message types."""
    lc_messages = []
    for m in (messages or []):
        if isinstance(m, dict):
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))
        else:
            lc_messages.append(m)
    return lc_messages


class _CompatRouter:
    """Deprecated compat wrapper — delegates chat() to ChatOpenAI instances.

    chat_stream() and validate_connection() still use the old LLMClient
    until the SSE migration sub-project replaces them.
    """

    def __init__(self):
        # Old LLMClient for streaming and validation (temporary)
        self._stream_clients: Dict[str, LLMClient] = {}

    def _get_stream_client(self, role: ModelRole = ModelRole.CHAT) -> LLMClient:
        """Get old-style LLMClient for streaming (temporary until SSE migration)."""
        key = role.value
        if key not in self._stream_clients:
            from app.core.config import settings
            provider = LLMProvider(settings.llm_provider.lower())
            config = create_llm_config_for_provider(provider, role)
            self._stream_clients[key] = LLMClient(config)
        return self._stream_clients[key]

    async def chat(
        self,
        messages: Optional[List[Dict[str, Any]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        role: Optional[ModelRole] = None,
        **kwargs,
    ) -> LLMResponse:
        """Deprecated: delegates to ChatOpenAI. Use get_planner_model()/get_chat_model() directly."""
        warnings.warn(
            "LLMRouter.chat() is deprecated. Use get_planner_model()/get_chat_model() directly.",
            DeprecationWarning,
            stacklevel=2,
        )

        effective_role = role if role is not None else ModelRole.CHAT
        model = get_chat_model() if effective_role == ModelRole.CHAT else get_planner_model()

        lc_messages = _convert_dict_messages(messages)

        if tools:
            model = model.bind_tools(tools)

        response: AIMessage = await model.ainvoke(lc_messages)

        # Map ChatOpenAI tool_calls to old ToolCall dataclass
        old_tool_calls = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                old_tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=tc["name"],
                    arguments=tc["args"],
                ))

        return LLMResponse(
            content=response.content or "",
            tool_calls=old_tool_calls,
            thinking=None,
        )

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        role: ModelRole = ModelRole.CHAT,
        **kwargs,
    ) -> AsyncGenerator[StreamEvent, None]:
        """Streaming via old LLMClient (temporary until SSE migration)."""
        client = self._get_stream_client(role)
        async for event in client.chat_stream(messages, tools, **kwargs):
            yield event

    async def validate_connection(self, provider: Optional[str] = None) -> Dict[str, Any]:
        """Validate connection via old LLMClient."""
        results = {}
        client = self._get_stream_client(ModelRole.CHAT)
        is_connected, message = await client.validate_connection()
        results["vllm:chat"] = {
            "connected": is_connected,
            "message": message,
            "model": client.config.model,
            "role": "chat",
        }
        return results

    async def close(self) -> None:
        """Close streaming clients."""
        for client in self._stream_clients.values():
            try:
                await client.close()
            except Exception as e:
                logger.warning(f"Error closing stream client: {e}")
        self._stream_clients.clear()

    @property
    def primary_provider(self) -> LLMProvider:
        from app.core.config import settings
        try:
            return LLMProvider(settings.llm_provider.lower())
        except ValueError:
            return LLMProvider.VLLM

    @property
    def fallback_chain(self) -> List[str]:
        return [self.primary_provider.value]

    @property
    def is_fallback_enabled(self) -> bool:
        return False

    @property
    def is_dual_model(self) -> bool:
        return False


_compat_router = None


async def get_llm_router() -> _CompatRouter:
    """Get global compat router instance.

    DEPRECATED: Use get_planner_model()/get_chat_model() from llm_models.py.
    """
    global _compat_router
    if _compat_router is None:
        _compat_router = _CompatRouter()
        logger.info("LLMRouter compat wrapper initialized (delegates to ChatOpenAI)")
    return _compat_router


async def close_llm_router() -> None:
    """Close global compat router."""
    global _compat_router
    if _compat_router:
        await _compat_router.close()
        _compat_router = None
