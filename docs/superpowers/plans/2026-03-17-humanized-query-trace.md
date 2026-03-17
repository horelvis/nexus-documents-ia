# Humanized Query Trace — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a humanized breadcrumb + post-hoc explanation to Emma's responses so legal/medical users can understand what Emma did and why.

**Architecture:** New `explain` LangGraph node after synthesize nodes generates a sector-adapted natural language explanation from verified facts. Frontend shows a phase breadcrumb during execution (derived from `phase_update` SSE events) and a collapsible explanation panel after completion.

**Tech Stack:** Python (LangGraph node), Langfuse (prompts), TypeScript/React (frontend components), custom i18n system.

**Spec:** `docs/superpowers/specs/2026-03-17-humanized-query-trace-design.md`

---

## File Structure

### Backend (New files)
- `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/explain.py` — Explain node: fact extraction + LLM reformulation + validation
- `backend/microservices/emma-agent-service/scripts/migrate_explain_prompts.py` — Langfuse prompt migration script
- `backend/microservices/emma-agent-service/tests/test_explain_node.py` — Unit tests for explain node
- `backend/microservices/emma-agent-service/tests/test_phase_mapping.py` — Unit tests for phase event mapping

### Backend (Modified files)
- `backend/microservices/emma-agent-service/app/agents/langgraph/state.py` — Add `explanation: Optional[str]` to `ReActState`
- `backend/microservices/emma-agent-service/app/agents/langgraph/graph.py` — Wire explain node after synthesize/synthesize_swarm
- `backend/microservices/emma-agent-service/app/agents/langgraph/api.py` — Include `explanation` in `complete` event data
- `backend/microservices/emma-agent-service/app/services/langgraph_adapter.py` — Forward `explanation` in final values snapshot + emit `phase_update` events
- `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py` — Add `explain_guidance` field to `SectorConfig`
- `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py` — Add `explain_guidance` to sector instances
- `backend/microservices/emma-agent-service/app/services/prompt_registry.py` — Register 2 new prompt entries
- `backend/microservices/emma-agent-service/app/core/config.py` — Add `EXPLAIN_ENABLED` flag

### Frontend (New files)
- `frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx` — Inline breadcrumb component
- `frontend/packages/shared/src/emma/displays/Generic/ExplanationPanel.tsx` — Collapsible explanation component

### Frontend (Modified files)
- `frontend/packages/shared/src/emma/types.ts` — Add `explanation?: string` to metadata
- `frontend/packages/shared/src/emma/displays/DisplayRenderer.tsx` — Integrate new components
- `frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx` — Add `explanation` to `EmmaStateType`
- `frontend/src/lib/i18n/locales/es.json` — Add phase + explanation labels
- `frontend/src/lib/i18n/locales/en.json` — Add phase + explanation labels

---

## Task 1: Backend — State + Config + Prompt Registry

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/state.py:517`
- Modify: `backend/microservices/emma-agent-service/app/core/config.py:359`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py:100`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py`
- Modify: `backend/microservices/emma-agent-service/app/services/prompt_registry.py`

- [ ] **Step 1: Add `explanation` field to `ReActState`**

In `state.py`, after the `sources` field (~line 517), add:

```python
# =========================================================================
# Explanation (humanized reasoning trace, feature-gated)
# =========================================================================
explanation: Optional[str]
```

- [ ] **Step 2: Add `EXPLAIN_ENABLED` to config**

In `core/config.py`, after the User Memory section (~line 362), add:

```python
# ==========================================================================
# Explanation Generation (humanized reasoning trace)
# ==========================================================================
explain_enabled: bool = os.getenv("EXPLAIN_ENABLED", "true").lower() == "true"
```

- [ ] **Step 3: Add `explain_guidance` to `SectorConfig`**

In `sectors/config.py`, after `hitl_default: bool = False` (~line 102), add:

```python
# Explanation sector guidance (injected into explain prompt)
explain_guidance: str = "Usa lenguaje accesible. Describe los documentos consultados."
```

- [ ] **Step 4: Add `explain_guidance` to sector instances**

In `sectors/registry.py`, add `explain_guidance` to each sector:

For LEGAL_SECTOR (after `hitl_default` or last field):
```python
explain_guidance="Usa terminología jurídica. Cita artículos y leyes por nombre completo.",
```

For MEDICAL_SECTOR:
```python
explain_guidance="Usa terminología clínica. Referencia protocolos y normativa sanitaria.",
```

For DOCUMENTAL_SECTOR (uses default from dataclass, no change needed).

- [ ] **Step 5: Register prompts in `prompt_registry.py`**

Add at the end of `PROMPT_REGISTRY` dict, before the closing `}`:

```python
# ── Explanation (humanized reasoning trace) ───────────────────────────
"emma_explain_system": PromptEntry(
    yaml_path=("explain", "system"),
    description="System prompt for humanized explanation generation",
    section="explain",
),
"emma_explain_user": PromptEntry(
    yaml_path=("explain", "user"),
    description="User template with verified facts and sector guidance",
    section="explain",
),
```

- [ ] **Step 6: Initialize `explanation` in `create_initial_react_state`**

In `state.py`, find `create_initial_react_state()` (~line 682) and add to the return dict:

```python
"explanation": None,
```

This ensures consistency with the pattern used for `final_answer`, `user_memory`, etc.

- [ ] **Step 7: Add `"explain"` to relevant guardrails**

In `app/services/guardrail_registry.py`, find sector guardrails that apply to synthesis output (e.g., `applies_to: ["synthesize"]`). Add `"explain"` to their `applies_to` arrays so the existing guardrails also validate the explanation output.

- [ ] **Step 8: Verify config loads**

Run: `cd backend/microservices/emma-agent-service && python -c "from app.core.config import settings; print(f'explain_enabled={settings.explain_enabled}')"` (expects: `explain_enabled=True`)

- [ ] **Step 9: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/state.py \
       backend/microservices/emma-agent-service/app/core/config.py \
       backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py \
       backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py \
       backend/microservices/emma-agent-service/app/services/prompt_registry.py \
       backend/microservices/emma-agent-service/app/services/guardrail_registry.py
git commit -m "feat(explain): add state field, config flag, sector guidance, prompt registry, guardrails"
```

