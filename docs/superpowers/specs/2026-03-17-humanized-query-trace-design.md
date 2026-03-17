# Humanized Query Trace — Design Spec

**Date**: 2026-03-17
**Status**: Approved
**Sector impact**: legal, medical, documental

## Problem

Emma's current reasoning display (`WorkflowProgress`, `SLMThinkingDisplay`, `ReasoningDisplay`) shows technical agent internals: tool names, step indices, raw metadata. This is unintelligible for end-users in legal and medical sectors who need to understand *why* Emma arrived at a conclusion — not *how* the pipeline executed.

## Solution

Two complementary features that humanize Emma's query execution visibility:

1. **Phase Breadcrumb** — Inline horizontal indicator showing fixed pipeline phases during execution. Disappears on completion.
2. **Explanation Panel** — Collapsible post-hoc block below the response with a sector-adapted natural language explanation of what Emma did and why.

## Architecture Decision

**Approach: Dedicated `explain` LangGraph node** (selected over extending synthesize or async post-processing).

Rationale:
- Clean separation of concerns — explain prompt is independent and versionable per sector in Langfuse
- ~200ms latency hidden behind streaming (user reading response while explain generates)
- Independently testable and disableable via `EXPLAIN_ENABLED` flag
- Prompt iteration via Langfuse without deploy

---

## 1. Phase Breadcrumb

### 1.1 Phases per flow type

| Flow | Phases |
|------|--------|
| **fast_path** | `understanding` → `responding` |
| **react_loop** | `understanding` → `searching` → `analyzing` → `responding` |
| **swarm** | `understanding` → `searching` → `analyzing (N tasks)` → `responding` |

### 1.2 Phase derivation from reasoning_steps

The breadcrumb is **frontend-only** — no new SSE event required. Phases are derived from `reasoning_steps` already flowing in LangGraph `values` events:

```typescript
const PHASE_MAP: Record<string, string> = {
  "routing": "understanding",
  "memory": "understanding",
  "tool_call": "searching",
  "tool_result": "searching",
  "validation": "analyzing",
  "synthesis": "responding",
}
```

### 1.3 Backend: `phase_update` event

Additionally, `langgraph_adapter.py` emits `phase_update` events for explicit phase transitions:

```python
PHASE_MAP = {
    "started": "understanding",
    "tool_call": "searching",
    "reasoning_step": "analyzing",
    "swarm_started": "analyzing",
    "token": "responding",
}
```

Only emitted when phase changes (deduplicated — no repeat events for same phase).

```json
{
  "type": "phase_update",
  "data": {
    "phase": "searching",
    "label": "Buscando información",
    "index": 1,
    "total": 4,
    "completed_phases": ["understanding"]
  }
}
```

### 1.4 Visual behavior

- Appears below user message as horizontal breadcrumb
- Active phase: icon + text + spinner animation (pulse)
- Completed phases: ✓ in muted gray
- Pending phases: light gray, no icon
- On `complete` event: fade-out 300ms, unmount
- Does NOT persist after response is rendered

### 1.5 i18n labels

| Phase ID | Spanish | English |
|----------|---------|---------|
| `understanding` | Entendiendo tu consulta | Understanding your query |
| `searching` | Buscando información | Searching for information |
| `analyzing` | Analizando resultados | Analyzing results |
| `responding` | Redactando respuesta | Writing response |

---

## 2. Explain Node

### 2.1 Position in graph

```
react_loop → synthesize → explain → END
decompose → swarm → synthesize_swarm → explain → END
fast_path (no explain) → END
```

Skipped when `fast_path_used=True` or `EXPLAIN_ENABLED=false`.

### 2.2 Input (from EmmaState)

| Field | Type | Purpose |
|-------|------|---------|
| `reasoning_steps` | `List[Dict]` | Raw steps accumulated during execution |
| `final_answer` | `str` | Response already generated |
| `sources` | `List[Dict]` | Documents and legislation used |
| `query` | `str` | Original or rewritten query |
| `intent` | `str` | Classified intent |
| `tools_used` | `List[str]` | Tools invoked |
| `active_sector` | `str` | legal, medical, or documental |

### 2.3 Output

```python
explanation: Optional[str]  # New field in EmmaState
```

### 2.4 Internal pipeline (2 steps)

**Step 1 — Deterministic fact extractor** (Python, 0ms):

Iterates `reasoning_steps` and `sources` to produce `facts: List[str]`:

