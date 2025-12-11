"""
Workflow Orchestration Patterns for Agent Framework

This module provides three workflow patterns for orchestrating
multi-agent interactions:

1. SequentialWorkflow (SequentialBuilder):
   Agents take turns in a fixed order. Good for pipelines like:
   Search -> Analyze -> Summarize

2. GroupChatWorkflow (GroupBuilder with Coordinator):
   A coordinator dynamically selects which agent should respond based on
   the conversation context. Good for complex queries requiring
   different specialists.

3. SwarmWorkflow (HandoffBuilder - RECOMMENDED):
   Coordinator routes to specialists using native handoffs.
   Good for triage patterns where a router distributes work.
   Uses Microsoft Agent Framework's HandoffBuilder for proper handoff orchestration.

FRAMEWORK: Microsoft Agent Framework
Reference: https://github.com/microsoft/agent-framework
"""

from .sequential import (
    SequentialWorkflow,
    WorkflowResult,
    create_analysis_pipeline,
    create_contract_review_pipeline,
)
from .group_chat import (
    GroupChatWorkflow,
    GroupChatResult,
    create_specialist_group,
    create_search_and_summarize_group,
)
from .swarm import (
    SwarmWorkflow,
    SwarmResult,
    create_document_swarm,
    create_simple_swarm,
)

__all__ = [
    # Workflow classes
    "SequentialWorkflow",
    "GroupChatWorkflow",
    "SwarmWorkflow",
    # Result types
    "WorkflowResult",
    "GroupChatResult",
    "SwarmResult",
    # Pre-configured workflows
    "create_analysis_pipeline",
    "create_contract_review_pipeline",
    "create_specialist_group",
    "create_search_and_summarize_group",
    "create_document_swarm",
    "create_simple_swarm",
]
