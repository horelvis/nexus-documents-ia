# Sector-Aware Guardrails & Medical Safety — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing guardrail framework to the LangGraph pipeline with sector-specific profiles, PHI/PII redaction, medical safety guardrails, and sector-aware verified generation overrides (confidence caps, evidence limits, HITL).

**Architecture:** Registry-first approach — `guardrail_registry.py` defines all 18 guardrails as Python code (single source of truth). `GuardrailService` merges registry baseline + DB admin overrides. Three synthesis nodes call a shared `apply_guardrails()` helper. `SectorConfig` gains 4 new fields for verified generation overrides.

**Tech Stack:** Python 3.9+, FastAPI, LangGraph, PostgreSQL (Alembic), Langfuse, Redis cache

**Spec:** `docs/superpowers/specs/2026-03-15-sector-guardrails-medical-safety-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/microservices/emma-agent-service/app/services/guardrail_registry.py` | 18 guardrail entries + `get_guardrails_for_sector()` |
| `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/guardrail_helper.py` | Shared `apply_guardrails()` helper for synthesis nodes |
| `backend/microservices/emma-agent-service/scripts/seed_guardrails.py` | Seed script: registry → SQL + Langfuse |
| `backend/alembic/versions/20260315_add_sector_to_guardrails.py` | Migration: `sector` column on `emma_guardrails` |

### Modified Files
| File | Change |
|------|--------|
| `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py` | 4 new fields on `SectorConfig` |
| `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py` | Sector values for new fields |
| `backend/microservices/emma-agent-service/app/services/guardrail_service.py` | Sector param, registry merge, `re.sub()`, `inject_text`, `require_pattern`, Langfuse in `_validate_llm()`, disclaimers |
| `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_react.py` | Call `apply_guardrails()` |
| `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py` | Call `apply_guardrails()` |
| `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py` | Call `apply_guardrails()` on fast-path |
| `backend/microservices/emma-agent-service/app/services/verified_generation/service.py` | Sector overrides in mode_config + HITL |
| `backend/microservices/emma-agent-service/app/agents/langgraph/stop_and_go/strategies/verified.py` | Dynamic `_get_fidelity_cap()` |
| `backend/microservices/emma-agent-service/app/agents/langgraph/stop_and_go/nodes/search_and_evaluate.py` | Dynamic `max_external` |
| `backend/microservices/emma-agent-service/app/api/emma.py` | SSE events for guardrail metadata |
| `backend/microservices/emma-agent-service/app/services/prompt_registry.py` | 2 new entries for dosage validator |
| `backend/microservices/emma-agent-service/app/core/config.py` | `VERIFIED_HITL_TIMEOUT_SECONDS` |
| `backend/microservices/emma-agent-service/config/prompts/emma_prompts.yaml` | YAML fallback for dosage prompts |
| `backend/app/api/v1/prompts.py` | `sector` field on `GuardrailCreate` + GET filter |

---

## Chunk 1: Foundation — Registry, SectorConfig, Migration

### Task 1: Database Migration — Add `sector` column

**Files:**
- Create: `backend/alembic/versions/20260315_add_sector_to_guardrails.py`

- [ ] **Step 1: Create Alembic migration**

```python
"""Add sector column to emma_guardrails table.

Revision ID: 20260315_sector
Revises: (auto-detected)
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260315_sector"
down_revision = None  # auto-detect via --autogenerate or set manually
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("emma_guardrails", sa.Column("sector", sa.String(50), nullable=True))
    op.create_index("ix_emma_guardrails_sector", "emma_guardrails", ["sector"])


def downgrade():
    op.drop_index("ix_emma_guardrails_sector", table_name="emma_guardrails")
    op.drop_column("emma_guardrails", "sector")
```

Use `python scripts/create_migration.py -m "add sector to guardrails"` to get the correct `down_revision` chain, then replace the upgrade/downgrade bodies with the above.

- [ ] **Step 2: Update Main API — GuardrailCreate schema + GET filter**

Modify: `backend/app/api/v1/prompts.py`

Find the `GuardrailCreate` Pydantic model (or inline dict) and add `sector: Optional[str] = None`.

Find the `GET /guardrails` endpoint and add:
```python
@router.get("/guardrails")
async def list_guardrails(
    active_only: bool = True,
    sector: Optional[str] = None,  # NEW
    ...
):
    query = select(EmmaGuardrails)
    if active_only:
        query = query.where(EmmaGuardrails.is_active == True)
    if sector:
        # Return sector-specific + global (NULL sector)
        query = query.where(
            or_(EmmaGuardrails.sector == sector, EmmaGuardrails.sector.is_(None))
        )
    query = query.order_by(EmmaGuardrails.priority)
    ...
```

Also update the INSERT/POST endpoint to include `sector` in the created row.

- [ ] **Step 3: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies cleanly, `emma_guardrails` table has `sector` column.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/20260315_add_sector_to_guardrails.py backend/app/api/v1/prompts.py
git commit -m "feat(guardrails): add sector column to emma_guardrails + API filter"
```

---

### Task 2: SectorConfig Extension — 4 new fields

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py:33-96`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py:22-175`

- [ ] **Step 1: Add fields to SectorConfig dataclass**

In `config.py`, add 4 new fields after `graph_search_properties` (line 84):

```python
    # Guardrail & Verification overrides
    guardrail_profile: str = "global"
    fidelity_confidence_cap: float = 0.80
    max_evidence: int = 5
    hitl_default: bool = False
```

All are immutable scalars — safe with `frozen=True`.

- [ ] **Step 2: Set sector-specific values in registry.py**

In `registry.py`, add to each `SectorConfig(...)` constructor:

**Legal** (after line 75, before closing `)`):
```python
        guardrail_profile="legal",
        fidelity_confidence_cap=0.80,
        max_evidence=5,
        hitl_default=False,
