# EmmaChat HITL Protocol — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the binary confirm/cancel email HITL with a generalised Approve/Edit/Reject protocol that any tool can opt into via `interrupt()`.

**Architecture:** Discriminated union of 3 interrupt types (`hitl_review`, `clarification`, `confirmation`) with a generic `HITLReviewCard` React component that renders editable fields. Backend `interrupt()` emits structured `HITLReviewRequest`; frontend dispatches on `type` field. Resume via existing `/emma/query/resume/stream` endpoint extended to accept `HITLDecision` objects.

**Tech Stack:** Python (LangGraph `interrupt()` + `Command(resume=...)`), React + TypeScript (Next.js 15), Tailwind CSS, SSE streaming

**Spec:** `docs/superpowers/specs/2026-03-15-emmachat-ux-redesign-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/microservices/emma-agent-service/app/schemas/hitl.py` | Pydantic models: `HITLReviewRequest`, `ClarificationRequest`, `ConfirmationRequest`, `HITLDecision` |
| `frontend/apps/on-premise/src/components/emma-chat/HITLReviewCard.tsx` | Generic Approve/Edit/Reject component for tool call review |

### Modified Files
| File | Change |
|------|--------|
| `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py` | Replace email-specific `interrupt()` (lines 872-931) with generic `HITLReviewRequest` |
| `backend/microservices/emma-agent-service/app/api/emma.py` | Extend `ResumeRequest` to accept dict, fix SSE interrupt type dispatch |
| `backend/microservices/emma-agent-service/app/agents/langgraph/api.py` | Fix SSE interrupt type dispatch in `resume_react_query()` |
| `frontend/apps/on-premise/src/lib/types/emma.ts` | Add `HITLReviewRequest`, `HITLDecision`, `InterruptValue` types + `hitl_review` in metadata |
| `frontend/packages/shared/src/emma/EmmaRenderChat.tsx` | Add `renderHITLReview` callback prop for on-premise card injection |
| `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` | Handle `hitl_review` SSE event, extract `processResumeStream`, add `handleHITLDecision` |
| `frontend/apps/on-premise/src/lib/services/emma.service.ts` | Update `resumeQueryStreamGenerator()` to accept `string | Record<string, unknown>` |

---

## Chunk 1: Backend — Schemas + interrupt() Migration

### Task 1: Create HITL Pydantic schemas

**Files:**
- Create: `backend/microservices/emma-agent-service/app/schemas/hitl.py`

- [ ] **Step 1: Create the schema file**

```python
"""HITL (Human-in-the-Loop) interrupt schemas.

Discriminated union of 3 interrupt types:
- hitl_review: Tool call review with Approve/Edit/Reject
- clarification: Query clarification with options
- confirmation: Simple Yes/No confirmation
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Interrupt Request types (backend → frontend) ──

class ActionRequest(BaseModel):
    """Tool call that needs human review."""
    name: str = Field(..., description="Tool name (e.g., send_email, forge_document)")
    args: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    description: Optional[str] = Field(None, description="Human-readable description of the action")


class ReviewConfig(BaseModel):
    """Configuration for how the frontend should render the review UI."""
    allowed_decisions: List[Literal["approve", "edit", "reject"]] = Field(
        ..., description="Which decision buttons to show"
    )
    editable_fields: Optional[List[str]] = Field(
        None, description="Which arg fields the user can edit (None = all)"
    )


class HITLReviewRequest(BaseModel):
    """Interrupt payload for tool call review (Approve/Edit/Reject)."""
    type: Literal["hitl_review"] = "hitl_review"
    action_request: ActionRequest
    review_config: ReviewConfig


class ClarificationRequest(BaseModel):
    """Interrupt payload for query clarification."""
    type: Literal["clarification"] = "clarification"
    question: str
    options: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of {label, value} dicts"
    )


class ConfirmationRequest(BaseModel):
    """Interrupt payload for simple Yes/No confirmation."""
    type: Literal["confirmation"] = "confirmation"
    question: str
    options: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of {label, value} dicts"
    )


# Union type for all interrupt values
InterruptValue = Union[HITLReviewRequest, ClarificationRequest, ConfirmationRequest]


# ── Decision types (frontend → backend) ──

class ApproveDecision(BaseModel):
    """User approved the tool call as-is."""
    type: Literal["approve"] = "approve"


class EditDecision(BaseModel):
    """User edited the tool args before approving."""
    type: Literal["edit"] = "edit"
    edited_args: Dict[str, Any] = Field(..., description="Modified tool arguments")


class RejectDecision(BaseModel):
    """User rejected the tool call with optional feedback."""
    type: Literal["reject"] = "reject"
    message: Optional[str] = Field(None, description="Rejection reason / feedback for agent")


HITLDecision = Union[ApproveDecision, EditDecision, RejectDecision]
```

