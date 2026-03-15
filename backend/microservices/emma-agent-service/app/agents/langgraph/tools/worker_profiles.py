"""
Swarm Worker Profiles — Typed SubAgent Definitions

Each worker profile defines a specialized mini-agent with its own:
- System prompt (domain-specific instructions)
- Tool set (only relevant tools)
- Model role (PLANNER for fast tasks, CHAT for quality analysis)
- Max steps (bounded by task complexity)
- Langfuse prompt key (for dynamic prompt management)

The decompose node assigns a profile to each sub-task based on its
focus category. The swarm_worker node dispatches using the profile
instead of a generic prompt.

Inspired by Deep Agents SubAgentMiddleware pattern where each subagent
has {name, description, system_prompt, tools}, but implemented natively
within LangGraph's Send() fan-out architecture.

Usage:
    profile = get_worker_profile("document_search")
    system_prompt = await profile.resolve_prompt()
    model_role = profile.model_role
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.agents.llm_types import ModelRole

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerProfile:
    """Typed configuration for a Swarm worker specialization.

    Each focus category maps to one profile that determines how the
    worker behaves: what prompt it uses, which tools it prefers,
    what model role, and how many steps it can take.

    Attributes:
        name: Human-readable profile name (for logging/SSE)
        focus: Focus category key (matches decompose output)
        system_prompt: Default system prompt (Langfuse override available)
        tool_names: Preferred tools for this profile
        model_role: PLANNER (fast, tool-calling) or CHAT (quality generation)
        max_steps: Maximum ReAct iterations for this worker type
        langfuse_prompt_key: Key for dynamic prompt override via Langfuse
    """
    name: str
    focus: str
    system_prompt: str
    tool_names: List[str] = field(default_factory=list)
    model_role: ModelRole = ModelRole.PLANNER
    max_steps: int = 2
    langfuse_prompt_key: Optional[str] = None

    async def resolve_prompt(self, task_description: str = "", tools_desc: str = "") -> str:
        """Resolve system prompt: Langfuse override → default.

        Args:
            task_description: The specific sub-task description
            tools_desc: Comma-separated tool names available

        Returns:
            Complete system prompt for the worker
        """
        # Try Langfuse prompt first
        if self.langfuse_prompt_key:
            try:
                from app.services.langfuse_prompt_client import get_langfuse_prompt_client
                client = get_langfuse_prompt_client()
                prompt = await client.get_prompt(
                    self.langfuse_prompt_key,
                    variables={
                        "task_description": task_description,
                        "tools_description": tools_desc,
                    },
                )
                if prompt and prompt.content:
                    return prompt.content
            except Exception as e:
                logger.debug(f"Langfuse prompt fetch failed for {self.langfuse_prompt_key}: {e}")

        # Default prompt with task injection
        prompt = self.system_prompt
        if task_description:
            prompt += f"\n\nTu tarea específica: {task_description}"
        if tools_desc:
            prompt += f"\n\nHerramientas disponibles: {tools_desc}"

        return prompt


# ─── Worker Profile Definitions ──────────────────────────────────────────

WORKER_PROFILES: Dict[str, WorkerProfile] = {
    "document_search": WorkerProfile(
        name="Investigador Documental",
        focus="document_search",
        system_prompt=(
            "Eres un investigador documental especializado. Tu trabajo es buscar "
            "y analizar documentos del tenant para responder preguntas específicas.\n\n"
            "Reglas:\n"
            "- Busca primero con smart_search usando términos precisos\n"
            "- Si necesitas más detalle, usa get_document_content con el ID\n"
            "- Cita siempre las fuentes (título, ID) en tu respuesta\n"
            "- Sé conciso: extrae la información relevante, no copies todo\n"
            "- Cuando tengas la información, usa 'terminate' con tu respuesta\n"
            "- Responde en el mismo idioma que el usuario"
        ),
        tool_names=["smart_search", "get_document_content"],
        model_role=ModelRole.PLANNER,
        max_steps=2,
        langfuse_prompt_key="emma_swarm_worker_document_search",
    ),

    "legislation_search": WorkerProfile(
        name="Investigador Legislativo",
        focus="legislation_search",
        system_prompt=(
            "Eres un investigador legislativo especializado en normativa española. "
            "Tu trabajo es buscar leyes, reglamentos y normativas relevantes en el BOE.\n\n"
            "Reglas:\n"
            "- Busca legislación con smart_search usando términos jurídicos precisos\n"
            "- Cita siempre: nombre de la ley, artículos específicos, BOE ID\n"
            "- Distingue entre normativa estatal, autonómica y europea\n"
            "- Indica la fecha de última modificación si está disponible\n"
            "- Cuando tengas la información, usa 'terminate' con tu respuesta\n"
            "- Responde en español"
        ),
        tool_names=["smart_search"],
        model_role=ModelRole.PLANNER,
        max_steps=2,
        langfuse_prompt_key="emma_swarm_worker_legislation_search",
    ),

    "jurisprudence_search": WorkerProfile(
        name="Investigador Jurisprudencial",
        focus="jurisprudence_search",
        system_prompt=(
            "Eres un investigador jurisprudencial especializado en CENDOJ. "
            "Tu trabajo es buscar sentencias, autos y providencias relevantes.\n\n"
            "Reglas:\n"
            "- Busca jurisprudencia con search_jurisprudence usando términos precisos\n"
            "- Cita siempre: ROJ, ECLI, tribunal, fecha, ponente\n"
            "- Resume el fundamento jurídico principal de cada sentencia\n"
            "- Indica si es doctrina consolidada o sentencia aislada\n"
            "- Cuando tengas la información, usa 'terminate' con tu respuesta\n"
            "- Responde en español"
        ),
        tool_names=["search_jurisprudence"],
        model_role=ModelRole.PLANNER,
        max_steps=2,
        langfuse_prompt_key="emma_swarm_worker_jurisprudence_search",
    ),

    "domain_analysis": WorkerProfile(
        name="Analista de Dominio",
        focus="domain_analysis",
        system_prompt=(
            "Eres un analista de dominio especializado. Tu trabajo es realizar "
            "análisis profundos desde una perspectiva experta (legal, fiscal, laboral, etc.).\n\n"
            "Reglas:\n"
            "- Primero busca contexto relevante con smart_search si es necesario\n"
            "- Luego usa analyze_domain con el dominio correcto y el contexto recopilado\n"
            "- Proporciona un análisis estructurado con conclusiones claras\n"
            "- Cita las fuentes que respaldan tu análisis\n"
            "- Cuando tengas el análisis completo, usa 'terminate'\n"
            "- Responde en el mismo idioma que el usuario"
        ),
        tool_names=["smart_search", "analyze_domain"],
        model_role=ModelRole.CHAT,  # Quality model for analysis
        max_steps=3,
        langfuse_prompt_key="emma_swarm_worker_domain_analysis",
    ),

    "web_search": WorkerProfile(
        name="Investigador Web",
        focus="web_search",
        system_prompt=(
            "Eres un investigador web especializado. Tu trabajo es buscar "
            "información actualizada en internet para complementar el conocimiento local.\n\n"
            "Reglas:\n"
            "- Busca con web_search usando queries bien formuladas\n"
            "- Prioriza fuentes oficiales y fiables\n"
            "- Indica siempre la URL de la fuente\n"
            "- Resume la información relevante, no copies páginas enteras\n"
            "- Cuando tengas la información, usa 'terminate' con tu respuesta\n"
            "- Responde en el mismo idioma que el usuario"
        ),
        tool_names=["web_search"],
        model_role=ModelRole.PLANNER,
        max_steps=2,
        langfuse_prompt_key="emma_swarm_worker_web_search",
    ),

    "structural_query": WorkerProfile(
        name="Analista de Datos",
        focus="structural_query",
        system_prompt=(
            "Eres un analista de datos especializado. Tu trabajo es consultar "
            "la estructura organizativa y contabilizar entidades.\n\n"
            "Reglas:\n"
            "- Usa structural_query para contar, listar y filtrar entidades\n"
            "- Formula consultas precisas (departamentos, empleados, carpetas)\n"
            "- Presenta los resultados de forma clara y estructurada\n"
            "- Si los datos son numéricos, incluye totales y desglose\n"
            "- Cuando tengas los datos, usa 'terminate' con tu respuesta\n"
            "- Responde en el mismo idioma que el usuario"
        ),
        tool_names=["structural_query"],
        model_role=ModelRole.PLANNER,
        max_steps=2,
        langfuse_prompt_key="emma_swarm_worker_structural_query",
    ),
}

# Default profile for unknown focus categories
_DEFAULT_PROFILE = WorkerProfile(
    name="Agente General",
    focus="general",
    system_prompt=(
        "Eres un agente especializado. Usa las herramientas proporcionadas "
        "para investigar y responder la tarea asignada.\n\n"
        "Reglas:\n"
        "- Usa SOLO las herramientas proporcionadas\n"
        "- Sé conciso y directo\n"
        "- Cuando tengas la información, usa 'terminate' con tu respuesta\n"
        "- Cita las fuentes encontradas\n"
        "- Responde en el mismo idioma que el usuario"
    ),
    tool_names=["smart_search"],
    model_role=ModelRole.PLANNER,
    max_steps=2,
)


def get_worker_profile(focus: str, sector: Optional[str] = None) -> WorkerProfile:
    """Get the worker profile for a focus category.

    Returns the typed profile if known, or the default profile for
    unknown categories. Never returns None.

    Sector-aware filtering:
    - jurisprudence_search is only valid for the legal sector
    - legislation_search is only valid for the legal sector

    Args:
        focus: Focus category key from decompose output
        sector: Active sector name (e.g., "legal", "medical", "documental")
    """
    # Legal-only profiles: fall back to default for non-legal sectors
    _LEGAL_ONLY_PROFILES = {"jurisprudence_search", "legislation_search"}
    if focus in _LEGAL_ONLY_PROFILES and sector and sector != "legal":
        logger.info(f"Worker profile '{focus}' not available for sector '{sector}', using default")
        return _DEFAULT_PROFILE

    return WORKER_PROFILES.get(focus, _DEFAULT_PROFILE)


def get_valid_focus_types() -> List[str]:
    """Get all valid focus type names for decompose validation."""
    return list(WORKER_PROFILES.keys())
