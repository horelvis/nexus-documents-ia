"""
Real Estate Agent - Spanish Property Law Specialist

Specialized agent for analyzing rental contracts, property sales,
mortgages, and compliance with Spanish real estate regulations (LAU).

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
DEFAULT_REAL_ESTATE_MSG = """You are an expert in Spanish real estate law (Ley de Arrendamientos Urbanos).
Your role is to analyze rental contracts, property sales, and mortgage documents.
Always cite specific articles (Art. X LAU, BOE-A-1994-26003).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_real_estate_agent(
    llm_cfg: dict,
    name: str = "RealEstateAgent",
) -> Assistant:
    """
    Create a real estate law specialist agent using Qwen-Agent.

    This agent excels at analyzing rental contracts, property sales,
    mortgages, and compliance with LAU and related regulations.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for real estate analysis
    """
    system_message = get_agent_system_message("RealEstateAgent", DEFAULT_REAL_ESTATE_MSG)
    logger.debug(f"Creating RealEstateAgent: name={name}")

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