- [ ] **Step 2: Verify import works**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/docker
docker compose exec emma-agent-service python -c "
from app.schemas.hitl import HITLReviewRequest, HITLDecision, EditDecision
req = HITLReviewRequest(
    action_request={'name': 'send_email', 'args': {'to': 'test@x.com'}},
    review_config={'allowed_decisions': ['approve', 'edit', 'reject']},
)
print(req.model_dump())
dec = EditDecision(edited_args={'to': 'new@x.com'})
print(dec.model_dump())
print('✅ Schemas OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/schemas/hitl.py
git commit -m "feat(hitl): add HITL interrupt Pydantic schemas — review, clarification, confirmation"
```

---

### Task 2: Migrate react_loop email interrupt to HITLReviewRequest

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py` (lines 855-931)

- [ ] **Step 1: Read the current email HITL block**

Read `react_loop.py` lines 855-931 to understand the current `interrupt()` schema and resume handling.

- [ ] **Step 2: Replace the interrupt() call with HITLReviewRequest**

Replace the block at lines 872-931 (the `if email_preview_pending:` block). The new code:

```python
    if email_preview_pending:
        from langgraph.types import interrupt
        tc = email_preview_pending["tool_call"]
        tc_args = tc["args"]
        tc_id = tc.get("id", "")
        result = email_preview_pending["result"]
        to_addr = result.data.get("to", tc_args.get("to", ""))

        logger.info(f"ReAct loop: email preview detected → HITL review (to={to_addr})")

        # Emit structured HITL review request
        decision = interrupt({
            "type": "hitl_review",
            "action_request": {
                "name": "send_email",
                "args": tc_args,
                "description": f"Enviar email a {to_addr}",
            },
            "review_config": {
                "allowed_decisions": ["approve", "edit", "reject"],
                "editable_fields": ["to", "subject", "body"],
            },
        })

        # Handle decision from user (backwards compat: old string values from pre-HITL frontend)
        if isinstance(decision, str):
            # Old frontend sends "confirm_send" / "cancel_send" strings
            decision_type = "approve" if decision == "confirm_send" else "reject"
        elif isinstance(decision, dict):
            decision_type = decision.get("type", "approve")
        else:
            decision_type = "approve"

        if decision_type == "approve":
            logger.info(f"ReAct loop: email approved → sending to {to_addr}")
            send_result = await registry.execute("send_email", {**tc_args, "confirmed": True}, context=tool_context)
            for i, m in enumerate(new_messages):
                if hasattr(m, "tool_call_id") and m.tool_call_id == tc_id:
                    new_messages[i] = ToolMessage(content=send_result.output, tool_call_id=tc_id)
                    break

        elif decision_type == "edit":
            edited_args = decision.get("edited_args", tc_args)
            logger.info(f"ReAct loop: email edited → sending to {edited_args.get('to', to_addr)}")
            send_result = await registry.execute("send_email", {**edited_args, "confirmed": True}, context=tool_context)
            for i, m in enumerate(new_messages):
                if hasattr(m, "tool_call_id") and m.tool_call_id == tc_id:
                    new_messages[i] = ToolMessage(content=send_result.output, tool_call_id=tc_id)
                    break

        elif decision_type == "reject":
            feedback = decision.get("message", "") if isinstance(decision, dict) else ""
            logger.info(f"ReAct loop: email rejected by user (feedback: {feedback[:80]})")
            rejection_msg = "El usuario ha cancelado el envío del email."
            if feedback:
                rejection_msg += f" Motivo: {feedback}"
            for i, m in enumerate(new_messages):
                if hasattr(m, "tool_call_id") and m.tool_call_id == tc_id:
                    new_messages[i] = ToolMessage(content=rejection_msg, tool_call_id=tc_id)
                    break
```

- [ ] **Step 3: Verify the node still imports correctly**

```bash
docker compose exec emma-agent-service python -c "
from app.agents.langgraph.nodes.react_loop import react_loop_node
print('✅ react_loop imports OK')
"
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py
git commit -m "feat(hitl): migrate email interrupt to HITLReviewRequest with approve/edit/reject"
```

---

### Task 3: Extend resume endpoint to accept HITLDecision

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py` (lines 1113-1183)
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/api.py` (lines 531-582)

- [ ] **Step 1: Read current ResumeRequest model and resume_react_query()**

Read `emma.py` lines 1113-1118 for `ResumeRequest` and `langgraph/api.py` lines 531-582 for `resume_react_query()`.

- [ ] **Step 2: Update ResumeRequest to accept dict resume_value**

In `emma.py`, change `ResumeRequest` (around line 1113):

```python
class ResumeRequest(BaseModel):
    """Request to resume a paused graph (HITL interrupt)."""
    thread_id: str = Field(..., description="Thread ID of the paused graph")
    resume_value: Any = Field(..., description="User's decision — string for clarification, dict for HITL review")
    tenant_id: str = Field(..., description="Tenant identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
```

The key change: `resume_value: str` → `resume_value: Any`. This allows both:
- Old: `"confirm_send"` (string for clarification/confirmation)
- New: `{"type": "edit", "edited_args": {...}}` (dict for HITL review)

- [ ] **Step 3: Verify resume_react_query passes value through**

Read `langgraph/api.py` line 578-582 to confirm `Command(resume=resume_value)` already passes any value through. It should — `Command(resume=...)` accepts any serializable value. No changes needed in `resume_react_query()`.

- [ ] **Step 4: CRITICAL — Fix SSE interrupt type dispatch in both endpoints**

The current code in `emma.py` and `langgraph/api.py` **always emits `"clarification"` for all interrupts** regardless of the `type` field in the interrupt value. This must be fixed to dispatch on the interrupt value's `type` field.

**In `langgraph/api.py` `resume_react_query()`** (around line 635-647, the `GraphInterrupt` handler):
Read the current code that catches `GraphInterrupt` and emits a `"clarification"` event. Change it to inspect the interrupt value's `type` field:

```python
# BEFORE (always emits "clarification"):
yield {"type": "clarification", "data": {...}}

# AFTER (dispatch on interrupt type):
interrupt_value = ...  # extract from GraphInterrupt
interrupt_type = "clarification"
if isinstance(interrupt_value, dict):
    interrupt_type = interrupt_value.get("type", "clarification")
yield {"type": interrupt_type, "data": interrupt_value}
```

**In `emma.py` `_generate_langgraph_sse()`** (the main streaming endpoint):
Find where `clarification_needed` or interrupt events are mapped to SSE. Add dispatch logic:

```python
# When a graph interrupt occurs, check the value's type field:
if event_type in ("clarification", "clarification_needed"):
    # Check if this is actually a hitl_review interrupt
    interrupt_data = event_data if isinstance(event_data, dict) else {}
    actual_type = interrupt_data.get("type", "clarification")
    yield f"event: {actual_type}\ndata: {json.dumps(interrupt_data)}\n\n"
```

**In `emma.py` resume endpoint SSE mapping** (lines 1150-1172):
Same pattern — dispatch on the interrupt value's `type` field instead of hardcoding `"clarification"`.

- [ ] **Step 5: Verify both endpoints emit correct event types**

After making the changes, verify by reading both functions to confirm that:
1. `hitl_review` interrupts emit `event: hitl_review` (not `event: clarification`)
2. `clarification` interrupts still emit `event: clarification` (backwards compat)
3. `confirmation` interrupts emit `event: confirmation`

- [ ] **Step 6: Commit**

```bash
git add backend/microservices/emma-agent-service/app/api/emma.py backend/microservices/emma-agent-service/app/agents/langgraph/api.py
git commit -m "feat(hitl): extend resume endpoint to accept HITLDecision dict + hitl_review SSE event"
```

---

### Task 4: Test backend HITL flow end-to-end

- [ ] **Step 1: Verify interrupt fires with new schema**

This requires a query that triggers send_email. Since we can't easily trigger email in test, verify the schema is correct by unit-testing the interrupt value construction:

```bash
docker compose exec emma-agent-service python -c "
from app.schemas.hitl import HITLReviewRequest
req = HITLReviewRequest(
    action_request={
        'name': 'send_email',
        'args': {'to': 'test@x.com', 'subject': 'Test', 'body': 'Hello'},
        'description': 'Send test email',
    },
    review_config={
        'allowed_decisions': ['approve', 'edit', 'reject'],
        'editable_fields': ['to', 'subject', 'body'],
    },
)
# Simulate what interrupt() receives
interrupt_payload = req.model_dump()
print(f'type: {interrupt_payload[\"type\"]}')
print(f'tool: {interrupt_payload[\"action_request\"][\"name\"]}')
print(f'decisions: {interrupt_payload[\"review_config\"][\"allowed_decisions\"]}')

# Simulate resume with edit decision
from app.schemas.hitl import EditDecision
dec = EditDecision(edited_args={'to': 'new@x.com', 'subject': 'Modified', 'body': 'Changed'})
resume_payload = dec.model_dump()
print(f'decision type: {resume_payload[\"type\"]}')
print(f'edited to: {resume_payload[\"edited_args\"][\"to\"]}')
print('✅ HITL schema round-trip OK')
"
```

- [ ] **Step 2: Verify greeting query still works (no regression)**

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)
docker compose exec emma-agent-service python -c "
import asyncio, httpx
async def test():
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post('http://localhost:8009/emma/query', json={
            'query': 'Hola',
            'tenant_id': '00000000-0000-0000-0000-000000000001',
            'context': {'user_id': 'a060f046-9992-4d1a-87c4-fa5c6f8c066c'},
        }, headers={'X-API-Key': '$API_KEY', 'X-Tenant-ID': '00000000-0000-0000-0000-000000000001'})
        print(f'Status: {r.status_code}')
        data = r.json()
        print(f'Answer: {data.get(\"answer\", \"\")[:100]}')
        print('✅ Greeting works')
