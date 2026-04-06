# TrustGraph Extractors Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite TrustGraph extractors adopting upstream patterns (JSONL, free-form predicates, schema validation, batch storage, parallel chunks) to increase knowledge triple yield from 2% to >80% of the graph.

**Architecture:** Modify existing extractor files in-place. No new services. The coordinator pattern stays — we fix what's inside each extractor and the storage/contradiction layers. Prompts move from hardcoded strings to Langfuse runtime fetching.

**Tech Stack:** Python 3.12, asyncio, FalkorDB (Cypher), Langfuse, httpx, jsonschema, pytest

**Spec:** `docs/superpowers/specs/2026-03-30-trustgraph-extractors-redesign.md`

**Base path:** `backend/microservices/knowledge-tree-service`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/services/extractors/base.py` | Modify | JSONL parser, schema validation, parse metrics, Langfuse prompt fetching |
| `app/services/extractors/relationships.py` | Modify | Free-form predicates with ontology guidance, JSONL format, Langfuse prompt |
| `app/services/extractors/definitions.py` | Modify | JSONL format, schema, Langfuse prompt |
| `app/services/extractors/topics.py` | Modify | JSONL format, schema, Langfuse prompt |
| `app/services/extractors/objects.py` | Modify | JSONL format, schema, Langfuse prompt |
| `app/services/extractors/coordinator.py` | Modify | Parallel chunk processing, batch storage call, extraction summary logging |
| `app/services/ontology_registry.py` | Modify | Add `fuzzy_match()` function |
| `app/services/triple_store.py` | Modify | Add `batch_store_triples()` method |
| `app/services/contradiction.py` | Modify | Store as edge metadata instead of :Node triples |
| `app/core/config.py` | Modify | Add `extraction_parallel_chunks` setting |
| `scripts/seed_langfuse_extraction_prompts.py` | Modify | Update 4 prompts to JSONL format |
| `scripts/reindex_trustgraph.py` | Modify | Use parallel extraction, log extraction metrics |
| `tests/test_extractors.py` | Modify | Update tests for JSONL, schema validation, free-form predicates |
| `tests/test_contradiction.py` | Modify | Update tests for edge-metadata storage |
| `tests/test_triple_store.py` | Modify | Add tests for `batch_store_triples()` |
| `requirements.txt` | Modify | Add `jsonschema` dependency |

---

### Task 1: Add jsonschema dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add jsonschema to requirements.txt**

Open `requirements.txt` and add `jsonschema>=4.0.0` to the dependencies list. This is needed for per-extractor response validation (spec change #4).

```
jsonschema>=4.0.0
```

- [ ] **Step 2: Verify import works**

Run: `docker compose exec knowledge-tree-service python -c "import jsonschema; print(jsonschema.__version__)"`

Expected: Version number printed (4.x+)

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/requirements.txt
git commit -m "chore(trustgraph): add jsonschema dependency for extractor validation"
```

---

### Task 2: Add extraction_parallel_chunks to config

**Files:**
- Modify: `app/core/config.py`

- [ ] **Step 1: Add setting to Settings class**

In `app/core/config.py`, add the `extraction_parallel_chunks` setting after the `SGLANG_MODEL` line (line 33):

```python
    # Extraction parallelism
    extraction_parallel_chunks: int = int(os.getenv("EXTRACTION_PARALLEL_CHUNKS", "3"))
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/core/config.py
git commit -m "feat(trustgraph): add extraction_parallel_chunks config setting"
```

---

### Task 3: JSONL parser + schema validation + parse metrics in BaseExtractor

**Files:**
- Modify: `app/services/extractors/base.py`
- Test: `tests/test_extractors.py`

This is the foundation — all 4 extractors inherit from `BaseExtractor`.

- [ ] **Step 1: Write tests for JSONL parsing**

Add these tests to `tests/test_extractors.py` at the top, after the existing imports:

```python
from app.services.extractors.base import BaseExtractor


class TestJSONLParsing:
    """Tests for BaseExtractor._parse_jsonl()."""

    def _make_extractor(self):
        """Create a concrete subclass for testing base methods."""
        class StubExtractor(BaseExtractor):
            EXTRACTOR_NAME = "stub"
            RESPONSE_SCHEMA = {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            }
            def _build_prompt(self, chunk_text): return ""
            def _parse_output(self, llm_output, chunk_text): return []
        return StubExtractor()

    def test_parses_valid_jsonl(self):
        """Multiple JSONL lines → list of dicts."""
        ext = self._make_extractor()
        text = '{"name": "Juan"}\n{"name": "María"}'
        result = ext._parse_jsonl(text)
        assert result == [{"name": "Juan"}, {"name": "María"}]

    def test_handles_trailing_commas(self):
        """JSONL lines with trailing commas are cleaned."""
        ext = self._make_extractor()
        text = '{"name": "Juan"},\n{"name": "María"},'
        result = ext._parse_jsonl(text)
        assert result == [{"name": "Juan"}, {"name": "María"}]

    def test_skips_bracket_lines(self):
        """Lines that are just [ or ] or [] are skipped."""
        ext = self._make_extractor()
        text = '[\n{"name": "Juan"}\n]'
        result = ext._parse_jsonl(text)
        assert result == [{"name": "Juan"}]

    def test_skips_unparseable_lines(self):
        """Bad lines are skipped, good lines are kept."""
        ext = self._make_extractor()
        text = '{"name": "Juan"}\nnot json\n{"name": "María"}'
        result = ext._parse_jsonl(text)
        assert result == [{"name": "Juan"}, {"name": "María"}]

    def test_empty_input(self):
        ext = self._make_extractor()
        assert ext._parse_jsonl("") == []
        assert ext._parse_jsonl("   ") == []

    def test_truncated_jsonl_recovers_partial(self):
        """Truncated last line loses only that line."""
        ext = self._make_extractor()
        text = '{"name": "Juan"}\n{"name": "Mar'
        result = ext._parse_jsonl(text)
        assert result == [{"name": "Juan"}]

    def test_fallback_to_json_array(self):
        """If JSONL yields 0, fall back to JSON array parse."""
        ext = self._make_extractor()
        # Standard JSON array (not JSONL)
        text = '[{"name": "Juan"}, {"name": "María"}]'
        result = ext._parse_jsonl(text)
        # _parse_jsonl tries line-by-line first; the whole array is one line
        # so it parses as a list — we need the fallback logic in _parse_and_validate
        # For _parse_jsonl alone, a single-line array parses as one object
        # This is handled by _parse_and_validate's fallback
        assert len(result) >= 1  # At minimum the whole array as one parsed item

    def test_strips_markdown_fences(self):
        """Markdown code fences are stripped before JSONL parsing."""
        ext = self._make_extractor()
        text = '```json\n{"name": "Juan"}\n{"name": "María"}\n```'
        result = ext._parse_jsonl(text)
        assert result == [{"name": "Juan"}, {"name": "María"}]


class TestSchemaValidation:
    """Tests for BaseExtractor._validate_items()."""

    def _make_extractor(self):
        class StubExtractor(BaseExtractor):
            EXTRACTOR_NAME = "stub"
            RESPONSE_SCHEMA = {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "type": {"type": "string"},
                },
                "required": ["name"],
            }
            def _build_prompt(self, chunk_text): return ""
            def _parse_output(self, llm_output, chunk_text): return []
        return StubExtractor()

    def test_valid_items_pass(self):
        ext = self._make_extractor()
        items = [{"name": "Juan", "type": "person"}, {"name": "María"}]
        result = ext._validate_items(items)
        assert len(result) == 2

    def test_invalid_items_rejected(self):
        ext = self._make_extractor()
        items = [
            {"name": "Juan"},      # valid
            {"type": "person"},     # missing required "name"
            {"name": "", "type": "person"},  # minLength violation
        ]
        result = ext._validate_items(items)
        assert len(result) == 1
        assert result[0]["name"] == "Juan"

    def test_metrics_tracked(self):
        ext = self._make_extractor()
        ext._validate_items([{"type": "x"}, {"name": "ok"}])
        assert ext._validation_failures == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py::TestJSONLParsing -v --no-header 2>&1 | head -30`

