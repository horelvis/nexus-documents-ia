"""
Search Agent - Document Search Specialist

Specialized agent for finding and retrieving relevant documents
using various search strategies (semantic, keyword, hybrid).

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_SEARCH_MSG = """You are a document search specialist with expertise in information retrieval.
Your role is to find relevant documents using semantic, keyword, or hybrid search.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_search_agent(
    chat_client: Any,
    name: str = "SearchAgent",
) -> ChatAgent:
    """
    Create a search specialist agent using Agent Framework.

    This agent excels at finding relevant documents using the appropriate
    search strategy based on the query characteristics.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for document search

    Example:
        >>> from app.agents.model_client import get_chat_client
        >>> client = get_chat_client()
        >>> search_agent = create_search_agent(client)
    """
    from ..tools.search_tools import (
        semantic_search,
        hybrid_search,
        keyword_search,
    )

    instructions = get_agent_system_message("SearchAgent", DEFAULT_SEARCH_MSG)
    logger.debug(f"Creating SearchAgent: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=instructions,
        tools=[semantic_search, hybrid_search, keyword_search],
    )


def create_search_agent_with_metadata(
    chat_client: Any,
    name: str = "SearchAgent",
) -> ChatAgent:
    """
    Create a search agent with metadata filtering capabilities.

    Extended version that includes the search_by_metadata tool
    for filtering documents by type, date, tags, etc.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent with metadata filtering
    """
    from ..tools.search_tools import (
        semantic_search,
        hybrid_search,
        keyword_search,
        search_by_metadata,
    )

    base_instructions = get_agent_system_message("SearchAgent", DEFAULT_SEARCH_MSG)
    extended_instructions = base_instructions + """

Additional capability: You can also filter documents by metadata:
- search_by_metadata: Filter by document type, date range, or tags without text query

Use this when the user wants to browse documents by category or time period.
"""

    logger.debug(f"Creating SearchAgent with metadata: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=extended_instructions,
        tools=[semantic_search, hybrid_search, keyword_search, search_by_metadata],
    )


def create_search_agent_with_sharing(
    chat_client: Any,
    name: str = "SearchAgent",
) -> ChatAgent:
    """
    Create a search agent with sharing insights capabilities.

    Extended version that includes tools for querying document sharing
    and site guest information from PostgreSQL via REST API.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent with sharing insights tools
    """
    from ..tools.search_tools import (
        semantic_search,
        hybrid_search,
        keyword_search,
        search_by_metadata,
    )
    from ..tools.sharing_insights_tools import (
        query_recent_shares,
        query_shares_to_recipient,
        query_sharing_statistics,
        query_site_guests,
        query_guest_documents,
        query_guest_activity,
        query_guest_statistics,
        query_sharing_overview,
    )

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

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=extended_instructions,
        tools=[
            # Search tools
            semantic_search,
            hybrid_search,
            keyword_search,
            search_by_metadata,
            # Sharing insights tools
            query_recent_shares,
            query_shares_to_recipient,
            query_sharing_statistics,
            query_site_guests,
            query_guest_documents,
            query_guest_activity,
            query_guest_statistics,
            query_sharing_overview,
        ],
    )