asyncio.run(test())
"
```

- [ ] **Step 3: Commit (if any fixes needed)**

---

## Chunk 2: Frontend — Types + HITLReviewCard Component

### Task 5: Add TypeScript types for HITL protocol

**Files:**
- Modify: `frontend/apps/on-premise/src/lib/types/emma.ts`

- [ ] **Step 1: Read the current types file**

Read `frontend/apps/on-premise/src/lib/types/emma.ts` to find where `ClarificationData` and `ClarificationOption` are defined (around line 46).

- [ ] **Step 2: Add new HITL types after ClarificationData**

```typescript
// ── HITL Protocol Types (Phase 1) ──

export interface ActionRequest {
  name: string
  args: Record<string, unknown>
  description?: string
}

export interface ReviewConfig {
  allowed_decisions: ('approve' | 'edit' | 'reject')[]
  editable_fields?: string[]
}

export interface HITLReviewRequest {
  type: 'hitl_review'
  action_request: ActionRequest
  review_config: ReviewConfig
}

export interface HITLClarificationRequest {
  type: 'clarification'
  question: string
  options: Array<{ label: string; value: string }>
}

export interface HITLConfirmationRequest {
  type: 'confirmation'
  question: string
  options: Array<{ label: string; value: string }>
}

export type InterruptValue =
  | HITLReviewRequest
  | HITLClarificationRequest
  | HITLConfirmationRequest

