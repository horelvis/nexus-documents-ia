"""
Privacy Agent - GDPR/LOPDGDD Specialist

Specialized agent for analyzing privacy policies, consent clauses,
data processing agreements, and GDPR/LOPDGDD compliance.

System message is loaded from YAML configuration (emma_prompts.yaml).

FRAMEWORK: Microsoft Agent Framework
"""

import logging
from typing import Any

from agent_framework import ChatAgent

from app.services.rag.prompt_loader import get_agent_system_message

logger = logging.getLogger(__name__)

# Fallback message if YAML config not available
DEFAULT_PRIVACY_MSG = """You are an expert in data protection law (GDPR and LOPDGDD).
Your role is to analyze privacy policies, consent mechanisms, and data processing compliance.
Always cite specific articles (Art. X RGPD, Art. Y LOPDGDD BOE-A-2018-16673).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_privacy_agent(
    chat_client: Any,
    name: str = "PrivacyAgent",
) -> ChatAgent:
    """
    Create a privacy/data protection specialist agent using Agent Framework.

    This agent excels at analyzing privacy policies, consent clauses,
    data processing agreements, and GDPR/LOPDGDD compliance.

    Args:
        chat_client: Agent Framework chat client (from get_chat_client())
        name: Agent name for identification

    Returns:
        Configured ChatAgent for privacy compliance analysis
    """
    from ..tools.analysis_tools import analyze_document, extract_entities
    from ..tools.search_tools import hybrid_search, keyword_search
    from ..tools.rag_tools import get_document_content, rag_answer

    instructions = get_agent_system_message("PrivacyAgent", DEFAULT_PRIVACY_MSG)
    logger.debug(f"Creating PrivacyAgent: name={name}")

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
