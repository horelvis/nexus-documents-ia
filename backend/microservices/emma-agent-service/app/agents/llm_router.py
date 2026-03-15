"""
DEPRECATED — use app.agents.llm_models instead.

All consumers have been migrated to get_planner_model()/get_chat_model().
This module is kept as a stub for backwards compatibility.
llm_client.py is still used by legacy EmmaService (emma.py) for streaming.
"""

from app.agents.llm_models import get_planner_model, get_chat_model, chat_with_thinking  # noqa: F401


async def get_llm_router():
    raise ImportError(
        "LLMRouter removed. Use get_planner_model()/get_chat_model() from app.agents.llm_models"
    )


async def close_llm_router():
    pass  # No-op — nothing to close