export type HITLDecision =
  | { type: 'approve' }
  | { type: 'edit'; edited_args: Record<string, unknown> }
  | { type: 'reject'; message?: string }
```

- [ ] **Step 3: Add `hitl_review` to EmmaStreamEvent types and EmmaMessage.metadata**

In the same file:
1. Find the SSE event type definition and add `hitl_review` as a valid event name.
2. Find the `EmmaMessage.metadata` interface (around line 306-337) and add:
```typescript
hitl_review?: HITLReviewRequest
```
This is needed because Task 7 stores `hitl_review` data in message metadata.

- [ ] **Step 4: Commit**

```bash
git add frontend/apps/on-premise/src/lib/types/emma.ts
git commit -m "feat(hitl): add TypeScript types for HITL protocol — InterruptValue, HITLDecision"
```

---

### Task 6: Create HITLReviewCard component

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/HITLReviewCard.tsx`

- [ ] **Step 1: Read EmmaClarificationUI.tsx for patterns**

Read `frontend/packages/shared/src/emma/EmmaClarificationUI.tsx` to understand the existing UI patterns (Card, Button, styling, icons). Follow the same Tailwind patterns.

- [ ] **Step 2: Create the HITLReviewCard component**

```typescript
'use client'

import React, { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Shield, Send, Pencil, X, RotateCcw } from 'lucide-react'
import type { HITLReviewRequest, HITLDecision } from '@/lib/types/emma'

interface HITLReviewCardProps {
  request: HITLReviewRequest
  isLoading?: boolean
  onSubmit: (decision: HITLDecision) => void
}

type Mode = 'view' | 'edit' | 'reject'

const TOOL_ICONS: Record<string, React.ReactNode> = {
  send_email: <Send className="h-5 w-5" />,
  forge_document: <Shield className="h-5 w-5" />,
  document_generator: <Shield className="h-5 w-5" />,
}

function prettifyKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

export function HITLReviewCard({ request, isLoading, onSubmit }: HITLReviewCardProps) {
  const { action_request, review_config } = request
  const { allowed_decisions, editable_fields } = review_config

  const [mode, setMode] = useState<Mode>('view')
  const [editedArgs, setEditedArgs] = useState<Record<string, unknown>>({ ...action_request.args })
  const [rejectMessage, setRejectMessage] = useState('')

  const canApprove = allowed_decisions.includes('approve')
  const canEdit = allowed_decisions.includes('edit')
  const canReject = allowed_decisions.includes('reject')

  const isEditable = (key: string) =>
    editable_fields ? editable_fields.includes(key) : true

  function handleReset() {
    setEditedArgs({ ...action_request.args })
    setMode('view')
  }

  function handleApprove() {
    onSubmit({ type: 'approve' })
  }

  function handleSubmitEdit() {
    onSubmit({ type: 'edit', edited_args: editedArgs })
  }

  function handleSubmitReject() {
    onSubmit({ type: 'reject', message: rejectMessage || undefined })
  }

  const icon = TOOL_ICONS[action_request.name] || <Shield className="h-5 w-5" />

  const borderColor =
    mode === 'edit'
      ? 'border-amber-400'
      : mode === 'reject'
        ? 'border-red-400'
        : 'border-indigo-400'

  return (
    <Card className={`border-2 ${borderColor} bg-white dark:bg-gray-900`}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-indigo-600 dark:text-indigo-400">{icon}</span>
            <CardTitle className="text-base">{action_request.name}</CardTitle>
            {mode === 'edit' && (
              <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                Editando
              </span>
            )}
          </div>
          <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600 dark:bg-indigo-900/30 dark:text-indigo-300">
            Requiere aprobación
          </span>
        </div>
        {action_request.description && (
          <p className="text-sm text-muted-foreground italic">{action_request.description}</p>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Args display / edit */}
        {Object.entries(action_request.args).map(([key, value]) => (
          <div key={key}>
            <label className="mb-1 block text-xs font-semibold text-muted-foreground">
              {prettifyKey(key)}
            </label>
            {mode === 'edit' && isEditable(key) ? (
              <Textarea
                value={String(editedArgs[key] ?? '')}
                onChange={(e) =>
                  setEditedArgs((prev) => ({ ...prev, [key]: e.target.value }))
                }
                className="border-2 border-amber-300 bg-amber-50 dark:border-amber-700 dark:bg-amber-950/30"
                rows={String(value).length > 80 ? 4 : 2}
                disabled={isLoading}
              />
            ) : (
              <div className="rounded-lg border bg-muted/50 px-3 py-2 text-sm">
                {String(value ?? '')}
              </div>
            )}
          </div>
        ))}

        {/* Reject feedback */}
        {mode === 'reject' && (
          <div className="rounded-lg border-2 border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30">
            <label className="mb-1 block text-xs font-semibold text-red-700 dark:text-red-300">
              Motivo del rechazo (opcional)
            </label>
            <Textarea
              value={rejectMessage}
              onChange={(e) => setRejectMessage(e.target.value)}
              placeholder="Indica al agente por qué rechazas esta acción..."
              rows={3}
              disabled={isLoading}
              className="border-red-200 dark:border-red-800"
            />
            <p className="mt-2 text-xs text-green-700 dark:text-green-400">
              💡 El agente recibirá tu feedback y podrá ajustar su siguiente acción.
            </p>
          </div>
        )}

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2 pt-1">
          {mode === 'view' && (
            <>
              {canApprove && (
                <Button
                  onClick={handleApprove}
                  disabled={isLoading}
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  ✅ Aprobar
                </Button>
              )}
              {canEdit && (
                <Button
                  onClick={() => setMode('edit')}
                  disabled={isLoading}
                  variant="outline"
                  className="border-amber-400 text-amber-700 hover:bg-amber-50 dark:text-amber-300"
                >
                  <Pencil className="mr-1 h-4 w-4" />
                  Editar
                </Button>
              )}
              {canReject && (
                <Button
                  onClick={() => setMode('reject')}
                  disabled={isLoading}
                  variant="outline"
                  className="border-red-400 text-red-700 hover:bg-red-50 dark:text-red-300"
                >
                  Rechazar
                </Button>
              )}
            </>
          )}

          {mode === 'edit' && (
            <>
              <Button
                onClick={handleSubmitEdit}
                disabled={isLoading}
                className="bg-amber-500 hover:bg-amber-600 text-white"
              >
                <Send className="mr-1 h-4 w-4" />
                Enviar editado
              </Button>
              <Button onClick={handleReset} disabled={isLoading} variant="ghost" size="sm">
                <RotateCcw className="mr-1 h-4 w-4" />
                Reset
              </Button>
            </>
          )}

          {mode === 'reject' && (
            <>
              <Button
                onClick={handleSubmitReject}
                disabled={isLoading}
                variant="destructive"
              >
                <X className="mr-1 h-4 w-4" />
                Confirmar rechazo
              </Button>
              <Button onClick={() => setMode('view')} disabled={isLoading} variant="ghost" size="sm">
                Cancelar
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/HITLReviewCard.tsx
git commit -m "feat(hitl): add HITLReviewCard component — Approve/Edit/Reject with editable fields"
```

