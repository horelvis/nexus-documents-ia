"""Utilities to run document categorization prompts against different LLM providers."""
import logging
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

VALID_CATEGORIES = [
    "contract",
    "invoice",
    "report",
    "legal",
    "financial",
    "technical",
    "correspondence",
    "presentation",
    "general",
]

CATEGORY_PROMPT = (
    "Clasifica este documento en una de las categorías: "
    "contract, invoice, report, legal, financial, technical, correspondence, presentation o general. "
    "Responde solo con el nombre de la categoría.\n\n"
    "Nombre: {filename}\n"
    "Contenido:\n{content}"
)

OPENAI_SYSTEM_PROMPT = (
    "Eres un asistente de clasificación documental. "
    "Lee el texto proporcionado y responde únicamente con el nombre de la categoría indicada."
)


def normalize_category(answer: Optional[str]) -> Optional[str]:
    """Normalize a free-form answer to one of the supported categories."""
    if not answer:
        return None

    clean = answer.strip().lower()
    for category in VALID_CATEGORIES:
        if category in clean:
            return category

    first_word = clean.split()[0]
    return first_word if first_word in VALID_CATEGORIES else None


def _build_prompt(filename: str, content_preview: str, preview_limit: int = 1200) -> str:
    """Build the categorization prompt using a limited preview."""
    preview = (content_preview or "")[:preview_limit]
    return CATEGORY_PROMPT.format(filename=filename or "Documento", content=preview)


async def categorize_with_ai(
    filename: str,
    content_preview: str,
    tenant_id: str,
    user_id: str,
    context: Optional[Dict[str, Any]] = None,
    preview_limit: int = 1200,
) -> Dict[str, Optional[str]]:
    """Route categorization to the configured provider and return normalized output."""
    prompt = _build_prompt(filename, content_preview, preview_limit)
    provider_pref = (settings.AUTO_CATEGORIZATION_PROVIDER or "cag").lower()
    answer: Optional[str] = None
    provider_used = provider_pref

    if provider_pref == "openai":
        if not settings.OPENAI_API_KEY:
            logger.warning("OpenAI provider selected but OPENAI_API_KEY is missing. Falling back to CAG service.")
        else:
            answer = await _call_openai(prompt)
            provider_used = "openai"

    if answer is None:
        answer = await _call_cag_service(prompt, tenant_id, user_id, context)
        provider_used = "cag"

    category = normalize_category(answer)
    return {
        "category": category,
        "provider": provider_used,
        "raw_answer": answer,
    }


async def _call_cag_service(
    prompt: str,
    tenant_id: str,
    user_id: str,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Invoke the legacy CAG microservice (Ollama) for categorization."""
    headers = {
        "X-API-Key": settings.MICROSERVICES_API_KEY,
        "X-Tenant-ID": str(tenant_id),
    }
    payload = {
        "query": prompt,
        "tenant_id": str(tenant_id),
        "user_id": str(user_id or "system"),
        "context": context or {},
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"{settings.CAG_SERVICE_URL.rstrip('/')}/api/v1/cag/query",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json().get("answer")
    except Exception as exc:
        logger.warning("CAG categorization request failed | tenant=%s error=%s", tenant_id, exc)
        return None


async def _call_openai(prompt: str) -> Optional[str]:
    """Call OpenAI's chat completions endpoint for categorization."""
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        return None

    url = f"{settings.OPENAI_API_BASE.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.OPENAI_CATEGORIZATION_MODEL,
        "temperature": settings.AUTO_CATEGORIZATION_TEMPERATURE,
        "max_tokens": 32,
        "messages": [
            {"role": "system", "content": OPENAI_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices", [])
            if not choices:
                return None
            message = choices[0].get("message") or {}
            return (message.get("content") or "").strip()
    except Exception as exc:
        logger.error("OpenAI categorization request failed: %s", exc)
        return None
