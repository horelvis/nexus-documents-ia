# Sector-Aware Guardrails & Medical Safety — Design Spec

**Date**: 2026-03-15
**Status**: Approved (spec-reviewer pass 2 — 0 critical, 0 important, 2 suggestions incorporated)
**Scope**: Phase 1 — Minimum Viable Safe for Medical Sector + Guardrail improvements across all sectors

## Problem Statement

Emma's guardrail framework (`GuardrailService`) has 6 validation types and 3 actions (BLOCK, WARN, REDACT) but is **not integrated into the LangGraph generation pipeline**. `validate_output()` is opt-in and no graph node invokes it. Additionally:

1. **No sector-specific guardrails** — the same (empty) guardrails apply to legal, medical, and documental sectors
2. **No PHI/PII redaction** in responses — `patterns.py` detects PII but isn't connected to output
3. **Verified generation confidence cap** is hard-coded at 0.80 — too high for medical claims
4. **Evidence limits** are hard-coded at 5 — insufficient for medical verification
5. **HITL is disabled by default** — the review node is implemented but `VERIFIED_HITL_ENABLED=false`

## Goals

1. **Connect guardrails to the LangGraph pipeline** — every response passes through validation before reaching the user
2. **Define sector-specific guardrail profiles** — medical, legal, documental, each with appropriate rules
3. **Medical safety layer** — PHI redaction, diagnosis blocking, mandatory disclaimers, dosage validation
4. **Sector-aware verified generation** — configurable confidence caps, evidence limits, and HITL per sector
5. **Single source of truth** — `guardrail_registry.py` following the `prompt_registry.py` pattern

## Non-Goals

- Frontend UI for guardrail management (admin uses API or seed script)
- Frontend HITL review UI (SSE events emitted; UI implementation is separate work)
- Medical knowledge bases (PubMed, DrugBank) — Phase 2
- Dedicated medical agent — Phase 3
- Pre-generation guardrails (input filtering) — future work
- Streaming-level guardrails (validating SSE chunks) — future work

## Architecture

### Approach: Hybrid — Nodos + Registry (Enfoque C)

```
guardrail_registry.py (source of truth)
        │
        ├── seed_guardrails.py → SQL (Main API) + Langfuse (LLM_VALIDATOR prompts)
        │
        ▼
GuardrailService.validate(content, agent, tenant, sector)
        │
        ├── Load from registry (baseline)
        ├── Load from DB (admin overrides)
        └── Merge (DB wins on name collision)
        │
        ▼
6 Validators: REGEX | KEYWORD | SEMANTIC | LLM_VALIDATOR | LENGTH | FORMAT
        │
        ▼
OverallValidationResult (should_block, redacted_content, disclaimers)
        │
        ▼
Synthesis nodes apply result:
  BLOCK  → sector-specific fallback message
  REDACT → cleaned content
  WARN   → append disclaimers
```

### Data Flow

```
SectorConfig (sectors/config.py + registry.py)
    ├── guardrail_profile: str       → GuardrailService sector filter
    ├── fidelity_confidence_cap: float → verified.py _combine_verdicts()
    ├── max_evidence: int             → search_and_evaluate.py MAX_EXTERNAL
    └── hitl_default: bool            → service.py state["hitl_enabled"]
```

## Detailed Design

### 1. Guardrail Registry (`guardrail_registry.py`)

**New file**: `emma-agent-service/app/services/guardrail_registry.py`

```python
@dataclass
class GuardrailEntry:
    name: str                          # "medical_phi_nhc_redact"
    description: str                   # Human-readable description
    guardrail_type: str                # "regex" | "keyword" | "semantic" | "llm_validator" | "length" | "format"
    action: str                        # "block" | "warn" | "redact"
    config: dict                       # Type-specific configuration
    sector: str | None                 # None = global, "medical" | "legal" | "documental"
    applies_to: list[str]              # Agent filter (empty = all agents)
    priority: int                      # Lower = higher priority (evaluated first)
    is_system: bool = True             # Distinguishes seed vs admin-created
    langfuse_prompt_key: str | None = None  # Only for LLM_VALIDATOR type

GUARDRAIL_ENTRIES: list[GuardrailEntry] = [...]

def get_guardrails_for_sector(sector: str | None) -> list[dict]:
    """Returns global guardrails + sector-specific guardrails, sorted by priority."""
```

#### Guardrail Definitions (18 total)

**Global (5)** — all sectors:

