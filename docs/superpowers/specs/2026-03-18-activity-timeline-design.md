# ActivityTimeline — Humanized Activity Indicator for Emma

## Problem

The current PhaseBreadcrumb maps backend SSE events to 4 fixed phases (understanding → searching → analyzing → responding) via a monotonic state machine. This approach has several issues:

1. **Phase gets stuck** — The ReAct loop emits events in non-linear order (tool_call → thinking → tool_call), and the monotonic constraint prevents backward transitions, but the phase mapping doesn't match the actual event flow, leaving the breadcrumb frozen on "Analizando".
2. **Too abstract** — Users see generic labels ("Buscando información") instead of what Emma actually found or read.
3. **Fixed 4 phases** — Cannot represent variable-length workflows (a query with 1 tool call vs 5 tool calls shows the same breadcrumb).
4. **Previous ReasoningCollapsible was too technical** — Showed raw tool names, confidence scores, and entity arrays that confused non-technical users.

## Solution

Replace PhaseBreadcrumb with **ActivityTimeline**: a vertical, accumulative timeline that shows human-readable steps derived directly from SSE events. Each step is one line of natural text describing what Emma did.

## Architecture

### Data Flow

```
Backend (langgraph_adapter.py)          Frontend
─────────────────────────────           ────────────────────────
SSE events:                             useMessageConverter
  started           ──────────────►       derives activity_steps[]
  tool_call         ──────────────►       from reasoning_steps
  tool_result       ──────────────►
  token             ──────────────►     ActivityTimeline component
  complete          ──────────────►       renders steps with status
```

### No backend changes required

The `reasoning_steps` array already contains all the data needed:
- `{type: "tool_call", content: "smart_search(query=contratos, stores=documents)"}`
- `{type: "tool_result", content: "Found 5 results...", source: "smart_search"}`
- `{type: "thinking", content: "..."}`

The humanization happens entirely in the frontend by parsing these existing fields. The `current_phase` field and `PHASE_MAP` in `langgraph_adapter.py` can be removed.

### Frontend Components

#### 1. `ActivityTimeline.tsx` (new component)

Location: `frontend/apps/on-premise/src/components/emma-chat/ActivityTimeline.tsx`

**Props:**
```typescript
interface ActivityStep {
  id: string
  text: string           // Humanized text: "Encontré 5 documentos relevantes"
  status: 'completed' | 'active'
  icon: 'understand' | 'search' | 'read' | 'analyze' | 'web' | 'legal' | 'write' | 'done'
}

interface ActivityTimelineProps {
  steps: ActivityStep[]
  isStreaming: boolean
  className?: string
}
```

**Visual structure (during streaming):**
```
  ✓  Entendiendo tu consulta
  ✓  Encontré 5 documentos relevantes
  ✓  Leí Contrato_ABC.pdf
  ●  Redactando respuesta...
```

- Vertical layout, one line per step
- Completed steps: green checkmark icon + muted text
- Active step: blue pulsing dot + bold text
- Compact: ~20px per step, no borders or backgrounds
- Animates in: new steps fade in from below

**Visual structure (after completion — collapsed):**
```
  ▸ 4 pasos · 2.3s
```

Clicking expands to show the full timeline. Uses the same collapsible pattern as ExplanationPanel.

**Fast-path queries:** No ActivityTimeline is rendered (no significant steps to show).

#### 2. `humanizeStep()` (pure function)

Location: `frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.ts`

Converts raw `reasoning_steps` from the backend into `ActivityStep[]`.

**Mapping rules:**

