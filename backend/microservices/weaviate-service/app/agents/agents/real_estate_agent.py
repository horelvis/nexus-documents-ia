"""
Real Estate Agent - Spanish Property Law Specialist

Specialized agent for analyzing rental contracts, property sales,
mortgages, and compliance with Spanish real estate regulations (LAU).

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_REAL_ESTATE_MSG = """You are an expert in Spanish real estate law (Ley de Arrendamientos Urbanos).
Your role is to analyze rental contracts, property sales, and mortgage documents.
Always cite specific articles (Art. X LAU, BOE-A-1994-26003).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_real_estate_agent(
    chat_client: Any,
    name: str = "RealEstateAgent",
) -> ChatAgent:
    """
    Create a real estate law specialist agent using Agent Framework.

    This agent excels at analyzing rental contracts, property sales,
    mortgages, and compliance with LAU and related regulations.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for real estate analysis
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("RealEstateAgent", DEFAULT_REAL_ESTATE_MSG)
    logger.debug(f"Creating RealEstateAgent: name={name}")

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
