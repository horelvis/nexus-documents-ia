# EmmaChat UX Redesign — HITL Protocol + Artifacts Panel + useStream SDK

**Date**: 2026-03-15
**Status**: Reviewed (pass 1 — 3 critical + 8 important issues resolved)
**Scope**: 3-phase UX overhaul for EmmaChat, inspired by LangChain agent-chat-ui patterns

## Problem Statement

EmmaChat's current UX has three limitations:

1. **HITL is binary** — Only confirm/cancel for email tool. No way to edit args before sending, no reject-with-feedback. Each new tool that needs review requires custom UI code.
2. **Artifacts are modals** — Verified Generation and Document Forge live in floating dialogs that block the chat. User can't continue chatting while verification runs.
3. **SSE is manual** — ~250 lines of custom SSE parsing in EmmaChat.tsx. No branch switching, no regenerate, no thread history. Every new SSE event requires frontend code changes.

## Goals

1. Generalised HITL protocol — any `interrupt()` renders with appropriate UI (review, clarification, or confirmation)
2. Persistent side panel for artifacts — Verified Generation, Predictive Analysis, and Forge coexist as tabs, non-blocking
3. Migrate to `@langchain/langgraph-sdk` `useStream` — eliminate custom SSE parsing, gain branch switching, regenerate, and thread history for free
4. Adapter endpoints in emma-agent-service — implement LangGraph Server protocol subset for SDK compatibility
5. Verified Generation as LangGraph subgraph — events flow through `useStream` to the artifacts panel (separate sub-spec due to complexity)

## Non-Goals

- Changing the ReAct graph topology or node logic
- Migrating EmmaTool to `@tool` decorators (separate sub-project)
- Social channel (Slack/Telegram) UX changes
- Mobile-first redesign (desktop priority)
- Full LangGraph Server implementation (only the subset `useStream` needs)

## Package Structure

Frontend files span two locations:

| Location | Scope | Examples |
|----------|-------|---------|
| `frontend/packages/shared/src/emma/` | Shared components (EmmaChat, EmmaRenderChat, types, displays) | EmmaChat.tsx, types.ts, EmmaClarificationUI.tsx |
| `frontend/apps/on-premise/src/` | On-premise specific (verified gen, forge, services) | VerifiedGenerationDialog.tsx, ForgeResult.tsx, emma.service.ts |

New components go in `frontend/apps/on-premise/src/components/emma-chat/` since they depend on on-premise services (LangGraph adapter, verified generation).

## Architecture

### Current State

```
Frontend
  ├── packages/shared/src/emma/EmmaChat.tsx — Main container, SSE handling (~250 lines)
  ├── packages/shared/src/emma/EmmaClarificationUI.tsx — Clarification HITL (radio/checkbox)
  ├── apps/on-premise/src/components/emma-chat/VerifiedGenerationDialog.tsx — Floating modal
  ├── apps/on-premise/src/components/emma-chat/ForgeResult.tsx — Inline forge result
  ├── apps/on-premise/src/components/emma-chat/PredictiveAnalysisDialog.tsx — Floating modal
  └── apps/on-premise/src/lib/services/emma.service.ts — SSE parsing, API calls

Backend (emma-agent-service)
  ├── /emma/stream → custom SSE events (plan_created, step_start, token, complete...)
  ├── /emma/query → non-streaming fallback
  ├── /emma/query/resume/stream → resume interrupted graph
  └── Verified/Predictive: separate SSE endpoints via stop-and-go runner
```

### Target State

```
Frontend
  ├── packages/shared/src/emma/EmmaChat.tsx — useStream hook (~30 lines)
  ├── apps/on-premise/src/components/emma-chat/HITLReviewCard.tsx — Approve/Edit/Reject
  ├── apps/on-premise/src/components/emma-chat/HITLClarificationCard.tsx — Clarification (migrated)
  ├── apps/on-premise/src/components/emma-chat/ArtifactsPanel.tsx — Side panel with tabs
  ├── apps/on-premise/src/components/emma-chat/BranchSwitcher.tsx — Checkpoint nav
  └── apps/on-premise/src/components/emma-chat/ThreadHistory.tsx — Conversation list

Backend (emma-agent-service)
  ├── /api/threads/{id}/runs → LangGraph protocol SSE (values, updates, interrupts, checkpoints)
  ├── /api/threads → thread list from checkpointer (tenant-filtered)
  ├── /api/threads/{id}/state → current graph state
  ├── /api/threads/{id}/history → checkpoint history for branch switching
  ├── /api/info → health check
  └── /emma/stream → kept for backwards compat (deprecated, feature-flagged)
```