---

## Task 2: Backend — Langfuse Prompt Migration Script

**Files:**
- Create: `backend/microservices/emma-agent-service/scripts/migrate_explain_prompts.py`

- [ ] **Step 1: Create migration script**

Create `scripts/migrate_explain_prompts.py` following the pattern of `migrate_retrieval_intelligence_prompts.py`:

```python
#!/usr/bin/env python3
"""
Migration: Explanation (humanized reasoning trace) prompts.

Pushes prompt changes directly to Langfuse.
Langfuse DB is the single source of truth for all prompts.

Changes:
  1. emma_explain_system — NEW prompt for explanation system instructions
  2. emma_explain_user — NEW prompt for explanation user template with facts

Usage:
    # Inside Docker container:
    docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py

    # Dry run:
    docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py --dry-run

    # From host (with env vars):
    LANGFUSE_HOST=http://localhost:3002 \\
    LANGFUSE_PUBLIC_KEY=pk-lf-xxx \\
    LANGFUSE_SECRET_KEY=sk-lf-xxx \\
    python scripts/migrate_explain_prompts.py
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


EXPLAIN_SYSTEM_PROMPT = """\
Eres un asistente que explica su proceso de investigación a profesionales.
Reformula los siguientes hechos verificados en 2-4 frases naturales y claras.

Sector del usuario: {sector}
Adaptación de tono: {sector_guidance}

Reglas estrictas:
- NO inventes pasos, fuentes ni datos que no estén en la lista de hechos.
- Si un hecho menciona un documento, cítalo por nombre exacto.
- Si un hecho menciona un artículo de ley, cítalo con su número y nombre de ley.
- Usa conectores naturales ("Para ello", "A continuación", "Finalmente").
- Escribe en el mismo idioma que los hechos proporcionados."""


EXPLAIN_USER_PROMPT = """\
Hechos verificados:
{facts_formatted}

Herramientas utilizadas: {tools_human_names}
Fuentes consultadas: {source_names}"""


def get_langfuse_client():
    """Create Langfuse client from environment."""
    from langfuse import Langfuse

    host = os.getenv("LANGFUSE_HOST", "http://langfuse:3000")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY", "")

    if not public_key or not secret_key:
        print("ERROR: LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY must be set")
        sys.exit(1)

    return Langfuse(public_key=public_key, secret_key=secret_key, host=host), host


def migrate_prompt(langfuse, name: str, content: str, section: str, dry_run: bool) -> bool:
    """Create a single prompt in Langfuse if it doesn't exist."""
    print(f"── {name}: creating new prompt ──")

    try:
        langfuse.get_prompt(name=name)
        print("  SKIP: Prompt already exists in Langfuse")
        return True
    except Exception:
        pass  # Expected: prompt doesn't exist yet

    if dry_run:
        print(f"  DRY RUN: Would create prompt ({len(content)} chars)")
        return True

    langfuse.create_prompt(
        name=name,
        prompt=content,
        type="text",
        labels=["production"],
        config={"section": section, "migrated_by": "humanized_query_trace"},
    )
    print(f"  OK: Created {name} ({len(content)} chars)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Explanation prompts to Langfuse"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without modifying Langfuse",
    )
    args = parser.parse_args()

    langfuse, host = get_langfuse_client()
    print(f"Connected to Langfuse at {host}\n")

    results = []
    results.append((
        "emma_explain_system",
        migrate_prompt(langfuse, "emma_explain_system", EXPLAIN_SYSTEM_PROMPT, "explain", args.dry_run),
    ))
    results.append((
        "emma_explain_user",
        migrate_prompt(langfuse, "emma_explain_user", EXPLAIN_USER_PROMPT, "explain", args.dry_run),
    ))

    print("\n── Summary ──")
    for name, ok in results:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")

    failures = sum(1 for _, ok in results if not ok)
    if failures:
        print(f"\n{failures} migration(s) failed")
        sys.exit(1)
    elif args.dry_run:
        print("\nDry run complete — no changes made")
    else:
        print("\nAll migrations applied successfully")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test dry run locally**

Run: `cd backend/microservices/emma-agent-service && python scripts/migrate_explain_prompts.py --dry-run`

Expected: 2x "DRY RUN: Would create prompt"

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/scripts/migrate_explain_prompts.py
git commit -m "feat(explain): add Langfuse prompt migration script"
```

---

## Task 3: Backend — Explain Node (with tests)

