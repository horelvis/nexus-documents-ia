"""
Contract Agent - Legal Contract Analysis Specialist

Specialized agent for reviewing contracts, identifying clauses,
obligations, and potential risks in legal documents.

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
DEFAULT_CONTRACT_MSG = """You are an expert legal analyst specializing in contract review.
Your role is to review contracts, identify key provisions, obligations, and potential risks.
Always include tenant_id in all tool calls. End with "TASK_COMPLETE" when done."""


def create_contract_agent(
    llm_cfg: dict,
    name: str = "ContractAgent",
) -> Assistant:
    """
    Create a contract review specialist agent using Qwen-Agent.

    This agent excels at reviewing contracts, identifying key provisions,
    obligations, and potential risks in legal documents.

    Args:
        llm_cfg: Qwen-Agent LLM configuration dict (from get_llm_config())
        name: Agent name for identification

    Returns:
        Configured Assistant for contract analysis

    Example:
        >>> from app.agents.model_client import get_llm_config
        >>> llm_cfg = get_llm_config()
        >>> contract_agent = create_contract_agent(llm_cfg)
    """
    system_message = get_agent_system_message("ContractAgent", DEFAULT_CONTRACT_MSG)
    logger.debug(f"Creating ContractAgent: name={name}")

    return Assistant(
        llm=llm_cfg,
        name=name,
        system_message=system_message,
        function_list=[
            'analyze_document',
            'extract_entities',
            'hybrid_search',
            'get_document_content',
            'rag_answer',
        ],
    )