```

**Medical** (after line 119, before closing `)`):
```python
        guardrail_profile="medical",
        fidelity_confidence_cap=0.60,
        max_evidence=15,
        hitl_default=True,
```

**Documental** (after line 173, before closing `)`):
```python
        guardrail_profile="documental",
        fidelity_confidence_cap=0.80,
        max_evidence=5,
        hitl_default=False,
```

- [ ] **Step 3: Verify import works**

Run: `cd backend/microservices/emma-agent-service && python -c "from app.agents.langgraph.sectors.registry import SECTOR_CONFIGS; print({k: (v.guardrail_profile, v.fidelity_confidence_cap, v.max_evidence, v.hitl_default) for k, v in SECTOR_CONFIGS.items()})"`

Expected: `{'legal': ('legal', 0.8, 5, False), 'medical': ('medical', 0.6, 15, True), 'documental': ('documental', 0.8, 5, False)}`

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/sectors/config.py backend/microservices/emma-agent-service/app/agents/langgraph/sectors/registry.py
git commit -m "feat(sectors): add guardrail_profile, confidence caps, max_evidence, HITL to SectorConfig"
```

---

### Task 3: Guardrail Registry — Source of Truth

**Files:**
- Create: `backend/microservices/emma-agent-service/app/services/guardrail_registry.py`

- [ ] **Step 1: Create the registry module**

Create `guardrail_registry.py` with:

1. `GuardrailEntry` dataclass (name, description, guardrail_type, action, config, sector, applies_to, priority, is_system, langfuse_prompt_key)
2. `GUARDRAIL_ENTRIES: list[GuardrailEntry]` — all 18 entries from spec
3. `get_guardrails_for_sector(sector: str | None) -> list[dict]` — filters global + sector-specific, returns as dicts sorted by priority

**Important implementation details:**
- Import PII patterns from `backend/app/core/patterns.py` — the patterns are defined there as constants. Reference them by importing the module or copying the regex strings (copying is simpler since the module is in the main backend, not in the microservice).
- Medical PHI patterns: use the entity patterns from `sectors/registry.py` medical config (`paciente` key).
- Each entry's `.config` dict must match what the existing `_validate_*` methods expect (e.g., `{"pattern": "...", "flags": "i"}` for REGEX).
- For REGEX guardrails with multiple patterns (e.g., `global_pii_phone` has ES + international), use `|` alternation in a single regex pattern string.

