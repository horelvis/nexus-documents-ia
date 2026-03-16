# EmmaChat useStream SDK Migration — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace manual SSE parsing in EmmaChat with `@langchain/langgraph-sdk` `useStream` hook, backed by adapter endpoints on emma-agent-service that implement the LangGraph Server protocol subset.

**Architecture:** Backend adapter layer (`/api/threads/{id}/runs/stream`) wraps our existing `stream_react_query()` / `resume_react_query()` and translates SSE events to LangGraph protocol format (`event: values`, `event: metadata`, `event: end`). Frontend replaces ~250 lines of manual SSE parsing with `useStream` hook (~30 lines). Branch switching and regenerate come free from the SDK. Verified Generation subgraph conversion is deferred to a separate sub-spec.

**Tech Stack:** Python (FastAPI, LangGraph `graph.astream()` + `graph.aget_state()` + `graph.aget_state_history()`), TypeScript (Next.js 15, `@langchain/langgraph-sdk/react` `useStream`), SSE

**Spec:** `docs/superpowers/specs/2026-03-15-emmachat-ux-redesign-design.md` (Phase 3 section)

---

## Scope

**In scope:**
- Backend adapter endpoints (6 routes) for LangGraph Server protocol
- Frontend `useStream` hook replacing manual SSE
- Interrupt rendering (HITL review + clarification) via `stream.interrupt`
- Branch switching + regenerate per-message
- Thread history sidebar
- Feature flag `USE_LANGGRAPH_PROTOCOL` for gradual rollout

**Deferred (separate sub-spec):**
- Verified Generation as subgraph (currently uses separate SSE)
- Predictive Analysis as subgraph
- Deletion of old `/emma/stream` endpoint (other consumers exist)

---

## File Structure

### New Files (Backend)
| File | Responsibility |
|------|---------------|
| `emma-agent-service/app/api/langgraph_protocol.py` | FastAPI router: 6 adapter endpoints |
| `emma-agent-service/app/services/langgraph_adapter.py` | SSE format translator: Emma events → LangGraph protocol events |

### New Files (Frontend)
| File | Responsibility |
|------|---------------|
| `on-premise/src/components/emma-chat/EmmaStreamProvider.tsx` | `useStream` context provider wrapping SDK with auth headers |
| `on-premise/src/components/emma-chat/messages/BranchSwitcher.tsx` | `← 2/3 →` navigation between checkpoint branches |
| `on-premise/src/components/emma-chat/messages/CommandBar.tsx` | Regenerate, copy, feedback buttons per AI message |
| `on-premise/src/components/emma-chat/ThreadHistory.tsx` | Sidebar with persistent conversation list |

### Modified Files
| File | Change |
|------|--------|
| `emma-agent-service/app/main.py` | Register `/api` router |
| `on-premise/package.json` | Add `@langchain/langgraph-sdk` dependency |
| `on-premise/src/components/emma-chat/EmmaChat.tsx` | Replace SSE manual with `useStream` hook via provider |
| `on-premise/src/components/emma-chat/EmmaRenderChat.tsx` | Add BranchSwitcher + CommandBar per AI message |

All paths relative to `backend/microservices/` (backend) or `frontend/apps/` (frontend).

---

## Chunk 1: Backend Adapter Endpoints

### Task 1: Create SSE format translator

**Files:**
- Create: `backend/microservices/emma-agent-service/app/services/langgraph_adapter.py`

- [ ] **Step 1: Read current SSE generator**

Read `langgraph/api.py` function `stream_react_query()` (lines 259-533). Understand the event types it yields: `thinking`, `tool_call`, `tool_result`, `reasoning_step`, `complete`, `clarification`, `hitl_review`, `error`.

- [ ] **Step 2: Create the translator**

The translator wraps our event generator and converts to LangGraph protocol SSE format. The `useStream` SDK expects these SSE events:

| LangGraph Event | Data | When |
|----------------|------|------|
| `event: metadata` | `{"run_id": "..."}` | Start of run |
| `event: values` | `{"messages": [...], ...}` | State snapshot after each node |
| `event: updates` | `{"node_name": {...}}` | Node-level output |
| `event: end` | `null` | Stream complete |

Our translator accumulates messages from our events and emits state snapshots:

```python
"""
LangGraph Protocol SSE Adapter.

Translates Emma's internal SSE events into LangGraph Server protocol format
that @langchain/langgraph-sdk useStream can consume.
"""

import json
import uuid
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)


async def translate_to_langgraph_sse(
    emma_event_generator: AsyncGenerator[Dict[str, Any], None],
    thread_id: str,
) -> AsyncGenerator[str, None]:
    """Translate Emma SSE events to LangGraph Server protocol SSE format.

    Emma yields: {"type": str, "data": dict}
    LangGraph expects: "event: {name}\ndata: {json}\n\n"

    The useStream SDK primarily consumes 'values' events (full state snapshots)
    and 'metadata' events (run info). We accumulate messages from our events
    and emit state snapshots.
    """
    run_id = str(uuid.uuid4())

    # Emit metadata event (start of run)
    yield f"event: metadata\ndata: {json.dumps({'run_id': run_id})}\n\n"

    # Accumulated state for values snapshots
    messages: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    current_ai_content = ""

    try:
        async for event in emma_event_generator:
            event_type = event.get("type", "")
            event_data = event.get("data", {})

            if event_type == "started":
                # Initial event — emit first values snapshot
                yield _values_event({"messages": messages})

            elif event_type == "thinking":
                # Emit as updates (node-level output)
                yield _updates_event("react_loop", {
                    "thinking": event_data.get("content", ""),
                })

            elif event_type == "tool_call":
                # Emit as updates
                yield _updates_event("react_loop", {
                    "tool_call": event_data.get("content", ""),
                })

            elif event_type == "tool_result":
                # Emit as updates
                yield _updates_event("react_loop", {
                    "tool_result": event_data.get("content", ""),
                    "source": event_data.get("source", ""),
                })

            elif event_type == "token":
                # Token streaming — accumulate content
                text = event_data.get("text", "")
                current_ai_content += text
                # Emit as values with partial AI message
                ai_msg = {"type": "ai", "content": current_ai_content, "id": f"ai-{run_id}"}
                yield _values_event({"messages": messages + [ai_msg]})

            elif event_type in ("clarification", "hitl_review", "confirmation"):
                # Interrupt — useStream expects this format
                interrupt_data = event_data if isinstance(event_data, dict) else {}
                yield f"event: error\ndata: {json.dumps({'type': 'interrupt', 'value': interrupt_data})}\n\n"

            elif event_type == "complete":
                # Final state snapshot
                answer = event_data.get("answer", current_ai_content)
                sources = event_data.get("sources", [])
                final_ai_msg = {"type": "ai", "content": answer, "id": f"ai-{run_id}"}
                metadata = event_data.get("metadata", {})

                yield _values_event({
                    "messages": messages + [final_ai_msg],
                    "sources": sources,
                    "metadata": metadata,
                })

            elif event_type == "error":
                yield f"event: error\ndata: {json.dumps(event_data)}\n\n"

            else:
                # Pass through as custom event
                yield f"event: custom\ndata: {json.dumps({'type': event_type, 'data': event_data})}\n\n"

    except Exception as e:
        logger.error(f"LangGraph SSE adapter error: {e}")
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    # End of stream
    yield "event: end\ndata: null\n\n"


def _values_event(state: Dict[str, Any]) -> str:
    """Format a 'values' SSE event (full state snapshot)."""
    return f"event: values\ndata: {json.dumps(state)}\n\n"


def _updates_event(node: str, output: Dict[str, Any]) -> str:
    """Format an 'updates' SSE event (node-level output)."""
    return f"event: updates\ndata: {json.dumps({node: output})}\n\n"
```