---

## Chunk 3: Frontend — SSE Integration + Resume Flow

### Task 7: Handle hitl_review SSE event in EmmaChat

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` (around line 652)

- [ ] **Step 1: Read the current clarification event handler**

Read `EmmaChat.tsx` lines 652-693 to understand how `clarification` events are currently handled (converting progress message → clarification message).

- [ ] **Step 2: Add hitl_review event handling**

After the existing `clarification` event handler (around line 693), add a new block for `hitl_review`:

```typescript
// Handle HITL review event (Approve/Edit/Reject for tool calls)
if (event.event === 'hitl_review') {
  streamCompleted = true
  const hitlData = data as HITLReviewRequest

  // Store pending review for resume
  pendingClarificationRef.current = {
    threadId: currentThreadId,
    progressMessageId: progressMessageId,
  }

  updateMessages((prev) =>
    prev.map((msg) =>
      msg.id === progressMessageId
        ? {
            ...msg,
            type: 'clarification' as const,
            content: hitlData.action_request.description || hitlData.action_request.name,
            isStreaming: false,
            metadata: {
              ...msg.metadata,
              isStreaming: false,
              slmIsThinking: false,
              hitl_review: hitlData,
            },
          }
        : msg
    )
  )
  continue
}
```

- [ ] **Step 3: Import the HITLReviewRequest type**

Add to the imports at the top of EmmaChat.tsx:

```typescript
import type { HITLReviewRequest, HITLDecision } from '@/lib/types/emma'
```

- [ ] **Step 4: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(hitl): handle hitl_review SSE event in EmmaChat"
```