| reasoning_step.type | reasoning_step.content/source | Output text | Icon |
|---|---|---|---|
| (first event) | — | "Entendiendo tu consulta" | understand |
| `tool_call` | starts with `smart_search(` | "Buscando información..." | search |
| `tool_result` | source=`smart_search`, extract N from "Found N results" | "Encontré N documentos relevantes" | search |
| `tool_call` | starts with `get_document_content(` | "Leyendo documento..." | read |
| `tool_result` | source=`get_document_content`, extract title | "Leí [título]" | read |
| `tool_call` | starts with `structural_query(` | "Consultando el grafo de conocimiento..." | analyze |
| `tool_result` | source=`structural_query`, extract count | "El grafo reportó N documentos" | analyze |
| `tool_call` | starts with `web_search(` | "Buscando en internet..." | web |
| `tool_call` | starts with `search_jurisprudence(` | "Buscando jurisprudencia..." | legal |
| `tool_call` | starts with `analyze_domain(` | "Realizando análisis especializado..." | analyze |
| `tool_call` | starts with `verified_generation(` | "Ejecutando generación verificada..." | analyze |
| `tool_call` | starts with `predictive_analysis(` | "Ejecutando análisis predictivo..." | analyze |
| `thinking` | — | Ignored (internal LLM reasoning, not user-facing) |
| `routing` | — | Ignored |

**Deduplication:** If a `tool_call` is followed by its `tool_result`, the `tool_call` step ("Buscando información...") is **replaced** by the `tool_result` step ("Encontré 5 documentos") — not appended. This keeps the timeline compact.

**"Redactando respuesta..."** is added when `isStreaming && accumulatedText.length > 0` (tokens are arriving) but is NOT derived from reasoning_steps — it's injected by the component based on streaming state.

#### 3. Integration in `ProgressBubble` and `MessageBubble`

**During streaming (ProgressBubble):**
- Replace current `PhaseProgressIndicator` with `<ActivityTimeline steps={steps} isStreaming={true} />`
- Steps derived from `values.reasoning_steps` via `humanizeStep()`

**After completion (MessageBubble, result type):**
- Replace `CompletedPhaseBreadcrumb` with collapsed `<ActivityTimeline steps={steps} isStreaming={false} />`
- Shows `"N pasos · Xs"` summary, expandable to full timeline
- Only rendered when `metadata.explanation` exists (explain node ran)

### What gets removed

1. **`PhaseBreadcrumb.tsx`** — Replaced by ActivityTimeline
2. **`PhaseProgressIndicator` / `CompletedPhaseBreadcrumb`** in EmmaRenderChat — Replaced by ActivityTimeline
3. **`PHASE_MAP` / `PHASE_ORDER` / `PHASE_LABELS`** in langgraph_adapter.py — No longer needed
4. **`_current_phase` / `_max_phase_idx`** tracking in adapter — No longer needed
5. **`current_phase` field** in all `values` SSE snapshots — No longer emitted
6. **`current_phase`** in `EmmaStateType`, `useMessageConverter`, `EmmaMessage.metadata` — Removed
7. **`@nexus/shared/emma/displays` export** — PhaseBreadcrumb removed from barrel

### Icons

Using `@tabler/icons-react` (already in the project):

| Icon key | Component | Used for |
|---|---|---|
| understand | `IconBrain` | Initial understanding |
| search | `IconSearch` | smart_search |
| read | `IconFileText` | get_document_content |
| analyze | `IconChartBar` | structural_query, analyze_domain |
| web | `IconWorld` | web_search |
| legal | `IconScale` | search_jurisprudence |
| write | `IconPencil` | Redactando respuesta |
| done | `IconCircleCheck` | Respuesta lista |

### Error handling

- If `humanizeStep()` encounters an unknown tool name, it produces a generic step: "Procesando..." with analyze icon
- If reasoning_steps is empty and streaming ends, no ActivityTimeline is shown (fast-path)
- The timeline is purely presentational — errors in rendering never affect the actual response

## Testing

1. **Unit tests for `humanizeStep()`**: Input reasoning_steps arrays → expected ActivityStep arrays. Cover all tool types + deduplication logic.
2. **Visual verification**: Send queries that trigger different tool combinations and verify the timeline shows correct humanized text.
3. **Fast-path**: Verify no timeline appears for greetings.
4. **Swarm queries**: Verify swarm events (worker_started, worker_complete) produce reasonable steps like "Analizando sub-tarea 1/3..."
