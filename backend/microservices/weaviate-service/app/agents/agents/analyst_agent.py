"""
Analyst Agent - Deep Document Analysis Specialist

Specialized agent for performing in-depth analysis of documents,
extracting insights, identifying patterns, and generating reports.

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
DEFAULT_ANALYST_MSG = """You are an expert document analyst specializing in corporate and legal document analysis.
Your role is to perform comprehensive analysis of documents and provide actionable insights.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_analyst_agent(
    llm_cfg: dict,
    name: str = "AnalystAgent",
) -> Assistant:
    """
    Create a document analyst agent using Qwen-Agent.

    This agent excels at deep document analysis, extracting insights,
    and generating comprehensive reports.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for document analysis

    Example:
        >>> from app.agents.model_client import get_llm_config
        >>> llm_cfg = get_llm_config()
        >>> analyst = create_analyst_agent(llm_cfg)
    """
    system_message = get_agent_system_message("AnalystAgent", DEFAULT_ANALYST_MSG)
    logger.debug(f"Creating AnalystAgent: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=system_message,
        function_list=[
            'analyze_document',
            'compare_documents',
            'extract_entities',
            'rag_answer',
            'get_document_content',
        ],
    )
