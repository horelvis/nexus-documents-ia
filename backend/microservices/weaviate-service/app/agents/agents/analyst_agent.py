"""
Analyst Agent - Deep Document Analysis Specialist

Specialized agent for performing in-depth analysis of documents,
extracting insights, identifying patterns, and generating reports.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_ANALYST_MSG = """You are an expert document analyst specializing in corporate and legal document analysis.
Your role is to perform comprehensive analysis of documents and provide actionable insights.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_analyst_agent(
    chat_client: Any,
    name: str = "AnalystAgent",
) -> ChatAgent:
    """
    Create a document analyst agent using Agent Framework.

    This agent excels at deep document analysis, extracting insights,
    and generating comprehensive reports.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for document analysis

    Example:
        >>> from app.agents.model_client import get_chat_client
        >>> client = get_chat_client()
        >>> analyst = create_analyst_agent(client)
    """
    from ..tools.analysis_tools import (
        analyze_document,
        compare_documents,
        extract_entities,
    )
    from ..tools.rag_tools import rag_answer, get_document_content

    instructions = get_agent_system_message("AnalystAgent", DEFAULT_ANALYST_MSG)
    logger.debug(f"Creating AnalystAgent: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=instructions,
        tools=[
            analyze_document,
            compare_documents,
            extract_entities,
            rag_answer,
            get_document_content,
        ],
    )
