"""
OpenAI-compatible NER provider for SGLang/vLLM.

Calls /v1/chat/completions directly with chat_template_kwargs to disable
Qwen3.5 thinking mode. Uses JSON output with tolerant parsing.

Prompts are managed in Langfuse (versioned, A/B testable):
  - ner_system: system prompt for entity extraction
  - ner_fewshot_user: few-shot example (user turn)
  - ner_fewshot_assistant: few-shot example (assistant turn)

Falls back to inline defaults if Langfuse is unavailable.
"""
import json
import logging
import re
from typing import Optional

import httpx

from app.providers.base import EntityProvider, Entity

logger = logging.getLogger(__name__)

# Map extraction class names to standard Entity types
CLASS_TO_TYPE: dict[str, str] = {
    "person": "PERSON", "party": "PERSON", "trabajador": "PERSON",
    "author": "PERSON", "demandante": "PERSON", "demandado": "PERSON",
    "empresa": "ORGANIZATION", "customer": "ORGANIZATION",
    "cliente": "ORGANIZATION", "declarante": "ORGANIZATION",
    "organization": "ORGANIZATION",
    "date": "DATE", "fecha": "DATE", "periodo": "DATE",
    "fecha_emision": "DATE", "ejercicio": "DATE",
    "amount": "AMOUNT", "devengo": "AMOUNT", "deduccion": "AMOUNT",
    "liquido": "AMOUNT", "retencion": "AMOUNT",
    "invoice_number": "IDENTIFIER", "expediente": "IDENTIFIER",
    "iban": "IDENTIFIER", "dni": "IDENTIFIER", "nif": "IDENTIFIER",
    "cif": "IDENTIFIER", "nie": "IDENTIFIER",
    "contract_type": "IDENTIFIER",
    "finding": "FINDING", "title": "TITLE", "puesto": "ROLE",
    "location": "LOCATION", "lugar": "LOCATION",
}

# ── Fallback prompts (used when Langfuse is unavailable) ──

_FALLBACK_SYSTEM = """Eres un extractor de entidades. Dado un texto, extrae SOLO entidades con nombre propio.

Devuelve SOLO un JSON array con objetos que tengan "class" y "text":
[{"class": "person", "text": "Juan García López"}, {"class": "empresa", "text": "TechCorp SL"}]

Clases válidas:
- person: Nombres de personas (ej: "Carlos Ruiz Fernández", "Dña. María López")
- empresa: Nombres de empresas u organizaciones (ej: "Construcciones del Norte SL", "INSS")
- date: Fechas concretas (ej: "15 de marzo de 2024", "01/02/2025")
- expediente: Números de expediente (ej: "EXP-2025/0341-FAM")

NO extraigas:
- Descripciones genéricas ("muy grave", "negligencia médica", "responsabilidad civil")
- Importes monetarios, horas, porcentajes
- Emails, teléfonos, direcciones postales
- DNI, NIF, CIF, NIE, IBAN (ya se extraen por otro medio)
- Artículos de ley o referencias legales (ej: "Artículo 96 del Código Civil")
- Roles o profesiones sin nombre propio

Reglas:
- Usa el texto EXACTO del documento
- NO inventes datos que no estén en el texto
- SOLO el JSON array, sin explicaciones
- Si no hay entidades, devuelve: []"""

_FALLBACK_FEWSHOT_USER = """Texto: Contrato entre TechCorp SL (CIF: B12345678) representada por D. Juan Garcia Lopez y la trabajadora Maria Perez Ruiz (NIF: 12345678A). Salario: 30.000 EUR anuales. Fecha inicio: 01/02/2025. Se regirá por el Estatuto de los Trabajadores. El email de contacto es rrhh@techcorp.es."""

_FALLBACK_FEWSHOT_ASSISTANT = """[{"class": "empresa", "text": "TechCorp SL"}, {"class": "person", "text": "Juan Garcia Lopez"}, {"class": "person", "text": "Maria Perez Ruiz"}, {"class": "date", "text": "01/02/2025"}]"""


# ── Langfuse prompt loader ──

_langfuse_client = None