---

## Phase 1: HITL Protocol — Unified Interrupt Handling

### Interrupt Type Registry

Three interrupt patterns exist in the codebase. Phase 1 unifies them under a discriminated union:

| Pattern | Current Location | `interrupt()` Schema | Frontend Renderer |
|---------|-----------------|---------------------|-------------------|
| **Tool Review** | `react_loop.py:888` (email) | `{type: "hitl_review", action_request, review_config}` | `HITLReviewCard` (Approve/Edit/Reject) |
| **Clarification** | `classify_node.py:269` | `{type: "clarification", question, options}` | `HITLClarificationCard` (replaces EmmaClarificationUI) |
| **Confirmation** | `react_loop.py:888` (current) | `{type: "confirmation", question, options}` | `HITLConfirmationCard` (simple Yes/No) |

The frontend dispatches on `interrupt.value.type`:

```typescript
type InterruptValue =
  | HITLReviewRequest      // type: "hitl_review"
  | ClarificationRequest   // type: "clarification"
  | ConfirmationRequest;   // type: "confirmation"
```

### Backend: Tool Review interrupt() Schema

When a tool needs human review:

```python
from langgraph.types import interrupt, Command

# Emit structured review request
decision = interrupt({
    "type": "hitl_review",
    "action_request": {
        "name": "send_email",
        "args": {
            "to": "user@test.com",
            "subject": "Contrato de arrendamiento",
            "body": "Adjunto el contrato...",
        },
        "description": "Enviar email con contrato adjunto",
    },
    "review_config": {
        "allowed_decisions": ["approve", "edit", "reject"],
        "editable_fields": ["to", "subject", "body"],
    },
})

# After resume — decision is the value passed to Command(resume=...)
if decision["type"] == "approve":
    await registry.execute("send_email", tc_args, context)
elif decision["type"] == "edit":
    await registry.execute("send_email", decision["edited_args"], context)
elif decision["type"] == "reject":
    feedback = decision.get("message", "")
    # Inject feedback as HumanMessage so agent can adjust
```

### Resume Mechanism

```
POST /emma/stream/resume
{
  "thread_id": "abc-123",
  "tenant_id": "00000000-...",
  "decision": {
    "type": "edit",
    "edited_args": {"to": "user@test.com, boss@company.com", ...}
  }
}
```

Backend resumes the interrupted graph:

```python
from langgraph.types import Command

# Command(resume=decision) is passed as input to ainvoke()
result = await graph.ainvoke(
    Command(resume=decision),
    config={"configurable": {"thread_id": thread_id}},
)
```

**Note**: `Command(resume=value)` is the first argument to `ainvoke()`, NOT `None`. The resume value is what `interrupt()` returns to the paused node.

### SSE Event (Phase 1 — pre-useStream)

During Phase 1 (before useStream migration), the existing SSE endpoint emits:

```
event: hitl_review
data: {
  "type": "hitl_review",
  "action_request": {
    "name": "send_email",
    "args": {"to": "...", "subject": "...", "body": "..."},
    "description": "Enviar email con contrato adjunto"
  },
  "review_config": {
    "allowed_decisions": ["approve", "edit", "reject"],
    "editable_fields": ["to", "subject", "body"]
  }
}
```

No `interrupt_id` field — the thread_id + checkpoint state is sufficient to resume. The frontend tracks which interrupt is active via the thread's current state.

### Frontend: HITLReviewCard Component

A generic React component that renders any tool review `interrupt()`:

- **Approve mode** (default): Args displayed read-only. "Aprobar" button sends `{type: "approve"}`.
- **Edit mode**: Fields listed in `editable_fields` become `<Textarea>` with amber border. "Enviar editado" sends `{type: "edit", edited_args: {...}}`. Reset button restores original values.
- **Reject mode**: Textarea for feedback ("Share feedback with the agent..."). "Confirmar rechazo" sends `{type: "reject", message: "..."}`. Agent receives the feedback as context.