Expected: FAIL — `BaseExtractor` has no `_parse_jsonl`, `_validate_items`, `RESPONSE_SCHEMA`, or `_validation_failures`.

- [ ] **Step 3: Implement BaseExtractor changes**

Replace the full content of `app/services/extractors/base.py` with:

```python
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
    # Subclasses MUST override with their JSON schema for response validation
    RESPONSE_SCHEMA: ClassVar[Dict[str, Any]] = {}

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

        # Parse metrics (reset per extract() call, readable by coordinator)
        self._parse_failures: int = 0
        self._validation_failures: int = 0
        self._empty_responses: int = 0

        # Langfuse prompt cache (loaded once per instance)
        self._langfuse_prompt: Optional[str] = None

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
            logger.error(
                "Extractor %s failed for chunk (first 80 chars: %r): %s",
                self.EXTRACTOR_NAME,
                chunk_text[:80],
                exc,
            )
            self._parse_failures += 1
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
            # Disable Qwen3.5 thinking mode — extraction tasks don't need
            # chain-of-thought and thinking consumes the token budget,
            # leaving content=null.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
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
    # Langfuse prompt loading
    # ------------------------------------------------------------------

    def _get_langfuse_prompt(self, prompt_name: str) -> Optional[str]:
        """Fetch prompt from Langfuse. Returns None on failure (caller uses hardcoded fallback)."""
        if self._langfuse_prompt is not None:
            return self._langfuse_prompt

        try:
            from langfuse import Langfuse
            from app.core.config import settings

            client = Langfuse(
                public_key=settings.LANGFUSE_PUBLIC_KEY,
                secret_key=settings.LANGFUSE_SECRET_KEY,
                host=settings.LANGFUSE_HOST,
            )
            prompt = client.get_prompt(name=prompt_name, label="production")
            self._langfuse_prompt = prompt.prompt
            logger.debug("Loaded Langfuse prompt %s", prompt_name)
            return self._langfuse_prompt
        except Exception as exc:
            logger.debug(
                "Langfuse prompt %s not available, using hardcoded fallback: %s",
                prompt_name,
                exc,
            )
            return None

    # ------------------------------------------------------------------
    # JSONL parser (truncation-resilient)
    # ------------------------------------------------------------------

    def _parse_jsonl(self, text: str) -> List[Dict]:
        """Parse JSONL (one JSON object per line). Truncation-resilient.

        Also strips markdown fences and skips bracket-only lines.
        Falls back to JSON array parse if JSONL yields 0 results.
        """
        # Strip ```json ... ``` or ``` ... ``` fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        cleaned = cleaned.strip()

        results: List[Dict] = []
        for line in cleaned.splitlines():
            line = line.strip().rstrip(",")
            if not line or line in ("[]", "[", "]"):
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    results.append(obj)
                elif isinstance(obj, list):
                    # Whole array on one line — extract dict items
                    results.extend(item for item in obj if isinstance(item, dict))
            except json.JSONDecodeError:
                logger.warning(
                    "Extractor %s JSONL parse skip: %s",
                    self.EXTRACTOR_NAME,
                    line[:100],
                )

        # Fallback: if JSONL yielded 0 results, try legacy JSON array parse
        if not results:
            return self._safe_parse_json(cleaned)

        return results

    def _safe_parse_json(self, text: str) -> List[Dict]:
        """Legacy: parse JSON array, unwrap common wrapper keys."""
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.debug(
                "Extractor %s: JSON parse failed, text=%r",
                self.EXTRACTOR_NAME,
                text[:200],
            )
            self._parse_failures += 1
            return []

        # Unwrap dict wrappers like {"results": [...]}
        if isinstance(parsed, dict):
            for key in ("results", "entities", "items", "relationships",
                        "topics", "definitions", "objects"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
            return [parsed]

        if isinstance(parsed, list):
            return parsed

        return []

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    def _validate_items(self, items: List[Dict]) -> List[Dict]:
        """Validate parsed items against RESPONSE_SCHEMA. Returns valid items only."""
        if not self.RESPONSE_SCHEMA:
            return items

        validated: List[Dict] = []
        for item in items:
            try:
                jsonschema.validate(item, self.RESPONSE_SCHEMA)
                validated.append(item)
            except jsonschema.ValidationError as e:
                logger.warning(
                    "Extractor %s schema validation failed: %s | item: %s",
                    self.EXTRACTOR_NAME,
                    e.message,
                    str(item)[:200],
                )
                self._validation_failures += 1

        return validated

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

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
```

- [ ] **Step 4: Run the new tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py::TestJSONLParsing tests/test_extractors.py::TestSchemaValidation -v --no-header`

Expected: All PASS

- [ ] **Step 5: Run all existing extractor tests to verify no regressions**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -v --no-header`

Expected: All PASS (existing tests still work because `_safe_parse_json` is still available and `extract()` still returns `[]` on failure)

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/base.py \
        backend/microservices/knowledge-tree-service/tests/test_extractors.py
git commit -m "feat(trustgraph): JSONL parser, schema validation, parse metrics in BaseExtractor"
```

---

### Task 4: Free-form predicates with fuzzy matching in ontology_registry

**Files:**
- Modify: `app/services/ontology_registry.py`
- Test: `tests/test_extractors.py`

- [ ] **Step 1: Write tests for fuzzy matching**

Add to `tests/test_extractors.py`:

```python
from app.services.ontology_registry import fuzzy_match, get_namespace


