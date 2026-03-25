"""
LangExtract entity provider — few-shot extraction with source grounding.

Uses the langextract library directly (no HTTP) with SGLang as the LLM
backend via its OpenAI-compatible API. Replaces both sglang_ner (basic NER)
and the standalone langextract-service microservice.
"""
import asyncio
import logging
from typing import Optional

import langextract as lx

from app.providers.base import EntityProvider, Entity
from app.providers.entities.few_shot_configs import EXTRACTION_CONFIGS

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

        extract_params = {
            "text_or_documents": text[: self._max_char_buffer],
            "prompt_description": config["prompt"],
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