**Files:**
- Create: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/explain.py`
- Create: `backend/microservices/emma-agent-service/tests/test_explain_node.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_explain_node.py`:

```python
"""Tests for the explain node — humanized reasoning trace."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.langgraph.nodes.explain import (
    explain_node,
    extract_facts,
    TOOL_HUMAN_NAMES,
    FALLBACK_TEMPLATE,
)


# ── Fixtures ────────────────────────────────────────────────────────────

def _make_state(**overrides):
    """Build a minimal ReActState dict for testing."""
    base = {
        "fast_path_used": False,
        "reasoning_steps": [
            {"type": "tool_call", "content": "smart_search", "metadata": {"stores_searched": "documents, legislation", "results_count": 3}},
            {"type": "tool_result", "content": "Found 3 results", "source": "smart_search", "metadata": {"top_sources": [{"title": "Contrato_ABC.pdf", "score": 0.95}]}},
        ],
        "sources": [{"title": "Contrato_ABC.pdf", "pages": "1-3", "score": 0.95}],
        "tool_calls_history": [{"name": "smart_search", "args": {}, "timestamp": 0}],
        "sector": "legal",
        "metadata": {"classify_intent": "document_query"},
        "messages": [],
        "final_answer": "El contrato está vigente.",
    }
    base.update(overrides)
    return base


# ── extract_facts tests ────────────────────────────────────────────────

class TestExtractFacts:
    def test_extracts_tool_call_facts(self):
        state = _make_state()
        facts = extract_facts(state["reasoning_steps"], state["sources"])
        assert len(facts) > 0
        assert any("documents" in f or "legislation" in f for f in facts)

    def test_extracts_source_facts(self):
        state = _make_state()
        facts = extract_facts(state["reasoning_steps"], state["sources"])
        assert any("Contrato_ABC.pdf" in f for f in facts)

    def test_empty_reasoning_steps(self):
        facts = extract_facts([], [])
        assert facts == []

    def test_unknown_step_type_skipped(self):
        steps = [{"type": "unknown_type", "content": "foo"}]
        facts = extract_facts(steps, [])
        assert facts == []


# ── explain_node tests ─────────────────────────────────────────────────

class TestExplainNode:
    @pytest.mark.asyncio
    @patch("app.agents.langgraph.nodes.explain.settings")
    async def test_skips_fast_path(self, mock_settings):
        mock_settings.explain_enabled = True
        state = _make_state(fast_path_used=True)
        result = await explain_node(state)
        assert result.get("explanation") is None
        assert result.get("is_complete") is True

    @pytest.mark.asyncio
    @patch("app.agents.langgraph.nodes.explain.settings")
    async def test_skips_when_disabled(self, mock_settings):
        mock_settings.explain_enabled = False
        state = _make_state()
        result = await explain_node(state)
        assert result.get("explanation") is None
        assert result.get("is_complete") is True

    @pytest.mark.asyncio
    @patch("app.agents.langgraph.nodes.explain.settings")
    @patch("app.agents.langgraph.nodes.explain._call_llm")
    @patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
    async def test_generates_explanation(self, mock_sector, mock_llm, mock_settings):
        mock_settings.explain_enabled = True
        mock_sector.return_value = MagicMock(explain_guidance="Usa terminología jurídica.")
        mock_llm.return_value = "Revisé 3 documentos y consulté legislación."
        state = _make_state()
        result = await explain_node(state)
        assert result["explanation"] is not None
        assert len(result["explanation"]) > 0
        assert result["is_complete"] is True

    @pytest.mark.asyncio
    @patch("app.agents.langgraph.nodes.explain.settings")
    @patch("app.agents.langgraph.nodes.explain._call_llm")
    async def test_empty_facts_uses_fallback(self, mock_llm, mock_settings):
        mock_settings.explain_enabled = True
        state = _make_state(reasoning_steps=[], sources=[], tool_calls_history=[])
        result = await explain_node(state)
        # Should use fallback, not call LLM
        mock_llm.assert_not_called()
        assert result.get("is_complete") is True

    @pytest.mark.asyncio
    @patch("app.agents.langgraph.nodes.explain.settings")
    @patch("app.agents.langgraph.nodes.explain._call_llm")
    @patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
    async def test_llm_failure_uses_fallback(self, mock_sector, mock_llm, mock_settings):
        mock_settings.explain_enabled = True
        mock_sector.return_value = MagicMock(explain_guidance="Usa terminología jurídica.")
        mock_llm.side_effect = Exception("LLM timeout")
        state = _make_state()
        result = await explain_node(state)
        assert result["explanation"] is not None  # Fallback, not None
        assert "Contrato_ABC.pdf" in result["explanation"]
        assert result["is_complete"] is True

    @pytest.mark.asyncio
    @patch("app.agents.langgraph.nodes.explain.settings")
    @patch("app.agents.langgraph.nodes.explain._call_llm")
    @patch("app.agents.langgraph.nodes.explain._detect_fabricated_data")
    @patch("app.agents.langgraph.nodes.explain.get_active_sector_config")
    async def test_fabricated_data_uses_fallback(self, mock_sector, mock_detect, mock_llm, mock_settings):
        mock_settings.explain_enabled = True
        mock_sector.return_value = MagicMock(explain_guidance="Usa terminología jurídica.")
        mock_llm.return_value = "Revisé el contrato XYZ con número 12345."  # fabricated
        mock_detect.return_value = ["12345"]  # detected as fabricated
        state = _make_state()
        result = await explain_node(state)
        # Should use fallback because validation rejected
        assert "Contrato_ABC.pdf" in result["explanation"]
        assert result["is_complete"] is True


# ── TOOL_HUMAN_NAMES coverage ──────────────────────────────────────────

class TestToolHumanNames:
    def test_known_tools_have_human_names(self):
        assert "smart_search" in TOOL_HUMAN_NAMES
        assert "web_search" in TOOL_HUMAN_NAMES
        assert "search_jurisprudence" in TOOL_HUMAN_NAMES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_explain_node.py -v`

Expected: FAIL (module not found)

- [ ] **Step 3: Implement explain node**

Create `app/agents/langgraph/nodes/explain.py`:

```python
"""
Emma ReAct Agent — Explain Node (humanized reasoning trace)