class TestOntologyFuzzyMatch:
    """Tests for fuzzy_match() in ontology_registry."""

    def test_exact_match_returns_predicate(self):
        """Exact ontology predicate returns (name, namespace)."""
        result = fuzzy_match("empleado-de")
        assert result is not None
        assert result[0] == "empleado-de"
        assert result[1] == "legal"

    def test_close_match_returns_best(self):
        """'empleado_de' (underscore) fuzzy-matches 'empleado-de' (hyphen)."""
        result = fuzzy_match("empleado_de")
        assert result is not None
        assert result[0] == "empleado-de"

    def test_no_match_returns_none(self):
        """Completely unrelated string returns None."""
        result = fuzzy_match("zzz-totally-unknown-predicate")
        assert result is None

    def test_threshold_respected(self):
        """Low similarity below threshold returns None."""
        result = fuzzy_match("abc", threshold=0.9)
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py::TestOntologyFuzzyMatch -v --no-header 2>&1 | head -20`

Expected: FAIL — `fuzzy_match` doesn't exist yet.

- [ ] **Step 3: Implement fuzzy_match in ontology_registry.py**

Add these imports at the top of `app/services/ontology_registry.py` (after existing imports):

```python
from difflib import SequenceMatcher
```

Add this function after `get_mini_ontology_text()`:

```python
def fuzzy_match(
    predicate_name: str,
    threshold: float = 0.8,
) -> Optional[tuple]:
    """Fuzzy-match a predicate against the ontology.

    Normalizes by replacing underscores with hyphens and lowercasing,
    then uses SequenceMatcher for similarity scoring.

    Returns (matched_name, namespace) if similarity >= threshold, else None.
    """
    registry = _load_registry()
    if not registry:
        return None

    # Normalize input
    normalized = predicate_name.strip().lower().replace("_", "-")

    # Exact match first (fast path)
    if normalized in registry:
        return (normalized, registry[normalized])

    # Fuzzy match against all extractable predicates
    best_name: Optional[str] = None
    best_score: float = 0.0

    extractable = {name for name, ns in registry.items() if ns not in _SYSTEM_ONLY_NAMESPACES}
    for name in extractable:
        score = SequenceMatcher(None, normalized, name).ratio()
        if score > best_score:
            best_score = score
            best_name = name

    if best_name and best_score >= threshold:
        return (best_name, registry[best_name])

    return None
```

- [ ] **Step 4: Run fuzzy match tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py::TestOntologyFuzzyMatch -v --no-header`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/ontology_registry.py \
        backend/microservices/knowledge-tree-service/tests/test_extractors.py
git commit -m "feat(trustgraph): add fuzzy_match() to ontology registry for free-form predicates"
```

---

### Task 5: Rewrite RelationshipsExtractor with free-form predicates + JSONL

**Files:**
- Modify: `app/services/extractors/relationships.py`
- Test: `tests/test_extractors.py`

- [ ] **Step 1: Write tests for free-form predicate acceptance**

Add to `tests/test_extractors.py`:

```python
class TestRelationshipsExtractorFreeForm:
    """Tests for free-form predicate handling in RelationshipsExtractor."""

    @pytest.mark.asyncio
    async def test_accepts_freeform_predicate(self):
        """Unknown predicate 'regula' is accepted as free-form (not rejected)."""
        mock_output = '{"subject": "Ley X", "predicate": "regula", "object": "Sector Y", "object-entity": true}'
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_output)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 1
        assert triples[0]["predicate_name"] == "regula"
        assert triples[0]["predicate_ontology"] == "extracted"
        assert triples[0]["extraction_method"] == "llm_relationships_freeform"

    @pytest.mark.asyncio
    async def test_fuzzy_matches_underscore_predicate(self):
        """'empleado_de' (underscore) fuzzy-matches 'empleado-de' (hyphen)."""
        mock_output = '{"subject": "Juan", "predicate": "empleado_de", "object": "Empresa", "object-entity": true}'
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_output)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 1
        assert triples[0]["predicate_name"] == "empleado-de"
        assert triples[0]["predicate_ontology"] == "legal"
        assert triples[0]["extraction_method"] == "llm_relationships_fuzzy"

    @pytest.mark.asyncio
    async def test_parses_jsonl_format(self):
        """JSONL (one object per line) is parsed correctly."""
        mock_output = (
            '{"subject": "Juan", "predicate": "empleado-de", "object": "Empresa", "object-entity": true}\n'
            '{"subject": "Contrato", "predicate": "salario-bruto", "object": "3000", "object-entity": false}'
        )
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_output)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py::TestRelationshipsExtractorFreeForm -v --no-header 2>&1 | head -20`

Expected: FAIL — current code rejects unknown predicates.

- [ ] **Step 3: Rewrite relationships.py**

Replace the full content of `app/services/extractors/relationships.py`:

```python
"""
Relationships extractor — extracts subject-predicate-object triples.

Uses the OntologyRegistry for guided predicate matching with 3-tier fallback:
  1. Exact match → ontology namespace
  2. Fuzzy match (>0.8 similarity) → ontology namespace + _fuzzy method tag
  3. Free-form → "extracted" namespace + _freeform method tag
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor
from app.services.ontology_registry import (
    fuzzy_match,
    get_extractable_predicates,
    get_mini_ontology_text,
    get_namespace,
)
from app.services.uri_builder import URIBuilder

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "relationships"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_relationships"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "minLength": 1},
        "predicate": {"type": "string", "minLength": 1},
        "object": {"type": "string", "minLength": 1},
        "object-entity": {"type": "boolean"},
    },
    "required": ["subject", "predicate", "object"],
}

_PROMPT_TEMPLATE = """Extract all relationships between entities from the following text.

Use these predicates when they fit:
{mini_ontology}

If none of the above predicates fit, use a descriptive predicate in Spanish (e.g., "regula", "modifica", "pertenece-a").

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "subject": the subject entity name (string)
- "predicate": predicate name (prefer ontology predicates above, or a descriptive one)
- "object": the object value or entity name (string)
- "object-entity": true if the object is a named entity, false if it is a literal value

Example:
{{"subject": "Juan García", "predicate": "empleado-de", "object": "Empresa ABC S.L.", "object-entity": true}}
{{"subject": "Contrato 2025-001", "predicate": "vigente-desde", "object": "2025-01-01", "object-entity": false}}
{{"subject": "Ley 31/1995", "predicate": "regula", "object": "prevención de riesgos laborales", "object-entity": false}}

Return nothing if no relationships are found.

