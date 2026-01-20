"""
Search Agent - Document Search Specialist

Specialized agent for finding and retrieving relevant documents
using various search strategies (semantic, keyword, hybrid).

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Qwen-Agent
Reference: https://github.com/QwenLM/Qwen-Agent

MIGRATION NOTE:
- Migrated from MS Agent Framework ChatAgent pattern
- Uses Assistant class with function_list (tool names as strings)
"""

import logging
from typing import Any

from qwen_agent.agents import Assistant

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_SEARCH_MSG = """You are a document search specialist with expertise in information retrieval.
Your role is to find relevant documents using semantic, keyword, or hybrid search.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_search_agent(
    llm_cfg: dict,
    name: str = "SearchAgent",
) -> Assistant:
    """
    Create a search specialist agent using Qwen-Agent.

    This agent excels at finding relevant documents using the appropriate
    search strategy based on the query characteristics.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for document search

    Example:
        >>> from app.agents.model_client import get_llm_config
        >>> llm_cfg = get_llm_config()
        >>> search_agent = create_search_agent(llm_cfg)
    """
    system_message = get_agent_system_message("SearchAgent", DEFAULT_SEARCH_MSG)
    logger.debug(f"Creating SearchAgent: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=system_message,
        function_list=[
            'nexus_semantic_search',
            'nexus_hybrid_search',
            'nexus_keyword_search',
        ],
    )


def create_search_agent_with_metadata(
    llm_cfg: dict,
    name: str = "SearchAgent",
) -> Assistant:
    """
    Create a search agent with metadata filtering capabilities.

    Extended version that includes the search_by_metadata tool
    for filtering documents by type, date, tags, etc.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant with metadata filtering
    """
    base_instructions = get_agent_system_message("SearchAgent", DEFAULT_SEARCH_MSG)
    extended_instructions = base_instructions + """

Additional capability: You can also filter documents by metadata:
- search_by_metadata: Filter by document type, date range, or tags without text query

Use this when the user wants to browse documents by category or time period.
"""

    logger.debug(f"Creating SearchAgent with metadata: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=extended_instructions,
        function_list=[
            'nexus_semantic_search',
            'nexus_hybrid_search',
            'nexus_keyword_search',
            'nexus_search_by_metadata',
        ],
    )


def create_search_agent_with_sharing(
    llm_cfg: dict,
    name: str = "SearchAgent",
) -> Assistant:
    """
    Create a search agent with sharing insights capabilities.

    Extended version that includes tools for querying document sharing
    and site guest information from PostgreSQL via REST API.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant with sharing insights tools
    """
    base_instructions = get_agent_system_message("SearchAgent", DEFAULT_SEARCH_MSG)
    extended_instructions = base_instructions + """

Additional capabilities:

1. Metadata filtering:
- search_by_metadata: Filter documents by type, date range, or tags

2. Sharing insights (queries PostgreSQL via REST API):
- query_recent_shares: Get recently shared documents
- query_shares_to_recipient: Find shares to a specific email
- query_sharing_statistics: Get sharing statistics
- query_site_guests: List external portal guests
- query_guest_documents: See what a guest can access
- query_guest_activity: View guest activity logs
- query_guest_statistics: Get guest statistics summary
- query_sharing_overview: High-level sharing overview

Use sharing tools when users ask about:
- "What have I shared?"
- "Who has access to...?"
- "List my external guests"
- "What can guest@example.com see?"
"""

    logger.debug(f"Creating SearchAgent with sharing insights: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=extended_instructions,
        function_list=[
            # Search tools (nexus_ prefix to avoid Qwen-Agent built-in conflicts)
            'nexus_semantic_search',
            'nexus_hybrid_search',
            'nexus_keyword_search',
            'nexus_search_by_metadata',
            # Sharing insights tools
            'query_recent_shares',
            'query_shares_to_recipient',
            'query_sharing_statistics',
            'query_site_guests',
            'query_guest_documents',
            'query_guest_activity',
            'query_guest_statistics',
            'query_sharing_overview',
        ],
    )