---

### Task 8: Render HITLReviewCard in message list

**Files:**
- Modify: `frontend/packages/shared/src/emma/EmmaRenderChat.tsx` (line ~254, where EmmaClarificationUI is rendered)
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` (pass callback prop)

**IMPORTANT**: `EmmaRenderChat.tsx` is in the **shared** package. `HITLReviewCard.tsx` is in the **on-premise** app. The shared package cannot import from on-premise. Solution: use a **render callback prop** so the on-premise wrapper passes the card renderer into the shared component.

- [ ] **Step 1: Read EmmaRenderChat.tsx message rendering**

Read `frontend/packages/shared/src/emma/EmmaRenderChat.tsx` to find where `EmmaClarificationUI` is rendered (around line 254). Understand the props interface.

- [ ] **Step 2: Add `renderHITLReview` optional prop to EmmaRenderChat**

In `EmmaRenderChat.tsx`, add a new optional prop to the component's props interface:

```typescript
renderHITLReview?: (request: any, messageId: string) => React.ReactNode
```

Then in the message rendering section, after the clarification check:

```typescript
{msg.metadata?.hitl_review && renderHITLReview && (
  renderHITLReview(msg.metadata.hitl_review, msg.id)
)}
```

- [ ] **Step 3: Pass HITLReviewCard from on-premise EmmaChat wrapper**

In `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx`, where `EmmaRenderChat` is used, pass the render callback:

```typescript
import { HITLReviewCard } from './HITLReviewCard'