```python
# Example mapping:
# tool_call:smart_search → "Busqué en {stores_searched} y encontré {results_count} resultados"
# tool_result:smart_search → "Consulté: {doc_title} (relevancia {score:.0%})"
# tool_call:search_jurisprudence → "Busqué jurisprudencia en CENDOJ"
# tool_call:web_search → "Busqué información en internet"
# source entry → "Fuente utilizada: {title}, páginas {pages}"
```

**Step 2 — LLM reformulation** (PLANNER model, ~200ms):

- Prompt loaded from Langfuse: `emma_explain_system` + `emma_explain_user`
- `sector_guidance` injected from `sectors/config.py`
- Temperature: 0.3, max tokens: 300
- The LLM **only reformulates** the provided facts — never sees the original query

### 2.5 Anti-hallucination (3 layers)

| Layer | Mechanism | How |
|-------|-----------|-----|
| **1. Restricted input** | Deterministic fact extractor | Only verified `facts[]` from `reasoning_steps` reach the LLM. Query is NOT passed. |
| **2. Post-LLM validation** | `_detect_fabricated_data()` from `quality_gate.py` | Compares explanation against ToolMessage corpus. Fabricated data → fallback template. |
| **3. Existing guardrails** | `guardrail_service.py` with `applies_to: ["explain"]` | Sector guardrails (medical, legal) validate the output. |

### 2.6 Fallback template

Used when: LLM fails, validation rejects, facts empty, or `EXPLAIN_ENABLED=false`.

```
"Consulté {n} fuentes ({source_names}) utilizando {tools_human_names}."
```

### 2.7 Sector guidance (in `sectors/config.py`)

| Sector | `explain_guidance` |
|--------|-------------------|
| `legal` | Usa terminología jurídica. Cita artículos y leyes por nombre completo. |
| `medical` | Usa terminología clínica. Referencia protocolos y normativa sanitaria. |
| `documental` | Usa lenguaje accesible. Describe los documentos consultados. |

### 2.8 Example outputs

**Legal sector** — Query: "¿Está vigente este contrato?"
> "Para responder tu consulta, revisé 3 contratos laborales de tu empresa y consulté el artículo 49 del Estatuto de los Trabajadores sobre extinción de contratos. Crucé las fechas de vencimiento con la legislación vigente para determinar cuáles están próximos a caducar."

**Medical sector** — Query: "¿El consentimiento informado cumple requisitos?"
> "Consulté el historial de protocolos clínicos archivados y la Guía de Práctica Clínica del SNS. Verifiqué que el consentimiento informado cumple los requisitos del artículo 8 de la Ley 41/2002 de autonomía del paciente."

**Documental sector** — Query: "¿Qué facturas hay de ACME?"
> "Busqué en tus documentos filtrando por la empresa ACME y encontré 5 facturas. Ordené los resultados por fecha para mostrarte las más recientes primero."

---

## 3. Frontend Components

### 3.1 `PhaseBreadcrumb.tsx` (NEW)

**Location**: `frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx`

Replaces: `WorkflowProgress.tsx` + `SLMThinkingDisplay.tsx`

```typescript
interface PhaseBreadcrumbProps {
  phases: Phase[]
  currentPhase: string | null  // null = completed, unmount
}

interface Phase {
  id: "understanding" | "searching" | "analyzing" | "responding"
  icon: string
  label: string       // i18n key
  status: "pending" | "active" | "completed"
}
```

### 3.2 `ExplanationPanel.tsx` (NEW)

**Location**: `frontend/packages/shared/src/emma/displays/Generic/ExplanationPanel.tsx`

Replaces: `ReasoningDisplay.tsx`

```typescript
interface ExplanationPanelProps {
  explanation: string | null   // null = don't render
  isLoading?: boolean          // shimmer while explain node runs
}
```

- Collapsible (shadcn/ui `Collapsible`), closed by default
- Header: "Así lo resolví" / "How I solved it" (i18n)
- Body: markdown prose (no code, no tables — natural language only)
- Not rendered when `explanation` is `null` (fast_path, error)

### 3.3 Integration in `DisplayRenderer.tsx`

```typescript
// During streaming (before complete):
{isStreaming && <PhaseBreadcrumb phases={phases} currentPhase={currentPhase} />}

// After response:
{message.type === "result" && message.metadata?.explanation && (
  <ExplanationPanel explanation={message.metadata.explanation} />
)}
```

### 3.4 Transport

`explanation` flows as part of `EmmaState` → `values` event snapshot → `useStream()` state → `EmmaMessage.metadata.explanation`. No new SSE event type needed for the explanation itself.

### 3.5 File changes summary

