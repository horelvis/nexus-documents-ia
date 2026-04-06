"""
Base extractor for TrustGraph LLM-based triple extraction.

All extractors share the same SGLang HTTP call, JSONL parsing, and schema
validation logic.  Subclasses implement _build_prompt() and _parse_output().
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Optional

import httpx
import jsonschema

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Abstract base for LLM-based triple extractors."""

    EXTRACTOR_NAME: str = "base"
    RESPONSE_SCHEMA: ClassVar[Dict[str, Any]] = {}
    _shared_client: ClassVar[Optional[httpx.AsyncClient]] = None

    @classmethod
    def get_shared_client(cls) -> httpx.AsyncClient:
        """Get or create a shared httpx.AsyncClient for all extractors."""
        if cls._shared_client is None or cls._shared_client.is_closed:
            cls._shared_client = httpx.AsyncClient(
                timeout=60.0,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return cls._shared_client

    @classmethod
    async def close_shared_client(cls) -> None:
        """Close the shared client. Call at shutdown or after reindex."""
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None

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

        # Parse metrics
        self._parse_failures: int = 0
        self._validation_failures: int = 0
        self._empty_responses: int = 0

        # Langfuse prompt cache
        self._langfuse_prompt: Optional[Any] = None

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
            if not llm_output or not llm_output.strip():
                self._empty_responses += 1
                return []
            return self._parse_output(llm_output, chunk_text)
        except Exception as exc:
            self._parse_failures += 1
            logger.error(
                "Extractor %s failed for chunk (first 80 chars: %r): %s",
                self.EXTRACTOR_NAME,
                chunk_text[:80],
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Abstract methods -- implemented by subclasses
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
    # JSONL parser (truncation-resilient)
    # ------------------------------------------------------------------

    def _parse_jsonl(self, text: str) -> List[Dict[str, Any]]:
        """Parse JSONL (one JSON object per line), with JSON-array fallback.

        Resilient to:
        - Markdown ```json fences
        - Trailing commas on lines
        - Bracket-only lines ([, ], [])
        - Truncated last line
        - Whole JSON array on a single line
        """
        if not text or not text.strip():
            return []

        # Strip markdown fences
        cleaned = re.sub(
            r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        cleaned = cleaned.strip()

        items: List[Dict[str, Any]] = []
        for line in cleaned.splitlines():
            line = line.strip()
            if not line:
                continue
            # Skip bracket-only lines
            if line in ("[", "]", "[]"):
                continue
            # Strip trailing comma
            if line.endswith(","):
                line = line[:-1].rstrip()
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    # Unwrap common wrapper keys (e.g. {"results": [...]})
                    unwrapped = False
                    for key in ("results", "entities", "items", "relationships",
                                "topics", "definitions", "objects"):
                        if key in parsed and isinstance(parsed[key], list):
                            items.extend(
                                item for item in parsed[key]
                                if isinstance(item, dict)
                            )
                            unwrapped = True
                            break
                    if not unwrapped:
                        items.append(parsed)
                elif isinstance(parsed, list):
                    # Whole JSON array on a single line
                    items.extend(
                        item for item in parsed if isinstance(item, dict)
                    )
            except (json.JSONDecodeError, ValueError):
                continue

        # Fallback to _safe_parse_json if JSONL yielded nothing
        if not items:
            items = self._safe_parse_json(text)

        return items

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    def _validate_items(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate items against RESPONSE_SCHEMA. Returns valid items only."""
        if not self.RESPONSE_SCHEMA:
            return items

        valid: List[Dict[str, Any]] = []
        for item in items:
            try:
                jsonschema.validate(instance=item, schema=self.RESPONSE_SCHEMA)
                valid.append(item)
            except jsonschema.ValidationError as exc:
                self._validation_failures += 1
                logger.warning(
                    "Extractor %s: schema validation failed for item %r: %s",
                    self.EXTRACTOR_NAME,
                    item,
                    exc.message,
                )
        return valid

    # ------------------------------------------------------------------
    # Langfuse prompt helper
    # ------------------------------------------------------------------

    def _get_langfuse_prompt(self, prompt_name: str) -> Optional[str]:
        """Load a prompt from Langfuse by name (label='production').

        Caches the result in self._langfuse_prompt.
        Returns None on any failure (caller should use hardcoded fallback).
        """
        if self._langfuse_prompt is not None:
            return self._langfuse_prompt

        try:
            from app.services.langfuse_client import get_langfuse  # type: ignore

            langfuse = get_langfuse()
            prompt_obj = langfuse.get_prompt(prompt_name, label="production")
            self._langfuse_prompt = prompt_obj.compile()
            return self._langfuse_prompt
        except Exception as exc:
            logger.debug(
                "Extractor %s: Langfuse prompt '%s' unavailable: %s",
                self.EXTRACTOR_NAME,
                prompt_name,
                exc,
            )
            return None

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
            # No response_format constraint -- JSONL is not valid JSON
            # Disable Qwen3.5 thinking mode -- extraction tasks don't need
            # chain-of-thought and thinking consumes the token budget,
            # leaving content=null.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        client = self.get_shared_client()
        resp = await client.post(
            f"{self._sglang_url}/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        msg = data["choices"][0]["message"]
        content = msg.get("content")
        # Fallback: some Qwen3.5 builds put output in reasoning_content
        if content is None:
            content = msg.get("reasoning_content", "")
        return content or ""

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
            self._parse_failures += 1
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
            # Single item dict (not a wrapper) -- treat as a one-element array.
            # This handles Qwen3.5 returning {"entity": "...", "definition": "..."}
            # instead of [{"entity": "...", "definition": "..."}] when using
            # response_format: json_object.
            return [parsed]

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
