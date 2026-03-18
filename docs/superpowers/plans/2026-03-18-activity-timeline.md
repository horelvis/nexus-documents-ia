# ActivityTimeline — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broken PhaseBreadcrumb with a humanized vertical activity timeline that shows what Emma is doing in plain language, derived from existing reasoning_steps.

**Architecture:** A pure frontend change. New `humanizeStep()` function converts raw reasoning_steps into user-friendly ActivityStep objects. New `ActivityTimeline` component renders them as a compact vertical list. Backend phase tracking machinery (PHASE_MAP, current_phase) is removed — no longer needed.

**Tech Stack:** TypeScript, React, @tabler/icons-react, Tailwind CSS.

**Spec:** `docs/superpowers/specs/2026-03-18-activity-timeline-design.md`

---

## File Structure

### Frontend (New files)
- `frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.ts` — Pure function: reasoning_steps → ActivityStep[]
- `frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.test.ts` — Unit tests for humanization logic
- `frontend/apps/on-premise/src/components/emma-chat/ActivityTimeline.tsx` — Vertical timeline component

### Frontend (Modified files)
- `frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx` — Replace PhaseBreadcrumb with ActivityTimeline
- `frontend/apps/on-premise/src/components/emma-chat/hooks/useMessageConverter.ts` — Remove currentPhase, pass reasoning_steps to metadata
- `frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx` — Remove current_phase from EmmaStateType
- `frontend/apps/on-premise/src/lib/types/emma.ts` — Replace currentPhase with activitySteps in metadata

### Frontend (Files to clean up)
- `frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx` — Delete
- `frontend/packages/shared/src/emma/displays/index.ts` — Remove PhaseBreadcrumb export
- `frontend/packages/shared/src/emma/index.ts` — Remove PhaseBreadcrumb export
- `frontend/packages/shared/package.json` — Remove `./emma/displays` export (if no other consumers)

### Backend (Modified files)
- `backend/microservices/emma-agent-service/app/services/langgraph_adapter.py` — Remove PHASE_MAP, PHASE_ORDER, PHASE_LABELS, _current_phase, _max_phase_idx, phase detection block, current_phase from all values snapshots

---

## Task 1: humanizeStep() — Pure function with tests

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.ts`
- Create: `frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.test.ts`

- [ ] **Step 1: Define types and write failing tests**

Create `utils/humanizeStep.test.ts`:

```typescript
import { humanizeSteps, type ActivityStep, type RawReasoningStep } from './humanizeStep'