**IMPORTANT**: The interrupt handling is the trickiest part. The `useStream` SDK detects interrupts from the graph state (via `__interrupt__` field in the checkpoint), NOT from SSE events. We may need to adjust this after the spike test. For now, emit interrupts as a special error event that the frontend can catch.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/services/langgraph_adapter.py
git commit -m "feat(usestream): create LangGraph protocol SSE adapter"
```

---

### Task 2: Create adapter endpoints

**Files:**
- Create: `backend/microservices/emma-agent-service/app/api/langgraph_protocol.py`
- Modify: `backend/microservices/emma-agent-service/app/main.py`

- [ ] **Step 1: Read main.py to understand router registration**

Read `app/main.py` to find how existing routers are registered (e.g., `app.include_router(emma_router, prefix="/emma")`).

- [ ] **Step 2: Create the adapter router**

```python
"""
LangGraph Server Protocol — Adapter Endpoints.

Implements the subset of LangGraph Server API that @langchain/langgraph-sdk
useStream hook requires. Delegates to existing Emma graph execution.

Endpoints:
  GET  /api/info                         → Server metadata
  POST /api/threads                      → Create thread (returns thread_id)
  GET  /api/threads                      → List threads (tenant-filtered)
  GET  /api/threads/{thread_id}          → Get thread details
  GET  /api/threads/{thread_id}/state    → Current graph state
  POST /api/threads/{thread_id}/history  → Checkpoint history
  POST /api/threads/{thread_id}/runs/stream → Execute run with SSE
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.auth import verify_api_key
from app.services.langgraph_adapter import translate_to_langgraph_sse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["langgraph-protocol"])


# ── Request/Response Models ──

class RunInput(BaseModel):
    """Input for creating a run."""
    input: Optional[Dict[str, Any]] = None
    assistant_id: str = "emma-react"
    stream_mode: List[str] = Field(default=["values"])
    command: Optional[Dict[str, Any]] = None  # For resume: {"resume": value}
    interrupt_before: Optional[List[str]] = None
    interrupt_after: Optional[List[str]] = None
    checkpoint: Optional[Dict[str, Any]] = None  # For regenerate


class ThreadCreate(BaseModel):
    """Input for creating a thread."""
    metadata: Optional[Dict[str, Any]] = None


# ── Endpoints ──

@router.get("/info")
async def get_info():
    """Server metadata — useStream checks this on init."""
    return {
        "version": "1.0.0",
        "graphs": {"emma-react": {"graph_id": "emma-react"}},
    }


@router.post("/threads")
async def create_thread(
    body: ThreadCreate = ThreadCreate(),
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Create a new thread."""
    thread_id = str(uuid.uuid4())
    return {
        "thread_id": thread_id,
        "metadata": {**(body.metadata or {}), "tenant_id": x_tenant_id},
        "created_at": None,
    }


@router.get("/threads")
async def list_threads(
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
    limit: int = 20,
    offset: int = 0,
):
    """List threads for tenant. Queries emma_sessions table."""
    # TODO: Query checkpointer or sessions table for thread list
    # For now, return empty — thread history will be implemented incrementally
    return []


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    _: bool = Depends(verify_api_key),
):
    """Get thread metadata."""
    return {"thread_id": thread_id, "metadata": {}, "created_at": None}


@router.get("/threads/{thread_id}/state")
async def get_thread_state(
    thread_id: str,
    _: bool = Depends(verify_api_key),
):
    """Get current graph state from checkpointer."""
    try:
        from app.agents.langgraph.graph import get_react_graph
        graph = await get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        if state and state.values:
            # Convert LangChain messages to SDK format
            messages = []
            for msg in state.values.get("messages", []):
                messages.append({
                    "type": msg.type if hasattr(msg, "type") else "unknown",
                    "content": msg.content if hasattr(msg, "content") else str(msg),
                    "id": msg.id if hasattr(msg, "id") else None,
                })
            return {
                "values": {"messages": messages},
                "next": state.next if hasattr(state, "next") else [],
                "checkpoint": {
                    "id": state.config.get("configurable", {}).get("checkpoint_id") if state.config else None,
                },
            }
    except Exception as e:
        logger.warning(f"Failed to get state for thread {thread_id}: {e}")

    return {"values": {"messages": []}, "next": [], "checkpoint": None}


