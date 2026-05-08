"""Internal endpoint for service-to-service prompt management.

Used by the Main API to push admin-curated agent personas into Langfuse
without bundling the langfuse SDK there. Authenticated with the shared
``MICROSERVICES_API_KEY`` header.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")) -> None:
    if x_api_key != settings.MICROSERVICES_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


class PushPersonaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    slug: str = Field(..., pattern=r"^[a-z][a-z0-9_]{1,49}$")
    instructions: str = Field(..., max_length=20000)


@router.post("/prompts/push-persona", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def push_persona(payload: PushPersonaRequest, _: None = Depends(_verify_api_key)):
    """Push an agent persona to Langfuse as ``agent_<slug>_persona``.

    Idempotent: each call creates a new Langfuse version with label ``production``.
    """
    name = f"agent_{payload.slug}_persona"
    try:
        from langfuse import Langfuse
        client = Langfuse(
            host=settings.langfuse_host,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
        )
        # langfuse SDK is sync; offload to a thread.
        import asyncio
        await asyncio.to_thread(
            client.create_prompt,
            name=name,
            prompt=payload.instructions,
            labels=["production"],
            type="text",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Langfuse push failed for %s", name)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Langfuse error: {exc}",
        ) from exc

    logger.info("Pushed Langfuse prompt name=%s len=%d", name, len(payload.instructions))


class GeneratePromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    semantic_types: list[str] = Field(default_factory=list)
    current_instructions: str = Field(default="", max_length=20000)


class GeneratePromptResponse(BaseModel):
    instructions: str


_META_PROMPT = """\
Eres un experto en redactar system prompts para asistentes IA especializados.

El admin está definiendo un agente con estos datos:
- Nombre: {name}
- Descripción: {description}
- Tipos semánticos del corpus que verá: {semantic_types}
{mode_block}

Devuelve UN ÚNICO system prompt en español, ESTRUCTURADO en secciones markdown:

## Identidad
Una frase: "Eres el asistente de <X>, especializado en <Y>." Sin adornos.

## Estilo
Lista de bullets con: tono, longitud objetivo, idioma, formato preferido.

## Conocimiento
Bullets con áreas de experticia derivadas de la descripción y los semantic_types.

## Restricciones
Bullets con: cita siempre fuentes cuando aplique, no inventes datos, prefiere documentos del corpus sobre conocimiento general.

## Fuera de scope
Una frase: cuándo redirigir al asistente general (consultas fuera del dominio).

Reglas duras:
- Cada sección con su header `##`. Ningún texto fuera de las secciones.
- Bullets cortos (≤ 15 palabras).
- Ningún meta-comentario, ningún preámbulo, ninguna explicación. Devuelve sólo el contenido del system prompt comenzando por `## Identidad`."""


@router.post("/agents/helpers/generate-prompt", response_model=GeneratePromptResponse)
async def generate_prompt(
    payload: GeneratePromptRequest,
    _: None = Depends(_verify_api_key),
) -> GeneratePromptResponse:
    """Generate (or improve) a system prompt for an admin-curated agent."""
    from langchain_core.messages import HumanMessage, SystemMessage

    semantic_types_str = ", ".join(payload.semantic_types) or "(ninguno especificado)"
    if payload.current_instructions.strip():
        mode_block = (
            f"- Prompt actual del admin (para MEJORAR, no para reemplazar bruscamente):\n"
            f"\"\"\"\n{payload.current_instructions.strip()}\n\"\"\"\n"
            f"\nMejora la claridad, concisión y profesionalidad del prompt actual "
            f"manteniendo su intención. No introduzcas información ajena."
        )
    else:
        mode_block = "- (No hay prompt previo: genera uno desde cero.)"

    system_text = _META_PROMPT.format(
        name=payload.name,
        description=payload.description or "(sin descripción)",
        semantic_types=semantic_types_str,
        mode_block=mode_block,
    )

    try:
        # Build a one-shot ChatOpenAI that tolerates an empty LLM_API_KEY env
        # (the shared singleton in llm_models.get_chat_model() inherits the
        # empty value and the OpenAI SDK rejects it).
        from langchain_openai import ChatOpenAI as _ChatOpenAI
        model = _ChatOpenAI(
            base_url=settings.llm_base_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key or "not-needed",
            temperature=0.3,
            max_tokens=1024,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        response = await model.ainvoke(
            [
                SystemMessage(content=system_text),
                HumanMessage(content="Genera o mejora el system prompt según las indicaciones."),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("generate-prompt LLM call failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM error: {exc}",
        ) from exc

    output = (response.content or "").strip()
    # Strip <think> blocks that some models emit
    import re
    if "<think>" in output:
        output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()

    if not output:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Model returned an empty prompt.",
        )

    return GeneratePromptResponse(instructions=output)
