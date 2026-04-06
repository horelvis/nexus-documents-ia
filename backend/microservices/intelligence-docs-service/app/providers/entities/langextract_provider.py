"""
LangExtract entity provider — few-shot extraction with source grounding.

Uses the langextract library directly (no HTTP) with SGLang as the LLM
backend via its OpenAI-compatible API. Replaces both sglang_ner (basic NER)
and the standalone langextract-service microservice.

Includes a monkey-patch for langextract's JSON parser to handle malformed
output from small LLMs (e.g., Qwen3.5-9B generating trailing tokens after
valid JSON).
"""
import asyncio
import json
import logging
import re
from typing import Optional

import langextract as lx
from langextract.core import format_handler as _fh

from app.providers.base import EntityProvider, Entity
from app.providers.entities.few_shot_configs import EXTRACTION_CONFIGS


# ── Monkey-patch: tolerant JSON parser for langextract ──
# Small LLMs often generate valid JSON followed by trailing tokens,
# which causes json.loads to fail with "Extra data". This patch
# truncates to the first valid JSON object/array.

_original_parse_output = _fh.FormatHandler.parse_output


def _tolerant_parse_output(self, text, *, strict=None):
    """Wrapper that retries with truncated JSON on parse failure."""
    try:
        return _original_parse_output(self, text, strict=strict)
    except Exception as first_error:
        # Only attempt repair for JSON format
        if self.format_type != _fh.data.FormatType.JSON:
            raise

        # Try to extract valid JSON from the response
        content = self._extract_content(text)
        repaired = _repair_json(content)
        if repaired and repaired != content:
            try:
                # Temporarily replace the text and retry
                # We re-wrap in fences if needed so _extract_content works
                patched_text = f"```json\n{repaired}\n```" if self.use_fences else repaired
                return _original_parse_output(self, patched_text, strict=strict)
            except Exception:
                pass  # repair didn't help, raise original

        raise first_error


def _repair_json(text: str) -> Optional[str]:
    """Attempt to extract valid JSON from text with trailing garbage.

    Handles common LLM failure modes:
    - Valid JSON followed by extra tokens
    - Multiple JSON objects concatenated
    - Trailing commas before closing brackets
    - Text/preamble before the JSON starts
    - Completely empty or non-JSON responses
    """
    text = text.strip()
    if not text:
        return None

    # Find the first JSON start character (LLM may emit preamble text)
    first_brace = text.find('{')
    first_bracket = text.find('[')
    if first_brace == -1 and first_bracket == -1:
        return None
    if first_brace == -1:
        start = first_bracket
    elif first_bracket == -1:
        start = first_brace
    else:
        start = min(first_brace, first_bracket)

    text = text[start:]

    open_char = text[0]
    if open_char == '{':
        close_char = '}'
    elif open_char == '[':
        close_char = ']'
    else:
        return None

    # Find the last matching close bracket by counting nesting
    depth = 0
    in_string = False
    escape_next = False
    last_valid_close = -1

    for i, ch in enumerate(text):
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

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                last_valid_close = i
                break  # First complete JSON — use it

    if last_valid_close > 0:
        candidate = text[:last_valid_close + 1]
        # Fix trailing commas before close brackets
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return None


_fh.FormatHandler.parse_output = _tolerant_parse_output

logger = logging.getLogger(__name__)

# Maps langextract extraction_class names to standard Entity types.
CLASS_TO_TYPE: dict[str, str] = {
    # People
    "party": "PERSON",
    "trabajador": "PERSON",
    "person": "PERSON",
    "author": "PERSON",
    # Organizations
    "empresa": "ORGANIZATION",
    "customer": "ORGANIZATION",
    "cliente": "ORGANIZATION",
    "declarante": "ORGANIZATION",
    # Dates
    "date": "DATE",
    "fecha": "DATE",
    "periodo": "DATE",
    "fecha_emision": "DATE",
    "ejercicio": "DATE",
    # Amounts
    "amount": "AMOUNT",
    "devengo": "AMOUNT",
    "deduccion": "AMOUNT",
    "liquido": "AMOUNT",
    "retencion": "AMOUNT",
    "percepciones": "AMOUNT",
    "retenciones": "AMOUNT",
    "iva_devengado": "AMOUNT",
    "iva_deducible": "AMOUNT",
    "resultado": "AMOUNT",
    "perceptores": "AMOUNT",
    # Identifiers
    "invoice_number": "IDENTIFIER",
    "expediente": "IDENTIFIER",
    "iban": "IDENTIFIER",
    "contract_type": "IDENTIFIER",
    # Misc
    "finding": "FINDING",
    "title": "TITLE",
    "puesto": "ROLE",
    "tipo_comunicacion": "COMMUNICATION_TYPE",
    "plazo": "DEADLINE",
}


class LangExtractProvider(EntityProvider):
    """Few-shot entity extraction with source grounding via langextract lib."""

    name = "langextract"

    def __init__(
        self,
        sglang_base_url: str,
        sglang_model: str,
        extraction_passes: int = 1,
        max_char_buffer: int = 10000,
        confidence_threshold: float = 0.7,
    ):
        # langextract expects base URL without /v1 suffix for Ollama-compatible mode
        self._base_url = sglang_base_url.rstrip("/").removesuffix("/v1")
        self._model = sglang_model
        self._extraction_passes = extraction_passes
        self._max_char_buffer = max_char_buffer
        self._confidence_threshold = confidence_threshold

    async def extract_entities(
        self,
        text: str,
        language: str = "es",
        document_type: str = "general",
    ) -> list[Entity]:
        if not text or len(text.strip()) < 30:
            return []

        config = EXTRACTION_CONFIGS.get(document_type, EXTRACTION_CONFIGS["general"])

        # Append /nothink to disable Qwen3.5 thinking mode — without it,
        # the model puts output in reasoning_content and returns empty content.
        prompt_text = config["prompt"] + "\n/nothink"

        extract_params = {
            "text_or_documents": text[: self._max_char_buffer],
            "prompt_description": prompt_text,
            "examples": config["examples"],
            "extraction_passes": self._extraction_passes,
            "max_char_buffer": self._max_char_buffer,
            "model_id": self._model,
            "model_url": self._base_url,
            "fence_output": False,
            "use_schema_constraints": False,
        }

        try:
            logger.info(
                f"LangExtract starting: doc_type={document_type}, "
                f"text_len={len(text)}, model={self._model}"
            )
            result = await asyncio.to_thread(lx.extract, **extract_params)
        except Exception as e:
            logger.warning(f"LangExtract extraction failed: {e}")
            return []

        entities: list[Entity] = []
        for ext in result.extractions or []:
            if not ext.extraction_text:
                continue

            entity_type = self._map_class(ext.extraction_class)
            start_pos = ext.source_indices[0] if ext.source_indices else None
            end_pos = ext.source_indices[-1] if ext.source_indices else None

            entities.append(
                Entity(
                    type=entity_type,
                    value=ext.extraction_text,
                    provider="langextract",
                    confidence=0.8,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    attributes=ext.attributes or {},
                )
            )

        logger.info(f"LangExtract extracted {len(entities)} entities")
        return entities

    @staticmethod
    def _map_class(extraction_class: str) -> str:
        """Map langextract extraction_class to standard Entity type."""
        return CLASS_TO_TYPE.get(extraction_class.lower(), extraction_class.upper())

    async def is_available(self) -> bool:
        if not self._model:
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/v1/models")
                return resp.status_code == 200
        except Exception:
            return False