```python
"""
Guardrail Registry — Single source of truth for all system guardrails.

Pattern follows prompt_registry.py: dataclass entries imported by
seed_guardrails.py (SQL + Langfuse) and guardrail_service.py (runtime merge).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GuardrailEntry:
    """A guardrail registered in the system."""
    name: str
    description: str
    guardrail_type: str  # regex | keyword | semantic | llm_validator | length | format
    action: str  # block | warn | redact
    config: Dict[str, Any]
    sector: Optional[str] = None  # None = global
    applies_to: List[str] = field(default_factory=list)  # empty = all agents
    priority: int = 100
    is_system: bool = True
    langfuse_prompt_key: Optional[str] = None


# =============================================================================
# GUARDRAIL ENTRIES — all 18 system guardrails
# =============================================================================

GUARDRAIL_ENTRIES: List[GuardrailEntry] = [
    # ── Global (5) — all sectors ──────────────────────────────────────────
    GuardrailEntry(
        name="global_pii_email",
        description="Redact email addresses from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "flags": "i"},
        priority=10,
    ),
    GuardrailEntry(
        name="global_pii_phone",
        description="Redact phone numbers (ES and international) from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"(?:\+34\s?)?(?:\d{3}\s?\d{3}\s?\d{3}|\d{2}\s?\d{3}\s?\d{2}\s?\d{2})|\+\d{1,3}[\s.-]?\(?\d{1,4}\)?[\s.-]?\d{1,4}[\s.-]?\d{1,9}", "flags": ""},
        priority=10,
    ),
    GuardrailEntry(
        name="global_pii_national_id",
        description="Redact DNI/NIE/NIF from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"\b\d{8}[A-Z]\b|\b[XYZ]\d{7}[A-Z]\b|\b[A-Z]\d{7}[A-Z0-9]\b", "flags": ""},
        priority=10,
    ),
    GuardrailEntry(
        name="global_pii_financial",
        description="Redact credit card numbers and IBAN from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b|\b[A-Z]{2}\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\b", "flags": ""},
        priority=10,
    ),
    GuardrailEntry(
        name="global_min_response",
        description="Warn on suspiciously short responses (possible error)",
        guardrail_type="length",
        action="warn",
        config={"min_chars": 20},
        priority=90,
    ),

    # ── Medical (7) — ACTIVE_SECTOR=medical ───────────────────────────────
    GuardrailEntry(
        name="medical_phi_nhc",
        description="Redact NHC and Historia Clínica references from responses",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"(?:H\.?\s*C\.?\s*|Historia\s+Clínica\s+)(?:n[úu]m\.?\s*)?[\w/-]+|NHC\s*[\w/-]+", "flags": "i"},
        sector="medical",
        priority=5,
    ),
    GuardrailEntry(
        name="medical_no_diagnosis",
        description="Block responses that issue direct medical diagnoses",
        guardrail_type="keyword",
        action="block",
        config={"blocked_words": [
            "el diagnóstico es", "usted tiene", "usted padece",
            "padece de", "su diagnóstico", "le diagnostico",
        ]},
        sector="medical",
        priority=20,
    ),
    GuardrailEntry(
        name="medical_no_prescription",
        description="Block responses that issue direct prescriptions",
        guardrail_type="keyword",
        action="block",
        config={"blocked_words": [
            "le receto", "debe tomar", "prescripción:",
            "le prescribo", "tome usted",
        ]},
        sector="medical",
        priority=20,
    ),
    GuardrailEntry(
        name="medical_disclaimer",
        description="Inject medical disclaimer if not already present",
        guardrail_type="format",
        action="warn",
        config={
            "inject_text": "⚕️ Esta información es documental y no sustituye el criterio médico profesional.",
            "check_absent": "no sustituye el criterio médico",
        },
        sector="medical",
        priority=80,
    ),
    GuardrailEntry(
        name="medical_dosage_check",
        description="LLM-based validation of dosage coherence in medical responses",
        guardrail_type="llm_validator",
        action="warn",
        config={"threshold": 0.9},
        sector="medical",
        priority=50,
        langfuse_prompt_key="guardrail_medical_dosage_system",
    ),
    GuardrailEntry(
        name="medical_sensitive_topics",
        description="Warn on sensitive medical topics (suicide, self-harm) — high threshold to avoid false positives",
        guardrail_type="semantic",
        action="warn",
        config={"forbidden_topics": ["suicidio", "autolesión", "eutanasia sin contexto legal"], "similarity_threshold": 0.90},
        sector="medical",
        priority=30,
    ),
    GuardrailEntry(
        name="medical_patient_data",
        description="Redact dates of birth and clinical data identifiers",
        guardrail_type="regex",
        action="redact",
        config={"pattern": r"(?:fecha\s+de\s+nacimiento|nacido\s+el|F\.?\s*N\.?\s*:?\s*)\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", "flags": "i"},
        sector="medical",
        priority=5,
    ),

    # ── Legal (3) — ACTIVE_SECTOR=legal ───────────────────────────────────
    GuardrailEntry(
        name="legal_disclaimer",
        description="Inject legal disclaimer if not already present",
        guardrail_type="format",
        action="warn",
        config={
            "inject_text": "⚖️ Esta información no constituye asesoramiento jurídico profesional.",
            "check_absent": "no constituye asesoramiento jurídico",
        },
        sector="legal",
        priority=80,
    ),
    GuardrailEntry(
        name="legal_no_verdict",
        description="Warn when response contains verdict-like statements",
        guardrail_type="keyword",
        action="warn",
        config={"blocked_words": [
            "el tribunal debe fallar", "la sentencia será", "el veredicto debe ser",
        ]},
        sector="legal",
        priority=50,
    ),
    GuardrailEntry(
        name="legal_source_citation",
        description="Warn if legal response lacks article/law citations",
        guardrail_type="format",
        action="warn",
        config={"require_pattern": r"Art\.?\s*\d+|Ley\s+\d+|Real\s+Decreto"},
        sector="legal",
        priority=70,
    ),

    # ── Documental (3) — ACTIVE_SECTOR=documental ─────────────────────────
    GuardrailEntry(
        name="documental_disclaimer",
        description="Inject informational disclaimer if not already present",
        guardrail_type="format",
        action="warn",
        config={
            "inject_text": "ℹ️ Esta información tiene carácter orientativo.",
            "check_absent": "carácter orientativo",
        },
        sector="documental",
        priority=80,
    ),
    GuardrailEntry(
        name="documental_source_required",
        description="Warn if response lacks source references",
        guardrail_type="format",
        action="warn",
        config={"must_contain_sources": True},
        sector="documental",
        priority=70,
    ),
    GuardrailEntry(
        name="documental_length_limit",
        description="Warn on excessively long documental responses",
        guardrail_type="length",
        action="warn",
        config={"max_chars": 8000},
        sector="documental",
        priority=90,
    ),
]


def get_guardrails_for_sector(sector: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get guardrails applicable to a sector.

    Returns global guardrails (sector=None) + sector-specific guardrails,
    sorted by priority (lower = higher priority).

    Args:
        sector: The active sector name, or None for global-only.

    Returns:
        List of guardrail dicts compatible with GuardrailService internal format.
    """
    applicable = []
    for entry in GUARDRAIL_ENTRIES:
        if entry.sector is None or entry.sector == sector:
            applicable.append({
                "id": f"registry:{entry.name}",  # Synthetic ID for registry entries
                "tenant_id": None,
                "guardrail_name": entry.name,
                "description": entry.description,
                "guardrail_type": entry.guardrail_type,
                "config": entry.config,
                "action_on_match": entry.action,
                "applies_to": entry.applies_to,
                "priority": entry.priority,
                "is_active": True,
                "sector": entry.sector,
                "is_system": True,
            })

    applicable.sort(key=lambda g: g["priority"])
    return applicable
```

- [ ] **Step 2: Verify registry loads correctly**

Run: `cd backend/microservices/emma-agent-service && python -c "
from app.services.guardrail_registry import get_guardrails_for_sector
medical = get_guardrails_for_sector('medical')
legal = get_guardrails_for_sector('legal')
global_only = get_guardrails_for_sector(None)
print(f'medical: {len(medical)} (expect 12 = 5 global + 7 medical)')
print(f'legal: {len(legal)} (expect 8 = 5 global + 3 legal)')
print(f'global: {len(global_only)} (expect 5)')
print(f'names: {[g[\"guardrail_name\"] for g in medical]}')
"`

Expected: `medical: 12`, `legal: 8`, `global: 5`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/services/guardrail_registry.py
git commit -m "feat(guardrails): add guardrail_registry.py — 18 system guardrails as source of truth"
```

---

## Chunk 2: GuardrailService Enhancements

### Task 4: Extend GuardrailService — sector awareness, re.sub, inject_text, Langfuse

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/services/guardrail_service.py`

