"""
Emma ReAct Agent — Analyze Domain Tool

Consolidates all 11 specialist agents into a single parametrized tool.
Instead of routing through separate graph nodes, the ReAct agent calls
`analyze_domain(domain="legal", question="...", context="...")` and gets
a focused domain-specific analysis.

Internally, this loads the specialist's system prompt and makes ONE
LLM call with the relevant context. The tool loop stays in the outer
ReAct loop — specialists don't have their own inner tool loops.
"""

import logging
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)

# Available domains for the analyze_domain tool
AVAILABLE_DOMAINS = [
    "legal", "labor", "fiscal", "contract", "compliance",
    "privacy", "realestate", "education", "general", "docgen",
]


async def _get_domain_prompt(domain: str) -> str:
    """Get the system prompt for a domain specialist from Langfuse."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    client = get_langfuse_prompt_client()
    prompt = await client.get_prompt(f"emma_domain_{domain}")
    return prompt.content


class AnalyzeDomainInput(BaseModel):
    """Input for domain-specific analysis."""
    domain: str = Field(
        description="Dominio de análisis: legal, labor, fiscal, contract, "
        "compliance, privacy, realestate, education, general, docgen."
    )
    question: str = Field(
        description="Pregunta específica para analizar en el contexto del dominio."
    )
    context: Optional[str] = Field(
        default=None,
        description="Contexto relevante ya recopilado (fragmentos de documentos, "
        "resultados de búsqueda anteriores). Si no se proporciona, "
        "el análisis se basa solo en la pregunta."
    )


class AnalyzeDomainTool(EmmaTool):
    """Domain-specific analysis by specialized prompts.

    Replaces the 11 individual specialist graph nodes with a single
    parametrized tool. The ReAct agent decides which domain to invoke
    and provides the context it has already gathered.
    """

    @property
    def name(self) -> str:
        return "analyze_domain"

    @property
    def description(self) -> str:
        return (
            "Análisis especializado por dominio: legal, laboral, fiscal, contractual, "
            "compliance, privacidad, inmobiliario, educación o generación de documentos. "
            "Proporciona el contexto relevante que ya hayas recopilado para un análisis más preciso."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return AnalyzeDomainInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        domain = arguments["domain"].lower().strip()
        question = arguments["question"]
        provided_context = arguments.get("context", "") or ""

        # Validate domain
        if domain not in AVAILABLE_DOMAINS:
            return ToolResult.from_error(
                f"Dominio desconocido: '{domain}'",
                suggestion=f"Dominios disponibles: {', '.join(AVAILABLE_DOMAINS)}",
            )

        # Build messages
        system_prompt = await _get_domain_prompt(domain)
        sector = context.get("sector", "")
        if sector:
            system_prompt += f"\n\nSector activo: {sector}"

        user_content = f"**Pregunta**: {question}"
        if provided_context:
            user_content = f"**Contexto disponible**:\n{provided_context[:6000]}\n\n{user_content}"

        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.agents.llm_models import get_chat_model
            model = get_chat_model().bind(max_tokens=2048)
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ])
        except Exception as e:
            logger.error(f"analyze_domain({domain}) LLM call failed: {e}")
            return ToolResult.from_error(
                f"Error en análisis de dominio '{domain}': {e}",
                suggestion="Intenta reformular la pregunta o usar un dominio diferente.",
            )

        output = response.content or ""

        # Strip thinking tags if present
        if "<think>" in output:
            import re
            output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()

        if not output:
            return ToolResult.from_error(
                f"El análisis de dominio '{domain}' no produjo resultados.",
                suggestion="Proporciona más contexto o reformula la pregunta.",
            )

        return ToolResult(
            output=output,
            data={"domain": domain},
        )
