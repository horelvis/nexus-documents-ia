"""
LLM Model Instances — ChatOpenAI backed by SGLang.

Two instances with different configs for dual-phase behavior:
- planner_model: fast, deterministic (classify, rewrite, tools, decompose)
- chat_model: creative, longer output (synthesize, social)

Uses lazy factory pattern — instantiated on first call, not at import time.
Replaces: llm_router.py + llm_client.py
"""

import logging
import re
from typing import List, Union

import httpx
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

_planner_model = None
_chat_model = None


def get_planner_model() -> ChatOpenAI:
    """Get the planner ChatOpenAI instance (lazy, singleton).

    Configured for fast, deterministic output:
    - Low temperature (0.3)
    - Thinking disabled
    - 4096 max tokens
    - repetition_penalty to prevent generation loops
    """
    global _planner_model
    if _planner_model is None:
        from app.core.config import settings

        _planner_model = ChatOpenAI(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=settings.planner_temperature,
            max_tokens=settings.planner_max_tokens,
            extra_body={
                "repetition_penalty": 1.15,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
    return _planner_model


def get_chat_model() -> ChatOpenAI:
    """Get the chat ChatOpenAI instance (lazy, singleton).

    Configured for quality generation:
    - Higher temperature (0.6)
    - Thinking disabled by default (toggle via chat_with_thinking)
    - 16384 max tokens
    - repetition_penalty to prevent generation loops
    """
    global _chat_model
    if _chat_model is None:
        from app.core.config import settings

        _chat_model = ChatOpenAI(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=settings.chat_temperature,
            max_tokens=settings.chat_max_tokens,
            extra_body={
                "repetition_penalty": 1.15,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
    return _chat_model


async def chat_with_thinking(
    messages: List[Union[BaseMessage, dict]],
    **kwargs,
) -> str:
    """Raw SGLang call with thinking enabled. Used for deep_reasoning toggle.

    Bypasses ChatOpenAI because enable_thinking requires chat_template_kwargs
    at the request level, which ChatOpenAI doesn't support per-call.

    Returns the content string with <think> tags stripped.
    """
    from app.core.config import settings

    # Convert LangChain messages to OpenAI dict format
    openai_messages = []
    for m in messages:
        if isinstance(m, dict):
            openai_messages.append(m)
        else:
            # BaseMessage — map .type to role
            role = m.type
            if role == "human":
                role = "user"
            elif role == "ai":
                role = "assistant"
            openai_messages.append({"role": role, "content": m.content})

    async with httpx.AsyncClient(timeout=settings.agent_timeout_seconds) as client:
        response = await client.post(
            f"{settings.llm_base_url}/chat/completions",
            json={
                "model": settings.llm_model,
                "messages": openai_messages,
                "temperature": settings.chat_temperature,
                "max_tokens": settings.chat_max_tokens,
                "chat_template_kwargs": {"enable_thinking": True},
                "repetition_penalty": 1.15,
                **kwargs,
            },
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"].get("content", "") or ""

    # Strip <think> tags — SGLang with reasoning-parser should separate them,
    # but handle inline tags as fallback
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    return content
