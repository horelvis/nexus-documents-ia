# EmmaChat Artifacts Panel — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace floating dialogs (VerifiedGeneration, PredictiveAnalysis) with a persistent, resizable side panel that coexists with the chat. Forge results also display in the panel.

**Architecture:** CSS grid layout splits the chat area into `[chat (flex-1)] | [panel (auto)]`. An `ArtifactsPanel` component renders tabs (Verified/Predictive/Forge). The existing `verified-generation-context.tsx` gains panel-awareness (open/active tab). Floating dialogs are deleted; their content moves into tab components. Services and SSE handlers remain unchanged.

**Tech Stack:** React + TypeScript, Tailwind CSS, Framer Motion (transitions), shadcn/ui (Tabs, Card, Button)

**Spec:** `docs/superpowers/specs/2026-03-15-emmachat-ux-redesign-design.md` (Phase 2 section)

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `apps/on-premise/src/components/emma-chat/ArtifactsPanel.tsx` | Side panel container: tabs, resize handle, collapse/expand, pill badge |
| `apps/on-premise/src/components/emma-chat/artifacts/VerifiedGenTab.tsx` | Claims list, progress bar, HITL review button (migrated from VerifiedGenerationDialog) |
| `apps/on-premise/src/components/emma-chat/artifacts/PredictiveTab.tsx` | Factors/outcomes progress (migrated from PredictiveAnalysisDialog) |
| `apps/on-premise/src/components/emma-chat/artifacts/ForgeTab.tsx` | Field detection list, confidence, edit/generate buttons |

### Modified Files
| File | Change |
|------|--------|
| `apps/on-premise/src/components/emma-chat/EmmaChat.tsx` | Replace floating dialogs with `<ArtifactsPanel>`. Add panel open/tab state. |
| `apps/on-premise/src/contexts/verified-generation-context.tsx` | Add `panelOpen`, `activeTab`, artifact registry for multi-type support |
| `apps/on-premise/src/app/layout.tsx` | Remove `<VerifiedGenerationFloating>` (panel is now inside EmmaChat) |

### Deleted Files
| File | Reason |
|------|--------|
| `apps/on-premise/src/components/emma-chat/VerifiedGenerationDialog.tsx` | Content moved to VerifiedGenTab |
| `apps/on-premise/src/components/emma-chat/VerifiedGenerationFloating.tsx` | Panel replaces floating widget |
| `apps/on-premise/src/components/emma-chat/PredictiveAnalysisDialog.tsx` | Content moved to PredictiveTab |

All paths relative to `frontend/`.

---

## Chunk 1: Panel Container + Layout Integration

### Task 1: Create ArtifactsPanel container component

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/ArtifactsPanel.tsx`

- [ ] **Step 1: Read existing dialog patterns**

Read `VerifiedGenerationDialog.tsx` (418 lines) to understand the collapsed pill, stats bar, and job rendering patterns. Also read `PredictiveAnalysisDialog.tsx` (273 lines) for the tab-like pattern.

- [ ] **Step 2: Create ArtifactsPanel**

The panel is a container with:
- Header with title + close button
- Tab bar (Verified / Predictive / Forge) with badge counts
- Active tab content area (scrollable)
- Collapse to floating pill
- Resize handle on left edge

```typescript
'use client'