This is the largest single task. Apply changes in order:

- [ ] **Step 1: Add `disclaimers` to `OverallValidationResult`**

At line 58, add after `redacted_content`:

```python
    disclaimers: List[str] = field(default_factory=list)
```

- [ ] **Step 2: Fix `_validate_regex` — use `re.sub()` for REDACT**

Replace `_validate_regex` method (lines 166-192). The key change: return ALL matches info, and for REDACT action, use `re.sub()` in the main loop.

```python
    async def _validate_regex(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content against regex pattern. Returns (matched, details, pattern_for_sub)."""
        pattern = config.get("pattern")
        if not pattern:
            return False, None, None

        flags = 0
        flag_str = config.get("flags", "")
        if "i" in flag_str:
            flags |= re.IGNORECASE
        if "m" in flag_str:
            flags |= re.MULTILINE
        if "s" in flag_str:
            flags |= re.DOTALL

        try:
            matches = list(re.finditer(pattern, content, flags))
            if matches:
                # Return the pattern itself so the main loop can re.sub() all occurrences
                return True, f"Regex pattern matched {len(matches)} time(s): {pattern}", pattern
            return False, None, None
        except re.error as e:
            logger.warning(f"Invalid regex pattern: {e}")
            return False, None, None
```

- [ ] **Step 3: Extend `_validate_format` — `inject_text` and `require_pattern`**

Add two new checks to `_validate_format()` method (after line 396, before the final return):

```python
        # Check required regex pattern (e.g., legal citations)
        require_pattern = config.get("require_pattern")
        if require_pattern:
            try:
                if not re.search(require_pattern, content, re.IGNORECASE):
                    issues.append(f"Required pattern not found: {require_pattern}")
            except re.error:
                pass

        # Check inject_text — triggers if disclaimer text is absent
        inject_text = config.get("inject_text")
        check_absent = config.get("check_absent")
        if inject_text and check_absent:
            if check_absent.lower() not in content.lower():
                # Trigger — the disclaimer is missing. The inject_text will be
                # added to result.disclaimers by the main validate() loop.
                issues.append(f"Disclaimer missing (will inject): {check_absent}")
```

- [ ] **Step 4: Extend `_validate_llm` — Langfuse prompt + LLMRouter**

Replace `_validate_llm()` method (lines 285-333):

```python
    async def _validate_llm(
        self,
        content: str,
        config: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Validate content using LLM-based validation via LLMRouter."""
        # Resolve prompt: Langfuse first, then config fallback
        validation_prompt = None
        langfuse_key = config.get("langfuse_prompt_key")

        if langfuse_key:
            try:
                from app.services.langfuse_prompt_client import get_langfuse_prompt_client
                client = get_langfuse_prompt_client()
                validation_prompt = await client.get_prompt(langfuse_key)
            except Exception as e:
                logger.warning(f"Langfuse prompt '{langfuse_key}' not found, using fallback: {e}")

        if not validation_prompt:
            validation_prompt = config.get("validation_prompt")

        if not validation_prompt:
            return False, None, None

        try:
            from app.agents.llm_router import get_llm_router
            from app.agents.llm_client import ModelRole

            router = await get_llm_router()
            response = await router.chat(
                messages=[
                    {"role": "system", "content": "You are a content validator. Respond with only 'PASS' or 'FAIL: <reason>'."},
                    {"role": "user", "content": f"{validation_prompt}\n\nContent to validate:\n{content[:2000]}"},
                ],
                role=ModelRole.PLANNER,
                max_tokens=100,
                temperature=0.1,
            )

            reply = response.content or ""
            if reply.strip().upper().startswith("FAIL"):
                reason = reply.replace("FAIL:", "").replace("FAIL", "").strip()
                return True, f"LLM validation failed: {reason}", None

            return False, None, None

        except Exception as e:
            logger.error(f"LLM validation error: {e}")
            return False, None, None
```

- [ ] **Step 5: Update `validate()` — sector param, registry merge, REDACT with re.sub, disclaimers**

Replace `validate()` method (lines 403-496):

