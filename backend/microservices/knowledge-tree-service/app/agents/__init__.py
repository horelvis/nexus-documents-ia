"""
Emma Agent System for NouxCubeIA

This module provides the Emma AI assistant with:
- **Emma**: Main agent with SIL fast path and domain routing
- **LangGraph**: Multi-agent RAG orchestration (via feature flag)
- **Domain Router**: Fast keyword-based domain detection
- **Skill Loader**: Filesystem-based procedural knowledge

## Quick Start

```python
from app.agents import get_emma, ExecutionContext

# Get Emma instance
emma = await get_emma()

# Execute a query
result = await emma.execute(
    query="¿Cuántos contratos laborales tengo?",
    context=ExecutionContext(
        tenant_id="tenant-123",
        user_id="user-456",
    )
)

print(result.answer)
```

## LangGraph Integration

For multi-agent workflows with explicit state management:

```python
from app.agents.langgraph import execute_langgraph_query

result = await execute_langgraph_query(
    query="¿Qué dice el RGPD sobre consentimiento?",
    tenant_id="tenant-123",
)
```

Set LANGGRAPH_RAG_ENABLED=true to enable LangGraph routing.

## LLM Provider Support

Supports multiple providers via LLM_PROVIDER environment variable:
- SGLang (PRIMARY): High-throughput GPU inference
- OpenAI (fallback): GPT-4o, GPT-4o-mini
- Anthropic (fallback): Claude models
"""

# Configuration
from .config import AgentConfig, agent_config, WorkflowType, AgentType

# Emma - Main agent with SIL integration
from .emma import (
    Emma,
    EmmaConfig,
    EmmaResult,
    ExecutionContext,
    get_emma,
    reset_emma,
)

# Domain Router - Fast keyword-based domain detection
from .domain_router import DomainRouter, DomainType, domain_router

# Dynamic Prompt Loader - Domain-specific prompts
from .dynamic_prompt_loader import (
    DynamicPromptLoader,
    dynamic_prompt_loader,
    get_system_prompt_for_domain,
)

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

# Skill Loader - Agent Skills Framework (filesystem-based procedural knowledge)
from .skill_loader import (
    Skill,
    SkillMatch,
    SkillLoader,
    skill_loader,
    get_skill,
    match_skills,
    get_skill_instructions,
    reload_skills,
)

# Emma Tools
from .emma_tools import (
    EMMA_TOOLS,
    ToolContext,
    ToolResult,
    execute_tool,
    get_emma_tools,
)

__all__ = [
    # Configuration
    "AgentConfig",
    "agent_config",
    "WorkflowType",
    "AgentType",
    # Emma (Main agent)
    "Emma",
    "EmmaConfig",
    "EmmaResult",
    "ExecutionContext",
    "get_emma",
    "reset_emma",
    # Domain Router
    "DomainRouter",
    "DomainType",
    "domain_router",
    # Dynamic Prompt Loader
    "DynamicPromptLoader",
    "dynamic_prompt_loader",
    "get_system_prompt_for_domain",
    # LLM Client (async native)
    "LLMClient",
    "LLMConfig",
    "LLMProvider",
    "LLMResponse",
    "StreamEvent",
    "ToolCall",
    "create_llm_client_from_settings",
    "get_llm_client",
    # Skill Loader (Agent Skills Framework)
    "Skill",
    "SkillMatch",
    "SkillLoader",
    "skill_loader",
    "get_skill",
    "match_skills",
    "get_skill_instructions",
    "reload_skills",
    # Emma Tools
    "EMMA_TOOLS",
    "ToolContext",
    "ToolResult",
    "execute_tool",
    "get_emma_tools",
]


# Lazy imports for LangGraph to avoid circular imports
def __getattr__(name):
    """Lazy load sub-modules on demand."""
    if name == "langgraph":
        from . import langgraph as _langgraph
        return _langgraph
    if name == "orchestration":
        from . import orchestration as _orchestration
        return _orchestration
    if name == "permissions":
        from . import permissions as _permissions
        return _permissions
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