### Tools Using HITL Review

| Tool | Actual Name | Editable Fields | Allowed Decisions |
|------|------------|----------------|-------------------|
| Send Email | `send_email` | to, subject, body, attachment_id | approve, edit, reject |
| Document Forge | `forge_document` | template, field values | approve, edit, reject |
| Document Generator | `document_generator` | modifications, format | approve, edit, reject |
| Future tools | (any) | Configured per-tool via `review_config` | Generic |

**Note**: `delete_document` does not currently exist as a tool. If added, it would use `approve/reject` only (no edit).

### TypeScript Types

```typescript
// Discriminated union for all interrupt types
type InterruptValue =
  | HITLReviewRequest
  | ClarificationRequest
  | ConfirmationRequest;

interface HITLReviewRequest {
  type: "hitl_review";
  action_request: {
    name: string;
    args: Record<string, unknown>;
    description?: string;
  };
  review_config: {
    allowed_decisions: ("approve" | "edit" | "reject")[];
    editable_fields?: string[];
  };
}

interface ClarificationRequest {
  type: "clarification";
  question: string;
  options: Array<{ label: string; value: string }>;
}

interface ConfirmationRequest {
  type: "confirmation";
  question: string;
  options: Array<{ label: string; value: string }>;
}

type HITLDecision =
  | { type: "approve" }
  | { type: "edit"; edited_args: Record<string, unknown> }
  | { type: "reject"; message?: string };
```

### Files Changed (Phase 1)

| File | Type | Description |
|------|------|-------------|
| `emma-agent-service/app/agents/langgraph/nodes/react_loop.py` | MOD | Replace email HITL with generic `interrupt(HITLReviewRequest)` |
| `emma-agent-service/app/api/emma.py` | MOD | Add `/emma/stream/resume` endpoint using `Command(resume=...)` |
| `emma-agent-service/app/schemas/hitl.py` | NEW | `HITLReviewRequest`, `ClarificationRequest`, `HITLDecision` Pydantic models |
| `on-premise/.../emma-chat/HITLReviewCard.tsx` | NEW | Generic Approve/Edit/Reject component |
| `on-premise/.../emma-chat/HITLClarificationCard.tsx` | NEW | Replaces shared EmmaClarificationUI with interrupt-aware version |
| `packages/shared/src/emma/types.ts` | MOD | Add `InterruptValue`, `HITLDecision` types |
| `packages/shared/src/emma/EmmaChat.tsx` | MOD | Handle `hitl_review` SSE event, dispatch to appropriate card |
| `packages/shared/src/emma/EmmaClarificationUI.tsx` | DEPRECATE | Kept for backwards compat, new card preferred |

### Backward Compatibility

Phase 1's `/emma/stream/resume` endpoint is **independent** of Phase 3's `/api/threads/{id}/runs`. Both coexist:
- Phase 1-2: Frontend uses `/emma/stream` + `/emma/stream/resume`
- Phase 3: Frontend migrates to `/api/threads/{id}/runs` with `Command(resume=...)` in body
- Feature flag `USE_LANGGRAPH_PROTOCOL=false` (default) controls which protocol the frontend uses

---

## Phase 2: Artifacts Panel — Verified Gen + Predictive + Forge

### Layout

Chat (3fr) + Artifacts Panel (2fr), using CSS grid `grid-cols-[1fr_0fr]` → `grid-cols-[3fr_2fr]` transition (same pattern as agent-chat-ui). Verify existing `EmmaRenderChat.tsx` layout before applying.

### Panel Behaviors

- **Auto-open**: Panel opens when Verified Generation, Predictive Analysis, or Forge starts. No manual button.
- **Non-blocking**: Chat continues while artifacts process. User can ask questions.
- **Tab persistence**: Multiple artifacts coexist as tabs. Completed artifacts stay until closed.
- **Collapse to pill**: Floating pill in corner shows artifact count + status. Click to reopen.
- **Resize handle**: Draggable divider between chat and panel. Min: 300px, max: 60% viewport.