import React, { useState } from 'react'
import { X, ChevronLeft, ChevronRight, GripVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface ArtifactTab {
  id: string
  label: string
  icon: React.ReactNode
  badge?: string | number
  content: React.ReactNode
}

interface ArtifactsPanelProps {
  tabs: ArtifactTab[]
  activeTabId: string | null
  onTabChange: (tabId: string) => void
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ArtifactsPanel({
  tabs,
  activeTabId,
  onTabChange,
  open,
  onOpenChange,
}: ArtifactsPanelProps) {
  const [width, setWidth] = useState(400)
  const activeTab = tabs.find((t) => t.id === activeTabId)

  // Collapsed pill
  if (!open) {
    if (tabs.length === 0) return null
    return (
      <button
        onClick={() => onOpenChange(true)}
        className="fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 text-sm text-white shadow-lg hover:bg-indigo-700 transition-colors"
      >
        {tabs.length} artifact{tabs.length !== 1 ? 's' : ''}
        {/* Show active badge */}
        {tabs.some((t) => t.badge) && (
          <span className="rounded-full bg-white/20 px-2 py-0.5 text-xs">
            {tabs.find((t) => t.badge)?.badge}
          </span>
        )}
      </button>
    )
  }

  return (
    <div
      className="flex h-full flex-col border-l bg-muted/30"
      style={{ width, minWidth: 300, maxWidth: '60vw' }}
    >
      {/* Resize handle */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-400 transition-colors"
        onMouseDown={(e) => {
          e.preventDefault()
          const startX = e.clientX
          const startWidth = width
          function onMove(ev: MouseEvent) {
            const delta = startX - ev.clientX
            setWidth(Math.max(300, Math.min(startWidth + delta, window.innerWidth * 0.6)))
          }
          function onUp() {
            document.removeEventListener('mousemove', onMove)
            document.removeEventListener('mouseup', onUp)
          }
          document.addEventListener('mousemove', onMove)
          document.addEventListener('mouseup', onUp)
        }}
      />

      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-2">
        <span className="text-sm font-semibold">Artifacts</span>
        <Button variant="ghost" size="icon" onClick={() => onOpenChange(false)}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Tab bar */}
      <div className="flex border-b overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={cn(
              'flex items-center gap-1.5 px-4 py-2 text-xs font-medium whitespace-nowrap transition-colors',
              tab.id === activeTabId
                ? 'border-b-2 border-indigo-500 text-indigo-600 dark:text-indigo-400'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {tab.icon}
            {tab.label}
            {tab.badge != null && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px]">
                {tab.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        {activeTab?.content ?? (
          <p className="text-center text-sm text-muted-foreground py-8">
            Selecciona un artifact
          </p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/ArtifactsPanel.tsx
git commit -m "feat(artifacts): create ArtifactsPanel container with tabs, resize, collapse"
```

---

### Task 2: Integrate panel into EmmaChat layout

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` (~line 1950-2065, rendering section)

- [ ] **Step 1: Read the current rendering section**

Read `EmmaChat.tsx` around the bottom (~lines 1950-2065) where `EmmaRenderChat`, `EmmaQueryInput`, and `PredictiveAnalysisDialog` are rendered. Understand the current flex layout.

- [ ] **Step 2: Add panel state**

Add state near the top of the component (after existing state declarations):

```typescript
const [artifactsPanelOpen, setArtifactsPanelOpen] = useState(false)
const [activeArtifactTab, setActiveArtifactTab] = useState<string | null>(null)
```

- [ ] **Step 3: Replace layout with grid**

Change the current `flex flex-col` layout to a grid that accommodates the side panel:

```typescript
<div className="flex h-full">
  {/* Chat area (flex-1) */}
  <div className="flex flex-1 flex-col min-w-0">
    {/* Deep Reasoning Toggle (existing) */}
    {/* EmmaRenderChat (existing) */}
    {/* EmmaQueryInput (existing) */}
  </div>

  {/* Artifacts Panel (conditional) */}
  {artifactTabs.length > 0 && (
    <ArtifactsPanel
      tabs={artifactTabs}
      activeTabId={activeArtifactTab}
      onTabChange={setActiveArtifactTab}
      open={artifactsPanelOpen}
      onOpenChange={setArtifactsPanelOpen}
    />
  )}
</div>
```

- [ ] **Step 4: Build artifactTabs from existing state**

Build the tabs array from `verifiedJobs` and `predictiveJobs` state (these already exist in EmmaChat):

```typescript
const artifactTabs: ArtifactTab[] = []

// Verified Generation tabs
if (Object.keys(verifiedJobs).length > 0) {
  const totalClaims = Object.values(verifiedJobs).reduce((sum, j) => sum + (j.total_claims || 0), 0)
  const verifiedCount = Object.values(verifiedJobs).reduce((sum, j) => sum + (j.verified_count || 0), 0)
  artifactTabs.push({
    id: 'verified',
    label: 'Verified Gen',
    icon: <FileCheck className="h-3.5 w-3.5" />,
    badge: `${verifiedCount}/${totalClaims}`,
    content: <VerifiedGenTab jobs={verifiedJobs} onSubmitReview={handleVerifiedReview} />,
  })
}

// Predictive Analysis tabs
if (Object.keys(predictiveJobs).length > 0) {
  artifactTabs.push({
    id: 'predictive',
    label: 'Predictive',
    icon: <TrendingUp className="h-3.5 w-3.5" />,
    content: <PredictiveTab jobs={predictiveJobs} />,
  })
}
```

- [ ] **Step 5: Auto-open panel when artifacts start**

In the existing SSE handlers for verified/predictive, add panel auto-open:

```typescript
// In handleVerifiedGenerationEvent (or wherever verifiedJobs state is updated):
if (!artifactsPanelOpen) {
  setArtifactsPanelOpen(true)
  setActiveArtifactTab('verified')
}
```

Same pattern for predictive.

- [ ] **Step 6: Remove PredictiveAnalysisDialog rendering**

Delete the `<PredictiveAnalysisDialog>` JSX at the bottom of the render. Its content now lives in the panel.

- [ ] **Step 7: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(artifacts): integrate ArtifactsPanel into EmmaChat layout with auto-open"
```

---

### Task 3: Remove VerifiedGenerationFloating from layout

**Files:**
- Modify: `frontend/apps/on-premise/src/app/layout.tsx`

- [ ] **Step 1: Read layout.tsx**

Read `frontend/apps/on-premise/src/app/layout.tsx` (48 lines). Find where `VerifiedGenerationFloating` is rendered.

- [ ] **Step 2: Remove the floating component**

Remove the `<VerifiedGenerationFloating />` JSX and its import. The panel is now inside EmmaChat, not at layout level.

Keep the `<VerifiedGenerationProvider>` wrapper — the context is still used by EmmaChat for job state management.

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/app/layout.tsx
git commit -m "feat(artifacts): remove VerifiedGenerationFloating from layout (moved to panel)"
```

---

## Chunk 2: Tab Content Components

### Task 4: Create VerifiedGenTab

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/artifacts/VerifiedGenTab.tsx`

- [ ] **Step 1: Read VerifiedGenerationDialog content**

Read `VerifiedGenerationDialog.tsx` (418 lines). Extract the job rendering logic: stats bar, claims list, per-claim status badges, HITL review button. This content moves into the tab.

- [ ] **Step 2: Create VerifiedGenTab**

The tab receives `jobs` (Record) and `onSubmitReview` callback — same props the dialog used. Extract the content rendering from the dialog into this focused component:

- Progress bar: verified/total claims
- Per-job sections (expandable when multiple jobs)
- Per-claim rows: status icon (spinner/check/x), claim text, confidence badge, verification_type badge
- HITL review button when claims need review
- Verification_reason text (italic, below claim)

Props interface:
```typescript
interface VerifiedGenTabProps {
  jobs: Record<string, VerifiedGenerationMetadata>
  onSubmitReview: (jobId: string, decisions: ReviewDecision[]) => void
  isResuming?: boolean
}
```

Follow the same Tailwind patterns as the existing dialog (green theme for verified, amber for verifying, red for rejected). Do NOT copy the floating/pill/overlay logic — only the content.

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/artifacts/VerifiedGenTab.tsx
git commit -m "feat(artifacts): create VerifiedGenTab with claims progress and HITL review"
```

---

### Task 5: Create PredictiveTab

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/artifacts/PredictiveTab.tsx`

- [ ] **Step 1: Read PredictiveAnalysisDialog content**

Read `PredictiveAnalysisDialog.tsx` (273 lines). Extract the factor extraction progress, outcome list, and prediction display.

- [ ] **Step 2: Create PredictiveTab**

Same pattern as VerifiedGenTab — extract content, drop floating/overlay logic. Receives `jobs` prop.

```typescript
interface PredictiveTabProps {
  jobs: Record<string, PredictiveAnalysisMetadata>
}
```

Blue theme (matching existing dialog).

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/artifacts/PredictiveTab.tsx
git commit -m "feat(artifacts): create PredictiveTab with factors and prediction progress"
```

---

### Task 6: Create ForgeTab

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/artifacts/ForgeTab.tsx`

- [ ] **Step 1: Read ForgeResult content**

Read `ForgeResult.tsx` (281 lines). Understand the 3 modes: analyze (field detection), render (download), persist (success). The tab shows the `analyze` mode content primarily — field list with detection status.

- [ ] **Step 2: Create ForgeTab**

Shows detected fields from Document Forge:
- Template name + overall confidence gauge
- Progress bar: N/M fields filled
- Field list: filled (green check) / missing (amber question mark) with values
- "Editar campos" button → opens field editor (can reuse ForgeResult's editor logic or link to it)
- "Generar PDF" button (when all required fields present)

```typescript
interface ForgeTabProps {
  metadata: ForgeMetadata | null
  onEditFields?: () => void
  onGenerate?: () => void
}
```

Violet theme (matching ForgeResult's `bg-violet-500/5`).

**Note:** ForgeResult.tsx stays for inline chat rendering. The tab provides a panel view with the same data.

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/artifacts/ForgeTab.tsx
git commit -m "feat(artifacts): create ForgeTab with field detection and generate button"
```

---

## Chunk 3: Wiring + Cleanup

### Task 7: Wire Forge results to panel

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx`

- [ ] **Step 1: Add forge state tracking**

The existing code detects forge results in `EmmaRenderChat.tsx` via `isForgeResult(msg)`. Add state to track the latest forge metadata:

```typescript
const [forgeMetadata, setForgeMetadata] = useState<ForgeMetadata | null>(null)
```

- [ ] **Step 2: Capture forge metadata from messages**

When a forge result message arrives (in the SSE handler or message processing), capture its metadata:

```typescript
// After message update, check for forge metadata
if (msg.metadata?.forge) {
  setForgeMetadata(msg.metadata.forge)
  if (!artifactsPanelOpen) {
    setArtifactsPanelOpen(true)
    setActiveArtifactTab('forge')
  }
}
```

- [ ] **Step 3: Add ForgeTab to artifactTabs array**

```typescript
if (forgeMetadata) {
  artifactTabs.push({
    id: 'forge',
    label: 'Document Forge',
    icon: <Hammer className="h-3.5 w-3.5" />,
    badge: forgeMetadata.fields_detected ? `${forgeMetadata.fields_filled}/${forgeMetadata.fields_detected}` : undefined,
    content: <ForgeTab metadata={forgeMetadata} />,
  })
}
```

- [ ] **Step 4: Add "Ver en panel" link in chat**

When Emma's response contains a forge or verified result, add an inline button that opens/focuses the panel tab. In `EmmaRenderChat.tsx`, after rendering the inline result:

```typescript
{renderArtifactLink && (
  <button
    onClick={() => renderArtifactLink(artifactType)}
    className="mt-2 text-xs text-indigo-600 hover:underline"
  >
    Ver en panel →
  </button>
)}
```

Pass `renderArtifactLink` as a callback prop from EmmaChat (same pattern as `renderHITLReview`).

- [ ] **Step 5: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx
git commit -m "feat(artifacts): wire Forge results to panel with auto-open and inline link"
```

---

### Task 8: Delete old floating dialogs

**Files:**
- Delete: `frontend/apps/on-premise/src/components/emma-chat/VerifiedGenerationDialog.tsx`
- Delete: `frontend/apps/on-premise/src/components/emma-chat/VerifiedGenerationFloating.tsx`
- Delete: `frontend/apps/on-premise/src/components/emma-chat/PredictiveAnalysisDialog.tsx`
- Modify: Any files that import the deleted components

- [ ] **Step 1: Search for imports of deleted files**

```bash
cd frontend && grep -r "VerifiedGenerationDialog\|VerifiedGenerationFloating\|PredictiveAnalysisDialog" --include="*.tsx" --include="*.ts" -l
```

- [ ] **Step 2: Remove imports and usages**

For each file found, remove the import and any JSX rendering of the deleted components. The functionality now lives in the ArtifactsPanel tabs.

- [ ] **Step 3: Delete the files**

```bash
rm frontend/apps/on-premise/src/components/emma-chat/VerifiedGenerationDialog.tsx
rm frontend/apps/on-premise/src/components/emma-chat/VerifiedGenerationFloating.tsx
rm frontend/apps/on-premise/src/components/emma-chat/PredictiveAnalysisDialog.tsx
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit --project apps/on-premise/tsconfig.json
```

Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(artifacts): delete old floating dialogs replaced by ArtifactsPanel"
```

---

### Task 9: Update context for panel state

**Files:**
- Modify: `frontend/apps/on-premise/src/contexts/verified-generation-context.tsx`

- [ ] **Step 1: Read the current context**

Read `verified-generation-context.tsx` (87 lines). It manages `dialogOpen`, `jobs`, `reviewHandler`.

- [ ] **Step 2: Replace dialogOpen with panelOpen + activeTab**

```typescript
// Replace:
dialogOpen: boolean
setDialogOpen: (open: boolean) => void

// With:
panelOpen: boolean
setPanelOpen: (open: boolean) => void
activeTab: string | null
setActiveTab: (tab: string | null) => void
```

Update all consumers. Since EmmaChat now manages panel state locally (from Task 2), the context may only need `panelOpen` for cross-component communication (e.g., if the input bar needs to open the panel).

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/contexts/verified-generation-context.tsx frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(artifacts): update context with panel state (panelOpen, activeTab)"
```

---

### Task 10: E2E verification

- [ ] **Step 1: TypeScript compile check**

```bash
cd frontend && npx tsc --noEmit --project apps/on-premise/tsconfig.json && npx tsc --noEmit --project packages/shared/tsconfig.json
```

Expected: zero errors for both.

- [ ] **Step 2: Visual test — Verified Generation**

Open browser → Start a verified generation (via EmmaQueryInput or API). Expected:
- Panel auto-opens on right side
- "Verified Gen" tab active with progress bar
- Claims stream in with status badges
- Panel is resizable (drag left edge)
- Collapse to pill (click X)
- Pill shows "1 artifact" with badge

- [ ] **Step 3: Visual test — Chat continues while panel open**

While verified generation runs, send a normal query ("Hola"). Expected:
- Chat responds normally in the left area
- Panel stays open with verification progress
- Scroll works independently in chat and panel

- [ ] **Step 4: Visual test — Forge**

Trigger a forge result in chat. Expected:
- ForgeTab appears in panel
- Field list with detection status
- "Ver en panel →" link in chat opens/focuses the tab

- [ ] **Step 5: Final commit (if fixes needed)**

```bash
git add -A
git commit -m "fix(artifacts): E2E fixes for artifacts panel"
```

---

## Post-Implementation Checklist

- [ ] ArtifactsPanel renders as side panel (not floating)
- [ ] Tabs show Verified Gen / Predictive / Forge with badge counts
- [ ] Panel auto-opens when artifacts start
- [ ] Panel collapses to pill (bottom-right)
- [ ] Panel is resizable (drag handle, min 300px, max 60vw)
- [ ] Chat remains interactive while panel open (non-blocking)
- [ ] VerifiedGenTab shows claims progress with HITL review button
- [ ] PredictiveTab shows factors/outcomes progress
- [ ] ForgeTab shows field detection with edit/generate buttons
- [ ] Old floating dialogs deleted
- [ ] "Ver en panel →" inline links work in chat
- [ ] TypeScript compiles with zero errors (both packages)
- [ ] Dark mode works for all panel components