@router.post("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    _: bool = Depends(verify_api_key),
    limit: int = 10,
):
    """Get checkpoint history for branch switching."""
    try:
        from app.agents.langgraph.graph import get_react_graph
        graph = await get_react_graph()
        config = {"configurable": {"thread_id": thread_id}}
        history = []
        async for state in graph.aget_state_history(config):
            checkpoint_info = {
                "checkpoint": {
                    "id": state.config.get("configurable", {}).get("checkpoint_id") if state.config else None,
                },
                "parent_checkpoint": {
                    "id": state.parent_config.get("configurable", {}).get("checkpoint_id") if state.parent_config else None,
                } if state.parent_config else None,
                "values": {
                    "messages": [
                        {"type": m.type, "content": m.content[:100], "id": m.id}
                        for m in state.values.get("messages", [])[:5]
                    ],
                },
            }
            history.append(checkpoint_info)
            if len(history) >= limit:
                break
        return history
    except Exception as e:
        logger.warning(f"Failed to get history for thread {thread_id}: {e}")
        return []


@router.post("/threads/{thread_id}/runs/stream")
async def create_run_stream(
    thread_id: str,
    body: RunInput,
    request: Request,
    _: bool = Depends(verify_api_key),
    x_tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    """Execute a graph run with SSE streaming.

    This is the main endpoint useStream calls. It delegates to our existing
    stream_react_query() or resume_react_query() and translates the SSE format.
    """
    from app.agents.langgraph.api import stream_react_query, resume_react_query

    # Determine if this is a resume (Command) or new query
    if body.command and "resume" in body.command:
        # Resume from interrupt
        emma_generator = resume_react_query(
            thread_id=thread_id,
            resume_value=body.command["resume"],
            tenant_id=x_tenant_id,
        )
    elif body.checkpoint:
        # Regenerate from checkpoint — re-run from a specific state
        # For now, treat as new run (full regenerate support needs checkpoint_id in config)
        query = ""
        if body.input and "messages" in body.input:
            msgs = body.input["messages"]
            if msgs:
                last_human = next((m for m in reversed(msgs) if m.get("type") == "human"), None)
                query = last_human.get("content", "") if last_human else ""

        emma_generator = stream_react_query(
            query=query,
            tenant_id=x_tenant_id,
            thread_id=thread_id,
            context=body.input.get("context") if body.input else None,
        )
    else:
        # New query
        query = ""
        user_id = None
        context = {}

        if body.input:
            messages = body.input.get("messages", [])
            if messages:
                last_msg = messages[-1] if messages else {}
                content = last_msg.get("content", "")
                # Handle both string and list content
                if isinstance(content, list):
                    query = next((c.get("text", "") for c in content if c.get("type") == "text"), "")
                else:
                    query = str(content)
            context = body.input.get("context", {})
            user_id = context.get("user_id")

        emma_generator = stream_react_query(
            query=query,
            tenant_id=x_tenant_id,
            user_id=user_id,
            thread_id=thread_id,
            context=context,
        )

    # Translate and stream
    langgraph_sse = translate_to_langgraph_sse(emma_generator, thread_id)

    return StreamingResponse(
        langgraph_sse,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

- [ ] **Step 3: Register router in main.py**

Find where routers are included and add:
```python
from app.api.langgraph_protocol import router as langgraph_router
app.include_router(langgraph_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/emma-agent-service/app/api/langgraph_protocol.py backend/microservices/emma-agent-service/app/main.py
git commit -m "feat(usestream): add LangGraph protocol adapter endpoints (/api/threads, /api/info, /api/runs/stream)"
```

---

### Task 3: Spike test — validate useStream connects

- [ ] **Step 1: Restart emma-agent-service**

```bash
cd backend/docker && docker compose restart emma-agent-service
```

- [ ] **Step 2: Test /api/info endpoint**

```bash
docker compose exec emma-agent-service python -c "
import asyncio, httpx
async def test():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get('http://localhost:8009/api/info')
        print(f'Status: {r.status_code}')
        print(f'Body: {r.json()}')
asyncio.run(test())
"
```

Expected: `{"version": "1.0.0", "graphs": {"emma-react": {...}}}`

- [ ] **Step 3: Test /api/threads/{id}/runs/stream endpoint**

```bash
API_KEY=$(grep MICROSERVICES_API_KEY .env | cut -d= -f2)
docker compose exec emma-agent-service python -c "
import asyncio, httpx, uuid
async def test():
    tid = str(uuid.uuid4())
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream('POST', f'http://localhost:8009/api/threads/{tid}/runs/stream',
            json={'input': {'messages': [{'type': 'human', 'content': 'Hola'}]}, 'assistant_id': 'emma-react'},
            headers={'X-API-Key': '$API_KEY', 'X-Tenant-ID': '00000000-0000-0000-0000-000000000001'},
        ) as response:
            print(f'Status: {response.status_code}')
            async for line in response.aiter_lines():
                if line.startswith('event:'):
                    print(f'  {line}')
                elif line.startswith('data:'):
                    print(f'  {line[:120]}')
                if 'event: end' in line:
                    break
asyncio.run(test())
"
```

Expected: `event: metadata` → `event: values` (with messages) → `event: end`

- [ ] **Step 4: Commit spike results (or fix issues)**

---

## Chunk 2: Frontend — useStream Integration

### Task 4: Install SDK dependency

**Files:**
- Modify: `frontend/apps/on-premise/package.json`

- [ ] **Step 1: Add dependency**

```bash
cd frontend && pnpm add @langchain/langgraph-sdk@^1.0.0 @langchain/core@^1.1.28 --filter on-premise
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/package.json frontend/pnpm-lock.yaml
git commit -m "feat(usestream): add @langchain/langgraph-sdk dependency"
```

---

### Task 5: Create EmmaStreamProvider

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx`

- [ ] **Step 1: Create the provider**

Wraps `useStream` from `@langchain/langgraph-sdk/react` with our auth headers and config:

```typescript
'use client'

import React, { createContext, useContext, ReactNode } from 'react'
import { useStream } from '@langchain/langgraph-sdk/react'
import type { Message } from '@langchain/langgraph-sdk'

type StateType = { messages: Message[] }

const useTypedStream = useStream<StateType>

type StreamContextType = ReturnType<typeof useTypedStream>
const StreamContext = createContext<StreamContextType | undefined>(undefined)

interface EmmaStreamProviderProps {
  children: ReactNode
  apiUrl: string         // "/api" or absolute URL
  assistantId?: string   // "emma-react"
  threadId: string | null
  onThreadId: (id: string) => void
  apiKey?: string
  tenantId: string
}

export function EmmaStreamProvider({
  children,
  apiUrl,
  assistantId = 'emma-react',
  threadId,
  onThreadId,
  apiKey,
  tenantId,
}: EmmaStreamProviderProps) {
  const stream = useTypedStream({
    apiUrl,
    assistantId,
    threadId,
    apiKey: apiKey || undefined,
    defaultHeaders: {
      'X-Tenant-ID': tenantId,
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
    },
    onThreadId,
    fetchStateHistory: true,
    streamMode: ['values'],
    streamResumable: true,
  })

  return (
    <StreamContext.Provider value={stream}>
      {children}
    </StreamContext.Provider>
  )
}

export function useEmmaStream(): StreamContextType {
  const context = useContext(StreamContext)
  if (!context) {
    throw new Error('useEmmaStream must be used within EmmaStreamProvider')
  }
  return context
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaStreamProvider.tsx
git commit -m "feat(usestream): create EmmaStreamProvider wrapping useStream SDK"
```

---

### Task 6: Create BranchSwitcher + CommandBar

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/messages/BranchSwitcher.tsx`
- Create: `frontend/apps/on-premise/src/components/emma-chat/messages/CommandBar.tsx`

- [ ] **Step 1: Read agent-chat-ui's BranchSwitcher**

Read `/tmp/agent-chat-ui/src/components/thread/messages/shared.tsx` for the BranchSwitcher pattern.

- [ ] **Step 2: Create BranchSwitcher**

Simple `← N/M →` navigation. Receives `branch`, `branchOptions`, `onSelect` props.

```typescript
'use client'

import { Button } from '@/components/ui/button'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface BranchSwitcherProps {
  branch?: number
  branchOptions?: number[]
  onSelect: (branch: number) => void
  isLoading?: boolean
}

export function BranchSwitcher({ branch, branchOptions, onSelect, isLoading }: BranchSwitcherProps) {
  if (!branchOptions || branchOptions.length <= 1) return null
  const currentIndex = branch != null ? branchOptions.indexOf(branch) : -1
  if (currentIndex < 0) return null

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost" size="icon" className="h-6 w-6"
        disabled={isLoading || currentIndex === 0}
        onClick={() => onSelect(branchOptions[currentIndex - 1])}
      >
        <ChevronLeft className="h-3.5 w-3.5" />
      </Button>
      <span className="text-xs text-muted-foreground">
        {currentIndex + 1}/{branchOptions.length}
      </span>
      <Button
        variant="ghost" size="icon" className="h-6 w-6"
        disabled={isLoading || currentIndex === branchOptions.length - 1}
        onClick={() => onSelect(branchOptions[currentIndex + 1])}
      >
        <ChevronRight className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}
```

- [ ] **Step 3: Create CommandBar**

Regenerate + Copy buttons. Visible on hover.

```typescript
'use client'

import { Button } from '@/components/ui/button'
import { RotateCcw, Copy, Check } from 'lucide-react'
import { useState } from 'react'

interface CommandBarProps {
  content: string
  isLoading?: boolean
  onRegenerate?: () => void
}

export function CommandBar({ content, isLoading, onRegenerate }: CommandBarProps) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
      {onRegenerate && (
        <Button variant="ghost" size="icon" className="h-6 w-6" disabled={isLoading} onClick={onRegenerate}>
          <RotateCcw className="h-3.5 w-3.5" />
        </Button>
      )}
      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={handleCopy}>
        {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/messages/
git commit -m "feat(usestream): add BranchSwitcher and CommandBar per-message components"
```

---

### Task 7: Create ThreadHistory sidebar

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/ThreadHistory.tsx`

- [ ] **Step 1: Create the sidebar**

A collapsible sidebar showing conversation threads. Gets thread list from `/api/threads` endpoint.

```typescript
'use client'

import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { SquarePen, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ThreadItem {
  thread_id: string
  metadata?: Record<string, any>
  created_at?: string
}

interface ThreadHistoryProps {
  currentThreadId: string | null
  onSelectThread: (threadId: string | null) => void
  apiUrl: string
  tenantId: string
  apiKey?: string
}

export function ThreadHistory({
  currentThreadId,
  onSelectThread,
  apiUrl,
  tenantId,
  apiKey,
}: ThreadHistoryProps) {
  const [threads, setThreads] = useState<ThreadItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  async function loadThreads() {
    setIsLoading(true)
    try {
      const headers: Record<string, string> = {
        'X-Tenant-ID': tenantId,
        ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      }
      const response = await fetch(`${apiUrl}/threads?limit=20`, { headers })
      if (response.ok) {
        const data = await response.json()
        setThreads(data)
      }
    } catch (err) {
      console.error('Failed to load threads:', err)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadThreads()
  }, [tenantId])

  return (
    <div className="flex h-full w-64 flex-col border-r bg-muted/30">
      <div className="flex items-center justify-between border-b p-3">
        <span className="text-sm font-semibold">Conversaciones</span>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onSelectThread(null)}>
          <SquarePen className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {threads.map((thread) => (
          <button
            key={thread.thread_id}
            onClick={() => onSelectThread(thread.thread_id)}
            className={cn(
              'w-full rounded-lg px-3 py-2 text-left text-sm transition-colors',
              thread.thread_id === currentThreadId
                ? 'bg-indigo-50 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-300'
                : 'hover:bg-muted',
            )}
          >
            <div className="flex items-center gap-2">
              <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
              <span className="truncate">
                {thread.metadata?.title || thread.thread_id.slice(0, 8)}
              </span>
            </div>
            {thread.created_at && (
              <div className="mt-0.5 text-xs text-muted-foreground">
                {new Date(thread.created_at).toLocaleDateString()}
              </div>
            )}
          </button>
        ))}
        {threads.length === 0 && !isLoading && (
          <p className="py-4 text-center text-xs text-muted-foreground">No hay conversaciones</p>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/ThreadHistory.tsx
git commit -m "feat(usestream): add ThreadHistory sidebar component"
```

---

## Chunk 3: Frontend — EmmaChat Migration + Wiring

### Task 8: Migrate EmmaChat to useStream (feature-flagged)

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx`

This is the most complex task. The migration must be **feature-flagged** so we can roll back.

- [ ] **Step 1: Add feature flag**

At the top of EmmaChat.tsx:
```typescript
const USE_LANGGRAPH_PROTOCOL = process.env.NEXT_PUBLIC_USE_LANGGRAPH_PROTOCOL === 'true'
```

- [ ] **Step 2: Create useStream-based chat handler**

When the flag is on, the component uses `useEmmaStream()` from the provider instead of manual SSE. Create a new function `handleSendQueryViaStream` that calls `stream.submit()`:

```typescript
if (USE_LANGGRAPH_PROTOCOL) {
  // useStream path
  function handleSendQueryViaStream(query: string) {
    stream.submit(
      { messages: [{ type: 'human', content: query }] },
      { streamMode: ['values'], streamResumable: true },
    )
  }
  // Messages come from stream.messages
  // Interrupts come from stream.interrupt
  // Loading from stream.isLoading
}
```

- [ ] **Step 3: Wire interrupt rendering**

When `stream.interrupt` is set, check the interrupt value's type and render the appropriate card:

```typescript
const interrupt = stream.interrupt
if (interrupt?.value?.type === 'hitl_review') {
  // Render HITLReviewCard
} else if (interrupt?.value?.type === 'clarification') {
  // Render EmmaClarificationUI
}
```

Resume via: `stream.submit({}, { command: { resume: decision } })`

- [ ] **Step 4: Wire BranchSwitcher + CommandBar in EmmaRenderChat**

Pass branch metadata and handlers to the message rendering:

```typescript
<EmmaRenderChat
  // existing props...
  renderBranchSwitcher={USE_LANGGRAPH_PROTOCOL ? (msg) => {
    const meta = stream.getMessagesMetadata(msg)
    return <BranchSwitcher
      branch={meta?.branch}
      branchOptions={meta?.branchOptions}
      onSelect={(b) => stream.setBranch(b)}
    />
  } : undefined}
  renderCommandBar={USE_LANGGRAPH_PROTOCOL ? (msg, content) => (
    <CommandBar
      content={content}
      isLoading={stream.isLoading}
      onRegenerate={() => {
        const meta = stream.getMessagesMetadata(msg)
        stream.submit(undefined, { checkpoint: meta?.firstSeenState?.parent_checkpoint })
      }}
    />
  ) : undefined}
/>
```

- [ ] **Step 5: Add callback props to EmmaRenderChat**

In `EmmaRenderChat.tsx`, add the optional callback props (same pattern as `renderHITLReview`):

```typescript
renderBranchSwitcher?: (msg: any) => React.ReactNode
renderCommandBar?: (msg: any, content: string) => React.ReactNode
```

Render them after AI messages (inside the `group` container for hover visibility).

- [ ] **Step 6: Wrap EmmaChat with EmmaStreamProvider (conditional)**

In the parent page or in EmmaChat itself:

```typescript
if (USE_LANGGRAPH_PROTOCOL) {
  return (
    <EmmaStreamProvider
      apiUrl="/api"
      threadId={threadId}
      onThreadId={setThreadId}
      tenantId={tenantId}
      apiKey={apiKey}
    >
      <EmmaChatInner ... />
    </EmmaStreamProvider>
  )
} else {
  return <EmmaChatInner ... />  // existing manual SSE path
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx
git commit -m "feat(usestream): migrate EmmaChat to useStream SDK (feature-flagged)"
```

---

### Task 9: Add ThreadHistory to layout

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx`

- [ ] **Step 1: Add thread history sidebar**

When `USE_LANGGRAPH_PROTOCOL` is on, render ThreadHistory as a collapsible left sidebar:

```typescript
<div className="flex h-full">
  {USE_LANGGRAPH_PROTOCOL && showHistory && (
    <ThreadHistory
      currentThreadId={threadId}
      onSelectThread={setThreadId}
      apiUrl="/api"
      tenantId={tenantId}
      apiKey={apiKey}
    />
  )}
  {/* Chat + Artifacts panel */}
</div>
```

Add a toggle button in the header.

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(usestream): add ThreadHistory sidebar to EmmaChat layout"
```

---

### Task 10: E2E verification

- [ ] **Step 1: TypeScript compile check**

```bash
cd frontend && npx tsc --noEmit --project apps/on-premise/tsconfig.json && npx tsc --noEmit --project packages/shared/tsconfig.json
```

- [ ] **Step 2: Test with flag OFF (no regression)**

Ensure `NEXT_PUBLIC_USE_LANGGRAPH_PROTOCOL` is not set. Send "Hola" — should work exactly as before via manual SSE.

- [ ] **Step 3: Test with flag ON**

Set `NEXT_PUBLIC_USE_LANGGRAPH_PROTOCOL=true`. Send "Hola":
- Should hit `/api/threads/{id}/runs/stream`
- Should receive SSE events in LangGraph format
- Should render the greeting response
- Branch switcher visible on hover (even if only 1 branch)

- [ ] **Step 4: Test interrupt (with flag ON)**

Trigger an email send. The HITL review interrupt should:
- Come through `stream.interrupt`
- Render HITLReviewCard
- Resume via `stream.submit({}, { command: { resume: decision } })`

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "fix(usestream): E2E fixes for useStream migration"
```

---

## Post-Implementation Checklist

- [ ] `/api/info` returns server metadata
- [ ] `/api/threads/{id}/runs/stream` streams SSE in LangGraph format
- [ ] `useStream` connects and renders messages
- [ ] Feature flag `NEXT_PUBLIC_USE_LANGGRAPH_PROTOCOL=true` enables new path
- [ ] Flag OFF: existing manual SSE works (no regression)
- [ ] Interrupt → HITLReviewCard works via `stream.interrupt`
- [ ] BranchSwitcher renders per AI message
- [ ] CommandBar (regenerate + copy) renders on hover
- [ ] ThreadHistory sidebar shows conversations
- [ ] TypeScript compiles (both packages, zero errors)
- [ ] Verified Generation still works via existing SSE (not migrated yet)
- [ ] Artifacts panel works with both old and new SSE paths