### Artifact Tabs

| Tab | Replaces | Content |
|-----|----------|---------|
| Verified Generation | `VerifiedGenerationDialog.tsx` | Claims list with progress, confidence, verification_type, HITL review button |
| Predictive Analysis | `PredictiveAnalysisDialog.tsx` | Factors, outcomes, predictions with confidence |
| Document Forge | `ForgeResult.tsx` (inline) | Fields list, detection confidence, edit/generate buttons |

### Chat Integration

When an artifact starts, Emma's response includes an inline link:

```
"He iniciado la generación verificada. Puedes seguir el progreso en el panel lateral →"
[📄 Ver en panel]  ← clickable, opens/focuses panel tab
```

### Files Changed (Phase 2)

| File | Type | Description |
|------|------|-------------|
| `on-premise/.../emma-chat/ArtifactsPanel.tsx` | NEW | Side panel container with tabs, resize, collapse |
| `on-premise/.../emma-chat/artifacts/VerifiedGenTab.tsx` | NEW | Claims list, progress, HITL review |
| `on-premise/.../emma-chat/artifacts/PredictiveTab.tsx` | NEW | Factors, outcomes, predictions |
| `on-premise/.../emma-chat/artifacts/ForgeTab.tsx` | NEW | Fields list, confidence, generate button |
| `packages/shared/src/emma/EmmaRenderChat.tsx` | MOD | Add artifacts panel to layout grid |
| `packages/shared/src/emma/EmmaChat.tsx` | MOD | Manage artifacts state, auto-open panel |
| `on-premise/.../emma-chat/VerifiedGenerationDialog.tsx` | DEL | Replaced by VerifiedGenTab |
| `on-premise/.../emma-chat/VerifiedGenerationFloating.tsx` | DEL | Replaced by panel pill |
| `on-premise/.../emma-chat/VerifiedGenerationProgress.tsx` | DEL | Merged into VerifiedGenTab |
| `on-premise/.../emma-chat/PredictiveAnalysisDialog.tsx` | DEL | Replaced by PredictiveTab |
| `on-premise/.../emma-chat/ForgeResult.tsx` | DEL | Replaced by ForgeTab |
| `on-premise/src/contexts/verified-generation-context.tsx` | MOD | Adapt to panel state management |
| `on-premise/src/lib/services/verified-generation.service.ts` | MOD | Wire SSE to panel tab updates |

---

## Phase 3: useStream SDK Migration

### Backend: Adapter Endpoints

New file `app/api/langgraph_protocol.py` implementing LangGraph Server protocol subset:

| Endpoint | Method | Handler |
|----------|--------|---------|
| `/api/info` | GET | Return server metadata + available graphs |
| `/api/threads` | GET | Query checkpointer threads (filtered by tenant_id via metadata) |
| `/api/threads/{id}` | GET | Get thread details from checkpointer |
| `/api/threads/{id}/state` | GET | Current graph state from checkpointer |
| `/api/threads/{id}/history` | GET | Checkpoint history for branch switching |
| `/api/threads/{id}/runs` | POST | Execute graph run with SSE streaming OR resume with Command |

Auth: Same `X-API-Key` + `X-Tenant-ID` headers. Tenant isolation on all thread queries.

**Tenant filtering for threads**: `AsyncPostgresSaver` does not store `tenant_id` as a column — it's inside the state JSONB. Options: (a) add a `metadata` JSONB column to the checkpoint table and store tenant_id there at write time, or (b) use the existing `thread_id` format which embeds tenant context. Decision deferred to implementation — the adapter endpoint abstracts this from the frontend.

### SSE Format Translation (Complete Mapping)

The adapter translates graph execution events into LangGraph protocol SSE:

