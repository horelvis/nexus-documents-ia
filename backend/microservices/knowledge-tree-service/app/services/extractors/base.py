"""
Base extractor for TrustGraph LLM-based triple extraction.

All extractors share the same SGLang HTTP call and JSON parsing logic.
Subclasses implement _build_prompt() and _parse_output() only.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Abstract base for LLM-based triple extractors."""

    EXTRACTOR_NAME: str = "base"

    def __init__(self) -> None:
        # Lazy import to avoid circular deps and allow env override in tests
        try:
            from app.core.config import settings  # type: ignore

            self._sglang_url = getattr(
                settings, "SGLANG_BASE_URL", "http://sglang:8000/v1"
            )
            self._model = getattr(settings, "SGLANG_MODEL", "Qwen/Qwen3-8B")
        except Exception:
            import os

            self._sglang_url = os.getenv(
                "SGLANG_BASE_URL", "http://sglang:8000/v1"
            )
            self._model = os.getenv("SGLANG_MODEL", "Qwen/Qwen3-8B")

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def extract(self, chunk_text: str) -> List[Dict[str, Any]]:
        """Extract triples from a text chunk.

        Returns a list of triple dicts on success, or [] on any failure.
        """
        try:
            prompt = self._build_prompt(chunk_text)
            llm_output = await self._call_llm(prompt)
            return self._parse_output(llm_output, chunk_text)
        except Exception as exc:
            logger.warning(
                "Extractor %s failed for chunk (first 80 chars: %r): %s",
                self.EXTRACTOR_NAME,
                chunk_text[:80],
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Abstract methods — implemented by subclasses
    # ------------------------------------------------------------------

    @abstractmethod
    def _build_prompt(self, chunk_text: str) -> str:
        """Build the LLM prompt for this extractor."""

    @abstractmethod
    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        """Parse LLM JSON output into a list of triple dicts."""

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _call_llm(self, prompt: str) -> str:
        """POST to SGLang /chat/completions and return the message content."""
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4096,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._sglang_url}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _safe_parse_json(self, text: str) -> List[Dict]:
        """Strip markdown fences, parse JSON, unwrap common wrapper keys."""
        # Strip ```json ... ``` or ``` ... ``` fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        cleaned = cleaned.strip()

        try:
            parsed = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.debug(
                "Extractor %s: JSON parse failed, text=%r",
                self.EXTRACTOR_NAME,
                text[:200],
            )
            return []

        # Unwrap dict wrappers like {"results": [...], "entities": [...], "items": [...]}
        if isinstance(parsed, dict):
            for key in ("results", "entities", "items", "relationships", "topics", "definitions", "objects"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            # If dict but no known wrapper key, return empty
            return []

        if isinstance(parsed, list):
            return parsed

        return []

    def _make_triple(
        self,
        subject: str,
        predicate_ontology: str,
        predicate_name: str,
        obj: str,
        object_is_node: bool,
        extraction_method: str,
        source_chunk: str,
    ) -> Dict[str, Any]:
        """Build a standardised triple dict."""
        return {
            "subject": subject,
            "predicate_ontology": predicate_ontology,
            "predicate_name": predicate_name,
            "object": obj,
            "object_is_node": object_is_node,
            "extraction_method": extraction_method,
            "source_chunk": source_chunk[:200],
        }