```python
    async def validate(
        self,
        content: str,
        *,
        agent_name: Optional[str] = None,
        tenant_id: Optional[UUID] = None,
        sector: Optional[str] = None,
    ) -> OverallValidationResult:
        """Validate content against all applicable guardrails."""
        if not settings.guardrails_enabled:
            return OverallValidationResult()

        start_time = time.time()
        guardrails = await self._load_guardrails(tenant_id, sector)

        results = []
        should_block = False
        should_warn = False
        redacted_content = content
        disclaimers: List[str] = []

        for guardrail in guardrails:
            if not self._applies_to_agent(guardrail, agent_name):
                continue

            guardrail_type = GuardrailType(guardrail["guardrail_type"])
            config = guardrail["config"]
            action = GuardrailAction(guardrail["action_on_match"])

            matched = False
            details = None
            matched_content = None

            if guardrail_type == GuardrailType.REGEX:
                matched, details, matched_content = await self._validate_regex(redacted_content, config)
            elif guardrail_type == GuardrailType.KEYWORD:
                matched, details, matched_content = self._validate_keyword(redacted_content, config)
            elif guardrail_type == GuardrailType.SEMANTIC:
                matched, details, matched_content = await self._validate_semantic(redacted_content, config)
            elif guardrail_type == GuardrailType.LLM_VALIDATOR:
                matched, details, matched_content = await self._validate_llm(redacted_content, config)
            elif guardrail_type == GuardrailType.LENGTH:
                matched, details, matched_content = self._validate_length(redacted_content, config)
            elif guardrail_type == GuardrailType.FORMAT:
                matched, details, matched_content = self._validate_format(redacted_content, config)

            result = ValidationResult(
                guardrail_id=guardrail["id"],
                guardrail_name=guardrail["guardrail_name"],
                guardrail_type=guardrail_type,
                matched=matched,
                action=action,
                details=details,
                matched_content=matched_content,
            )
            results.append(result)

            if matched:
                logger.warning(f"🛡️ Guardrail '{guardrail['guardrail_name']}' triggered: {details}")

                if action == GuardrailAction.BLOCK:
                    should_block = True
                elif action == GuardrailAction.WARN:
                    should_warn = True
                    # Collect disclaimers from FORMAT guardrails with inject_text
                    inject_text = config.get("inject_text")
                    if inject_text:
                        disclaimers.append(inject_text)
                elif action == GuardrailAction.REDACT and matched_content:
                    # matched_content is the regex pattern for REGEX type
                    if guardrail_type == GuardrailType.REGEX:
                        flags = 0
                        flag_str = config.get("flags", "")
                        if "i" in flag_str: flags |= re.IGNORECASE
                        if "m" in flag_str: flags |= re.MULTILINE
                        if "s" in flag_str: flags |= re.DOTALL
                        try:
                            redacted_content = re.sub(matched_content, "[REDACTED]", redacted_content, flags=flags)
                        except re.error:
                            redacted_content = redacted_content.replace(matched_content, "[REDACTED]")
                    else:
                        redacted_content = redacted_content.replace(matched_content, "[REDACTED]")

        elapsed_ms = (time.time() - start_time) * 1000

        return OverallValidationResult(
            results=results,
            should_block=should_block,
            should_warn=should_warn,
            redacted_content=redacted_content if redacted_content != content else None,
            disclaimers=disclaimers,
            processing_time_ms=elapsed_ms,
        )
```

- [ ] **Step 6: Update `_load_guardrails` — merge registry + DB**

Replace `_load_guardrails()` method (lines 95-153):

```python
    async def _load_guardrails(
        self,
        tenant_id: Optional[UUID] = None,
        sector: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Load guardrails: registry baseline merged with DB overrides."""
        import time as time_module
        from app.services.guardrail_registry import get_guardrails_for_sector

        cache_key = (tenant_id, sector)
        now = time_module.time()

        if cache_key in self._guardrails_cache:
            if (now - self._cache_time.get(cache_key, 0)) < self._cache_ttl:
                return self._guardrails_cache[cache_key]

        # Step 1: Registry baseline (in-memory, instant)
        registry_guardrails = get_guardrails_for_sector(sector)

        # Step 2: DB overrides (via Main API HTTP)
        db_guardrails = []
        try:
            client = await self._get_http_client()
            headers = {
                "X-API-Key": settings.MICROSERVICES_API_KEY,
                "Content-Type": "application/json",
            }
            if tenant_id:
                headers["X-Tenant-ID"] = str(tenant_id)

            url = f"{settings.api_url}/api/v1/prompts/guardrails"
            params = {"active_only": "true"}
            if sector:
                params["sector"] = sector
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()

            guardrails_data = response.json()
            items = guardrails_data if isinstance(guardrails_data, list) else guardrails_data.get("guardrails", [])
            for g in items:
                db_guardrails.append({
                    "id": g.get("id"),
                    "tenant_id": g.get("tenant_id"),
                    "guardrail_name": g.get("guardrail_name"),
                    "description": g.get("description"),
                    "guardrail_type": g.get("guardrail_type"),
                    "config": g.get("config", {}),
                    "action_on_match": g.get("action_on_match"),
                    "applies_to": g.get("applies_to", []),
                    "priority": g.get("priority", 100),
                    "is_active": g.get("is_active", True),
                    "sector": g.get("sector"),
                })
        except Exception as e:
            logger.warning(f"Failed to load DB guardrails: {e}. Using registry only.")

        # Step 3: Merge — DB wins on name collision, DB deactivation removes registry entry
        db_by_name = {g["guardrail_name"]: g for g in db_guardrails}
        merged = []
        for rg in registry_guardrails:
            name = rg["guardrail_name"]
            if name in db_by_name:
                db_entry = db_by_name.pop(name)
                if db_entry.get("is_active", True):
                    merged.append(db_entry)  # DB override wins
                # else: admin deactivated — skip
            else:
                merged.append(rg)  # Registry baseline

        # Add remaining DB-only entries (admin custom guardrails)
        for db_entry in db_by_name.values():
            if db_entry.get("is_active", True):
                merged.append(db_entry)

        merged.sort(key=lambda g: g.get("priority", 100))

        # Cache
        self._guardrails_cache[cache_key] = merged
        self._cache_time[cache_key] = now

        logger.debug(f"Loaded {len(merged)} guardrails (registry={len(registry_guardrails)}, db={len(db_guardrails)}) for tenant={tenant_id}, sector={sector}")
        return merged
```

- [ ] **Step 7: Update cache — tuple keys**

Update `__init__` (line 82):
```python
        self._guardrails_cache: Dict[tuple, List[Dict[str, Any]]] = {}
        self._cache_time: Dict[tuple, float] = {}
```

Update `invalidate_cache` (lines 539-548):
```python
    def invalidate_cache(self, tenant_id: Optional[UUID] = None, sector: Optional[str] = None) -> None:
        """Invalidate guardrails cache."""
        if tenant_id is None and sector is None:
            self._guardrails_cache.clear()
            self._cache_time.clear()
            logger.info("🗑️ Invalidated all guardrails cache")
        else:
            key = (tenant_id, sector)
            self._guardrails_cache.pop(key, None)
            self._cache_time.pop(key, None)
            logger.info(f"🗑️ Invalidated guardrails cache for tenant={tenant_id}, sector={sector}")
```

