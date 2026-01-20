"""
Education Agent - Spanish Education Law Specialist

Specialized agent for analyzing educational regulations, school policies,
student rights, and compliance with LOMLOE/LOE.

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
DEFAULT_EDUCATION_MSG = """You are an expert in Spanish education law (LOMLOE/LOE).
Your role is to analyze educational regulations, school policies, and student rights.
Always cite specific articles (Art. X LOMLOE, BOE-A-2020-17264).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_education_agent(
    llm_cfg: dict,
    name: str = "EducationAgent",
) -> Assistant:
    """
    Create an education law specialist agent using Qwen-Agent.

    This agent excels at analyzing educational regulations, school policies,
    student rights, and compliance with LOMLOE/LOE.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for education law analysis
    """
    system_message = get_agent_system_message("EducationAgent", DEFAULT_EDUCATION_MSG)
    logger.debug(f"Creating EducationAgent: name={name}")

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