| Name | Type | Action | Config |
|------|------|--------|--------|
| `global_pii_email` | REGEX | REDACT | Patterns from `patterns.py` EMAIL_PATTERN |
| `global_pii_phone` | REGEX | REDACT | Patterns from `patterns.py` PHONE_PATTERNS (ES, intl) |
| `global_pii_national_id` | REGEX | REDACT | Patterns from `patterns.py` (DNI/NIE/NIF/SSN) |
| `global_pii_financial` | REGEX | REDACT | Patterns from `patterns.py` (credit cards, IBAN) |
| `global_min_response` | LENGTH | WARN | `min_chars: 20` |

**Medical (7)** — `ACTIVE_SECTOR=medical`:

| Name | Type | Action | Config |
|------|------|--------|--------|
| `medical_phi_nhc` | REGEX | REDACT | NHC, Historia Clínica patterns from sector entity_patterns |
| `medical_no_diagnosis` | KEYWORD | BLOCK | `blocked_words: ["el diagnóstico es", "usted tiene", "usted padece", "padece de", "su diagnóstico"]` |
| `medical_no_prescription` | KEYWORD | BLOCK | `blocked_words: ["le receto", "debe tomar", "prescripción:", "le prescribo", "tome X mg"]` |
| `medical_disclaimer` | FORMAT | WARN | `inject_text: "⚕️ Esta información es documental y no sustituye el criterio médico profesional."` |
| `medical_dosage_check` | LLM_VALIDATOR | WARN | `langfuse_prompt_key: "guardrail_medical_dosage_system"` |
| `medical_sensitive_topics` | SEMANTIC | WARN | `forbidden_topics: ["suicidio", "autolesión", "eutanasia sin contexto legal"], similarity_threshold: 0.90` — WARN (not BLOCK) to avoid false positives on legitimate psychiatric/occupational health documentation |
| `medical_patient_data` | REGEX | REDACT | Date of birth patterns + clinical data identifiers |

**Legal (3)** — `ACTIVE_SECTOR=legal`:

| Name | Type | Action | Config |
|------|------|--------|--------|
| `legal_disclaimer` | FORMAT | WARN | `inject_text: "⚖️ Esta información no constituye asesoramiento jurídico profesional."` |
| `legal_no_verdict` | KEYWORD | WARN | `blocked_words: ["el tribunal debe fallar", "la sentencia será", "el veredicto debe ser"]` |
| `legal_source_citation` | FORMAT | WARN | `require_pattern: "Art\\.\\s*\\d+|Ley\\s+\\d+"` — warns if no legal citation |

**Documental (3)** — `ACTIVE_SECTOR=documental`:

| Name | Type | Action | Config |
|------|------|--------|--------|
| `documental_disclaimer` | FORMAT | WARN | `inject_text: "ℹ️ Esta información tiene carácter orientativo."` |
| `documental_source_required` | FORMAT | WARN | Warns if response lacks source references |
| `documental_length_limit` | LENGTH | WARN | `max_chars: 8000` |

### 2. SectorConfig Extension

**Modified file**: `emma-agent-service/app/agents/langgraph/sectors/config.py`

4 new fields on `SectorConfig` dataclass:

```python
guardrail_profile: str = "global"
fidelity_confidence_cap: float = 0.80
max_evidence: int = 5
hitl_default: bool = False
```

**Values per sector** (in `registry.py`):

| Field | Legal | Medical | Documental |
|-------|-------|---------|------------|
| `guardrail_profile` | `"legal"` | `"medical"` | `"documental"` |
| `fidelity_confidence_cap` | `0.80` | `0.60` | `0.80` |
| `max_evidence` | `5` | `15` | `5` |
| `hitl_default` | `False` | `True` | `False` |

### 3. GuardrailService Modifications

**Modified file**: `emma-agent-service/app/services/guardrail_service.py`

Changes:

1. **`validate()` signature** — add `sector: str | None = None` parameter
2. **`_load_guardrails(tenant_id, sector)`** — merge registry baseline + DB overrides:
   - Step 1: `get_guardrails_for_sector(sector)` — in-memory, no network call
   - Step 2: `GET /api/v1/prompts/guardrails?active_only=true&sector={sector}` — DB via Main API
   - Step 3: Merge by `guardrail_name` — DB wins on collision
