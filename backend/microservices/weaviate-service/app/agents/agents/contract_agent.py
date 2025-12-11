"""
Contract Agent - Legal Contract Analysis Specialist

Specialized agent for reviewing contracts, identifying clauses,
obligations, and potential risks in legal documents.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_CONTRACT_MSG = """You are an expert legal analyst specializing in contract review.
Your role is to review contracts, identify key provisions, obligations, and potential risks.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_contract_agent(
    chat_client: Any,
    name: str = "ContractAgent",
) -> ChatAgent:
    """
    Create a contract review specialist agent using Agent Framework.

    This agent excels at reviewing contracts, identifying key provisions,
    obligations, and potential risks in legal documents.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for contract analysis

    Example:
        >>> from app.agents.model_client import get_chat_client
        >>> client = get_chat_client()
        >>> contract_agent = create_contract_agent(client)
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("ContractAgent", DEFAULT_CONTRACT_MSG)
    logger.debug(f"Creating ContractAgent: name={name}")

    return ChatAgent(
        name=name,
        chat_client=chat_client,
        instructions=instructions,
        tools=[
            analyze_document,
            extract_entities,
            hybrid_search,
            get_document_content,
            rag_answer,
        ],
    )