def _get_langfuse():
    """Lazy-init Langfuse client. Returns None if not configured."""
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client

    try:
        from app.core.config import settings
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            logger.info("Langfuse not configured — using fallback NER prompts")
            return None

        from langfuse import Langfuse
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info(f"Langfuse connected at {settings.langfuse_host}")
        return _langfuse_client
    except Exception as e:
        logger.warning(f"Langfuse init failed, using fallback prompts: {e}")
        return None


def _get_prompt(name: str, fallback: str) -> str:
    """Get prompt from Langfuse with inline fallback."""
    lf = _get_langfuse()
    if not lf:
        return fallback
    try:
        prompt = lf.get_prompt(name=name, label="production", fallback=fallback)
        return prompt.prompt if hasattr(prompt, 'prompt') else fallback
    except Exception as e:
        logger.debug(f"Langfuse prompt '{name}' not found, using fallback: {e}")
        return fallback


# ── JSON repair ──

def _repair_json_array(text: str) -> Optional[str]:
    """Extract a valid JSON array from potentially malformed LLM output."""
    text = text.strip()
    if not text:
        return None

    start = text.find('[')
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                candidate = re.sub(r',\s*\]', ']', candidate)
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    pass
                break

    return None


# ── Provider ──

class OpenAINerProvider(EntityProvider):
    """NER via OpenAI-compatible chat API (SGLang/vLLM) with Langfuse prompts."""

    name = "openai_ner"

    def __init__(
        self,
        base_url: str,
        model: str,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        max_text_chars: int = 8000,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._max_text_chars = max_text_chars

    async def extract_entities(
        self,
        text: str,
        language: str = "es",
        document_type: str = "general",
    ) -> list[Entity]:
        if not text or len(text.strip()) < 30:
            return []

        truncated = text[:self._max_text_chars]

        # Load prompts from Langfuse (or fallback)
        system_prompt = _get_prompt("ner_system", _FALLBACK_SYSTEM)
        fewshot_user = _get_prompt("ner_fewshot_user", _FALLBACK_FEWSHOT_USER)
        fewshot_assistant = _get_prompt("ner_fewshot_assistant", _FALLBACK_FEWSHOT_ASSISTANT)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Texto: {fewshot_user}"},
            {"role": "assistant", "content": fewshot_assistant},
            {"role": "user", "content": f"Texto: {truncated}"},
        ]

        try:
            logger.info(f"OpenAI NER starting: text_len={len(text)}, model={self._model}")

            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json={
                        "model": self._model,
                        "messages": messages,
                        "temperature": self._temperature,
                        "max_tokens": self._max_tokens,
                        "chat_template_kwargs": {"enable_thinking": False},
                    },
                )
                resp.raise_for_status()

            data = resp.json()
            content = data["choices"][0]["message"].get("content") or ""

            if not content.strip():
                logger.warning("OpenAI NER: empty content response")
                return []

            repaired = _repair_json_array(content)
            if not repaired:
                logger.warning(f"OpenAI NER: could not parse response: {content[:200]}")
                return []

            raw_entities = json.loads(repaired)
            if not isinstance(raw_entities, list):
                return []

            entities: list[Entity] = []
            seen: set[str] = set()

            for item in raw_entities:
                if not isinstance(item, dict):
                    continue
                cls = (item.get("class") or "").strip().lower()
                val = (item.get("text") or "").strip()
                if not cls or not val or len(val) < 2:
                    continue

                key = f"{cls}:{val.lower()}"
                if key in seen:
                    continue
                seen.add(key)

                entity_type = CLASS_TO_TYPE.get(cls, cls.upper())
                entities.append(Entity(
                    type=entity_type,
                    value=val,
                    provider="openai_ner",
                    confidence=0.8,
                    attributes={"class": cls},
                ))

            logger.info(
                f"OpenAI NER extracted {len(entities)} entities: "
                f"{', '.join(f'{e.type}:{e.value[:25]}' for e in entities[:5])}"
            )
            return entities

        except Exception as e:
            logger.warning(f"OpenAI NER extraction failed: {e}")
            return []

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
                return resp.status_code == 200
        except Exception:
            return False