Generates a sector-adapted natural language explanation of what Emma did
and why, based on verified facts extracted from reasoning_steps.

Anti-hallucination: The LLM only reformulates pre-extracted facts.
It never sees the original query. Post-LLM validation checks for
fabricated data against the ToolMessage corpus.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.agents.langgraph.quality_gate import _detect_fabricated_data
from app.agents.langgraph.sectors.registry import get_active_sector_config
from app.services.langfuse_prompt_client import get_langfuse_prompt_client

logger = logging.getLogger(__name__)


# ── Human-readable tool names ───────────────────────────────────────────

TOOL_HUMAN_NAMES = {
    "smart_search": "búsqueda inteligente",
    "get_document_content": "lectura de documento",
    "structural_query": "consulta estructural",
    "analyze_domain": "análisis de dominio",
    "web_search": "búsqueda web",
    "search_jurisprudence": "búsqueda de jurisprudencia",
    "list_sources": "exploración de fuentes",
    "query_connector": "consulta a conector externo",
    "generate_document": "generación de documento",
    "forge_document": "creación de documento PDF",
    "send_email": "envío de email",
    "verified_generation": "generación verificada",
    "predictive_analysis": "análisis predictivo",
    "terminate": "finalización",
}

FALLBACK_TEMPLATE = "Consulté {n} fuente(s) ({source_names}) utilizando {tools_human_names}."


# ── Fact extraction (deterministic, no LLM) ────────────────────────────

def extract_facts(
    reasoning_steps: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
) -> List[str]:
    """Extract verified facts from reasoning steps and sources.

    Returns a list of human-readable fact strings. Only includes
    information actually present in the steps/sources — no inference.
    """
    facts: List[str] = []

    for step in reasoning_steps:
        step_type = step.get("type", "")
        content = step.get("content", "")
        metadata = step.get("metadata", {})
        source = step.get("source", "")

        if step_type == "tool_call":
            tool_name = content if isinstance(content, str) else str(content)
            if tool_name == "smart_search" or source == "smart_search":
                stores = metadata.get("stores_searched", "documentos")
                count = metadata.get("results_count", 0)
                facts.append(
                    f"Busqué en {stores} y encontré {count} resultado(s)"
                )
            elif tool_name == "search_jurisprudence":
                facts.append("Busqué jurisprudencia en CENDOJ")
            elif tool_name == "web_search":
                facts.append("Busqué información en internet")
            elif tool_name == "get_document_content":
                doc_id = metadata.get("document_id", "")
                if doc_id:
                    facts.append(f"Leí el contenido del documento {doc_id}")
            elif tool_name == "structural_query":
                facts.append("Realicé una consulta estructural al grafo de conocimiento")
            elif tool_name == "analyze_domain":
                facts.append("Realicé un análisis de dominio especializado")

        elif step_type == "tool_result" and source == "smart_search":
            top_sources = metadata.get("top_sources", [])
            for src in top_sources[:3]:
                title = src.get("title", "documento")
                score = src.get("score", 0)
                facts.append(f"Consulté: {title} (relevancia {score:.0%})")

    # Add final sources
    for src in sources:
        title = src.get("title", "documento")
        pages = src.get("pages", "N/A")
        if not any(title in f for f in facts):
            facts.append(f"Fuente utilizada: {title}, páginas {pages}")

    return facts


# ── LLM call (isolated for testability) ─────────────────────────────

async def _call_llm(
    facts_formatted: str,
    tools_human_names: str,
    source_names: str,
    sector: str,
    sector_guidance: str,
) -> str:
    """Call PLANNER model to reformulate facts into natural language."""
    from app.agents.llm_models import get_planner_model

    client = get_langfuse_prompt_client()
    system_prompt_obj = await client.get_prompt(
        "emma_explain_system",
        variables={"sector": sector, "sector_guidance": sector_guidance},
    )
    user_prompt_obj = await client.get_prompt(
        "emma_explain_user",
        variables={
            "facts_formatted": facts_formatted,
            "tools_human_names": tools_human_names,
            "source_names": source_names,
        },
    )

    model = get_planner_model()
    response = await model.ainvoke([
        {"role": "system", "content": system_prompt_obj.content},
        {"role": "user", "content": user_prompt_obj.content},
    ])
    return response.content.strip()


# ── Fallback builder ────────────────────────────────────────────────

