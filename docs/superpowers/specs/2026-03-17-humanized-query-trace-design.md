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

### 1.2 Backend: `phase_update` event

The breadcrumb is driven by `phase_update` events emitted by `langgraph_adapter.py`. Deriving phases purely from `reasoning_steps` types on the frontend is fragile because `ReasoningTracker.StepType` does not cleanly map to the four user-facing phases. Instead, the backend adapter emits explicit phase transitions:

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

Skipped when `fast_path_used=True` or `EXPLAIN_ENABLED=false`. The skip is handled via **early return inside the node** (not a conditional edge), consistent with how other nodes handle feature flags in this codebase (e.g., memory_recall checks `USER_MEMORY_ENABLED`).

### 2.2 Input (from ReActState)

| Field | Type | Purpose |
|-------|------|---------|
| `reasoning_steps` | `List[Dict]` | Raw steps accumulated during execution |
| `final_answer` | `str` | Response already generated |
| `sources` | `List[Dict]` | Documents and legislation used |
| `query` | `str` | Original or rewritten query |
| `tool_calls_history` | `List[Dict[str, Any]]` | Tool invocations with name, args, timestamps. Extract unique tool names via `{entry["name"] for entry in tool_calls_history}`. |
| `sector` | `Optional[str]` | legal, medical, or documental (from `ReActState.sector`) |
| `messages` | `List[BaseMessage]` | Full message sequence (accessed for anti-hallucination validation only — NOT passed to LLM prompt) |
| `metadata` | `Dict[str, Any]` | Contains `intent` from classify node (access via `metadata.get("intent")`) |

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
| **2. Post-LLM validation** | `_detect_fabricated_data()` from `quality_gate.py` | Compares explanation against ToolMessage corpus extracted from `state["messages"]`. Fabricated data → fallback template. Note: `messages` are accessed here for validation but are NOT passed to the LLM prompt. |
| **3. Existing guardrails** | `guardrail_service.py` with agent_name `"explain"` | Sector guardrails (medical, legal) validate the output. Requires adding `"explain"` to `applies_to` arrays of relevant existing guardrails in `guardrail_registry.py`, or creating new explain-specific guardrails via the migration script. |

### 2.6 Fallback template

Used when: LLM fails, validation rejects, facts empty, or `EXPLAIN_ENABLED=false`.

```
"Consulté {n} fuentes ({source_names}) utilizando {tools_human_names}."
```

Where `tools_human_names` is derived from `tool_calls_history`:
```python
TOOL_HUMAN_NAMES = {
    "smart_search": "búsqueda inteligente",
    "get_document_content": "lectura de documento",
    "structural_query": "consulta estructural",
    "search_jurisprudence": "búsqueda de jurisprudencia",
    "web_search": "búsqueda web",
    "analyze_domain": "análisis de dominio",
    # ...
}
tools_human_names = ", ".join(TOOL_HUMAN_NAMES.get(t, t) for t in unique_tool_names)
```

### 2.7 Sector guidance (in `sectors/config.py`)

New `explain_guidance: str` field on `SectorConfig` (which is `@dataclass(frozen=True)` — adding a field with a default is safe). Each sector registry instantiation (`LEGAL_SECTOR`, `MEDICAL_SECTOR`, `DOCUMENTAL_SECTOR`) must be updated with the new field value:

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

The `explanation` field requires **explicit wiring** through the streaming pipeline (the adapter is explicit, not passthrough):

1. **`api.py`** (`stream_react_query()`): Include `explanation` in the `complete` event data, alongside `answer`, `sources`, and `metadata`. Read from the graph's final state.
2. **`langgraph_adapter.py`** (`translate_to_langgraph_sse()`): Forward `explanation` in the final `values` snapshot within the `complete` handler, same as `sources` and `metadata`.
3. **Frontend**: Read `explanation` from the `values` event state in `useStream()` → map to `EmmaMessage.metadata.explanation`.

No new SSE event type needed — `explanation` rides the existing `complete` → `values` pipeline, but both `api.py` and `langgraph_adapter.py` must be updated to include the new field.

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
| `graph.py` | Connect explain after synthesize/synthesize_swarm (simple edges, skip via early return) | Modify |
| `state.py` | Add `explanation: Optional[str]` | Modify |
| `api.py` | Include `explanation` in `complete` event data from graph final state | Modify |
| `langgraph_adapter.py` | Emit `phase_update` events + forward `explanation` in final `values` snapshot | Modify |
| `sectors/config.py` | Add `explain_guidance` field to `SectorConfig` + update LEGAL/MEDICAL/DOCUMENTAL instances | Modify |
| `prompt_registry.py` | 2 new entries (emma_explain_system, emma_explain_user) | Modify |
| `guardrail_registry.py` | Add `"explain"` to `applies_to` of relevant sector guardrails | Modify |
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
4. Add `explain_guidance` to `SectorConfig` and sector instances
5. Add `"explain"` to relevant guardrails in `guardrail_registry.py`
6. Connect node in `graph.py`
7. Wire `explanation` through `api.py` + `langgraph_adapter.py`
8. Add `phase_update` to adapter
9. Validate with integration tests

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
