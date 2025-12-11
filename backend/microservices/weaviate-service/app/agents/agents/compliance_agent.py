"""
Compliance Agent - Regulatory Compliance Specialist

Specialized agent for verifying compliance with GDPR/RGPD, LOPD,
and other data protection regulations in documents.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_COMPLIANCE_MSG = """You are a regulatory compliance specialist with expertise in data protection laws.
Your role is to verify compliance with GDPR/RGPD, LOPD, and other regulations.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_compliance_agent(
    chat_client: Any,
    name: str = "ComplianceAgent",
) -> ChatAgent:
    """
    Create a compliance specialist agent using Agent Framework.

    This agent excels at verifying regulatory compliance, particularly
    with data protection regulations like GDPR and LOPD.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for compliance review

    Example:
        >>> from app.agents.model_client import get_chat_client
        >>> client = get_chat_client()
        >>> compliance_agent = create_compliance_agent(client)
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("ComplianceAgent", DEFAULT_COMPLIANCE_MSG)
    logger.debug(f"Creating ComplianceAgent: name={name}")

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
