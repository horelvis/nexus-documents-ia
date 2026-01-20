"""
Workflow Orchestration Patterns for Multi-Agent Systems

This module provides three workflow patterns for orchestrating
multi-agent interactions:

1. SequentialWorkflow:
   Agents take turns in a fixed order. Good for pipelines like:
   Search -> Analyze -> Summarize

2. GroupChatWorkflow:
   A coordinator dynamically selects which agent should respond based on
   the conversation context. Good for complex queries requiring
   different specialists.

3. SwarmWorkflow (RECOMMENDED):
   Coordinator routes to specialists using handoffs.
   Good for triage patterns where a router distributes work.

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework builder patterns
- Now uses Qwen-Agent's Assistant class with our orchestration patterns
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
