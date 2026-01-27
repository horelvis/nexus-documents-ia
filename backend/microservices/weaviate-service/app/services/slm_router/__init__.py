"""
SLM Router: Small Language Model Based Query Planning

A unified routing system that replaces fragmented routing approaches
with a single, deterministic planning system using a Small Language Model.

Key Components:
    - TOONPlan: Task-Oriented Orchestration Notation - structured query plans
    - SLMClient: Client for the Small Language Model (Qwen2-0.5B or similar)
    - TOONExecutor: Executes plans against Apache AGE and Weaviate
    - TenantSchemaProvider: Extracts tenant context for planning
    - HistoryManager: Manages conversation history for contextual queries
    - SLMRouter: Main router that coordinates all components

Usage:
    from app.services.slm_router import get_slm_router, TOONRoute

    router = get_slm_router()
    await router.initialize()

    # Full route (plan + execute)
    result = await router.route(
        query="How many contracts does ACME have?",
        tenant_id="tenant-123",
        session_id="session-456"
    )

    if result.plan.route == TOONRoute.ASK_CLARIFY:
        print(f"Need clarification: {result.clarification_question}")
    else:
        print(f"Context for LLM: {result.context_for_llm}")

Version 1.0 - January 2026
"""

# Core schemas
from .toon_schema import (
    # Main plan model
    TOONPlan,
    TOONExecutionResult,
    TOONPlanBuilder,
    TOONParser,

    # Enums
    TOONRoute,
    GraphOperation,
    VectorOperation,
    EntitySource,

    # Config models
    GraphQueryConfig,
    VectorQueryConfig,
    VectorFilters,
    DateRange,
    ClarificationConfig,
    ExtractedEntity,

    # Guardrails
    TOONGuardrails,

    # Chain-of-Thought (visible reasoning)
    ThinkingStepType,
    ThinkingStep,
    ChainOfThought
)

# SLM Client
from .slm_client import (
    SLMClient,
    SLMConfig,
    get_slm_client,
    initialize_slm_client
)

# TOON Executor
from .toon_executor import (
    TOONExecutor,
    GraphExecutor,
    VectorExecutor,
    get_toon_executor,
    initialize_toon_executor
)

# Tenant Schema
from .tenant_schema import (
    TenantSchema,
    TenantSchemaProvider,
    get_schema_provider,
    initialize_schema_provider
)

# History Manager
from .history_manager import (
    ConversationTurn,
    ConversationHistory,
    HistoryManager,
    ReferencePatterns,
    get_history_manager,
    initialize_history_manager
)

# Main Router
from .router import (
    SLMRouter,
    SLMRouterConfig,
    get_slm_router,
    initialize_slm_router
)

# Continuous Learning (automated fine-tuning)
from .continuous_learning import (
    ContinuousLearningService,
    LearningConfig,
    LearningState,
    get_learning_service,
    set_learning_service,
    initialize_continuous_learning
)

__all__ = [
    # Main entry points
    "SLMRouter",
    "get_slm_router",
    "initialize_slm_router",
    "SLMRouterConfig",

    # TOON Schema
    "TOONPlan",
    "TOONExecutionResult",
    "TOONPlanBuilder",
    "TOONParser",
    "TOONRoute",
    "TOONGuardrails",

    # Operations
    "GraphOperation",
    "VectorOperation",
    "EntitySource",

    # Config models
    "GraphQueryConfig",
    "VectorQueryConfig",
    "VectorFilters",
    "DateRange",
    "ClarificationConfig",
    "ExtractedEntity",

    # Chain-of-Thought (visible reasoning)
    "ThinkingStepType",
    "ThinkingStep",
    "ChainOfThought",

    # SLM Client
    "SLMClient",
    "SLMConfig",
    "get_slm_client",
    "initialize_slm_client",

    # Executor
    "TOONExecutor",
    "GraphExecutor",
    "VectorExecutor",
    "get_toon_executor",
    "initialize_toon_executor",

    # Schema
    "TenantSchema",
    "TenantSchemaProvider",
    "get_schema_provider",
    "initialize_schema_provider",

    # History
    "ConversationTurn",
    "ConversationHistory",
    "HistoryManager",
    "ReferencePatterns",
    "get_history_manager",
    "initialize_history_manager",

    # Continuous Learning
    "ContinuousLearningService",
    "LearningConfig",
    "LearningState",
    "get_learning_service",
    "set_learning_service",
    "initialize_continuous_learning",
]