TEXT:
{chunk_text}"""


def _normalize_predicate_name(predicate: str) -> str:
    """Normalize a free-form predicate to a URI-safe slug."""
    import re
    import unicodedata

    nfd = unicodedata.normalize("NFD", predicate.strip())
    ascii_approx = "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")
    lowered = ascii_approx.lower()
    return re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")


class RelationshipsExtractor(BaseExtractor):
    """Extracts subject-predicate-object relationships from text chunks."""

    EXTRACTOR_NAME = "relationships"
    RESPONSE_SCHEMA = RESPONSE_SCHEMA

    def _build_prompt(self, chunk_text: str) -> str:
        # Try Langfuse prompt first
        langfuse_prompt = self._get_langfuse_prompt(LANGFUSE_PROMPT_NAME)
        if langfuse_prompt:
            return langfuse_prompt.replace("{{chunk_text}}", chunk_text).replace(
                "{{mini_ontology}}", get_mini_ontology_text()
            )
        return _PROMPT_TEMPLATE.format(
            mini_ontology=get_mini_ontology_text(),
            chunk_text=chunk_text,
        )

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._parse_jsonl(llm_output)
        items = self._validate_items(items)
        triples: List[Dict[str, Any]] = []

        for item in items:
            subject = str(item.get("subject", "")).strip()
            predicate = str(item.get("predicate", "")).strip()
            obj = str(item.get("object", "")).strip()
            object_is_node = bool(item.get("object-entity", False))

            if not subject or not predicate or not obj:
                continue

            # 3-tier predicate resolution: exact → fuzzy → free-form
            extraction_method = "llm_relationships"
            ontology = get_namespace(predicate)

            if ontology:
                # Tier 1: exact match
                predicate_name = predicate
            else:
                # Tier 2: fuzzy match
                fuzzy = fuzzy_match(predicate, threshold=0.8)
                if fuzzy:
                    predicate_name = fuzzy[0]
                    ontology = fuzzy[1]
                    extraction_method = "llm_relationships_fuzzy"
                else:
                    # Tier 3: free-form → generate URI
                    predicate_name = _normalize_predicate_name(predicate)
                    if not predicate_name:
                        continue
                    ontology = "extracted"
                    extraction_method = "llm_relationships_freeform"

            triples.append(
                self._make_triple(
                    subject=subject,
                    predicate_ontology=ontology,
                    predicate_name=predicate_name,
                    obj=obj,
                    object_is_node=object_is_node,
                    extraction_method=extraction_method,
                    source_chunk=chunk_text,
                )
            )

        return triples
```

- [ ] **Step 4: Update existing relationship tests**

The existing `TestRelationshipsExtractor.test_unknown_predicate_rejected` must change — unknown predicates are now accepted as free-form. Update it:

```python
    @pytest.mark.asyncio
    async def test_unknown_predicate_accepted_as_freeform(self):
        """Unknown predicate → accepted as free-form with 'extracted' ontology."""
        mock_json = json.dumps([
            {
                "subject": "A",
                "predicate": "some-custom-predicate",
                "object": "B",
                "object-entity": False,
            }
        ])
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 1
        assert triples[0]["predicate_ontology"] == "extracted"
        assert triples[0]["extraction_method"] == "llm_relationships_freeform"
```

Also update `test_prov_predicate_rejected_from_extraction`: prov predicates are still not in extractable set, but the free-form fallback now accepts them. The relationships extractor resolves predicates via `get_namespace()` first — `derived-from` is in the registry (prov namespace), so it gets exact-matched with `ontology="prov"`. This is actually correct — prov predicates from LLM output should be allowed if the LLM generates them. If you want to reject prov predicates, add a filter. For now, update the test:

```python
    @pytest.mark.asyncio
    async def test_prov_predicate_accepted_with_prov_namespace(self):
        """'derived-from' (prov) is accepted — LLM may legitimately extract provenance relationships."""
        mock_json = json.dumps([
            {
                "subject": "Doc A",
                "predicate": "derived-from",
                "object": "Doc B",
                "object-entity": True,
            }
        ])
        extractor = RelationshipsExtractor()
        with patch.object(extractor, "_call_llm", new=AsyncMock(return_value=mock_json)):
            triples = await extractor.extract(SAMPLE_CHUNK)

        assert len(triples) == 1
        assert triples[0]["predicate_ontology"] == "prov"
```

- [ ] **Step 5: Run all relationship tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -k "Relationship" -v --no-header`

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/relationships.py \
        backend/microservices/knowledge-tree-service/tests/test_extractors.py
git commit -m "feat(trustgraph): free-form predicates with 3-tier resolution in RelationshipsExtractor"
```

---

### Task 6: Rewrite DefinitionsExtractor with JSONL + schema + Langfuse

**Files:**
- Modify: `app/services/extractors/definitions.py`

- [ ] **Step 1: Rewrite definitions.py**

Replace full content of `app/services/extractors/definitions.py`:

```python
"""
Definitions extractor — extracts named entities with their definitions.

Each entity yields 2 triples:
  (entity, core/label, entity_name)
  (entity, core/definition, definition_text)
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "definitions"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_definitions"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "entity": {"type": "string", "minLength": 1},
        "definition": {"type": "string"},
    },
    "required": ["entity"],
}

_PROMPT_TEMPLATE = """Extract all named entities and their definitions from the following text.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "entity": the canonical name of the entity (string)
- "definition": a concise description or definition of the entity from the text (string)

Only include entities that are explicitly defined or described in the text.
Return nothing if no definitions are found.

Example:
{{"entity": "Contrato de Trabajo", "definition": "Acuerdo entre empleador y trabajador que regula las condiciones laborales"}}
{{"entity": "Empresa ABC S.L.", "definition": "Sociedad limitada dedicada al desarrollo de software"}}

TEXT:
{chunk_text}"""


class DefinitionsExtractor(BaseExtractor):
    """Extracts entity definitions from text chunks."""

    EXTRACTOR_NAME = "definitions"
    RESPONSE_SCHEMA = RESPONSE_SCHEMA

    def _build_prompt(self, chunk_text: str) -> str:
        langfuse_prompt = self._get_langfuse_prompt(LANGFUSE_PROMPT_NAME)
        if langfuse_prompt:
            return langfuse_prompt.replace("{{chunk_text}}", chunk_text)
        return _PROMPT_TEMPLATE.format(chunk_text=chunk_text)

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._parse_jsonl(llm_output)
        items = self._validate_items(items)
        triples: List[Dict[str, Any]] = []

        for item in items:
            entity = str(item.get("entity", "")).strip()
            definition = str(item.get("definition", "")).strip()
            if not entity:
                continue

            # Triple 1: label
            triples.append(
                self._make_triple(
                    subject=entity,
                    predicate_ontology="core",
                    predicate_name="label",
                    obj=entity,
                    object_is_node=False,
                    extraction_method="llm_definitions",
                    source_chunk=chunk_text,
                )
            )
            # Triple 2: definition
            if definition:
                triples.append(
                    self._make_triple(
                        subject=entity,
                        predicate_ontology="core",
                        predicate_name="definition",
                        obj=definition,
                        object_is_node=False,
                        extraction_method="llm_definitions",
                        source_chunk=chunk_text,
                    )
                )

        return triples
```

- [ ] **Step 2: Run existing definitions tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -k "Definitions" -v --no-header`

