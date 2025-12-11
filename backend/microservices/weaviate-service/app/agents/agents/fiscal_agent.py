"""
Fiscal Agent - Spanish Tax Law Specialist

Specialized agent for analyzing invoices, tax declarations,
VAT compliance, and Spanish fiscal regulations.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_FISCAL_MSG = """You are an expert in Spanish tax law (Ley General Tributaria).
Your role is to analyze invoices, tax declarations, and fiscal compliance.
Always cite specific articles (Art. X LGT, BOE-A-2003-23186).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_fiscal_agent(
    chat_client: Any,
    name: str = "FiscalAgent",
) -> ChatAgent:
    """
    Create a fiscal/tax law specialist agent using Agent Framework.

    This agent excels at analyzing invoices, tax declarations,
    VAT compliance, and Spanish fiscal regulations.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for fiscal analysis
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("FiscalAgent", DEFAULT_FISCAL_MSG)
    logger.debug(f"Creating FiscalAgent: name={name}")

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