| Current SSE Event | LangGraph Event | Data Mapping |
|-------------------|----------------|--------------|
| `start` | `event: metadata` | `{run_id: uuid}` |
| `plan_created` | `event: updates` | `{classify: {intent, steps}}` |
| `step_start` | `event: updates` | `{react_loop: {current_step, tool_name}}` |
| `step_complete` | `event: updates` | `{react_loop: {step_result, findings_count}}` |
| `slm_thinking` | `event: updates` | `{react_loop: {thinking: text}}` (or custom event) |
| `token` | `event: values` | Full state snapshot with latest content appended |
| `clarification_needed` | `event: interrupts` | `[{value: {type: "clarification", ...}}]` |
| `confirmation_needed` / `hitl_review` | `event: interrupts` | `[{value: {type: "hitl_review", ...}}]` |
| `complete` | `event: values` | Final state snapshot with all messages |
| `error` | `event: error` | `{error: message}` |
| `swarm_started` | `event: updates` | `{decompose: {num_workers, sub_tasks}}` |
| `worker_started` / `worker_complete` | `event: updates` | `{swarm_worker: {worker_id, status}}` |
| `swarm_synthesizing` | `event: updates` | `{synthesize_swarm: {status: "synthesizing"}}` |
| Checkpoint after each node | `event: checkpoint` | `{id, ts, parent_id}` |

**Events dropped**: `suggestions_available` (rarely used, can be custom event), `delegation` (legacy).

### Frontend: useStream Integration

```typescript
import { useStream } from "@langchain/langgraph-sdk/react";

const stream = useStream({
  apiUrl: "/api",
  assistantId: "emma-react",
  threadId,
  onThreadId: setThreadId,
  fetchStateHistory: true,
  streamMode: ["values"],
  streamSubgraphs: true,
  streamResumable: true,
});

// Available:
// stream.messages — message list (auto-updated)
// stream.isLoading — loading state
// stream.interrupt — current interrupt (HITLReviewRequest | ClarificationRequest | ...)
// stream.error — error state
// stream.submit(input) — send new message
// stream.submit({}, {command: {resume: decision}}) — resume from interrupt
// stream.setBranch(branchId) — switch checkpoint branch
// stream.getMessagesMetadata(msg) — get branch info for BranchSwitcher
```

### New UX Features (Free from SDK)

1. **Branch Switching**: Navigate between alternative responses. `← 2/3 →` controls per AI message.
2. **Regenerate**: Re-run from parent checkpoint. "🔄 Regenerar" button on AI messages.
3. **Thread History**: Sidebar with persistent conversations from checkpointer. Click to resume.
4. **Optimistic Updates**: User message appears instantly before SSE confirms.

### Verified Generation as Subgraph (Separate Sub-Spec)

Converting the stop-and-go graph to a LangGraph subgraph is architecturally complex due to:

- **State incompatibility**: `StopAndGoState` has 30+ domain-specific fields (`source_sections`, `jurisprudence_evidence`, `source_doi_validations`, etc.) that don't exist in `ReActState`
- **Redis cache dependency**: Review node reads/writes claims from Redis, needs session_id and tenant_id from parent
- **Custom SSE runner**: `pending_events` merge_lists reducer bridges to SSE — needs mapping to `streamSubgraphs` protocol
- **15 files, ~1645 lines** with strategy patterns, DOI validation, CENDOJ integration

**Decision**: Break out into a dedicated sub-spec (`2026-XX-XX-verified-gen-subgraph-design.md`) to be written after Phase 3 step 2 (chat migration) validates the adapter pattern. Until then, Verified Generation keeps its separate SSE endpoint and the artifacts panel connects to it directly (not through `useStream`).

### Migration Strategy (Incremental)

1. **Spike test** (~2 days): Minimal `/api/info` + `/api/threads/{id}/runs`. Validate `useStream` connects and renders messages.
2. **Chat migration** (~1 week): Replace manual SSE with `useStream` hook. Interrupt rendering via discriminated union. Old `/emma/stream` kept behind feature flag.
3. **Branch + Regen + History** (~3 days): Wire SDK features to UI components. Checkpoint history endpoint.
4. **Verified Gen subgraph** (separate sub-spec, ~2-3 weeks): Convert stop-and-go to subgraph after validating adapter pattern.
5. **Cleanup** (~2 days): Remove old SSE endpoints. **Caveat**: `/emma/stream` is also used by `emma_background_service.py` (reactive system) and social agent — those consumers must be migrated or given their own endpoint before deletion.

### Files Changed (Phase 3)