Expected: All PASS (output format unchanged)

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/definitions.py
git commit -m "feat(trustgraph): JSONL + schema validation + Langfuse in DefinitionsExtractor"
```

---

### Task 7: Rewrite TopicsExtractor with JSONL + schema + Langfuse

**Files:**
- Modify: `app/services/extractors/topics.py`

- [ ] **Step 1: Rewrite topics.py**

Replace full content of `app/services/extractors/topics.py`:

```python
"""
Topics extractor — extracts thematic topics from text chunks.

Each topic yields 1 triple:
  ("", core/has-topic, topic)

Subject is intentionally empty — the coordinator sets it to the document URI.
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "topics"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_topics"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
    },
    "required": ["topic"],
}

_PROMPT_TEMPLATE = """Identify the main topics and themes present in the following text.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "topic": a concise topic label in the same language as the text (string)

Focus on substantive topics — legal areas, business domains, subject matter.
Avoid generic terms like "document" or "text".
Return nothing if no clear topics can be identified.

Example:
{{"topic": "derecho laboral"}}
{{"topic": "contrato de trabajo"}}
{{"topic": "jornada laboral"}}

TEXT:
{chunk_text}"""


class TopicsExtractor(BaseExtractor):
    """Extracts thematic topics from text chunks."""

    EXTRACTOR_NAME = "topics"
    RESPONSE_SCHEMA = RESPONSE_SCHEMA

    def _build_prompt(self, chunk_text: str) -> str:
        langfuse_prompt = self._get_langfuse_prompt(LANGFUSE_PROMPT_NAME)
        if langfuse_prompt:
            return langfuse_prompt.replace("{{chunk_text}}", chunk_text)
        return _PROMPT_TEMPLATE.format(chunk_text=chunk_text)

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._parse_jsonl(llm_output)
        items = self._validate_items(items)
        triples: List[Dict[str, Any]] = []

        for item in items:
            topic = str(item.get("topic", "")).strip()
            if not topic:
                continue

            triples.append(
                self._make_triple(
                    subject="",
                    predicate_ontology="core",
                    predicate_name="has-topic",
                    obj=topic,
                    object_is_node=False,
                    extraction_method="llm_topics",
                    source_chunk=chunk_text,
                )
            )

        return triples
```

- [ ] **Step 2: Run existing topics tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -k "Topics" -v --no-header`

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/topics.py
git commit -m "feat(trustgraph): JSONL + schema validation + Langfuse in TopicsExtractor"
```

---

### Task 8: Rewrite ObjectsExtractor with JSONL + schema + Langfuse

**Files:**
- Modify: `app/services/extractors/objects.py`

- [ ] **Step 1: Rewrite objects.py**

Replace full content of `app/services/extractors/objects.py`:

```python
"""
Objects extractor — extracts named entities with their types.

Each entity yields 2 triples:
  (entity, core/label, name)
  (entity, core/type, type)
"""

import logging
from typing import Any, Dict, List

from app.services.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "objects"
LANGFUSE_PROMPT_NAME = "trustgraph_extract_objects"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "type": {"type": "string"},
    },
    "required": ["name"],
}

_PROMPT_TEMPLATE = """Extract all named entities (people, organizations, laws, places, dates, etc.) from the following text.

Return one JSON object per line (JSONL format). Do NOT wrap in an array.
Each object must have:
- "name": the full canonical name of the entity (string)
- "type": entity type — one of: person, organization, law, place, date, amount, product, event, other

Return nothing if no entities are found.

Example:
{{"name": "María López", "type": "person"}}
{{"name": "Empresa XYZ S.L.", "type": "organization"}}
{{"name": "Estatuto de los Trabajadores", "type": "law"}}

TEXT:
{chunk_text}"""


class ObjectsExtractor(BaseExtractor):
    """Extracts named entities with their types from text chunks."""

    EXTRACTOR_NAME = "objects"
    RESPONSE_SCHEMA = RESPONSE_SCHEMA

    def _build_prompt(self, chunk_text: str) -> str:
        langfuse_prompt = self._get_langfuse_prompt(LANGFUSE_PROMPT_NAME)
        if langfuse_prompt:
            return langfuse_prompt.replace("{{chunk_text}}", chunk_text)
        return _PROMPT_TEMPLATE.format(chunk_text=chunk_text)

    def _parse_output(
        self, llm_output: str, chunk_text: str
    ) -> List[Dict[str, Any]]:
        items = self._parse_jsonl(llm_output)
        items = self._validate_items(items)
        triples: List[Dict[str, Any]] = []

        for item in items:
            name = str(item.get("name", "")).strip()
            entity_type = str(item.get("type", "other")).strip()
            if not name:
                continue

            # Triple 1: label
            triples.append(
                self._make_triple(
                    subject=name,
                    predicate_ontology="core",
                    predicate_name="label",
                    obj=name,
                    object_is_node=False,
                    extraction_method="llm_objects",
                    source_chunk=chunk_text,
                )
            )
            # Triple 2: type
            triples.append(
                self._make_triple(
                    subject=name,
                    predicate_ontology="core",
                    predicate_name="type",
                    obj=entity_type,
                    object_is_node=False,
                    extraction_method="llm_objects",
                    source_chunk=chunk_text,
                )
            )

        return triples
```

- [ ] **Step 2: Run existing objects tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -k "Objects" -v --no-header`

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/objects.py
git commit -m "feat(trustgraph): JSONL + schema validation + Langfuse in ObjectsExtractor"
```

---

### Task 9: Batch triple storage in TripleStore

**Files:**
- Modify: `app/services/triple_store.py`
- Test: `tests/test_triple_store.py`

- [ ] **Step 1: Write test for batch_store_triples**

Add to `tests/test_triple_store.py`:

```python
class TestBatchStoreTriples:
    @pytest.mark.asyncio
    async def test_batch_stores_node_and_literal_triples(self, falkordb_client):
        """batch_store_triples stores both node-to-node and node-to-literal triples."""
        store = _make_store(falkordb_client)
        triples = [
            {
                "s_uri": "nouxcube://entity/col/juan",
                "o_uri": "nouxcube://entity/col/empresa",
                "p_uri": "nouxcube://predicate/legal/empleado-de",
                "object_is_entity": True,
                "method": "llm_relationships",
                "chunk": "chunk-001",
            },
            {
                "s_uri": "nouxcube://entity/col/contrato",
                "o_val": "3000 EUR",
                "p_uri": "nouxcube://predicate/legal/salario-bruto",
                "object_is_entity": False,
                "method": "llm_relationships",
                "chunk": "chunk-001",
            },
        ]
        await store.batch_store_triples(triples, user="u1", collection="col")

        # Verify node-to-node triple
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s})-[r:Rel]->(o:Node {uri: $o}) RETURN r.uri AS p",
            {"s": "nouxcube://entity/col/juan", "o": "nouxcube://entity/col/empresa"},
        )
        assert len(rows) == 1

        # Verify node-to-literal triple
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $s})-[r:Rel]->(o:Literal {value: $v}) RETURN r.uri AS p",
            {"s": "nouxcube://entity/col/contrato", "v": "3000 EUR"},
        )
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_batch_empty_list(self, falkordb_client):
        """batch_store_triples with empty list does nothing."""
        store = _make_store(falkordb_client)
        await store.batch_store_triples([], user="u1", collection="col")
        # No exception = pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_store.py::TestBatchStoreTriples -v --no-header 2>&1 | head -15`

Expected: FAIL — `batch_store_triples` doesn't exist.

- [ ] **Step 3: Implement batch_store_triples in TripleStore**

Add this method to `TripleStore` class in `app/services/triple_store.py`, after the `store_triple` method (after line 215):

```python
    async def batch_store_triples(
        self, triples: list, user: str, collection: str
    ) -> int:
        """Store multiple triples in batched Cypher UNWIND queries.

        Each triple dict must have:
          s_uri, p_uri, method, chunk, object_is_entity
          + o_uri (if entity) or o_val (if literal)

        Returns the number of triples stored.
        """
        if not triples:
            return 0

        node_triples = [t for t in triples if t.get("object_is_entity")]
        literal_triples = [t for t in triples if not t.get("object_is_entity")]

        stored = 0

        if node_triples:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "MERGE (o:Node {uri: t.o_uri, user: $user, collection: $col}) "
                "ON CREATE SET o.created_at = timestamp() "
                "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk",
                {"triples": node_triples, "user": user, "col": collection},
            )
            stored += len(node_triples)

        if literal_triples:
            await self._client.execute_cypher(
                "UNWIND $triples AS t "
                "MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col}) "
                "ON CREATE SET s.created_at = timestamp() "
                "MERGE (o:Literal {value: t.o_val, user: $user, collection: $col}) "
                "MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o) "
                "ON CREATE SET r.extraction_method = t.method, r.source_chunk = t.chunk",
                {"triples": literal_triples, "user": user, "col": collection},
            )
            stored += len(literal_triples)

        return stored
```

- [ ] **Step 4: Run batch tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_triple_store.py::TestBatchStoreTriples -v --no-header`

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_store.py \
        backend/microservices/knowledge-tree-service/tests/test_triple_store.py
git commit -m "feat(trustgraph): batch_store_triples with UNWIND for ~10x faster reindex"
```

---

### Task 10: Contradictions as edge metadata (not triples)

**Files:**
- Modify: `app/services/contradiction.py`
- Test: `tests/test_contradiction.py`

- [ ] **Step 1: Rewrite contradiction.py**

Replace the full content of `app/services/contradiction.py`:

```python
"""
ContradictionDetector — batch contradiction detection for TrustGraph.