| File | Change | Type |
|------|--------|------|
| `PhaseBreadcrumb.tsx` | New breadcrumb component | New |
| `ExplanationPanel.tsx` | New collapsible explanation | New |
| `DisplayRenderer.tsx` | Route to new components | Modify |
| `types.ts` | Add `explanation?: string` to metadata | Modify |
| `WorkflowProgress.tsx` | Deprecate | Deprecate |
| `SLMThinkingDisplay.tsx` | Deprecate | Deprecate |
| `ReasoningDisplay.tsx` | Deprecate | Deprecate |
| i18n files | Phase labels + "Así lo resolví" | Modify |

---

## 4. Backend Changes Summary

| File | Change | Type |
|------|--------|------|
| `nodes/explain.py` | Explain node with fact extraction + LLM + validation | New |
| `graph.py` | Connect explain after synthesize/synthesize_swarm | Modify |
| `state.py` | Add `explanation: Optional[str]` | Modify |
| `langgraph_adapter.py` | Emit `phase_update` events | Modify |
| `sectors/config.py` | Add `explain_guidance` per sector | Modify |
| `prompt_registry.py` | 2 new entries (emma_explain_system, emma_explain_user) | Modify |
| `scripts/migrate_explain_prompts.py` | Langfuse migration script | New |
| `core/config.py` | Add `EXPLAIN_ENABLED: bool = True` | Modify |

---

## 5. Prompts (Langfuse)

Created via `scripts/migrate_explain_prompts.py` following the migration pattern.

### `emma_explain_system`

```
Eres un asistente que explica su proceso de investigación.
Reformula los siguientes hechos en 2-4 frases naturales.
Sector del usuario: {sector}
Adaptación: {sector_guidance}
NO inventes pasos, fuentes ni datos que no estén en la lista de hechos.
Si un hecho menciona un documento, cítalo por nombre.
```

### `emma_explain_user`

```
Hechos verificados:
{facts_formatted}

Herramientas utilizadas: {tools_human_names}
Fuentes consultadas: {source_names}
```

---

## 6. Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `EXPLAIN_ENABLED` | `true` | Master switch for explain node |

No additional flags. Breadcrumb is frontend-only. Explanation is naturally skipped on fast_path.

---

## 7. Testing

### Unit tests

| File | Tests |
|------|-------|
| `test_explain_node.py` | generates explanation, skips fast_path, skips when disabled, empty facts fallback, fabricated data fallback, respects sector guidance, LLM failure fallback |
| `test_phase_mapping.py` | tool_call → searching, dedup no repeat, complete flow 4 phases, fast_path only 2 phases |

### Integration tests

| Test | Validates |
|------|-----------|
| `test_stream_includes_explanation` | Real query → SSE stream includes `explanation` in final state |
| `test_stream_includes_phase_updates` | Real query → `phase_update` events received during execution |
| `test_explanation_no_hallucination` | Explanation only mentions documents present in `sources` |

### Frontend manual checklist

1. Breadcrumb appears on query, shows phases progressively
2. Breadcrumb fades out on completion
3. Fast-path (greeting) → no breadcrumb, no ExplanationPanel
4. Normal query → ExplanationPanel appears collapsed below response
5. Open ExplanationPanel → humanized readable text
6. Swarm query → breadcrumb shows "Analizando (N tareas)"
7. LLM error → fallback template in ExplanationPanel
8. i18n → switch language → labels translate

---

## 8. Rollout

### Phase 1 — Backend (no frontend impact)
1. Create `explain_node.py` with unit tests
2. Register prompts in `prompt_registry.py`
3. Run `migrate_explain_prompts.py` in Langfuse
4. Connect node in `graph.py`
5. Add `phase_update` to adapter
6. Validate with integration tests

### Phase 2 — Frontend
1. Create `PhaseBreadcrumb.tsx`
2. Create `ExplanationPanel.tsx`
3. Integrate in `DisplayRenderer.tsx`
4. Manual testing with checklist
5. Deprecate old components

### Phase 3 — Cleanup
1. Remove deprecated components (`WorkflowProgress`, `SLMThinkingDisplay`, `ReasoningDisplay`)
2. Remove legacy event types from `types.ts`

---

## 9. Risks

| Risk | Probability | Mitigation |
|------|-------------|------------|
| LLM hallucinates in explanation | Low (restricted input) | 3-layer anti-hallucination + fallback template |
| +200ms perceived latency | Low (user reading response) | Explain runs after last streaming token |
| Explain prompt needs tuning | Medium | Langfuse allows iteration without deploy |
| Legacy component breakage during deprecation | Low | Phase 3 separate, only after Phase 2 validated |
