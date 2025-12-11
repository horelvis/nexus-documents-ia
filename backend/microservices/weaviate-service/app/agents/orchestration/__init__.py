"""
Orchestration Patterns for Emma Multi-Agent System

This module provides different orchestration patterns for coordinating
multiple AI agents based on the task requirements.

PATTERNS:
- HANDOFF (default): LLM decides via .as_tool() - best for simple queries
- SEQUENTIAL: Pipeline A → B → C - best for step-by-step analysis
- CONCURRENT: Parallel A | B | C - best for multi-perspective analysis

USAGE:
```python
from app.agents.orchestration import (
    OrchestrationPattern,
    detect_orchestration_pattern,
    get_sequential_orchestration,
    get_concurrent_orchestration,
    get_agents_for_pattern
)

# Detect pattern from query
pattern = await detect_orchestration_pattern(query, use_llm=True)

# Get appropriate agents
agents = get_agents_for_pattern(pattern, query, available_agents)

# Execute
if pattern == OrchestrationPattern.SEQUENTIAL:
    orchestration = get_sequential_orchestration()
    result = await orchestration.execute(query, tenant_id, session_id, agents)

elif pattern == OrchestrationPattern.CONCURRENT:
    orchestration = get_concurrent_orchestration()
    result = await orchestration.execute(query, tenant_id, session_id, agents)

else:  # HANDOFF
    # Use EmmaCoordinator with .as_tool() delegation
    ...
```
"""

from .base import (
    # Enums
    OrchestrationPattern,
    # Data classes
    AgentResult,
    OrchestrationResult,
    # Base class
    BaseOrchestration,
    # Pattern detection
    detect_orchestration_pattern,
    detect_orchestration_pattern_keywords,
    detect_orchestration_pattern_llm,
    # Agent selection
    get_agents_for_pattern,
)

# Semantic Routers (optional - graceful fallback if not installed)
try:
    from .router import (
        # Pattern Router - classifies orchestration patterns (HANDOFF, SEQUENTIAL, CONCURRENT)
        SemanticPatternRouter,
        get_semantic_router,
        classify_pattern,
        # Domain Router - classifies legal/business domains (contract, labor, fiscal, etc.)
        SemanticDomainRouter,
        get_domain_router,
        classify_domain,
    )
    _SEMANTIC_ROUTER_AVAILABLE = True
except ImportError:
    _SEMANTIC_ROUTER_AVAILABLE = False
    # Pattern Router
    SemanticPatternRouter = None
    get_semantic_router = None
    classify_pattern = None
    # Domain Router
    SemanticDomainRouter = None
    get_domain_router = None
    classify_domain = None

from .sequential import (
    SequentialOrchestration,
    SequentialConfig,
    get_sequential_orchestration,
)

from .concurrent import (
    ConcurrentOrchestration,
    ConcurrentConfig,
    get_concurrent_orchestration,
)

__all__ = [
    # Enums
    "OrchestrationPattern",
    # Data classes
    "AgentResult",
    "OrchestrationResult",
    # Base
    "BaseOrchestration",
    # Detection (main entry point)
    "detect_orchestration_pattern",
    "get_agents_for_pattern",
    # Deprecated (kept for backward compatibility)
    "detect_orchestration_pattern_keywords",
    "detect_orchestration_pattern_llm",
    # Semantic Pattern Router (classifies HANDOFF/SEQUENTIAL/CONCURRENT)
    "SemanticPatternRouter",
    "get_semantic_router",
    "classify_pattern",
    # Semantic Domain Router (classifies legal/business domains)
    "SemanticDomainRouter",
    "get_domain_router",
    "classify_domain",
    # Availability flag
    "_SEMANTIC_ROUTER_AVAILABLE",
    # Sequential orchestration
    "SequentialOrchestration",
    "SequentialConfig",
    "get_sequential_orchestration",
    # Concurrent orchestration
    "ConcurrentOrchestration",
    "ConcurrentConfig",
    "get_concurrent_orchestration",
]