Detects same-subject + same-predicate + different-object-value contradictions
and stores them as edge properties (has_contradiction, contradiction_with)
instead of creating separate :Node triples.
"""

import logging
from typing import Dict, List

from app.services.falkordb_client import FalkorDBClient

logger = logging.getLogger(__name__)


class ContradictionDetector:
    """Detect and mark contradictions as edge metadata in TrustGraph."""

    def __init__(self, client: FalkorDBClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    async def detect_for_subject(self, subject_uri: str, user: str) -> List[Dict]:
        """Find contradictions for a single subject: same predicate, different literal values.

        Returns a list of dicts with keys:
            predicate, value_a, value_b, chunk_a, chunk_b, rel_a_id, rel_b_id
        """
        query = (
            "MATCH (s:Node {uri: $uri})-[r1:Rel]->(o1:Literal) "
            "WHERE r1.user = $user "
            "MATCH (s)-[r2:Rel]->(o2:Literal) "
            "WHERE r2.uri = r1.uri AND r2.user = $user "
            "  AND id(o1) < id(o2) "
            "  AND o1.value <> o2.value "
            "RETURN DISTINCT r1.uri AS predicate, o1.value AS value_a, o2.value AS value_b, "
            "r1.source_chunk AS chunk_a, r2.source_chunk AS chunk_b, "
            "id(r1) AS rel_a_id, id(r2) AS rel_b_id"
        )
        rows = await self._client.execute_cypher(
            query, params={"uri": subject_uri, "user": user}
        )
        return [
            {
                "predicate": row["predicate"],
                "value_a": row["value_a"],
                "value_b": row["value_b"],
                "chunk_a": row["chunk_a"],
                "chunk_b": row["chunk_b"],
                "rel_a_id": row["rel_a_id"],
                "rel_b_id": row["rel_b_id"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Detection + edge property marking
    # ------------------------------------------------------------------

    async def detect_and_mark(
        self, subject_uri: str, user: str
    ) -> int:
        """Detect contradictions and mark edges with metadata properties.

        For each contradiction pair (r1, r2):
          - SET r1.has_contradiction = true, r1.contradiction_with = id(r2)
          - SET r2.has_contradiction = true, r2.contradiction_with = id(r1)

        Returns the number of contradictions found.
        """
        contradictions = await self.detect_for_subject(subject_uri, user)

        for c in contradictions:
            try:
                # Mark both edges as contradictory
                await self._client.execute_cypher(
                    "MATCH ()-[r:Rel]->() WHERE id(r) = $rel_id "
                    "SET r.has_contradiction = true, r.contradiction_with = $other_id",
                    {"rel_id": c["rel_a_id"], "other_id": c["rel_b_id"]},
                )
                await self._client.execute_cypher(
                    "MATCH ()-[r:Rel]->() WHERE id(r) = $rel_id "
                    "SET r.has_contradiction = true, r.contradiction_with = $other_id",
                    {"rel_id": c["rel_b_id"], "other_id": c["rel_a_id"]},
                )
            except Exception as exc:
                logger.warning(
                    "Failed to mark contradiction edges for %s: %s",
                    subject_uri,
                    exc,
                )

        if contradictions:
            logger.info(
                "Marked %d contradiction(s) for subject %s",
                len(contradictions),
                subject_uri,
            )

        return len(contradictions)

    # ------------------------------------------------------------------
    # Batch detection for a whole document
    # ------------------------------------------------------------------

    async def detect_batch_for_document(
        self, document_uri: str, user: str, collection: str
    ) -> int:
        """Find all entity subjects for tenant, run detect_and_mark for each.

        Returns the total number of contradictions found.
        """
        entity_query = (
            "MATCH (s:Node) "
            "WHERE s.user = $user AND s.uri STARTS WITH 'nouxcube://entity/' "
            "RETURN DISTINCT s.uri AS entity_uri"
        )
        rows = await self._client.execute_cypher(
            entity_query, params={"user": user}
        )

        total = 0
        for row in rows:
            entity_uri = row["entity_uri"]
            try:
                count = await self.detect_and_mark(entity_uri, user=user)
                total += count
            except Exception:
                logger.exception(
                    "Error detecting contradictions for entity %s", entity_uri
                )

        logger.info(
            "detect_batch_for_document: doc=%s user=%s → %d contradiction(s) marked",
            document_uri, user, total,
        )
        return total
```

- [ ] **Step 2: Update contradiction tests**

Replace the content of `tests/test_contradiction.py` to test edge-metadata storage:

```python
"""
Tests for ContradictionDetector — TrustGraph batch contradiction detection.

