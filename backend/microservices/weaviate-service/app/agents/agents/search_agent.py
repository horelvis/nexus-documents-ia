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