<EmmaRenderChat
  // ... existing props
  renderHITLReview={(request, messageId) => (
    <HITLReviewCard
      request={request}
      isLoading={isResuming}
      onSubmit={(decision) => handleHITLDecision(messageId, decision)}
    />
  )}
/>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/packages/shared/src/emma/EmmaRenderChat.tsx frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(hitl): render HITLReviewCard via callback prop in message list"
```

---

### Task 9: Extract shared resume stream processing

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` (extract helper from handleClarificationResume)

- [ ] **Step 1: Extract processResumeStream helper**

Read `EmmaChat.tsx` lines 1583-1700 (`handleClarificationResume`). The SSE event processing loop (token, slm_thinking, complete, error) is ~120 lines that will be reused by `handleHITLDecision`. Extract it as a standalone async function:

```typescript
async function processResumeStream(
  generator: AsyncGenerator<EmmaStreamEvent, void, unknown>,
  progressMessageId: string,
  updateMessages: (updater: (prev: EmmaMessage[]) => EmmaMessage[], force?: boolean) => void,
): Promise<void> {
  let streamedAnswer = ''
  let slmThinkingSteps: SLMThinkingStep[] = []
  let streamCompleted = false

  for await (const event of generator) {
    const data = event.data || {}
    // ... token, slm_thinking, complete, error handling
    // (copy from handleClarificationResume lines 1583-1640+)
  }
}
```

- [ ] **Step 2: Refactor handleClarificationResume to use processResumeStream**

Replace the inline event loop in `handleClarificationResume` with a call to `processResumeStream()`. Verify existing clarification flow still works.

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "refactor(hitl): extract processResumeStream helper from handleClarificationResume"
```

---

### Task 10: Update resume service + add handleHITLDecision

**Files:**
- Modify: `frontend/apps/on-premise/src/lib/services/emma.service.ts` (lines 477-498)
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx` (new handler)

