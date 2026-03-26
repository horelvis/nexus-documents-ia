"""
Agents module for Knowledge Tree Service.

Legacy Emma agent code has been removed (now lives in emma-agent-service).
Remaining modules provide supporting utilities used by the langgraph sub-package.
"""

# Configuration
from .config import AgentConfig, agent_config, WorkflowType, AgentType

# Domain Router - Fast keyword-based domain detection
from .domain_router import DomainRouter, DomainType, domain_router

# LLM Client - Native async multi-provider client
from .llm_client import (
    LLMClient,
    LLMConfig,
    LLMProvider,
    LLMResponse,
    StreamEvent,
    ToolCall,
    create_llm_client_from_settings,
    get_llm_client,
)

__all__ = [
    # Configuration
    "AgentConfig",
    "agent_config",
    "WorkflowType",
    "AgentType",
    # Domain Router
    "DomainRouter",
    "DomainType",
    "domain_router",
    # LLM Client (async native)
    "LLMClient",
    "LLMConfig",
    "LLMProvider",
    "LLMResponse",
    "StreamEvent",
    "ToolCall",
    "create_llm_client_from_settings",
    "get_llm_client",
]


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
