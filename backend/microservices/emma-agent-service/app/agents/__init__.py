"""
Emma Agent System — LangGraph ReAct Agent

LangGraph is the single orchestration engine. All queries route through
the ReAct agent graph with tool calling, swarm decomposition, and
conversation persistence.

Usage:
    from app.agents.langgraph import execute_langgraph_query

    result = await execute_langgraph_query(
        query="¿Qué dice el RGPD sobre consentimiento?",
        tenant_id="tenant-123",
        user_id="user-456",
    )
"""

# LLM Models — ChatOpenAI backed by SGLang
from .llm_models import get_planner_model, get_chat_model


# Lazy imports for LangGraph to avoid circular imports
def __getattr__(name):
    """Lazy load sub-modules on demand."""
    if name == "langgraph":
        from . import langgraph as _langgraph
        return _langgraph
    if name == "permissions":
        from . import permissions as _permissions
        return _permissions
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_planner_model",
    "get_chat_model",
]