3. **`OverallValidationResult`** — add `disclaimers: list[str]` field (default `[]`)
4. **`_validate_format()` extended** — 2 new config keys:
   - `inject_text: str` — when FORMAT+WARN triggers and text is missing, the disclaimer text is added to `result.disclaimers[]` (not `matched_content`). Flow: `_validate_format()` returns `(matched=True, details, None)` → in the main validation loop, if `action==WARN` and `config.get("inject_text")`, append to `result.disclaimers`.
   - `require_pattern: str` — regex pattern that MUST be present in content. If absent, guardrail triggers. Used by `legal_source_citation`.
5. **`_validate_regex()` fix for REDACT** — replace `re.search()` + `str.replace()` with `re.sub(pattern, "[REDACTED]", content)` to catch ALL occurrences. Critical for PHI where multiple NHC/phone numbers may appear.
6. **`_validate_llm()` Langfuse integration** — check `config.get("langfuse_prompt_key")` first → resolve via `get_langfuse_prompt_client().get_prompt(key)` → fall back to `config.get("validation_prompt")`. Route through `LLMRouter` with `ModelRole.PLANNER` instead of raw HTTP.
7. **Cache key** — change from `tenant_id` to `(tenant_id, sector)` tuple
8. **Early exit** — `apply_guardrails()` helper checks `settings.guardrails_enabled` first and returns no-op `(content, {})` immediately if disabled

Merge priority:
1. Registry guardrails (baseline, `is_system=True` — handled in-memory, not stored in DB column)
2. DB guardrails with same name (admin override, wins)
3. DB guardrails with new names (admin additions)
4. Admin deactivations (`is_active=False` in DB) remove registry entries with same name

**Note on `is_system`**: This flag is NOT a DB column — it exists only in-memory on `GuardrailEntry`. Registry entries are always `is_system=True`. DB-only entries (created by admin via API) are implicitly `is_system=False`. The merge logic uses `guardrail_name` matching, not a DB flag.

### 4. Graph Integration — 3 Synthesis Nodes

**New file**: `emma-agent-service/app/agents/langgraph/nodes/guardrail_helper.py`

Shared helper to avoid duplication across nodes:

```python
SECTOR_FALLBACK_MESSAGES = {
    "medical": "⚕️ No puedo proporcionar esta información en el contexto sanitario. "
               "Consulte con un profesional sanitario cualificado.",
    "legal": "⚖️ No puedo generar esta respuesta. Consulte con un profesional jurídico.",
    "documental": "No puedo generar esta respuesta. Reformule su consulta.",
    None: "No puedo generar esta respuesta.",
}

async def apply_guardrails(content: str, state: dict) -> tuple[str, dict]:
    """
    Validates content against sector-aware guardrails.
    Returns (final_content, metadata_dict).

    metadata_dict keys:
      - guardrail_blocked: bool
      - guardrail_redacted: bool
      - guardrail_warnings: list[str]  (triggered guardrail names)
    """
```

**Integration points** (3 nodes):

| Node | File | When |
|------|------|------|
| `synthesize_react_node` | `nodes/synthesize_react.py` | After formatting final response |
| `synthesize_swarm_node` | `nodes/synthesize_swarm.py` | After LLM synthesis of worker results |
| `classify_node` | `nodes/classify.py` | Only on fast-path responses (greetings, identity) |

**SSE event mapping for guardrail metadata**: Each node stores guardrail metadata in state (e.g., `state["guardrail_metadata"]`). In `_generate_langgraph_sse()`, when the final state snapshot contains `guardrail_metadata`, the SSE mapper emits the corresponding events. For classify fast-path, the returned state dict includes `guardrail_metadata` alongside `final_answer` and `is_fast_path`, which `_generate_langgraph_sse()` picks up from the state diff.

### 5. Verified Generation — Sector Overrides

**Modified files**:

| File | Change |
|------|--------|
| `verified_generation/service.py` | Read `sector_config.hitl_default` → `state["hitl_enabled"]`; inject `fidelity_confidence_cap` and `max_evidence` into `mode_config` |
| `stop_and_go/strategies/verified.py` | Replace `FIDELITY_CONFIDENCE_CAP = 0.80` with `_get_fidelity_cap(state)` reading from `mode_config` |
| `stop_and_go/nodes/search_and_evaluate.py` | Replace `MAX_EXTERNAL = 5` with `mode_config.get("max_evidence", 5)` |