- [ ] **Step 1: Update resumeQueryStreamGenerator to accept any resume value**

In `emma.service.ts`, change the `resumeValue` parameter type from `string` to `string | Record<string, unknown>`:

```typescript
async function* resumeQueryStreamGenerator(
  threadId: string,
  resumeValue: string | Record<string, unknown>,  // ← Accept dict for HITL decisions
  tenantId: string,
  userId?: string,
): AsyncGenerator<EmmaStreamEvent, void, unknown> {
  // ... rest stays the same, JSON.stringify handles both types
```

In the fetch body, `resume_value` already uses `JSON.stringify` so dicts serialize correctly.

- [ ] **Step 2: Add handleHITLDecision handler in EmmaChat**

Add a new handler function alongside the existing `handleClarificationResume`. Uses `processResumeStream` from Task 9. No `useCallback` (per CLAUDE.md patterns):

```typescript
async function handleHITLDecision(messageId: string, decision: HITLDecision) {
  const pending = pendingClarificationRef.current
  if (!pending || !user?.id || !tenantId) return

  pendingClarificationRef.current = null
  const { threadId } = pending

  // Update the HITL card to show the decision was made
  const decisionLabel =
    decision.type === 'approve' ? 'Aprobado'
      : decision.type === 'edit' ? 'Editado y enviado'
      : `Rechazado${decision.message ? `: ${decision.message}` : ''}`

  updateMessages((prev) =>
    prev.map((msg) =>
      msg.id === messageId
        ? { ...msg, type: 'info' as const, content: decisionLabel, metadata: { ...msg.metadata, hitl_review: undefined } }
        : msg
    )
  )

  // Create resume progress message
  const resumeProgressId = (Date.now() + 1).toString()
  updateMessages((prev) => [
    ...prev,
    { id: resumeProgressId, type: 'progress' as const, content: 'Procesando tu decisión...', timestamp: new Date(), metadata: { progress: 0, streaming_text: '' } },
  ])

  // Resume the graph with the decision object — reuse shared helper
  try {
    const generator = resumeQueryStreamGenerator(threadId, decision, tenantId, user.id)
    await processResumeStream(generator, resumeProgressId, updateMessages)
  } catch (error) {
    console.error('HITL resume failed:', error)
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/lib/services/emma.service.ts frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(hitl): update resume flow to send HITLDecision object + handleHITLDecision handler"
```

---

### Task 11: E2E verification

- [ ] **Step 1: Test greeting query (no regression)**

```bash
# Via browser: open https://localhost, send "Hola" — should get greeting response
```

- [ ] **Step 2: Test clarification (existing behavior preserved)**

```bash
# Ensure REACT_QUERY_CLARIFICATION_ENABLED=true
# Send a short ambiguous query like "facturas"
# Should show clarification UI (EmmaClarificationUI or HITLClarificationCard)
```

- [ ] **Step 3: Test email HITL (new behavior)**

```bash
# Send: "Envía un email a test@example.com con el resumen del último contrato"
# Expected: Agent searches, prepares email, shows HITLReviewCard with:
#   - To: test@example.com (editable)
#   - Subject: ... (editable)
#   - Body: ... (editable)
#   - Buttons: Aprobar | Editar | Rechazar
# Test each button:
#   - Approve: sends email as-is
#   - Edit: change "to" field, submit → sends with modified args
#   - Reject: type feedback → agent receives rejection message
```

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(hitl): E2E fixes for HITL review protocol"
```

---

## Post-Implementation Checklist

- [ ] HITLReviewCard renders for send_email with Approve/Edit/Reject buttons
- [ ] Edit mode makes `to`, `subject`, `body` fields editable
- [ ] Reject sends feedback message to agent via `Command(resume=...)`
- [ ] Existing clarification interrupt still works (no regression)
- [ ] Greeting fast-path still works
- [ ] Resume endpoint accepts both string and dict `resume_value`
- [ ] `hitl_review` SSE event correctly mapped in both `/emma/stream` and `/emma/query/resume/stream`
- [ ] HITLReviewCard follows existing Tailwind patterns and supports dark mode