- [ ] **Step 8: Verify the service loads**

Run: `cd backend/microservices/emma-agent-service && python -c "from app.services.guardrail_service import get_guardrail_service; print('OK')"`

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add backend/microservices/emma-agent-service/app/services/guardrail_service.py
git commit -m "feat(guardrails): sector-aware validate(), re.sub redaction, inject_text, Langfuse LLM validator"
```

---

## Chunk 3: Graph Integration — Helper + Synthesis Nodes + SSE

### Task 5: Guardrail Helper — shared `apply_guardrails()`

**Files:**
- Create: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/guardrail_helper.py`

- [ ] **Step 1: Create the helper module**

```python
"""
Guardrail Helper — shared validation for synthesis nodes.

Called by synthesize_react, synthesize_swarm, and classify (fast-path).
Returns (final_content, metadata_dict) after applying guardrail results.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

SECTOR_FALLBACK_MESSAGES = {
    "medical": (
        "⚕️ No puedo proporcionar esta información en el contexto sanitario. "
        "Consulte con un profesional sanitario cualificado."
    ),
    "legal": "⚖️ No puedo generar esta respuesta. Consulte con un profesional jurídico.",
    "documental": "No puedo generar esta respuesta. Reformule su consulta.",
}

DEFAULT_FALLBACK = "No puedo generar esta respuesta."


async def apply_guardrails(
    content: str,
    state: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """
    Validate content against sector-aware guardrails.

    Args:
        content: LLM-generated response text.
        state: LangGraph state dict (needs 'sector', 'tenant_id').

    Returns:
        (final_content, metadata_dict) where metadata_dict has:
          guardrail_blocked: bool
          guardrail_redacted: bool
          guardrail_warnings: list[str]
    """
    empty_metadata = {
        "guardrail_blocked": False,
        "guardrail_redacted": False,
        "guardrail_warnings": [],
    }

    # Early exit if guardrails disabled
    if not settings.guardrails_enabled:
        return content, empty_metadata

    try:
        from app.services.guardrail_service import get_guardrail_service

        service = get_guardrail_service()
        sector = state.get("sector")
        tenant_id = state.get("tenant_id")

        result = await service.validate(
            content=content,
            agent_name="synthesize",
            tenant_id=tenant_id,
            sector=sector,
        )

        metadata = {
            "guardrail_blocked": result.should_block,
            "guardrail_redacted": result.redacted_content is not None,
            "guardrail_warnings": [
                r.guardrail_name for r in result.results if r.matched
            ],
        }

        if result.should_block:
            fallback = SECTOR_FALLBACK_MESSAGES.get(sector, DEFAULT_FALLBACK)
            return fallback, metadata

        if result.redacted_content:
            content = result.redacted_content

        if result.disclaimers:
            content += "\n\n---\n" + "\n".join(result.disclaimers)

        return content, metadata

    except Exception as e:
        logger.error(f"Guardrail validation failed (non-blocking): {e}")
        return content, empty_metadata
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/guardrail_helper.py
git commit -m "feat(guardrails): add guardrail_helper.py — shared apply_guardrails() for synthesis nodes"
```

---

### Task 6: Integrate guardrails into synthesis nodes

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_react.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py`

- [ ] **Step 1: Integrate in `synthesize_react_node`**

Read `synthesize_react.py` fully first. Find where `final_answer` is set (before the return statement). Add:

```python
from .guardrail_helper import apply_guardrails

# ... inside synthesize_react_node, before the return dict ...

# Guardrail validation
final_answer, guardrail_metadata = await apply_guardrails(final_answer, state)
```

Add `"guardrail_metadata": guardrail_metadata` to the returned dict.

- [ ] **Step 2: Integrate in `synthesize_swarm_node`**

Read `synthesize_swarm.py` fully first. Find where `content` (the final synthesized response) is set. Add:

```python
from .guardrail_helper import apply_guardrails

# ... after LLM synthesis, before return ...

content, guardrail_metadata = await apply_guardrails(content, state)
```

Add `"guardrail_metadata": guardrail_metadata` to the returned dict.

- [ ] **Step 3: Integrate in `classify_node` fast-path only**

Read `classify.py` fully first. Find the fast-path branch where `is_fast_path=True` and `final_answer` is set. Add:

```python
from .guardrail_helper import apply_guardrails

# ... inside the fast-path branch, before return ...

fast_response, guardrail_metadata = await apply_guardrails(fast_response, state)
```

Add `"guardrail_metadata": guardrail_metadata` to the fast-path return dict.

- [ ] **Step 4: Add `guardrail_metadata` to ReActState**

Read `state.py` and add `guardrail_metadata` as an optional dict field if not already present. This allows the SSE mapper to access it.

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_react.py backend/microservices/emma-agent-service/app/agents/langgraph/nodes/synthesize_swarm.py backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py backend/microservices/emma-agent-service/app/agents/langgraph/state.py
git commit -m "feat(guardrails): integrate apply_guardrails() in synthesize_react, synthesize_swarm, classify"
```

---

### Task 7: SSE events for guardrail actions

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py`

- [ ] **Step 1: Add SSE event mapping**

Read `emma.py` fully first. Find `_generate_langgraph_sse()`. In the section that processes state snapshots, add detection for `guardrail_metadata`:

```python
# After processing final_answer / other state fields:
guardrail_meta = state_snapshot.get("guardrail_metadata", {})
if guardrail_meta.get("guardrail_blocked"):
    yield {
        "event": "guardrail_blocked",
        "data": json.dumps({
            "sector": state_snapshot.get("sector"),
            "warnings": guardrail_meta.get("guardrail_warnings", []),
        }),
    }