**HITL activation flow** (medical sector):
```
SectorConfig.hitl_default=True
    → service.py: hitl_enabled = True
    → state["hitl_enabled"] = True
    → review_node: calls interrupt() for claims below confidence_threshold
    → SSE: "review_required" event emitted
    → Frontend: shows review UI (future work)
    → POST /verified/resume: Command(resume=decisions)
    → synthesize: assembles document with human-reviewed claims
```

### 6. SSE Events

**Modified file**: `emma-agent-service/app/api/emma.py`

New SSE event types in `_generate_langgraph_sse()`:

| Event | When | Data |
|-------|------|------|
| `guardrail_blocked` | Response was blocked | `{"sector": "medical", "guardrail": "medical_no_diagnosis"}` |
| `guardrail_redacted` | Content was redacted | `{"fields_redacted": 3}` |
| `guardrail_warning` | Disclaimer injected | `{"disclaimers": ["⚕️ Esta información..."]}` |

### 7. Seed Script (`seed_guardrails.py`)

**New file**: `emma-agent-service/scripts/seed_guardrails.py`

```
Usage:
  python scripts/seed_guardrails.py              # Create missing only (safe default)
  python scripts/seed_guardrails.py --force       # Overwrite all system guardrails
  python scripts/seed_guardrails.py --diff        # Show registry vs DB differences
  python scripts/seed_guardrails.py --dry-run     # Preview without changes
  python scripts/seed_guardrails.py --sector medical  # Single sector only
```

Flow:
1. Import `GUARDRAIL_ENTRIES` from `guardrail_registry.py`
2. For each entry:
   - `POST /api/v1/prompts/guardrails` on Main API (creates in SQL)
   - If `langfuse_prompt_key` → create/update prompt in Langfuse via `langfuse_prompt_client`
3. Default mode: skip if `guardrail_name` already exists in DB
4. `--force` mode: upsert (update config, action, priority)

### 8. Langfuse Prompt Entries

**Modified file**: `emma-agent-service/app/services/prompt_registry.py`

2 new entries for the medical dosage LLM_VALIDATOR:

| Key | YAML Path | Description |
|-----|-----------|-------------|
| `guardrail_medical_dosage_system` | `guardrails.medical_dosage.system` | System prompt for dosage coherence validation |
| `guardrail_medical_dosage_user` | `guardrails.medical_dosage.user` | User template: validates doses mentioned in content |

## Files Changed Summary

All paths relative to `backend/microservices/emma-agent-service/`:

| File | Type | Description |
|------|------|-------------|
| `app/services/guardrail_registry.py` | NEW | 18 guardrail entries, `get_guardrails_for_sector()` |
| `scripts/seed_guardrails.py` | NEW | Seed script for SQL + Langfuse |
| `app/agents/langgraph/nodes/guardrail_helper.py` | NEW | `apply_guardrails()` shared helper with early-exit check |
| `app/services/guardrail_service.py` | MOD | Sector param, registry merge, disclaimers, cache key, `re.sub()` fix, Langfuse in `_validate_llm()`, `inject_text`/`require_pattern` in `_validate_format()` |
| `app/agents/langgraph/sectors/config.py` | MOD | 4 new scalar fields on `SectorConfig` (frozen=True safe) |
| `app/agents/langgraph/sectors/registry.py` | MOD | Sector values (caps, evidence, HITL) |
| `app/services/verified_generation/service.py` | MOD | Sector overrides in mode_config + HITL |
| `app/agents/langgraph/stop_and_go/strategies/verified.py` | MOD | Dynamic `_get_fidelity_cap()` |
| `app/agents/langgraph/stop_and_go/nodes/search_and_evaluate.py` | MOD | Dynamic `max_external` |
| `app/agents/langgraph/nodes/synthesize_react.py` | MOD | Call `apply_guardrails()`, store metadata in state |
| `app/agents/langgraph/nodes/synthesize_swarm.py` | MOD | Call `apply_guardrails()`, store metadata in state |
| `app/agents/langgraph/nodes/classify.py` | MOD | Call `apply_guardrails()` on fast-path |
| `app/api/emma.py` | MOD | SSE events for guardrail actions from `guardrail_metadata` state |
| `app/services/prompt_registry.py` | MOD | 2 new entries for dosage validator |
| `app/core/config.py` | MOD | Add `VERIFIED_HITL_TIMEOUT_SECONDS` setting (default 300) |
| `config/prompts/emma_prompts.yaml` | MOD | Add `guardrails.medical_dosage.system` and `.user` YAML fallback content |

Paths relative to `backend/`:

| File | Type | Description |
|------|------|-------------|
| `alembic/versions/XXXX_add_sector_to_guardrails.py` | NEW | Migration: add `sector VARCHAR(50)` column to `emma_guardrails` table + index |
| `app/api/v1/prompts.py` | MOD | Add `sector` query parameter to `GET /guardrails` endpoint; add `sector: Optional[str]` to `GuardrailCreate` schema and INSERT statement |

## Testing Strategy

1. **Unit tests** for `guardrail_registry.py`:
   - `get_guardrails_for_sector("medical")` returns 5 global + 7 medical
   - `get_guardrails_for_sector(None)` returns 5 global only

2. **Integration tests** for `guardrail_service.py`:
   - REGEX guardrail redacts NHC from medical response
   - KEYWORD guardrail blocks diagnosis statement
   - FORMAT guardrail injects medical disclaimer
   - DB override deactivates a system guardrail
   - Merge logic: DB wins on name collision

3. **E2E tests** via diagnostics:
   - Send medical query through ReAct pipeline → verify disclaimer present
   - Send response with NHC number → verify redacted in output
   - Send diagnosis-like response → verify blocked and fallback returned

4. **Verified generation tests**:
   - Medical sector: confidence cap at 0.60 (not 0.80)
   - Medical sector: max_evidence=15 used in search
   - Medical sector: HITL enabled, review_node calls interrupt()

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| KEYWORD false positives ("diagnóstico" in legitimate context) | Use phrase-level keywords ("el diagnóstico es") not single words; WARN action for borderline cases |
| Guardrail latency on every response | REGEX/KEYWORD/LENGTH/FORMAT are <5ms; SEMANTIC ~20ms (BGE-M3 already loaded); LLM_VALIDATOR ~200ms but only for medical. Total expected: <50ms for non-medical, <250ms for medical |
| HITL breaks SSE flow without frontend UI | SSE emits `review_required` event; add `VERIFIED_HITL_TIMEOUT_SECONDS=300` (5 min) config — auto-approves all claims if no human review within timeout, so system doesn't hang permanently. Document that frontend HITL UI is required for full medical verified generation |
| Admin accidentally deactivates critical medical guardrail | Registry entries are baseline; seed script `--force` can restore. API response includes `is_system_override: true` warning when deactivating a registry-defined guardrail |
| REDACT misses PII occurrences | Fixed: `_validate_regex()` now uses `re.sub()` instead of `re.search()` + `str.replace()` to catch ALL matches |
| Source metadata contains PII | Guardrails validate `content` (LLM response) only. Source document titles/snippets in `sources[]` are NOT redacted. For medical compliance, a future phase should extend redaction to source metadata |

## Migration

### Database Migration Required

New Alembic migration `XXXX_add_sector_to_guardrails.py`:

```python
def upgrade():
    op.add_column('emma_guardrails', sa.Column('sector', sa.String(50), nullable=True))
    op.create_index('ix_emma_guardrails_sector', 'emma_guardrails', ['sector'])

def downgrade():
    op.drop_index('ix_emma_guardrails_sector', table_name='emma_guardrails')
    op.drop_column('emma_guardrails', 'sector')
```

- `sector` is nullable — `NULL` means global (applies to all sectors)
- Index on `sector` for efficient filtering in `GET /guardrails?sector=medical`
- Main API `GET /guardrails` endpoint gains `sector: Optional[str]` query param — filters `WHERE sector = :sector OR sector IS NULL`

### Behavioral Compatibility

- Seed script is additive (safe by default)
- `SectorConfig` new fields have defaults matching current behavior (no behavioral change for legal/documental without explicit opt-in)
- `FIDELITY_CONFIDENCE_CAP` constant kept as fallback when `mode_config` doesn't have override
- Existing guardrails in DB (if any) have `sector=NULL` → treated as global → no behavioral change

### Testing: Merge Logic Edge Cases

Specific test cases for the merge logic:

1. Registry entry `medical_disclaimer` + no DB entry → registry wins
2. Registry entry `medical_disclaimer` + DB entry with same name, `is_active=True` → DB config wins
3. Registry entry `medical_disclaimer` + DB entry with same name, `is_active=False` → guardrail removed (admin deactivation respected)
4. No registry entry + DB entry `custom_medical_rule` → DB entry added (admin custom)
5. Registry entry `global_pii_email` + DB entry `global_pii_email` with different `config` → DB config wins (admin override)