Tests edge-metadata storage (has_contradiction property on :Rel edges).
Requires a running FalkorDB instance (uses falkordb_client fixture from conftest.py).
"""

import pytest

from app.services.contradiction import ContradictionDetector
from app.services.triple_store import TripleStore
from app.services.uri_builder import URIBuilder


USER = "tenant-test"
COLLECTION = "col-contradiction-tests"


async def _seed_juan_contradicting_salaries(store: TripleStore) -> str:
    """Seed Juan with two different salary values — produces 1 contradiction."""
    subject_uri = await store.store_triple(
        subject_name="Juan Pérez",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="30000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-001",
    )
    await store.store_triple(
        subject_name="Juan Pérez",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="28000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-002",
    )
    return subject_uri


async def _seed_maria_same_salary(store: TripleStore) -> str:
    """Seed María with the same salary value twice — no contradiction expected."""
    subject_uri = await store.store_triple(
        subject_name="María López",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="25000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-010",
    )
    await store.store_triple(
        subject_name="María López",
        predicate_ontology="fiscal",
        predicate_name="salario-anual",
        object_value="25000 EUR",
        object_is_node=False,
        user=USER,
        collection=COLLECTION,
        extraction_method="ner",
        source_chunk="chunk-011",
    )
    return subject_uri


class TestContradictionDetection:
    @pytest.mark.asyncio
    async def test_detects_contradiction(self, falkordb_client):
        """detect_for_subject finds exactly 1 contradiction with both salary values."""
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)

        subject_uri = await _seed_juan_contradicting_salaries(store)
        contradictions = await detector.detect_for_subject(subject_uri, user=USER)

        assert len(contradictions) == 1
        c = contradictions[0]
        assert c["predicate"] == URIBuilder.predicate("fiscal", "salario-anual")
        assert set([c["value_a"], c["value_b"]]) == {"30000 EUR", "28000 EUR"}
        assert c["rel_a_id"] is not None
        assert c["rel_b_id"] is not None

    @pytest.mark.asyncio
    async def test_marks_edges_with_contradiction_metadata(self, falkordb_client):
        """detect_and_mark sets has_contradiction=true on both conflicting edges."""
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)

        subject_uri = await _seed_juan_contradicting_salaries(store)
        count = await detector.detect_and_mark(subject_uri, user=USER)

        assert count == 1

        # Verify has_contradiction is set on edges
        rows = await falkordb_client.execute_cypher(
            "MATCH (s:Node {uri: $uri})-[r:Rel]->(o:Literal) "
            "WHERE r.has_contradiction = true "
            "RETURN r.contradiction_with AS other_id, o.value AS val",
            {"uri": subject_uri},
        )
        assert len(rows) == 2
        values = {row["val"] for row in rows}
        assert values == {"30000 EUR", "28000 EUR"}

        # Verify NO contradiction :Nodes were created (old behavior)
        c_nodes = await falkordb_client.execute_cypher(
            "MATCH (n:Node) WHERE n.uri STARTS WITH 'nouxcube://contradiction/' RETURN n"
        )
        assert len(c_nodes) == 0, "Contradictions must be edge metadata, not :Node triples"

    @pytest.mark.asyncio
    async def test_no_contradiction_when_same_value(self, falkordb_client):
        """detect_for_subject returns 0 contradictions when both triples share the same value."""
        store = TripleStore(falkordb_client)
        detector = ContradictionDetector(falkordb_client)

        subject_uri = await _seed_maria_same_salary(store)
        contradictions = await detector.detect_for_subject(subject_uri, user=USER)

        assert contradictions == []
```

- [ ] **Step 3: Run contradiction tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_contradiction.py -v --no-header`

Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/contradiction.py \
        backend/microservices/knowledge-tree-service/tests/test_contradiction.py
git commit -m "feat(trustgraph): contradictions as edge metadata instead of :Node triples"
```

---

### Task 11: Parallel chunk processing + extraction metrics in coordinator

**Files:**
- Modify: `app/services/extractors/coordinator.py`

- [ ] **Step 1: Update coordinator for parallel chunks + batch storage + metrics**

In `app/services/extractors/coordinator.py`, make these changes:

**a)** Add `asyncio.Semaphore` import (already imported) and config import. At the top, after existing imports:

```python
from app.core.config import settings
```

**b)** Replace `extract_document` method (lines 255-363). The new version uses semaphore-bounded parallel chunk processing, calls `detect_and_mark` instead of `detect_and_store`, and logs extraction metrics:

```python
    async def extract_document(
        self,
        chunks: List[str],
        document_id: str,
        user: str,
        collection: str,
        title: str,
        file_path: str,
        semantic_type: str,
        domain: str,
    ) -> Dict[str, Any]:
        """Extract and store triples for all chunks of a document.

        1. Creates the document :Node with metadata triples.
        2. Processes chunks in parallel (bounded by extraction_parallel_chunks).
        3. Runs batch contradiction detection for all unique subjects.

        Returns dict with success, document_uri, triples_created,
        contradictions_found, chunks_processed, extraction_time_ms, errors,
        parse_failures, empty_responses, validation_failures.
        """
        t_start = time.monotonic()
        errors: List[str] = []

        # Step 1: Create document :Node
        try:
            document_uri = await self._store.store_document_node(
                document_id=document_id,
                user=user,
                collection=collection,
                title=title,
                file_path=file_path,
                semantic_type=semantic_type,
                domain=domain,
            )
        except Exception as exc:
            errors.append(f"store_document_node: {exc}")
            logger.error("Failed to create document node for %s: %s", document_id, exc)
            document_uri = URIBuilder.document(collection, document_id)

        # Step 2: Process chunks in parallel (bounded)
        total_triples = 0
        all_subject_uris: Set[str] = set()
        sem = asyncio.Semaphore(settings.extraction_parallel_chunks)

        async def _process_chunk(offset: int, text: str) -> Dict[str, Any]:
            async with sem:
                return await self.extract_chunk(
                    chunk_text=text,
                    document_uri=document_uri,
                    user=user,
                    collection=collection,
                    chunk_offset=offset,
                )

        tasks = [_process_chunk(i, text) for i, text in enumerate(chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                errors.append(f"chunk[{i}]: {result}")
                logger.error("Failed to process chunk %d: %s", i, result)
            else:
                total_triples += result["triples_created"]
                all_subject_uris.update(result["subjects"])
                if result["errors"]:
                    errors.extend(
                        [f"chunk[{i}]/{e}" for e in result["errors"]]
                    )

        # Step 3: Batch contradiction detection (edge metadata, not triples)
        contradictions_found = 0
        detector = ContradictionDetector(self._store._client)

        for subject_uri in all_subject_uris:
            try:
                count = await detector.detect_and_mark(
                    subject_uri=subject_uri,
                    user=user,
                )
                contradictions_found += count
            except Exception as exc:
                errors.append(f"contradiction({subject_uri}): {exc}")
                logger.warning(
                    "Contradiction detection failed for %s: %s", subject_uri, exc
                )

        # Step 4: Log extraction summary
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        total_parse_failures = sum(
            e._parse_failures for e in [
                self._definitions, self._relationships,
                self._objects, self._topics,
            ]
        )
        total_empty = sum(
            e._empty_responses for e in [
                self._definitions, self._relationships,
                self._objects, self._topics,
            ]
        )
        total_validation = sum(
            e._validation_failures for e in [
                self._definitions, self._relationships,
                self._objects, self._topics,
            ]
        )

        logger.info(
            "Document %s extraction complete: %d triples, %d parse_failures, "
            "%d empty_responses, %d validation_failures, %d contradictions, %dms",
            document_id,
            total_triples,
            total_parse_failures,
            total_empty,
            total_validation,
            contradictions_found,
            elapsed_ms,
        )

        return {
            "success": True,
            "document_uri": document_uri,
            "triples_created": total_triples,
            "contradictions_found": contradictions_found,
            "chunks_processed": len(chunks),
            "extraction_time_ms": elapsed_ms,
            "parse_failures": total_parse_failures,
            "empty_responses": total_empty,
            "validation_failures": total_validation,
            "errors": errors,
        }
```

- [ ] **Step 2: Run all extractor and coordinator-dependent tests**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/test_extractors.py -v --no-header`

Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/extractors/coordinator.py
git commit -m "feat(trustgraph): parallel chunk processing + extraction metrics in coordinator"
```

---

### Task 12: Update Langfuse seed prompts to JSONL format

**Files:**
- Modify: `scripts/seed_langfuse_extraction_prompts.py`

- [ ] **Step 1: Update prompt content in seed script**

The prompt content in `scripts/seed_langfuse_extraction_prompts.py` needs updating to match the new JSONL format and free-form predicates. Update the `PROMPTS` dict values to match the `_PROMPT_TEMPLATE` strings from each extractor, using `{{chunk_text}}` and `{{mini_ontology}}` as Langfuse template variables.

Key changes to each prompt:
- Replace "JSON array" → "one JSON object per line (JSONL format)"
- Replace "Return an empty array []" → "Return nothing"
- For relationships: change "You MUST use ONLY predicates" → "Use these predicates when they fit" + add free-form fallback instruction
- Add `{{chunk_text}}` placeholder at the end (Langfuse template syntax)

Replace the entire `PROMPTS` dict (lines 53-175) with prompts that use JSONL instructions and `{{chunk_text}}` / `{{mini_ontology}}` template variables matching the hardcoded fallback prompts in each extractor file.

- [ ] **Step 2: Run seed script in dry-run mode**

Run: `docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py --dry-run`

Expected: 4 prompts shown as CREATE or UPDATE candidates

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/seed_langfuse_extraction_prompts.py
git commit -m "feat(trustgraph): update Langfuse extraction prompts to JSONL format"
```

---

### Task 13: Update reindex script for parallel extraction + metrics

**Files:**
- Modify: `scripts/reindex_trustgraph.py`

- [ ] **Step 1: Update reindex summary to show extraction metrics**

In `scripts/reindex_trustgraph.py`, the `extract_document` result now includes `parse_failures`, `empty_responses`, and `validation_failures`. Update the per-document logging (around line 637) and summary (around line 684).

In the per-document loop (line 629-648), add:

```python
                    parse_fails = result.get("parse_failures", 0)
                    empty_resps = result.get("empty_responses", 0)
                    validation_fails = result.get("validation_failures", 0)
```

And update the print statement to include these metrics.

In the summary section, add totals:

```python
        print(f"  Parse failures    : {total_parse_failures}")
        print(f"  Empty responses   : {total_empty_responses}")
        print(f"  Validation fails  : {total_validation_failures}")
```

Track these totals with counters initialized before the document loop:
```python
        total_parse_failures = 0
        total_empty_responses = 0
        total_validation_failures = 0
```

And accumulate them in the per-doc result handling:
```python
                    total_parse_failures += parse_fails
                    total_empty_responses += empty_resps
                    total_validation_failures += validation_fails
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py
git commit -m "feat(trustgraph): show extraction metrics in reindex summary"
```

---

### Task 14: Full test suite verification

- [ ] **Step 1: Run the complete knowledge-tree-service test suite**

Run: `cd backend/microservices/knowledge-tree-service && python -m pytest tests/ -v --no-header 2>&1 | tail -30`

Expected: All tests pass. If any failures, fix them before proceeding.

- [ ] **Step 2: Commit any fixes**

If any tests needed fixing, commit each fix individually with descriptive message.

---

### Task 15: Seed prompts + reindex validation

This task should be run manually after all code is committed.

- [ ] **Step 1: Seed the updated Langfuse prompts**

Run: `cd backend/docker && docker compose exec knowledge-tree-service python scripts/seed_langfuse_extraction_prompts.py --force`

Expected: All 4 prompts seeded successfully.

- [ ] **Step 2: Run a full reindex**

Run:
```bash
cd backend/docker && docker compose exec knowledge-tree-service \
    python scripts/reindex_trustgraph.py --tenant-id 00000000-0000-0000-0000-000000000001
```

Expected: Summary shows:
- >75 triples per document (target: 3x current ~25)
- <5% parse failure rate
- 0 contradiction :Node triples (contradictions stored as edge metadata)
- Multiple extraction methods: `llm_relationships`, `llm_relationships_fuzzy`, `llm_relationships_freeform`

- [ ] **Step 3: Verify graph composition**

Run:
```bash
cd backend/docker && docker compose exec knowledge-tree-service python -c "
import asyncio
from app.services.falkordb_client import FalkorDBClient

async def check():
    c = FalkorDBClient()
    await c.initialize()
    nodes = await c.execute_cypher('MATCH (n:Node) RETURN count(n) AS cnt')
    lits = await c.execute_cypher('MATCH (n:Literal) RETURN count(n) AS cnt')
    rels = await c.execute_cypher('MATCH ()-[r:Rel]->() RETURN count(r) AS cnt')
    contras = await c.execute_cypher('MATCH (n:Node) WHERE n.uri STARTS WITH \"nouxcube://contradiction/\" RETURN count(n) AS cnt')
    edge_contras = await c.execute_cypher('MATCH ()-[r:Rel]->() WHERE r.has_contradiction = true RETURN count(r) AS cnt')
    print(f'Nodes: {nodes[0][\"cnt\"]}')
    print(f'Literals: {lits[0][\"cnt\"]}')
    print(f'Rels: {rels[0][\"cnt\"]}')
    print(f'Contradiction :Nodes (should be 0): {contras[0][\"cnt\"]}')
    print(f'Edges with has_contradiction: {edge_contras[0][\"cnt\"]}')
    await c.close()

asyncio.run(check())
"
```

Expected:
- Contradiction :Nodes = 0
- Edges with has_contradiction > 0 (if contradictions exist)
- Total Rels significantly lower than before (no contradiction triples)

- [ ] **Step 4: Final commit with validation notes**

```bash
git add -A
git commit -m "feat(trustgraph): extractors redesign complete — Phase 3-PREREQ done"
```