elif guardrail_meta.get("guardrail_redacted"):
    yield {
        "event": "guardrail_redacted",
        "data": json.dumps({
            "warnings": guardrail_meta.get("guardrail_warnings", []),
        }),
    }
elif guardrail_meta.get("guardrail_warnings"):
    yield {
        "event": "guardrail_warning",
        "data": json.dumps({
            "warnings": guardrail_meta.get("guardrail_warnings", []),
        }),
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/api/emma.py
git commit -m "feat(guardrails): emit SSE events for guardrail_blocked, guardrail_redacted, guardrail_warning"
```

---

## Chunk 4: Verified Generation Overrides + HITL + Prompts

### Task 8: Verified generation — sector overrides

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/services/verified_generation/service.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/stop_and_go/strategies/verified.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/stop_and_go/nodes/search_and_evaluate.py`
- Modify: `backend/microservices/emma-agent-service/app/core/config.py`

- [ ] **Step 1: Add `VERIFIED_HITL_TIMEOUT_SECONDS` to config**

In `config.py`, after line 295, add:

```python
    verified_hitl_timeout_seconds: int = int(os.getenv("VERIFIED_HITL_TIMEOUT_SECONDS", "300"))
```

- [ ] **Step 2: Inject sector overrides in verified service**

Read `service.py` fully. Find where `mode_config` is built and `hitl_enabled` is set. Modify:

```python
from app.agents.langgraph.sectors.registry import get_active_sector_config

# ... inside generate_verified_document() or equivalent ...

sector_config = get_active_sector_config()

# HITL: sector override takes priority
if sector_config and sector_config.hitl_default:
    hitl_enabled = True
else:
    hitl_enabled = settings.verified_hitl_enabled

# Inject sector overrides into mode_config
mode_config = {
    "auto_correct": request.auto_correct,
    "max_correction_attempts": request.max_correction_attempts,
    "verification_timeout_seconds": request.verification_timeout_seconds,
    "document_type": request.document_type,
    # Sector overrides
    "fidelity_confidence_cap": sector_config.fidelity_confidence_cap if sector_config else 0.80,
    "max_evidence": sector_config.max_evidence if sector_config else 5,
}
```

- [ ] **Step 3: Dynamic fidelity cap in verified.py**

In `verified.py`, replace the hard-coded constant usage. Keep `FIDELITY_CONFIDENCE_CAP = 0.80` as fallback, but add a method:

```python
    def _get_fidelity_cap(self, state: dict) -> float:
        """Get fidelity confidence cap — sector override or default."""
        mode_config = state.get("mode_config", {})
        return mode_config.get("fidelity_confidence_cap", FIDELITY_CONFIDENCE_CAP)
```

Find `_combine_verdicts()` and replace `FIDELITY_CONFIDENCE_CAP` usage with `self._get_fidelity_cap(state)`. The `state` parameter needs to be passed to `_combine_verdicts()` — check current signature and add if needed.

- [ ] **Step 4: Dynamic max_evidence in search_and_evaluate.py**

Find `MAX_EXTERNAL = 5` and replace with:

```python
mode_config = state.get("mode_config", {})
max_external = mode_config.get("max_evidence", 5)
```

Apply this wherever `MAX_EXTERNAL` is used for limiting evidence (search the file for all references).

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/core/config.py backend/microservices/emma-agent-service/app/services/verified_generation/service.py backend/microservices/emma-agent-service/app/agents/langgraph/stop_and_go/strategies/verified.py backend/microservices/emma-agent-service/app/agents/langgraph/stop_and_go/nodes/search_and_evaluate.py
git commit -m "feat(verified): sector-aware confidence caps, max_evidence, HITL activation"
```

---

### Task 9: Langfuse prompts for medical dosage validator

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/services/prompt_registry.py`
- Modify: `backend/microservices/emma-agent-service/config/prompts/emma_prompts.yaml`

- [ ] **Step 1: Add entries to prompt_registry.py**

At the end of `PROMPT_REGISTRY` dict, add:

```python
    # ── Guardrail prompts ─────────────────────────────────────────────────
    "guardrail_medical_dosage_system": PromptEntry(
        yaml_path=("guardrails", "medical_dosage", "system"),
        description="System prompt for medical dosage coherence validation guardrail",
        section="guardrails",
    ),
    "guardrail_medical_dosage_user": PromptEntry(
        yaml_path=("guardrails", "medical_dosage", "user"),
        description="User prompt template for medical dosage validation",
        section="guardrails",
    ),
```

- [ ] **Step 2: Add YAML fallback content**

In `emma_prompts.yaml`, add at the end:

```yaml
# =============================================================================
# Guardrail Prompts
# =============================================================================
guardrails:
  medical_dosage:
    system: |
      Eres un validador de coherencia farmacológica. Tu tarea es verificar que
      las dosis mencionadas en el texto son coherentes y no contienen errores
      evidentes. NO diagnostiques ni prescribas — solo verifica coherencia.

      Reglas:
      - Si el texto menciona dosis específicas, verifica que los rangos son razonables
      - Si detectas una dosis potencialmente peligrosa (10x fuera de rango), responde FAIL
      - Si no hay dosis mencionadas, responde PASS
      - Si las dosis parecen razonables, responde PASS
      - Responde SOLO con 'PASS' o 'FAIL: <razón>'

    user: |
      Verifica la coherencia de las dosis mencionadas en el siguiente texto:

      {content}
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/services/prompt_registry.py backend/microservices/emma-agent-service/config/prompts/emma_prompts.yaml
git commit -m "feat(guardrails): add Langfuse prompt entries for medical dosage validator"
```

---

### Task 10: Seed Script

**Files:**
- Create: `backend/microservices/emma-agent-service/scripts/seed_guardrails.py`

- [ ] **Step 1: Create the seed script**

Follow the same pattern as `scripts/seed_langfuse_prompts.py`. The script should:

1. Parse args: `--force`, `--diff`, `--dry-run`, `--sector`
2. Import `GUARDRAIL_ENTRIES` from `guardrail_registry`
3. For each entry:
   - Call `POST /api/v1/prompts/guardrails` on Main API (with `sector` field)
   - If `langfuse_prompt_key` → also seed the Langfuse prompt
4. Default mode: skip if `guardrail_name` exists
5. `--force`: update existing entries
6. `--diff`: show differences

Read `scripts/seed_langfuse_prompts.py` first to match the exact pattern (arg parsing, HTTP client, error handling, output formatting).

- [ ] **Step 2: Test the script**

Run: `cd backend/microservices/emma-agent-service && python scripts/seed_guardrails.py --dry-run`

Expected: Lists all 18 guardrails with their sector and action, shows what would be created.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/scripts/seed_guardrails.py
git commit -m "feat(guardrails): add seed_guardrails.py — populates SQL + Langfuse from registry"
```

---

## Chunk 5: Testing & Verification

### Task 11: Manual verification with running services

**Prerequisites:** Services must be running (`cd backend/docker && ./start-dev.sh`)

- [ ] **Step 1: Run migration**

```bash
cd backend && alembic upgrade head
```

- [ ] **Step 2: Seed guardrails**

```bash
cd backend/docker && docker compose exec emma-agent-service python scripts/seed_guardrails.py
```

Expected: `Created 18 guardrails (5 global, 7 medical, 3 legal, 3 documental)`

- [ ] **Step 3: Verify guardrails via API**

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)

# All guardrails
curl -s "http://localhost:8000/api/v1/prompts/guardrails?active_only=true" \
  -H "X-API-Key: $API_KEY" > /tmp/guardrails.json
python3 -c "import json; data=json.load(open('/tmp/guardrails.json')); print(f'Total: {len(data)}')"

# Medical only
curl -s "http://localhost:8000/api/v1/prompts/guardrails?active_only=true&sector=medical" \
  -H "X-API-Key: $API_KEY" > /tmp/guardrails_medical.json
python3 -c "import json; data=json.load(open('/tmp/guardrails_medical.json')); print(f'Medical+Global: {len(data)}')"
```

Expected: Total ≥18, Medical+Global = 12

- [ ] **Step 4: Test guardrail validation directly**

```bash
cd backend/docker && docker compose exec emma-agent-service python -c "
import asyncio
from app.services.guardrail_service import get_guardrail_service

async def test():
    service = get_guardrail_service()

    # Test 1: REDACT — NHC in medical
    result = await service.validate(
        'El paciente con NHC 12345 tiene dolor.',
        sector='medical',
    )
    print(f'Test REDACT NHC: blocked={result.should_block}, redacted={result.redacted_content}')
    assert result.redacted_content and 'REDACTED' in result.redacted_content, 'NHC not redacted!'

    # Test 2: BLOCK — diagnosis
    result = await service.validate(
        'El diagnóstico es diabetes tipo 2.',
        sector='medical',
    )
    print(f'Test BLOCK diagnosis: blocked={result.should_block}')
    assert result.should_block, 'Diagnosis not blocked!'

    # Test 3: WARN — disclaimer
    result = await service.validate(
        'Los resultados del análisis muestran valores normales.',
        sector='medical',
    )
    print(f'Test WARN disclaimer: disclaimers={result.disclaimers}')
    assert len(result.disclaimers) > 0, 'No disclaimer injected!'

    # Test 4: Legal disclaimer
    result = await service.validate(
        'Según el artículo 52 del Estatuto, el despido es improcedente.',
        sector='legal',
    )
    print(f'Test legal disclaimer: disclaimers={result.disclaimers}')

    # Test 5: Global PII — email
    result = await service.validate(
        'Contacte con juan@empresa.com para más información.',
        sector='legal',
    )
    print(f'Test REDACT email: redacted={result.redacted_content}')
    assert result.redacted_content and 'REDACTED' in result.redacted_content, 'Email not redacted!'

    print('\\n✅ All guardrail tests passed!')

asyncio.run(test())
"
```

- [ ] **Step 5: Test E2E via Emma query (if services running)**

```bash
# Send a medical query through the full pipeline
curl -s -X POST "http://localhost:8009/emma/stream" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000001" \
  -d '{"query": "Hola, buenos días", "context": {"user_id": "a060f046-9992-4d1a-87c4-fa5c6f8c066c"}}' \
  > /tmp/emma_response.txt
cat /tmp/emma_response.txt | grep -c "guardrail"
```

Expected: Response contains guardrail SSE events if medical sector is active.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "test(guardrails): verify sector-aware guardrails with running services"
```

---

## Post-Implementation Checklist

- [ ] All 18 guardrails seeded successfully
- [ ] REDACT catches ALL PII occurrences (not just first)
- [ ] Medical disclaimer injected on medical responses
- [ ] Diagnosis/prescription blocked in medical sector
- [ ] Legal disclaimer injected on legal responses
- [ ] Confidence cap is 0.60 for medical (not 0.80)
- [ ] max_evidence is 15 for medical (not 5)
- [ ] HITL enabled by default for medical verified generation
- [ ] SSE events emitted for guardrail actions
- [ ] Admin can override via DB (merge logic works)
- [ ] `--force` seed restores defaults after admin changes