| File | Type | Description |
|------|------|-------------|
| `emma-agent-service/app/api/langgraph_protocol.py` | NEW | Adapter endpoints (6 routes) |
| `emma-agent-service/app/services/langgraph_adapter.py` | NEW | Graph exec → LangGraph SSE translator |
| `frontend/apps/on-premise/package.json` | MOD | Add `@langchain/langgraph-sdk` dependency |
| `packages/shared/src/emma/EmmaChat.tsx` | REWRITE | Replace SSE manual with `useStream` hook |
| `on-premise/.../emma-chat/EmmaStreamProvider.tsx` | NEW | `useStream` context provider with auth headers |
| `on-premise/.../emma-chat/BranchSwitcher.tsx` | NEW | Branch navigation per AI message |
| `on-premise/.../emma-chat/CommandBar.tsx` | NEW | Regenerate, copy, feedback buttons per message |
| `on-premise/.../emma-chat/ThreadHistory.tsx` | NEW | Sidebar with thread list from checkpointer |
| `on-premise/src/lib/services/emma.service.ts` | DEL | Manual SSE parsing removed (after all consumers migrated) |

---

## Dependencies

### New Frontend Dependencies

```
@langchain/langgraph-sdk >= 1.0.0
@langchain/core >= 1.1.28
```

### Backend Dependencies

Already present: `langgraph`, `langchain-core`, `psycopg`, `langchain-openai` (via `llm_models.py`).

No new backend dependencies needed — adapter endpoints use existing `graph.ainvoke()` + `graph.astream()`.

---

## Langfuse Tracing

The current `/emma/stream` endpoint integrates with Langfuse (`trace_emma_query`, `score_emma_result`). The new `/api/threads/{id}/runs` adapter must preserve this:

- Wrap `graph.ainvoke()` / `graph.astream()` calls with Langfuse trace context
- Pass `thread_id` and `tenant_id` as trace metadata
- Score completed runs the same way as current endpoint

---

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| `useStream` SDK protocol changes between versions | Pin `@langchain/langgraph-sdk` version. Adapter endpoints are our code — we control the contract. |
| Adapter endpoint complexity | Spike test first. Minimal protocol subset (not full LangGraph Server). |
| Verified Gen subgraph too complex for Phase 3 | Broken out as separate sub-spec. Panel connects to existing SSE until subgraph is ready. |
| Two SSE protocols during transition | Feature flag `USE_LANGGRAPH_PROTOCOL=false`. Old endpoints functional until cleanup. |
| Thread history tenant isolation | Defer implementation detail — adapter endpoint abstracts query logic. |
| `/emma/stream` deletion breaks background consumers | Identify all consumers (background_service, reactive, social) before cleanup step. |
| Langfuse tracing gaps in new endpoints | Wrap adapter with same trace context as current endpoints. |

---

## Post-Implementation Checklist

### Phase 1
- [ ] HITLReviewCard renders for send_email with Approve/Edit/Reject
- [ ] Edit mode allows modifying tool args (to, subject, body) before approve
- [ ] Reject sends feedback message to agent
- [ ] Clarification interrupt renders via HITLClarificationCard
- [ ] `/emma/stream/resume` endpoint resumes graph with `Command(resume=...)`
- [ ] forge_document tool uses HITL review protocol

### Phase 2
- [ ] Artifacts panel opens automatically for Verified Generation
- [ ] Predictive Analysis renders in panel tab
- [ ] Forge tab shows detected fields with confidence
- [ ] Panel collapses to pill, resizable with drag handle
- [ ] Chat remains interactive while artifacts process (non-blocking)
- [ ] VerifiedGenerationDialog.tsx and PredictiveAnalysisDialog.tsx deleted

### Phase 3
- [ ] Spike test: `useStream` connects to `/api/threads/{id}/runs`
- [ ] Messages render from SDK state
- [ ] All 3 interrupt types render correctly via `stream.interrupt`
- [ ] Branch switching functional
- [ ] Regenerate from checkpoint works
- [ ] Thread history shows past conversations (tenant-filtered)
- [ ] All current SSE events mapped to LangGraph protocol
- [ ] Langfuse tracing preserved in adapter endpoints
- [ ] Feature flag rollback to old SSE works
- [ ] Old SSE consumer audit completed before cleanup
