"""
Compliance Agent - Regulatory Compliance Specialist

Specialized agent for verifying compliance with GDPR/RGPD, LOPD,
and other data protection regulations in documents.

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
DEFAULT_COMPLIANCE_MSG = """You are a regulatory compliance specialist with expertise in data protection laws.
Your role is to verify compliance with GDPR/RGPD, LOPD, and other regulations.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_compliance_agent(
    llm_cfg: dict,
    name: str = "ComplianceAgent",
) -> Assistant:
    """
    Create a compliance specialist agent using Qwen-Agent.

    This agent excels at verifying regulatory compliance, particularly
    with data protection regulations like GDPR and LOPD.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for compliance review

    Example:
        >>> from app.agents.model_client import get_llm_config
        >>> llm_cfg = get_llm_config()
        >>> compliance_agent = create_compliance_agent(llm_cfg)
    """
    system_message = get_agent_system_message("ComplianceAgent", DEFAULT_COMPLIANCE_MSG)
    logger.debug(f"Creating ComplianceAgent: name={name}")

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
