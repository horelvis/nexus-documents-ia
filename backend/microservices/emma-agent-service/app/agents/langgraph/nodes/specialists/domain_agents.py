"""
Domain Specialist Agent Nodes (Factory)

Activates 6 specialist agents that were previously placeholders:
- LaborAgent, FiscalAgent, ContractAgent
- ComplianceAgent, RealEstateAgent, EducationAgent

Each agent loads its system prompt from emma_prompts.yaml and receives
shared tools (document_search, document_summary, structural_query) plus
an optional domain-filtered boe_search tool for legislation lookups.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ...state import RAGState
from .base import create_specialist_node
from .general import general_tools

logger = logging.getLogger(__name__)

# Cached YAML config
_YAML_CONFIG: Optional[Dict[str, Any]] = None

# Agent name → YAML key mapping
AGENT_YAML_MAP = {
    "labor_agent": "LaborAgent",
    "fiscal_agent": "FiscalAgent",
    "contract_agent": "ContractAgent",
    "compliance_agent": "ComplianceAgent",
    "realestate_agent": "RealEstateAgent",
    "education_agent": "EducationAgent",
}

# Domain filter for BOE search (None = no BOE tool, cross-domain agent)
AGENT_BOE_DOMAIN = {
    "labor_agent": "labor",
    "fiscal_agent": "fiscal",
    "realestate_agent": "civil",
    "contract_agent": None,
    "compliance_agent": None,
    "education_agent": None,
}


def _load_yaml_config() -> Dict[str, Any]:
    """Load and cache emma_prompts.yaml."""
    global _YAML_CONFIG
    if _YAML_CONFIG is not None:
        return _YAML_CONFIG

    config_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "config" / "prompts" / "emma_prompts.yaml"
    )
    try:
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            _YAML_CONFIG = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load emma_prompts.yaml: {e}")
        _YAML_CONFIG = {}
    return _YAML_CONFIG


def _get_yaml_prompt(agent_name: str) -> str:
    """Load system_message from autogen_agents[YamlName] in emma_prompts.yaml."""
    yaml_key = AGENT_YAML_MAP.get(agent_name)
    if not yaml_key:
        return ""

    config = _load_yaml_config()
    agents = config.get("autogen_agents", {})
    agent_config = agents.get(yaml_key, {})
    prompt = agent_config.get("system_message", "")
    # Truncate to ~2000 chars (consistent with DynamicPromptLoader)
    return prompt[:2000] if prompt else ""


# BOE search tool schema (reused from legal.py pattern)
class BOESearchInput(BaseModel):
    """Input for domain-filtered BOE legislation search."""
    query: str = Field(description="Natural language query about Spanish legislation")
    limit: int = Field(default=5, description="Maximum number of results")


def _make_boe_tool(domain_filter: str) -> StructuredTool:
    """Create a BOE search tool pre-filtered to a specific legal domain."""

    async def _boe_search(query: str, limit: int = 5) -> str:
        try:
            from app.services.public_knowledge_service import public_knowledge_service

            if not public_knowledge_service._initialized:
                await public_knowledge_service.initialize()

            results = await public_knowledge_service.search(
                query=query,
                limit=limit,
                filters={"domain": domain_filter},
            )

            if not results:
                return f"No se encontraron resultados legislativos ({domain_filter}) para: '{query}'"

            formatted = [f"**Resultados BOE ({domain_filter})**: '{query}'\n"]
            for i, doc in enumerate(results, 1):
                title = doc.get("title", "Sin título")
                boe_id = doc.get("boe_id", "")
                content = doc.get("content", "")[:200]
                ref = f" ({boe_id})" if boe_id else ""
                formatted.append(f"{i}. **{title}**{ref}\n   {content}...\n")

            return "\n".join(formatted)
        except Exception as e:
            logger.error(f"BOE search ({domain_filter}) failed: {e}")
            return f"Error en búsqueda BOE: {str(e)}"

    return StructuredTool.from_function(
        coroutine=_boe_search,
        name="boe_search",
        description=f"Search Spanish legislation in the BOE database, filtered to '{domain_filter}' domain.",
        args_schema=BOESearchInput,
    )


def _get_tools(agent_name: str) -> list:
    """Get tools for a domain agent: general_tools + optional BOE search."""
    boe_domain = AGENT_BOE_DOMAIN.get(agent_name)
    if boe_domain:
        return list(general_tools) + [_make_boe_tool(boe_domain)]
    return list(general_tools)


def _create_domain_node(agent_name: str):
    """Create an async node function for a domain specialist agent."""

    async def _node(state: RAGState) -> Dict[str, Any]:
        prompt = _get_yaml_prompt(agent_name)
        if not prompt:
            logger.warning(f"⚠️ No YAML prompt for {agent_name}, falling back to general")
            from .general import general_node
            return await general_node(state)

        tools = _get_tools(agent_name)
        return await create_specialist_node(
            agent_name=agent_name,
            system_prompt=prompt,
            tools=tools,
            state=state,
        )

    _node.__name__ = f"{agent_name}_node"
    return _node


# Export the 6 domain agent nodes
labor_node = _create_domain_node("labor_agent")
fiscal_node = _create_domain_node("fiscal_agent")
contract_node = _create_domain_node("contract_agent")
compliance_node = _create_domain_node("compliance_agent")
realestate_node = _create_domain_node("realestate_agent")
education_node = _create_domain_node("education_agent")
