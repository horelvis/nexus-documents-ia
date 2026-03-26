"""
Regex-based entity provider for Spanish documents.

Extracts structured identifiers using patterns that are unambiguous
and work across all document types. No LLM dependency, <1ms execution.

Patterns covered:
  - DNI: 8 digits + letter
  - NIE: X/Y/Z + 7 digits + letter
  - CIF: letter + 8 digits (company tax ID)
  - IBAN: ES + 22 digits
  - NIF: contextual (preceded by "NIF" label)

Person names and organizations are left to LangExtract since they require
contextual understanding that varies by document type.
"""
import re
import logging
from typing import Optional

from app.providers.base import EntityProvider, Entity

logger = logging.getLogger(__name__)

# ── Compiled regex patterns ──

# DNI: 8 digits + letter (with optional space)
_DNI_RE = re.compile(r"\b(\d{8}\s?[A-Z])\b")

# NIE: X/Y/Z + 7 digits + letter
_NIE_RE = re.compile(r"\b([XYZ]\d{7}\s?[A-Z])\b")

# CIF: letter + 8 digits (Spanish company tax ID)
_CIF_RE = re.compile(r"\b([ABCDEFGHJNPQRSUVW]\d{8})\b")

# IBAN: ES + 2 check + 20 digits (with optional spaces)
_IBAN_RE = re.compile(r"\b(ES\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4})\b")

# Contextual patterns: "NIF: 12345678A", "CIF: B12345678"
_NIF_CONTEXT_RE = re.compile(r"(?:NIF|N\.I\.F\.)[:\s]+(\d{8}\s?[A-Z])", re.IGNORECASE)
_CIF_CONTEXT_RE = re.compile(r"(?:CIF|C\.I\.F\.)[:\s]+([ABCDEFGHJNPQRSUVW]\d{8})", re.IGNORECASE)


class RegexEntityProvider(EntityProvider):
    """Fast regex-based NER for Spanish document identifiers."""

    name = "regex"

    async def extract_entities(
        self,
        text: str,
        language: str = "es",
        document_type: str = "general",
    ) -> list[Entity]:
        if not text or len(text.strip()) < 10:
            return []

        entities: list[Entity] = []
        seen: set[str] = set()

        def _add(entity_type: str, value: str, confidence: float = 0.9,
                 start: Optional[int] = None):
            normalized = value.strip().replace(" ", "")
            key = f"{entity_type}:{normalized.lower()}"
            if key in seen:
                return
            seen.add(key)
            entities.append(Entity(
                type=entity_type,
                value=normalized,
                provider="regex",
                confidence=confidence,
                start_pos=start,
            ))

        # DNI — contextual first (higher confidence), then bare pattern
        for m in _NIF_CONTEXT_RE.finditer(text):
            _add("DNI", m.group(1), confidence=0.95, start=m.start(1))
        for m in _DNI_RE.finditer(text):
            _add("DNI", m.group(1), confidence=0.80, start=m.start(1))

        # NIE
        for m in _NIE_RE.finditer(text):
            _add("NIE", m.group(1), confidence=0.90, start=m.start(1))

        # CIF — contextual first
        for m in _CIF_CONTEXT_RE.finditer(text):
            _add("CIF", m.group(1), confidence=0.95, start=m.start(1))
        for m in _CIF_RE.finditer(text):
            _add("CIF", m.group(1), confidence=0.75, start=m.start(1))

        # IBAN
        for m in _IBAN_RE.finditer(text):
            _add("IBAN", m.group(1), confidence=0.95, start=m.start(1))

        if entities:
            logger.info(
                f"Regex extracted {len(entities)} identifiers: "
                f"{', '.join(f'{e.type}:{e.value}' for e in entities[:5])}"
            )

        return entities

    async def is_available(self) -> bool:
        return True
