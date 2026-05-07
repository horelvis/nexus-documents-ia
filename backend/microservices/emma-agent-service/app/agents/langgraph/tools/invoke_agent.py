"""invoke_agent — replaces analyze_domain.

Delegates a focused question to a specialist agent loaded from the
admin-curated catalog (Main API DB row + Langfuse persona). Wraps a
single LLM call with the persona as the system prompt and the scope
filters surfaced in the user content so downstream sub-tools (when
chained) can apply them.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Type

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.llm_models import get_chat_model, get_planner_model
from app.agents.llm_types import ModelRole
from app.services.agent_loader import AgentLoader, LoadedAgent

from .base import EmmaTool, ToolResult

logger = logging.getLogger(__name__)


class InvokeAgentInput(BaseModel):
    """Input for invoke_agent."""

    agent_slug: str = Field(
        description=(
            "Slug del agente a invocar (e.g. 'contabilidad'). Lista los "
            "agentes disponibles en <available_agents> del system prompt."
        )
    )
    question: str = Field(description="Pregunta específica para el agente especialista.")
    context: Optional[str] = Field(
        default=None,
        description=(
            "Contexto ya recopilado (fragmentos, resultados previos). "
            "Si no se proporciona, el agente responde sólo desde la pregunta."
        ),
    )


class InvokeAgentTool(EmmaTool):
    """Calls a specialist agent's LLM with its persona + scope hint."""

    def __init__(
        self,
        *,
        loader: Optional[AgentLoader] = None,
        usage_counter=None,
    ) -> None:
        self._loader = loader  # injected for tests; lazy resolved otherwise
        self._usage_counter = usage_counter

    @property
    def name(self) -> str:
        return "invoke_agent"

    @property
    def description(self) -> str:
        return (
            "Delega una pregunta a un agente especialista del catálogo. "
            "Úsalo cuando el usuario menciona @<slug> en su consulta. "
            "Consulta <available_agents> en este system prompt para los slugs disponibles."
        )

    @property
    def parameters_schema(self) -> Type[BaseModel]:
        return InvokeAgentInput

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        slug = (arguments.get("agent_slug") or "").strip()
        question = (arguments.get("question") or "").strip()
        provided_context = arguments.get("context") or ""

        if not slug or not question:
            return ToolResult.from_error(
                "agent_slug y question son obligatorios.",
                suggestion="Llama al tool con un slug del catálogo y una pregunta concreta.",
            )

        loader = self._loader or _default_loader()
        loaded: Optional[LoadedAgent] = None
        try:
            loaded = await loader.load_by_slug(slug)
        except Exception as exc:  # noqa: BLE001
            logger.exception("AgentLoader failed for slug=%s", slug)
            return ToolResult.from_error(
                f"No se pudo cargar el agente '{slug}': {exc}",
                suggestion="Verifica que el slug existe y que la persona está publicada en Langfuse.",
            )

        if loaded is None:
            return ToolResult.from_error(
                f"Agente '{slug}' no encontrado o inactivo.",
                suggestion="Consulta /agents para ver el catálogo activo.",
            )

        system_prompt = self._compose_persona(loaded)
        user_content = self._compose_user_content(loaded.scope, provided_context, question)

        try:
            model = self._resolve_model(loaded.model_role).bind(
                max_tokens=2048,
                temperature=loaded.temperature,
            )
            response = await model.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("invoke_agent LLM call failed slug=%s", slug)
            return ToolResult.from_error(
                f"La llamada al modelo falló para '{slug}': {exc}",
                suggestion="Reintenta o usa Emma general (sin @-mention).",
            )

        output = response.content or ""
        if "<think>" in output:
            output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()

        if not output:
            return ToolResult.from_error(
                f"El agente '{slug}' no produjo respuesta.",
                suggestion="Reformula la pregunta o aporta más contexto.",
            )

        # Best-effort usage counter (must not break the response on failure).
        try:
            counter = self._usage_counter or _default_usage_counter()
            await counter.increment(loaded.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("usage_counter.increment failed for slug=%s: %s", slug, exc)

        return ToolResult(
            output=output,
            data={
                "agent_id": loaded.id,
                "agent_slug": loaded.slug,
                "agent_name": loaded.name,
                "agent_color": loaded.color,
                "agent_icon": loaded.icon,
            },
        )

    @staticmethod
    def _compose_persona(loaded: LoadedAgent) -> str:
        modifier_lines = []
        if loaded.persona_style == "concise":
            modifier_lines.append("Estilo: respuestas breves (2-3 frases salvo que se pidan datos extensos).")
        elif loaded.persona_style == "detailed":
            modifier_lines.append("Estilo: respuestas detalladas con razonamiento paso a paso.")
        elif loaded.persona_style == "conversational":
            modifier_lines.append("Estilo: tono conversacional, cercano.")
        if loaded.persona_language and loaded.persona_language != "auto":
            modifier_lines.append(f"Idioma: {loaded.persona_language}.")
        modifiers = "\n".join(modifier_lines)
        return f"{loaded.persona_instructions}\n\n{modifiers}".strip()

    @staticmethod
    def _compose_user_content(scope: dict, extra: str, question: str) -> str:
        parts: list[str] = []
        if scope:
            scope_lines = ["[Scope filters]"]
            if scope.get("semantic_types"):
                scope_lines.append(f"- semantic_types: {', '.join(scope['semantic_types'])}")
            if scope.get("folders"):
                scope_lines.append(f"- folders: {len(scope['folders'])} folder(s)")
            if scope.get("date_range"):
                dr = scope["date_range"] or {}
                scope_lines.append(f"- date_range: {dr.get('from') or '*'} → {dr.get('to') or '*'}")
            if scope.get("quality_min") is not None:
                scope_lines.append(f"- quality_min: {scope['quality_min']}")
            parts.append("\n".join(scope_lines))
        if extra:
            parts.append(f"**Contexto disponible**:\n{extra[:6000]}")
        parts.append(f"**Pregunta**: {question}")
        return "\n\n".join(parts)

    @staticmethod
    def _resolve_model(role: ModelRole):
        return get_planner_model() if role == ModelRole.PLANNER else get_chat_model()


def _default_loader() -> AgentLoader:
    """Build the production AgentLoader on first use."""
    from app.services.langfuse_prompt_client import get_langfuse_prompt_client
    from app.services.main_api_client import MainAPIClient

    redis_client = None
    try:
        from app.core.redis_client import get_redis  # type: ignore
        redis_client = get_redis()
    except Exception:  # noqa: BLE001
        # Redis is optional for the loader; cache misses are acceptable.
        redis_client = None

    return AgentLoader(
        main_api=MainAPIClient(),
        langfuse=_LangfuseAdapter(get_langfuse_prompt_client()),
        redis=redis_client,
    )


def _default_usage_counter():
    """Build the production usage counter on first use."""
    from app.services.main_api_client import MainAPIClient

    class _Counter:
        def __init__(self) -> None:
            self._client = MainAPIClient()

        async def increment(self, agent_id: str) -> None:
            await self._client.increment_agent_usage(agent_id)

    return _Counter()


class _LangfuseAdapter:
    """Wraps ``LangfusePromptClient.get_prompt`` to return raw content string."""

    def __init__(self, client) -> None:
        self._client = client

    async def get_prompt(self, name: str, *, label: str = "production") -> str:
        prompt = await self._client.get_prompt(name, label=label)
        return getattr(prompt, "content", str(prompt))