describe('humanizeSteps', () => {
  it('returns empty array for empty input', () => {
    expect(humanizeSteps([])).toEqual([])
  })

  it('converts smart_search tool_call + tool_result into single step', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=contratos, stores=documents)' },
      { type: 'tool_result', content: 'Found 5 results for query', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toContain('5')
    expect(result[0].icon).toBe('search')
    expect(result[0].status).toBe('completed')
  })

  it('converts get_document_content into read step with title', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'get_document_content(document_id=abc123)' },
      { type: 'tool_result', content: 'Content of document: Contrato_ABC.pdf\n...', source: 'get_document_content' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toMatch(/Contrato_ABC/)
    expect(result[0].icon).toBe('read')
  })

  it('converts structural_query into analyze step', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'structural_query(query=total de documentos, max_results=1)' },
      { type: 'tool_result', content: '**Total de documentos**: 15\n**Desglose...', source: 'structural_query' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toContain('15')
    expect(result[0].icon).toBe('analyze')
  })

  it('converts web_search into web step', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'web_search(query=weather Madrid)' },
      { type: 'tool_result', content: 'Search results: ...', source: 'web_search' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].icon).toBe('web')
  })

  it('converts search_jurisprudence into legal step', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'search_jurisprudence(query=despido improcedente)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].icon).toBe('legal')
  })

  it('ignores thinking steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'thinking', content: 'I should search for contracts...' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(0)
  })

  it('ignores routing steps', () => {
    const steps: RawReasoningStep[] = [
      { type: 'routing', content: 'Intent: document_query (confidence: 0.85)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(0)
  })

  it('deduplicates tool_call when tool_result follows', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
      { type: 'tool_result', content: 'Found 3 results', source: 'smart_search' },
    ]
    const result = humanizeSteps(steps)
    // Should be 1 step, not 2 (tool_call replaced by tool_result)
    expect(result).toHaveLength(1)
    expect(result[0].text).not.toContain('Buscando')
    expect(result[0].text).toContain('3')
  })

  it('keeps tool_call if no tool_result follows', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=facturas)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toContain('Buscando')
    expect(result[0].status).toBe('active')
  })

  it('handles unknown tool gracefully', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'unknown_tool(arg=value)' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(1)
    expect(result[0].text).toBe('Procesando...')
    expect(result[0].icon).toBe('analyze')
  })

  it('handles multiple tool calls in sequence', () => {
    const steps: RawReasoningStep[] = [
      { type: 'tool_call', content: 'smart_search(query=contratos)' },
      { type: 'tool_result', content: 'Found 5 results', source: 'smart_search' },
      { type: 'tool_call', content: 'get_document_content(document_id=abc)' },
      { type: 'tool_result', content: 'Content of document: Nomina_2024.pdf\n...', source: 'get_document_content' },
    ]
    const result = humanizeSteps(steps)
    expect(result).toHaveLength(2)
    expect(result[0].icon).toBe('search')
    expect(result[1].icon).toBe('read')
    expect(result[0].status).toBe('completed')
    expect(result[1].status).toBe('completed')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run apps/on-premise/src/components/emma-chat/utils/humanizeStep.test.ts`

Expected: FAIL — module not found

- [ ] **Step 3: Implement humanizeStep()**

Create `utils/humanizeStep.ts`:

```typescript
export type ActivityIcon = 'search' | 'read' | 'analyze' | 'web' | 'legal' | 'write' | 'done'

export interface ActivityStep {
  id: string
  text: string
  status: 'completed' | 'active'
  icon: ActivityIcon
}

export interface RawReasoningStep {
  type: string
  content: string
  source?: string
}

/** Regex to extract tool name from content like "smart_search(query=contratos)" */
const TOOL_NAME_RE = /^(\w+)\(/

/** Extract a number from "Found N results" or "N resultado" patterns */
function extractResultCount(content: string): number | null {
  const match = content.match(/(?:Found\s+)?(\d+)\s+result/i)
    || content.match(/(\d+)\s+resultado/i)
  return match ? parseInt(match[1], 10) : null
}

/** Extract document title from tool_result content */
function extractDocTitle(content: string): string | null {
  // Pattern: "Content of document: Titulo.pdf\n..."
  const match = content.match(/(?:Content of document|Documento):\s*(.+?)[\n|$]/i)
  if (match) return match[1].trim()
  // Fallback: extract filename pattern
  const fileMatch = content.match(/([A-Za-zÀ-ÿ0-9_\-]+\.\w{2,5})/)
  return fileMatch ? fileMatch[1] : null
}

/** Extract total from structural_query: "**Total de documentos**: 15" */
function extractStructuralCount(content: string): number | null {
  const match = content.match(/Total de documentos\*?\*?:\s*(\d+)/)
  return match ? parseInt(match[1], 10) : null
}

function getToolName(content: string): string {
  const m = TOOL_NAME_RE.exec(content)
  return m ? m[1] : ''
}

interface ToolCallTexts {
  active: string
  icon: ActivityIcon
}

const TOOL_CALL_MAP: Record<string, ToolCallTexts> = {
  smart_search:         { active: 'Buscando información...',               icon: 'search' },
  get_document_content: { active: 'Leyendo documento...',                  icon: 'read' },
  structural_query:     { active: 'Consultando el grafo de conocimiento...', icon: 'analyze' },
  web_search:           { active: 'Buscando en internet...',               icon: 'web' },
  search_jurisprudence: { active: 'Buscando jurisprudencia...',            icon: 'legal' },
  analyze_domain:       { active: 'Realizando análisis especializado...',  icon: 'analyze' },
  verified_generation:  { active: 'Ejecutando generación verificada...',   icon: 'analyze' },
  predictive_analysis:  { active: 'Ejecutando análisis predictivo...',     icon: 'analyze' },
  list_sources:         { active: 'Explorando fuentes disponibles...',     icon: 'search' },
  query_connector:      { active: 'Consultando conector externo...',       icon: 'search' },
  generate_document:    { active: 'Generando documento...',                icon: 'write' },
  forge_document:       { active: 'Creando documento PDF...',              icon: 'write' },
  send_email:           { active: 'Enviando email...',                     icon: 'write' },
}

function buildResultText(toolName: string, content: string): string | null {
  switch (toolName) {
    case 'smart_search': {
      const n = extractResultCount(content)
      return n !== null ? `Encontré ${n} documentos relevantes` : 'Búsqueda completada'
    }
    case 'get_document_content': {
      const title = extractDocTitle(content)
      return title ? `Leí ${title}` : 'Documento leído'
    }
    case 'structural_query': {
      const n = extractStructuralCount(content)
      return n !== null ? `El grafo reportó ${n} documentos` : 'Consulta estructural completada'
    }
    case 'web_search':
      return 'Resultados de internet obtenidos'
    case 'search_jurisprudence':
      return 'Jurisprudencia encontrada'
    default:
      return null
  }
}

const IGNORED_TYPES = new Set(['thinking', 'routing'])

/**
 * Convert raw reasoning_steps from the LangGraph adapter into
 * human-readable ActivityStep[] for the ActivityTimeline component.
 *
 * Key behaviors:
 * - thinking/routing steps are ignored (internal LLM reasoning)
 * - tool_call followed by its tool_result are merged into one step
 * - A standalone tool_call (no result yet) shows as "active"
 * - All completed tool_result steps show as "completed"
 */
export function humanizeSteps(raw: RawReasoningStep[]): ActivityStep[] {
  const steps: ActivityStep[] = []
  let stepCounter = 0

  for (let i = 0; i < raw.length; i++) {
    const step = raw[i]

    if (IGNORED_TYPES.has(step.type)) continue

    if (step.type === 'tool_call') {
      const toolName = getToolName(step.content)
      const mapping = TOOL_CALL_MAP[toolName]

      // Look ahead for matching tool_result
      const nextResult = raw.slice(i + 1).find(
        s => s.type === 'tool_result' && s.source === toolName
      )

      if (nextResult) {
        // Merge: skip the tool_call, use the tool_result text
        const resultText = buildResultText(toolName, nextResult.content)
        steps.push({
          id: `step-${stepCounter++}`,
          text: resultText || mapping?.active || 'Procesando...',
          status: 'completed',
          icon: mapping?.icon || 'analyze',
        })
        // Skip the tool_result when we encounter it later
        const resultIdx = raw.indexOf(nextResult)
        if (resultIdx > i) {
          // Mark it so we skip it (we use a set for this)
        }
      } else {
        // No result yet — show as active
        steps.push({
          id: `step-${stepCounter++}`,
          text: mapping?.active || 'Procesando...',
          status: 'active',
          icon: mapping?.icon || 'analyze',
        })
      }
    } else if (step.type === 'tool_result') {
      // Check if this was already consumed by a preceding tool_call merge
      const toolName = step.source || ''
      const precedingCall = raw.slice(0, i).reverse().find(
        s => s.type === 'tool_call' && getToolName(s.content) === toolName
      )
      if (precedingCall) {
        // Already merged — skip
        continue
      }
      // Orphan tool_result (no preceding tool_call) — render it
      const mapping = TOOL_CALL_MAP[toolName]
      const resultText = buildResultText(toolName, step.content)
      steps.push({
        id: `step-${stepCounter++}`,
        text: resultText || 'Paso completado',
        status: 'completed',
        icon: mapping?.icon || 'analyze',
      })
    }
  }

  return steps
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npx vitest run apps/on-premise/src/components/emma-chat/utils/humanizeStep.test.ts`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.ts \
       frontend/apps/on-premise/src/components/emma-chat/utils/humanizeStep.test.ts
git commit -m "feat(explain): add humanizeStep() — converts reasoning_steps to user-friendly ActivitySteps"
```

---

## Task 2: ActivityTimeline component

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/ActivityTimeline.tsx`

- [ ] **Step 1: Create ActivityTimeline component**

```typescript
'use client'

import { useState } from 'react'
import {
  IconCircleCheck,
  IconSearch,
  IconFileText,
  IconChartBar,
  IconWorld,
  IconScale,
  IconPencil,
  IconChevronRight,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { ActivityStep, ActivityIcon } from './utils/humanizeStep'

const ICON_MAP: Record<ActivityIcon, React.ElementType> = {
  search: IconSearch,
  read: IconFileText,
  analyze: IconChartBar,
  web: IconWorld,
  legal: IconScale,
  write: IconPencil,
  done: IconCircleCheck,
}

interface ActivityTimelineProps {
  steps: ActivityStep[]
  isStreaming: boolean
  executionTimeMs?: number
  className?: string
}

export function ActivityTimeline({ steps, isStreaming, executionTimeMs, className }: ActivityTimelineProps) {
  const [isExpanded, setIsExpanded] = useState(true)

  if (steps.length === 0) return null

  // After completion: show collapsed summary
  if (!isStreaming && !isExpanded) {
    const timeStr = executionTimeMs
      ? executionTimeMs < 1000
        ? `${Math.round(executionTimeMs)}ms`
        : `${(executionTimeMs / 1000).toFixed(1)}s`
      : null

    return (
      <button
        onClick={() => setIsExpanded(true)}
        className={cn(
          "flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors",
          className,
        )}
      >
        <IconChevronRight className="h-3 w-3" />
        <span>{steps.length} pasos{timeStr ? ` · ${timeStr}` : ''}</span>
      </button>
    )
  }

  // Collapse handler — only available after streaming ends
  const handleCollapse = !isStreaming ? () => setIsExpanded(false) : undefined

  return (
    <div className={cn("space-y-0.5", className)}>
      {handleCollapse && (
        <button
          onClick={handleCollapse}
          className="flex items-center gap-1 text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors mb-1"
        >
          <IconChevronRight className="h-3 w-3 rotate-90" />
          <span>colapsar</span>
        </button>
      )}
      {steps.map((step) => {
        const Icon = ICON_MAP[step.icon] || IconChartBar
        return (
          <div
            key={step.id}
            className={cn(
              "flex items-center gap-2 text-xs py-0.5 animate-in fade-in-50 duration-300",
              step.status === 'completed' && "text-muted-foreground/60",
              step.status === 'active' && "text-foreground font-medium",
            )}
          >
            {step.status === 'completed' ? (
              <IconCircleCheck className="h-3.5 w-3.5 text-emerald-500/60 flex-shrink-0" />
            ) : (
              <span className="relative flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center">
                <Icon className="h-3 w-3 text-primary" />
                <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
              </span>
            )}
            <span>{step.text}</span>
          </div>
        )
      })}
      {isStreaming && steps.every(s => s.status === 'completed') && (
        <div className="flex items-center gap-2 text-xs py-0.5 text-foreground font-medium animate-in fade-in-50 duration-300">
          <span className="relative flex h-3.5 w-3.5 flex-shrink-0 items-center justify-center">
            <IconPencil className="h-3 w-3 text-primary" />
            <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
          </span>
          <span>Redactando respuesta...</span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/ActivityTimeline.tsx
git commit -m "feat(explain): add ActivityTimeline component — vertical humanized step indicator"
```

---

## Task 3: Wire ActivityTimeline into EmmaRenderChat

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx`
- Modify: `frontend/apps/on-premise/src/components/emma-chat/hooks/useMessageConverter.ts`

- [ ] **Step 1: Update useMessageConverter to pass reasoning_steps as raw array**

In `hooks/useMessageConverter.ts`:

Replace the `currentPhase` extraction (line 72) and metadata attachment (line 116):

```typescript
// Remove this line:
const currentPhase = values?.current_phase

// Replace the stepsMetadata block (lines 113-120) with:
if (reasoningSteps.length > 0 || sources.length > 0 || explanation) {
  const stepsMetadata: EmmaMessage['metadata'] = {
    slmIsThinking: !success && reasoningSteps.length > 0,
    rawReasoningSteps: reasoningSteps,
  }

  if (explanation) {
    stepsMetadata!.explanation = explanation
  }
```

Update the memoization dependency array (line 209) — remove `currentPhase`:

```typescript
}, [sdkMessages, reasoningLen, sourcesLen, success, explanation, interrupt])
```

- [ ] **Step 2: Update EmmaMessage metadata type**

In `frontend/apps/on-premise/src/lib/types/emma.ts`, replace `currentPhase` (line 384) with:

```typescript
    // Raw reasoning steps for ActivityTimeline
    rawReasoningSteps?: Array<{ type: string; content: string; source?: string }>
```

- [ ] **Step 3: Replace PhaseBreadcrumb with ActivityTimeline in EmmaRenderChat**

In `EmmaRenderChat.tsx`:

Remove imports (line 10):
```typescript
// DELETE: import { PhaseBreadcrumb, type Phase, type PhaseId } from '@nexus/shared/emma/displays'
```

Add imports:
```typescript
import { ActivityTimeline } from './ActivityTimeline'
import { humanizeSteps } from './utils/humanizeStep'
```

Replace ProgressBubble phase indicator (lines 611-614):
```typescript
// Replace:
//   {slmIsThinking && (
//     <PhaseProgressIndicator currentPhase={message.metadata?.currentPhase ?? null} />
//   )}
// With:
{(message.metadata?.rawReasoningSteps?.length ?? 0) > 0 && (
  <ActivityTimeline
    steps={humanizeSteps(message.metadata!.rawReasoningSteps!)}
    isStreaming={true}
  />
)}
```

Replace CompletedPhaseBreadcrumb in MessageBubble (lines 438-440):
```typescript
// Replace:
//   {message.metadata?.explanation && (
//     <CompletedPhaseBreadcrumb />
//   )}
// With:
{message.metadata?.explanation && (message.metadata?.rawReasoningSteps?.length ?? 0) > 0 && (
  <ActivityTimeline
    steps={humanizeSteps(message.metadata!.rawReasoningSteps!)}
    isStreaming={false}
    executionTimeMs={message.metadata?.execution_time_ms}
  />
)}
```

Delete the `PHASE_DEFINITIONS`, `PhaseProgressIndicator`, and `CompletedPhaseBreadcrumb` functions (lines 771-805).

- [ ] **Step 4: Verify the app compiles**

Run: `cd frontend && npx tsc --noEmit --project apps/on-premise/tsconfig.json 2>&1 | grep -E "ActivityTimeline|humanizeStep|EmmaRenderChat|useMessageConverter"`

Expected: No errors in our modified files

- [ ] **Step 5: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx \
       frontend/apps/on-premise/src/components/emma-chat/hooks/useMessageConverter.ts \
       frontend/apps/on-premise/src/lib/types/emma.ts
git commit -m "feat(explain): replace PhaseBreadcrumb with ActivityTimeline in chat UI"
```

---

## Task 4: Backend cleanup — Remove phase tracking machinery

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/services/langgraph_adapter.py`

- [ ] **Step 1: Remove phase constants and tracking**

In `langgraph_adapter.py`:

Delete lines 27-50 (PHASE_MAP, PHASE_LABELS, PHASE_ORDER constants).

Delete lines 127-129 (_current_phase and _max_phase_idx variables).

Delete lines 139-155 (phase detection block).

- [ ] **Step 2: Remove `current_phase` from all values snapshots**

Remove `"current_phase": _current_phase,` from every `_sse_line("values", {...})` call:
- Line 166 (started event)
- Line 182 (thinking event)
- Line 197 (tool_call event)
- Line 221 (tool_result event)
- Line 240 (reasoning_step event)
- Line 303 (interrupt event)
- Line 338 (complete event)

Also remove the comment `# Phase detection already set _current_phase = "responding" above` from the complete handler.

- [ ] **Step 3: Remove phase_update SSE emission**

The `yield _sse_line("updates", {"phase_update": {...}})` block was already removed with the phase detection block in Step 1.

- [ ] **Step 4: Restart emma-agent-service and test**

Run: `cd backend/docker && docker compose restart emma-agent-service`

Expected: Service starts healthy, no errors in logs

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/services/langgraph_adapter.py
git commit -m "refactor(explain): remove phase tracking from langgraph adapter — ActivityTimeline uses reasoning_steps directly"
```

---

## Task 5: Frontend cleanup — Remove PhaseBreadcrumb

**Files:**
- Modify: `frontend/packages/shared/src/emma/displays/index.ts`
- Modify: `frontend/packages/shared/src/emma/index.ts`
- Modify: `frontend/packages/shared/src/emma/types.ts`
- Modify: `frontend/packages/shared/package.json`
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx`
- Delete: `frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx`

- [ ] **Step 1: Remove PhaseBreadcrumb exports**

In `frontend/packages/shared/src/emma/displays/index.ts`, remove line 2:
```typescript
// DELETE: export { PhaseBreadcrumb, type Phase, type PhaseId, type PhaseStatus } from "./Generic/PhaseBreadcrumb"
```

In `frontend/packages/shared/src/emma/index.ts`, remove line 12:
```typescript
// DELETE: export { PhaseBreadcrumb, type Phase, type PhaseId, type PhaseStatus } from "./displays/Generic/PhaseBreadcrumb"
```

- [ ] **Step 2: Remove `currentPhase` from shared types**

In `frontend/packages/shared/src/emma/types.ts`, remove the `currentPhase` field from the metadata interface.

- [ ] **Step 3: Remove `current_phase` from EmmaStateType**

In `frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx`, remove line 29:
```typescript
// DELETE: current_phase?: string | null
```

- [ ] **Step 4: Remove `./emma/displays` export from package.json if unused**

In `frontend/packages/shared/package.json`, check if any other file imports from `@nexus/shared/emma/displays`. If not, remove:
```json
"./emma/displays": "./src/emma/displays/index.ts",
```

Note: Keep the `displays/index.ts` file itself — it still exports `ExplanationPanel` and `DisplayRenderer`.

- [ ] **Step 5: Delete PhaseBreadcrumb component**

```bash
rm frontend/packages/shared/src/emma/displays/Generic/PhaseBreadcrumb.tsx
```

- [ ] **Step 6: Commit**

```bash
git add -A frontend/packages/shared/src/emma/ \
       frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx \
       frontend/packages/shared/package.json
git commit -m "refactor(explain): remove PhaseBreadcrumb and phase tracking types"
```

---

## Task 6: Update phase mapping tests

**Files:**
- Modify: `backend/microservices/emma-agent-service/tests/test_phase_mapping.py`

- [ ] **Step 1: Remove or update test file**

The test file `tests/test_phase_mapping.py` imports `PHASE_MAP`, `PHASE_ORDER`, `PHASE_LABELS` which no longer exist. Delete it:

```bash
rm backend/microservices/emma-agent-service/tests/test_phase_mapping.py
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/tests/test_phase_mapping.py
git commit -m "test(explain): remove phase mapping tests — replaced by humanizeStep tests"
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| `humanizeStep()` doesn't parse all tool_result formats | Unit tests cover all known tools; unknown tools get "Procesando..." fallback |
| ActivityTimeline too tall with many steps | Deduplication (tool_call+result → 1 step) keeps it compact; post-completion collapse |
| ExplanationPanel still works | Not touched — explanation comes from a separate field, unrelated to phase/activity tracking |
| Backend restart needed | Only Task 4 requires restart; Tasks 1-3 and 5-6 are frontend-only |
