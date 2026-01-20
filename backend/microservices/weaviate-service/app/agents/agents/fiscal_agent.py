"""
Fiscal Agent - Spanish Tax Law Specialist

Specialized agent for analyzing invoices, tax declarations,
VAT compliance, and Spanish fiscal regulations.

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
DEFAULT_FISCAL_MSG = """You are an expert in Spanish tax law (Ley General Tributaria).
Your role is to analyze invoices, tax declarations, and fiscal compliance.
Always cite specific articles (Art. X LGT, BOE-A-2003-23186).
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_fiscal_agent(
    llm_cfg: dict,
    name: str = "FiscalAgent",
) -> Assistant:
    """
    Create a fiscal/tax law specialist agent using Qwen-Agent.

    This agent excels at analyzing invoices, tax declarations,
    VAT compliance, and Spanish fiscal regulations.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for fiscal analysis
    """
    system_message = get_agent_system_message("FiscalAgent", DEFAULT_FISCAL_MSG)
    logger.debug(f"Creating FiscalAgent: name={name}")

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
