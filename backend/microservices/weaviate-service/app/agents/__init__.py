"""
Microsoft Agent Framework Integration for NexusDocs360

This module provides multi-agent orchestration using Microsoft's Agent Framework,
enabling advanced document intelligence capabilities:

- **Sequential workflows** (SequentialBuilder): Step-by-step processing
  Example: Search -> Analyze -> Summarize

- **GroupChat** (GroupBuilder): Coordinator dynamically selects which agent responds
  Example: Complex queries requiring different specialists

- **Swarm patterns** (SwarmBuilder): Explicit delegation between agents
  Example: Triage -> Specialist -> Summarizer

The agents use the existing RAG pipeline as tools, providing a higher-level
orchestration layer on top of the document intelligence capabilities.

## Quick Start

```python
from app.agents import get_orchestrator, WorkflowType

# Get the orchestrator singleton
orchestrator = get_orchestrator()

# Execute a query (auto-selects workflow)
result = await orchestrator.execute(
    query="What are the payment terms in the contract?",
    tenant_id="tenant-123"
)

# Or specify a workflow
result = await orchestrator.execute(
    query="Analyze this contract for compliance",
    tenant_id="tenant-123",
    workflow_type=WorkflowType.SWARM
)

# Stream responses
async for message in orchestrator.execute_stream(query, tenant_id):
    print(f"{message['agent']}: {message['content']}")
```

## LLM Provider Support

Supports multiple LLM providers via configuration:
- vLLM (PRIMARY): High-throughput GPU inference with Ministral 14B
- OpenAI (fallback): GPT-4o, GPT-4o-mini

Set via environment variable: LLM_PROVIDER=vllm|openai

FRAMEWORK: Microsoft Agent Framework
"""

# Configuration
from .config import AgentConfig, agent_config, WorkflowType, AgentType

# Model Client - Multi-provider support
from .model_client import (
    get_chat_client,
    get_available_providers,
    get_provider_info,
    ModelClientError,
)

# Orchestrator - Main entry point
from .orchestrator import (
    AgentOrchestrator,
    AgentResponse,
    get_orchestrator,
    reset_orchestrator,
)

# Analysis Flow - Document analysis using SwarmWorkflow native (RECOMMENDED)
from .flows import DocumentAnalysisFlow, AnalysisResult, get_document_analysis_flow

# Planning Flow - OpenManus-style orchestration (LEGACY)
from .flows import PlanningFlow, FlowResult, get_planning_flow
from .tools.planning_tool import PlanningTool, PlanStepStatus, get_planning_tool

# Handoff Workflow - Multi-agent with HandoffBuilder
from .handoff_workflow import (
    EmmaHandoffWorkflow,
    HandoffWorkflowResult,
    get_emma_handoff_workflow,
    initialize_handoff_workflow,
    classify_query_for_agent,      # Regex fallback
    classify_agent_with_llm,       # LLM-based classification (preferred)
)

# Emma Coordinator - RECOMMENDED: Main agent with subagent delegation via .as_tool()
from .emma_coordinator import (
    EmmaCoordinator,
    EmmaCoordinatorResult,
    get_emma_coordinator,
    initialize_emma_coordinator,
    reset_emma_coordinator,
)

__all__ = [
    # Configuration
    "AgentConfig",
    "agent_config",
    "WorkflowType",
    "AgentType",
    # Model Client
    "get_chat_client",
    "get_available_providers",
    "get_provider_info",
    "ModelClientError",
    # Orchestrator
    "AgentOrchestrator",
    "AgentResponse",
    "get_orchestrator",
    "reset_orchestrator",
    # Document Analysis Flow (SwarmWorkflow native - RECOMMENDED)
    "DocumentAnalysisFlow",
    "AnalysisResult",
    "get_document_analysis_flow",
    # Planning Flow (OpenManus-style - LEGACY)
    "PlanningFlow",
    "FlowResult",
    "get_planning_flow",
    "PlanningTool",
    "PlanStepStatus",
    "get_planning_tool",
    # Handoff Workflow (Multi-agent)
    "EmmaHandoffWorkflow",
    "HandoffWorkflowResult",
    "get_emma_handoff_workflow",
    "initialize_handoff_workflow",
    # Emma Coordinator (RECOMMENDED - Main agent with .as_tool() delegation)
    "EmmaCoordinator",
    "EmmaCoordinatorResult",
    "get_emma_coordinator",
    "initialize_emma_coordinator",
    "reset_emma_coordinator",
]


# Lazy imports for sub-modules to avoid circular imports
def __getattr__(name):
    """Lazy load sub-modules on demand."""
    if name == "agents":
        from . import agents as _agents
        return _agents
    if name == "tools":
        from . import tools as _tools
        return _tools
    if name == "workflows":
        from . import workflows as _workflows
        return _workflows
    if name == "flows":
        from . import flows as _flows
        return _flows
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
