"""
Education Agent - Spanish Education Law Specialist

Specialized agent for analyzing educational regulations, school policies,
student rights, and compliance with LOMLOE/LOE.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_EDUCATION_MSG = """You are an expert in Spanish education law (LOMLOE/LOE).
Your role is to analyze educational regulations, school policies, and student rights.
Always cite specific articles (Art. X LOMLOE, BOE-A-2020-17264).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_education_agent(
    chat_client: Any,
    name: str = "EducationAgent",
) -> ChatAgent:
    """
    Create an education law specialist agent using Agent Framework.

    This agent excels at analyzing educational regulations, school policies,
    student rights, and compliance with LOMLOE/LOE.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for education law analysis
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("EducationAgent", DEFAULT_EDUCATION_MSG)
    logger.debug(f"Creating EducationAgent: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=instructions,
        tools=[
            analyze_document,
            extract_entities,
            hybrid_search,
            keyword_search,
            get_document_content,
            rag_answer,
        ],
    )
