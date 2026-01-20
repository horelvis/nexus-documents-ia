"""
Privacy Agent - GDPR/LOPDGDD Specialist

Specialized agent for analyzing privacy policies, consent clauses,
data processing agreements, and GDPR/LOPDGDD compliance.

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
DEFAULT_PRIVACY_MSG = """You are an expert in data protection law (GDPR and LOPDGDD).
Your role is to analyze privacy policies, consent mechanisms, and data processing compliance.
Always cite specific articles (Art. X RGPD, Art. Y LOPDGDD BOE-A-2018-16673).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_privacy_agent(
    llm_cfg: dict,
    name: str = "PrivacyAgent",
) -> Assistant:
    """
    Create a privacy/data protection specialist agent using Qwen-Agent.

    This agent excels at analyzing privacy policies, consent clauses,
    data processing agreements, and GDPR/LOPDGDD compliance.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for privacy compliance analysis
    """
    system_message = get_agent_system_message("PrivacyAgent", DEFAULT_PRIVACY_MSG)
    logger.debug(f"Creating PrivacyAgent: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=system_message,
        function_list=[
            'analyze_document',
            'extract_entities',
            'hybrid_search',
            'keyword_search',
            'get_document_content',
            'rag_answer',
        ],
    )
