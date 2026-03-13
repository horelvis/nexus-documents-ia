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
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)

# Domain → YAML key mapping (same as domain_agents.py)
DOMAIN_PROMPT_MAP = {
    "legal": "LegalAgent",
    "labor": "LaborAgent",
    "fiscal": "FiscalAgent",
    "contract": "ContractAgent",
    "compliance": "ComplianceAgent",
    "privacy": "PrivacyAgent",
    "realestate": "RealEstateAgent",
    "education": "EducationAgent",
    "general": "GeneralAgent",
    "docgen": "DocGenAgent",
}

AVAILABLE_DOMAINS = list(DOMAIN_PROMPT_MAP.keys())

# Inline fallback prompts for the most common domains
DOMAIN_FALLBACK_PROMPTS = {
    "legal": (
        "Eres un experto en legislación española y derecho. "
        "Analiza la consulta citando artículos, leyes (BOE) y normativas aplicables. "
        "Distingue entre normativa estatal, autonómica y europea."
    ),
    "labor": (
        "Eres un experto en derecho laboral español. "
        "Analiza consultas sobre Estatuto de Trabajadores, convenios colectivos, "
        "despidos, contratos laborales, prestaciones y Seguridad Social."
    ),
    "fiscal": (
        "Eres un experto en derecho tributario y fiscal español. "
        "Analiza consultas sobre impuestos (IRPF, IS, IVA), obligaciones tributarias, "
        "deducciones, y normativa de la Agencia Tributaria."
    ),
    "contract": (
        "Eres un experto en análisis contractual. "
        "Revisa cláusulas, identifica riesgos, verifica cumplimiento legal, "
        "y sugiere mejoras en contratos y acuerdos."
    ),
    "compliance": (
        "Eres un experto en compliance y normativa empresarial. "
        "Analiza cumplimiento regulatorio, blanqueo de capitales, "
        "gobernanza corporativa y gestión de riesgos."
    ),
    "privacy": (
        "Eres un experto en protección de datos y privacidad. "
        "Analiza consultas sobre RGPD, LOPDGDD, derechos ARCO, "
        "evaluaciones de impacto y transferencias internacionales."
    ),
    "general": (
        "Eres un experto en gestión documental empresarial. "
        "Analiza documentos, extrae información clave y proporciona "
        "resúmenes claros y estructurados."
    ),
    "docgen": (
        "Eres un experto en generación de documentos empresariales. "
        "Genera borradores de contratos, informes, cartas y otros documentos "
        "siguiendo la normativa aplicable. Usa [PLACEHOLDER] para datos faltantes."
    ),
}

# Cached YAML prompts
_yaml_prompts_cache: Optional[Dict[str, Any]] = None


def _load_specialist_prompts() -> Dict[str, Any]:
    """Load specialist prompts from emma_prompts.yaml (cached)."""
    global _yaml_prompts_cache
    if _yaml_prompts_cache is not None:
        return _yaml_prompts_cache

    candidates = [
        Path("/app/config/prompts/emma_prompts.yaml"),
        Path(__file__).parent.parent.parent.parent.parent / "config" / "prompts" / "emma_prompts.yaml",
    ]

    for p in candidates:
        if p.exists():
            try:
                import yaml
                with open(p, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                _yaml_prompts_cache = data.get("analysis_agents", {})
                return _yaml_prompts_cache
            except Exception as e:
                logger.warning(f"Failed to load specialist prompts: {e}")

    _yaml_prompts_cache = {}
    return _yaml_prompts_cache


def _get_domain_prompt(domain: str) -> str:
    """Get the system prompt for a domain specialist."""
    # Try YAML first
    yaml_prompts = _load_specialist_prompts()
    yaml_key = DOMAIN_PROMPT_MAP.get(domain, "")
    if yaml_key and yaml_key in yaml_prompts:
        agent_config = yaml_prompts[yaml_key]
        if isinstance(agent_config, dict):
            return agent_config.get("system_prompt", agent_config.get("prompt", ""))
        return str(agent_config)

    # Fallback to inline prompts
    return DOMAIN_FALLBACK_PROMPTS.get(domain, DOMAIN_FALLBACK_PROMPTS["general"])


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
        from app.agents.llm_router import get_llm_router

        domain = arguments["domain"].lower().strip()
        question = arguments["question"]
        provided_context = arguments.get("context", "") or ""

        # Validate domain
        if domain not in DOMAIN_PROMPT_MAP:
            return ToolResult.from_error(
                f"Dominio desconocido: '{domain}'",
                suggestion=f"Dominios disponibles: {', '.join(AVAILABLE_DOMAINS)}",
            )

        # Build messages
        system_prompt = _get_domain_prompt(domain)
        sector = context.get("sector", "")
        if sector:
            system_prompt += f"\n\nSector activo: {sector}"

        user_content = f"**Pregunta**: {question}"
        if provided_context:
            user_content = f"**Contexto disponible**:\n{provided_context[:6000]}\n\n{user_content}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            from app.agents.llm_client import ModelRole
            router = await get_llm_router()
            response = await router.chat(messages=messages, max_tokens=2048, role=ModelRole.CHAT)
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