def _build_fallback(
    sources: List[Dict[str, Any]],
    tool_calls_history: List[Dict[str, Any]],
) -> Optional[str]:
    """Build deterministic fallback explanation from sources and tools."""
    source_names = ", ".join(
        s.get("title", "documento") for s in sources[:5]
    ) or "ninguna fuente específica"

    unique_tools = {entry.get("name", "") for entry in tool_calls_history}
    tools_human = ", ".join(
        TOOL_HUMAN_NAMES.get(t, t) for t in unique_tools if t and t != "terminate"
    ) or "análisis directo"

    if not sources and not unique_tools:
        return None

    return FALLBACK_TEMPLATE.format(
        n=len(sources),
        source_names=source_names,
        tools_human_names=tools_human,
    )


# ── Main node ───────────────────────────────────────────────────────

async def explain_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a humanized explanation of the reasoning process.

    Skips (early return) when:
    - fast_path_used is True (greetings, identity, general knowledge)
    - EXPLAIN_ENABLED is False

    Always sets is_complete=True (this is the final node before END).
    """
    # Guard: fast path or disabled
    if state.get("fast_path_used") or not settings.explain_enabled:
        return {"is_complete": True}

    start = time.time()
    reasoning_steps = state.get("reasoning_steps", [])
    sources = state.get("sources", [])
    tool_calls_history = state.get("tool_calls_history", [])
    sector_name = state.get("sector") or "documental"
    messages = state.get("messages", [])

    # Extract facts (deterministic)
    facts = extract_facts(reasoning_steps, sources)

    # If no facts, use fallback or skip
    if not facts:
        fallback = _build_fallback(sources, tool_calls_history)
        return {
            "explanation": fallback,
            "is_complete": True,
        }

    # Build LLM inputs
    facts_formatted = "\n".join(f"- {f}" for f in facts)

    unique_tools = {entry.get("name", "") for entry in tool_calls_history}
    tools_human_names = ", ".join(
        TOOL_HUMAN_NAMES.get(t, t) for t in unique_tools if t and t != "terminate"
    ) or "análisis directo"

    source_names = ", ".join(
        s.get("title", "documento") for s in sources[:5]
    ) or "ninguna fuente específica"

    # Get sector guidance (singleton — one sector per deployment)
    try:
        sector_config = get_active_sector_config()
        sector_guidance = sector_config.explain_guidance if sector_config else "Usa lenguaje accesible."
    except Exception:
        sector_guidance = "Usa lenguaje accesible."

    # Call LLM
    try:
        explanation = await _call_llm(
            facts_formatted=facts_formatted,
            tools_human_names=tools_human_names,
            source_names=source_names,
            sector=sector_name,
            sector_guidance=sector_guidance,
        )
    except Exception as e:
        logger.warning("Explain LLM failed, using fallback: %s", e)
        explanation = _build_fallback(sources, tool_calls_history)
        latency_ms = (time.time() - start) * 1000
        return {
            "explanation": explanation,
            "is_complete": True,
            "metadata": {"explain_latency_ms": latency_ms, "explain_fallback": True},
        }

    # Anti-hallucination: validate against ToolMessage corpus
    fabricated = _detect_fabricated_data(explanation, messages)
    if fabricated:
        logger.warning("Explain contained fabricated data: %s — using fallback", fabricated)
        explanation = _build_fallback(sources, tool_calls_history)

    latency_ms = (time.time() - start) * 1000
    logger.info("Explain node completed in %.0fms (sector=%s)", latency_ms, sector_name)

    return {
        "explanation": explanation,
        "is_complete": True,
        "metadata": {"explain_latency_ms": latency_ms, "explain_fallback": False},
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_explain_node.py -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/explain.py \
       backend/microservices/emma-agent-service/tests/test_explain_node.py
git commit -m "feat(explain): implement explain node with fact extraction and tests"
```

---

## Task 4: Backend — Wire Explain Node into Graph

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/graph.py:110,163-165`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py`

- [ ] **Step 1: Import explain node in graph.py**

In `graph.py`, add import after existing node imports (~line 8-15):

```python
from .nodes.explain import explain_node
```

- [ ] **Step 2: Add explain node to graph**

In `graph.py`, after existing `add_node` calls (~line 115):

```python
workflow.add_node("explain", explain_node)
```

- [ ] **Step 3: Rewire edges to go through explain**

In `graph.py`, replace (~lines 163-165):

```python
# Before:
workflow.add_edge("synthesize", END)
workflow.add_edge("synthesize_swarm", END)

# After:
workflow.add_edge("synthesize", "explain")
workflow.add_edge("synthesize_swarm", "explain")
workflow.add_edge("explain", END)
```

- [ ] **Step 4: Remove `is_complete=True` from synthesize_swarm**

In `synthesize_swarm.py`, at all 3 locations (lines 121, 160, 287), **remove** the `"is_complete": True,` line from each return dict. The explain node now sets `is_complete`.

**Important**: `synthesize_react.py` does NOT set `is_complete` (it only sets `success`), so no changes needed there. The `react_loop.py` does set `is_complete=True` in multiple places, but those are for the conditional edge routing within the react loop — the graph's conditional edge checks `is_complete` to decide loop vs exit. This is separate from the `api.py` streaming check. The explain node's `is_complete=True` is the final one that triggers the `complete` event.

**Verification note**: During integration testing (Task 6), verify that `api.py` receives the explain node's state update with `is_complete=True` AFTER the synthesize state. If the streaming loop breaks on an earlier `is_complete` from `react_loop`, the fix is to rename the explain signal to a different field (e.g., `explain_complete`) and update `api.py` accordingly. This is the main integration risk.

- [ ] **Step 5: Verify graph compiles**

Run: `cd backend/microservices/emma-agent-service && python -c "from app.agents.langgraph.graph import create_react_graph; g = create_react_graph(); print('Graph OK, nodes:', list(g.nodes))"`

Expected: Nodes list includes `explain`

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/graph.py \
       backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py
git commit -m "feat(explain): wire explain node into graph after synthesize"
```

---

## Task 5: Backend — Streaming Transport (api.py + adapter)

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/api.py:398-420`
- Modify: `backend/microservices/emma-agent-service/app/services/langgraph_adapter.py:260-282`

- [ ] **Step 1: Fix streaming break condition in api.py**

The current `api.py` (~line 399) breaks on `event.get("final_answer") and event.get("is_complete")`. Since `react_loop` sets both fields, the loop breaks before `synthesize` or `explain` ever run. Fix by adding an `explanation` check when explain is enabled:

In `api.py`, replace the break condition (~line 399):

```python
# Before:
if event.get("final_answer") and event.get("is_complete"):

# After:
if event.get("final_answer") and event.get("is_complete"):
    # If explain is enabled, wait for the explanation field
    # (explain node sets it; synthesize/react_loop don't)
    from app.core.config import settings as app_settings
    if app_settings.explain_enabled and not event.get("fast_path_used"):
        if event.get("explanation") is None:
            continue  # Not yet — explain node hasn't run
```

This makes the loop skip `is_complete` events that don't yet have `explanation`, allowing the graph to continue through `synthesize` → `explain`. The explain node sets both `explanation` AND `is_complete`, which satisfies the full condition.

- [ ] **Step 2: Add `explanation` to complete event data in `stream_react_query`**

In `api.py` `stream_react_query()` complete event data dict (~line 410), add after `"guardrail_metadata"`:

```python
"explanation": event.get("explanation"),
```

- [ ] **Step 3: Add same changes to `resume_react_query`**

In `api.py` `resume_react_query()` (~line 582-596), apply the same two changes:
1. Add the `explanation` wait condition to the break check
2. Add `"explanation": event.get("explanation")` to the complete event data dict

- [ ] **Step 2: Add `explanation` to langgraph_adapter.py values snapshot**

In `langgraph_adapter.py`, inside the `_sse_line("values", {...})` dict in the complete handler (~line 278), add after `"guardrail_metadata"`:

```python
"explanation": data.get("explanation"),
```

- [ ] **Step 3: Add `phase_update` emission to adapter**

In `langgraph_adapter.py`, add a phase tracking mechanism at the top of `translate_to_langgraph_sse()`:

```python
# Phase tracking for breadcrumb
_current_phase = None

PHASE_MAP = {
    "started": "understanding",
    "thinking": "understanding",
    "tool_call": "searching",
    "tool_result": "searching",
    "reasoning_step": "analyzing",
    "swarm_started": "analyzing",
    "worker_started": "analyzing",
    "worker_complete": "analyzing",
    "swarm_synthesizing": "responding",
    "token": "responding",
}

PHASE_LABELS = {
    "understanding": "Entendiendo tu consulta",
    "searching": "Buscando información",
    "analyzing": "Analizando resultados",
    "responding": "Redactando respuesta",
}

PHASE_ORDER = ["understanding", "searching", "analyzing", "responding"]
```

Then, inside the event processing loop, before the existing event handling, add phase detection. Use `"updates"` event type (not `"custom"` which is not in the LangGraph protocol and would be silently ignored by `useStream`):

```python
new_phase = PHASE_MAP.get(event_type)
if new_phase and new_phase != _current_phase:
    _current_phase = new_phase
    phase_idx = PHASE_ORDER.index(new_phase)
    completed = PHASE_ORDER[:phase_idx]
    yield _sse_line("updates", {
        "phase_update": {
            "phase": new_phase,
            "label": PHASE_LABELS[new_phase],
            "index": phase_idx,
            "total": len(PHASE_ORDER),
            "completed_phases": completed,
        }
    })
```

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/api.py \
       backend/microservices/emma-agent-service/app/services/langgraph_adapter.py
git commit -m "feat(explain): wire explanation through streaming pipeline + phase_update events"
```

---

## Task 6: Backend — Integration Test

**Files:**
- Create: `backend/microservices/emma-agent-service/tests/test_phase_mapping.py`

- [ ] **Step 1: Write phase mapping tests**

```python
"""Tests for phase_update event mapping in the langgraph adapter."""

import pytest
from app.services.langgraph_adapter import PHASE_MAP, PHASE_ORDER, PHASE_LABELS


class TestPhaseMapping:
    def test_all_phases_have_labels(self):
        for phase in PHASE_ORDER:
            assert phase in PHASE_LABELS

    def test_tool_call_maps_to_searching(self):
        assert PHASE_MAP["tool_call"] == "searching"

    def test_token_maps_to_responding(self):
        assert PHASE_MAP["token"] == "responding"

    def test_started_maps_to_understanding(self):
        assert PHASE_MAP["started"] == "understanding"

    def test_swarm_started_maps_to_analyzing(self):
        assert PHASE_MAP["swarm_started"] == "analyzing"

    def test_phase_order_has_four_phases(self):
        assert len(PHASE_ORDER) == 4

    def test_fast_path_uses_two_phases(self):
        """Fast path only goes through understanding → responding."""
        fast_path_events = ["started", "token"]
        phases = [PHASE_MAP[e] for e in fast_path_events]
        assert phases == ["understanding", "responding"]
```

- [ ] **Step 2: Run tests**

Run: `cd backend/microservices/emma-agent-service && python -m pytest tests/test_phase_mapping.py -v`

Expected: All PASS

- [ ] **Step 3: Manual integration verification**

Start the backend services and test with a real query:

```bash
cd backend/docker && ./start-dev.sh
```

Then in another terminal:

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)
curl -N -X POST "http://localhost:8009/emma/query/stream" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-ID: a060f046-9992-4d1a-87c4-fa5c6f8c066c" \
  -d '{"query": "¿Cuántos contratos hay?", "session_id": "test-explain"}' \
  > /tmp/explain_test_stream.txt 2>&1
```

Verify: `grep -c "phase_update" /tmp/explain_test_stream.txt` (should be >= 1)
Verify: `grep "explanation" /tmp/explain_test_stream.txt` (should contain explanation text)

**If `explanation` is missing from the complete event**: The `is_complete` from `react_loop` triggered the break before `explain` ran. Fix by checking `api.py` event ordering and adjusting the break condition (see spec section 3.4 for details).

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/tests/test_phase_mapping.py
git commit -m "test(explain): add phase mapping tests and verify integration"
```

---

## Task 7: Frontend — Types + Stream Provider

**Files:**
- Modify: `frontend/packages/shared/src/emma/types.ts`
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx`

- [ ] **Step 1: Add `explanation` to `EmmaMessage` metadata**

In `types.ts`, inside the `metadata` interface (~after `slmIsExecuting?: boolean`), add:

```typescript
// Humanized reasoning explanation
explanation?: string
```

- [ ] **Step 2: Add `explanation` to `EmmaStateType`**

In `EmmaStreamProvider.tsx`, inside the `EmmaStateType` type (~after `metadata?`), add:

```typescript
explanation?: string
```

- [ ] **Step 3: Commit**

```bash
git add frontend/packages/shared/src/emma/types.ts \
       frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx
git commit -m "feat(explain): add explanation type to frontend message and stream state"
```

---

## Task 8: Frontend — PhaseBreadcrumb Component

**Files:**
- Create: `frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx`

- [ ] **Step 1: Create PhaseBreadcrumb component**

```typescript
"use client"

import React from "react"
import { cn } from "@/lib/utils"
import { Brain, Search, BarChart3, PenLine, Check } from "lucide-react"

export type PhaseId = "understanding" | "searching" | "analyzing" | "responding"
export type PhaseStatus = "pending" | "active" | "completed"

export interface Phase {
  id: PhaseId
  label: string
  status: PhaseStatus
}

interface PhaseBreadcrumbProps {
  phases: Phase[]
  currentPhase: string | null
  className?: string
}

const PHASE_ICONS: Record<PhaseId, React.ElementType> = {
  understanding: Brain,
  searching: Search,
  analyzing: BarChart3,
  responding: PenLine,
}

export function PhaseBreadcrumb({ phases, currentPhase, className }: PhaseBreadcrumbProps) {
  if (!currentPhase) return null

  return (
    <div className={cn("flex items-center gap-1.5 px-3 py-2 text-xs text-muted-foreground", className)}>
      {phases.map((phase, idx) => {
        const Icon = PHASE_ICONS[phase.id]
        return (
          <React.Fragment key={phase.id}>
            {idx > 0 && (
              <span className="text-muted-foreground/40">&rarr;</span>
            )}
            <span
              className={cn(
                "flex items-center gap-1 transition-all duration-300",
                phase.status === "active" && "text-foreground font-medium",
                phase.status === "completed" && "text-muted-foreground/60",
                phase.status === "pending" && "text-muted-foreground/30",
              )}
            >
              {phase.status === "completed" ? (
                <Check className="h-3 w-3 text-green-500/60" />
              ) : (
                <Icon className="h-3 w-3" />
              )}
              {phase.status === "active" && (
                <>
                  <span>{phase.label}</span>
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
                </>
              )}
            </span>
          </React.Fragment>
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx
git commit -m "feat(explain): add PhaseBreadcrumb component"
```

---

## Task 9: Frontend — ExplanationPanel Component

**Files:**
- Create: `frontend/packages/shared/src/emma/displays/Generic/ExplanationPanel.tsx`

- [ ] **Step 1: Create ExplanationPanel component**

```typescript
"use client"

import React, { useState } from "react"
import { cn } from "@/lib/utils"
import { ChevronRight } from "lucide-react"

interface ExplanationPanelProps {
  explanation: string | null
  isLoading?: boolean
  className?: string
}

export function ExplanationPanel({ explanation, isLoading, className }: ExplanationPanelProps) {
  const [isOpen, setIsOpen] = useState(false)

  if (!explanation && !isLoading) return null

  return (
    <div className={cn("mt-2 rounded-lg border border-border/50 bg-muted/30", className)}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={isOpen}
      >
        <ChevronRight
          className={cn(
            "h-3 w-3 transition-transform duration-200",
            isOpen && "rotate-90",
          )}
        />
        <span className="font-medium">Así lo resolví</span>
      </button>

      {isOpen && (
        <div className="px-3 pb-3 text-sm text-muted-foreground leading-relaxed animate-in fade-in-0 duration-200">
          {isLoading ? (
            <div className="space-y-2">
              <div className="h-3 w-3/4 rounded bg-muted animate-pulse" />
              <div className="h-3 w-1/2 rounded bg-muted animate-pulse" />
            </div>
          ) : (
            <p>{explanation}</p>
          )}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/packages/shared/src/emma/displays/Generic/ExplanationPanel.tsx
git commit -m "feat(explain): add ExplanationPanel collapsible component"
```

---

## Task 10: Frontend — Integrate in DisplayRenderer

**Files:**
- Modify: `frontend/packages/shared/src/emma/displays/DisplayRenderer.tsx`

- [ ] **Step 1: Import new components**

At the top of `DisplayRenderer.tsx`, add imports:

```typescript
import { ExplanationPanel } from "./Generic/ExplanationPanel"
import { PhaseBreadcrumb, type Phase } from "./Generic/PhaseBreadcrumb"
```

- [ ] **Step 2: Add PhaseBreadcrumb to progress messages**

In `DisplayRenderer.tsx`, find the `"progress"` case (~line 90-110) where it routes to `SLMThinkingDisplay` or `WorkflowProgress`. Replace the progress rendering with `PhaseBreadcrumb`:

```typescript
case "progress": {
  // If phase data is available, use new PhaseBreadcrumb
  const phases = message.metadata?.phases as Phase[] | undefined
  const currentPhase = message.metadata?.currentPhase as string | null | undefined
  if (phases && currentPhase !== undefined) {
    return <PhaseBreadcrumb phases={phases} currentPhase={currentPhase} />
  }
  // Fallback to legacy components while migrating
  if (message.metadata?.slmThinkingSteps) {
    return <SLMThinkingDisplay ... />
  }
  return <WorkflowProgress ... />
}
```

- [ ] **Step 3: Add ExplanationPanel to result messages**

In `DisplayRenderer.tsx`, find the `"result"` case (~line 115-135) where it renders `<TextDisplay>`, `<DocumentDisplay>`, and `<ReasoningDisplay>`. After the `<ReasoningDisplay>` block, add:

```typescript
{message.metadata?.explanation && (
  <ExplanationPanel explanation={message.metadata.explanation} />
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/packages/shared/src/emma/displays/DisplayRenderer.tsx
git commit -m "feat(explain): integrate ExplanationPanel in DisplayRenderer"
```

---

## Task 11: Frontend — i18n Labels

**Files:**
- Modify: `frontend/src/lib/i18n/locales/es.json`
- Modify: `frontend/src/lib/i18n/locales/en.json`

- [ ] **Step 1: Add Spanish labels**

In `es.json`, inside the `"emma"` section, add:

```json
"phases": {
  "understanding": "Entendiendo tu consulta",
  "searching": "Buscando información",
  "analyzing": "Analizando resultados",
  "responding": "Redactando respuesta"
},
"explanation": {
  "title": "Así lo resolví",
  "loading": "Generando explicación..."
}
```

- [ ] **Step 2: Add English labels**

In `en.json`, inside the `"emma"` section, add:

```json
"phases": {
  "understanding": "Understanding your query",
  "searching": "Searching for information",
  "analyzing": "Analyzing results",
  "responding": "Writing response"
},
"explanation": {
  "title": "How I solved it",
  "loading": "Generating explanation..."
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/i18n/locales/es.json \
       frontend/src/lib/i18n/locales/en.json
git commit -m "feat(explain): add i18n labels for phases and explanation"
```

---

## Task 12: Run Langfuse Migration + Full Manual Test

- [ ] **Step 1: Run Langfuse prompt migration**

```bash
cd backend/docker
docker compose exec emma-agent-service python scripts/migrate_explain_prompts.py
```

Expected: 2x "OK: Created emma_explain_*"

- [ ] **Step 2: Verify prompts in Langfuse UI**

Open `http://localhost:3002` (admin@nouxcube.com / LangfuseAdmin2024!). Check that `emma_explain_system` and `emma_explain_user` exist with label "production".

- [ ] **Step 3: Full stack test**

Start backend: `cd backend/docker && ./start-dev.sh`
Start frontend: `cd frontend && npm run dev:on-premise`

Test queries:
1. "Hola" → No breadcrumb, no explanation (fast_path)
2. "¿Cuántos contratos hay?" → Breadcrumb animates → response + collapsible explanation
3. Open "Así lo resolví" → Readable, sector-adapted text
4. Verify explanation mentions actual documents, not fabricated ones

- [ ] **Step 4: Final commit**

```bash
git commit --allow-empty -m "feat(explain): humanized query trace — complete feature"
```

---

## Risk Checklist

| Risk | Check During | Mitigation |
|------|-------------|------------|
| `api.py` breaks on `react_loop`'s `is_complete` before explain runs | Task 6 Step 3 | Rename explain's signal or adjust break condition |
| LLM hallucination in explanation | Task 6 Step 3 | 3-layer validation + fallback template |
| Phase events not reaching frontend | Task 6 Step 3 | Check adapter `_sse_line("custom", ...)` format matches frontend expectations |
| Prompt not found in Langfuse | Task 12 Step 1 | Migration script creates with label "production" |
