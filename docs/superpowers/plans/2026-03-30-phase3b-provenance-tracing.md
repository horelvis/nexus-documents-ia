# Phase 3b: Document Provenance Tracing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable graph_rag to trace scored edges back to source document chunks and expose the evidence to the user via inline LLM context + frontend panel.

**Architecture:** New KTS endpoint resolves edge source_chunk URIs → document chunks via weaviate-service. graph_rag calls this after scoring, appends evidence to context text and ToolResult.data. react_loop emits source_evidence reasoning step. Frontend renders SourceEvidence component in MessageBubble.

**Tech Stack:** Python (FastAPI, httpx, FalkorDB Cypher), TypeScript (React, Next.js, Tailwind)

**Spec:** `docs/superpowers/specs/2026-03-30-trustgraph-phase3b-provenance-tracing-design.md`

**Base paths:**
- KTS: `backend/microservices/knowledge-tree-service`
- Emma: `backend/microservices/emma-agent-service`
- Frontend: `frontend/src`

---

## File Map

| File | Service | Action | Responsibility |
|------|---------|--------|---------------|
| `KTS/app/services/triple_query.py` | KTS | Modify | `trace_sources()` method |
| `KTS/app/api/triples.py` | KTS | Modify | `POST /triples/trace-sources` endpoint |
| `Emma/app/clients/knowledge_tree_client.py` | Emma | Modify | `trace_sources()` client method |
| `Emma/app/agents/langgraph/tools/graph_rag.py` | Emma | Modify | Resolve sources + enrich context + ToolResult.data |
| `Emma/app/agents/langgraph/nodes/react_loop.py` | Emma | Modify | Emit source_evidence reasoning step |
| `frontend/src/components/emma-chat/SourceEvidence.tsx` | Frontend | Create | Collapsible source evidence panel |
| `frontend/src/components/emma-chat/messages/MessageBubble.tsx` | Frontend | Modify | Render SourceEvidence |
| `frontend/src/components/emma-chat/hooks/useMessageConverter.ts` | Frontend | Modify | Extract source_evidence from reasoning_steps |
| `frontend/src/components/emma-chat/types.ts` | Frontend | Modify | Add SourceEvidenceItem type |

---

### Task 1: KTS trace_sources method + endpoint

**Files:**
- Modify: `KTS/app/services/triple_query.py`
- Modify: `KTS/app/api/triples.py`

- [ ] **Step 1: Add trace_sources to TripleQuery**

In `triple_query.py`, add a new method to the `TripleQuery` class:

```python
    async def trace_sources(
        self,
        edges: List[Dict[str, str]],
        user: str,
        collection: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Trace edges back to their source chunks.

        For each edge (subject_uri, predicate_uri, object_uri), queries
        the :Rel for source_chunk and confidence, then parses the
        source_chunk URI to extract document_id and chunk_offset.

        Returns list of dicts with: subject_uri, predicate_uri, object_uri,
        document_id, chunk_offset, confidence, source_chunk.
        """
        if not edges:
            return []

        col_filter = _col_where("r", collection)
        results = []

        for edge in edges:
            s_uri = edge.get("subject_uri", "")
            p_uri = edge.get("predicate_uri", "")
            o_uri = edge.get("object_uri", "")

            if not s_uri or not p_uri:
                continue

            # Query the edge for source_chunk and confidence
            query = (
                "MATCH (s:Node {uri: $s_uri, user: $user})"
                "-[r:Rel {uri: $p_uri}]->"
                "(o {user: $user}) "
                f"WHERE (o.uri = $o_uri OR o.value = $o_uri){col_filter} "
                "RETURN r.source_chunk AS source_chunk, r.confidence AS confidence "
                "LIMIT 1"
            )
            params = {"s_uri": s_uri, "p_uri": p_uri, "o_uri": o_uri,
                      "user": user}
            if collection:
                params["collection"] = collection

            rows = await self._client.execute_cypher(query, params=params)
            if not rows:
                continue

            source_chunk = rows[0].get("source_chunk") or ""
            confidence = rows[0].get("confidence")

            # Parse source_chunk URI: nouxcube://document/{col}/{doc_id}#offset={n}
            doc_id = ""
            chunk_offset = 0
            if source_chunk and "#offset=" in source_chunk:
                doc_part = source_chunk.split("#")[0]
                doc_id = doc_part.rsplit("/", 1)[-1] if "/" in doc_part else ""
                try:
                    chunk_offset = int(source_chunk.split("offset=")[-1])
                except ValueError:
                    chunk_offset = 0

            if doc_id:
                results.append({
                    "subject_uri": s_uri,
                    "predicate_uri": p_uri,
                    "object_uri": o_uri,
                    "document_id": doc_id,
                    "chunk_offset": chunk_offset,
                    "confidence": confidence,
                    "source_chunk": source_chunk,
                })

        return results
```

- [ ] **Step 2: Add POST /triples/trace-sources endpoint**

In `KTS/app/api/triples.py`, add a new endpoint. First add the Pydantic schema:

```python
class TraceSourcesRequest(BaseModel):
    edges: List[Dict[str, str]]
    tenant_id: str
    collection: str = "default"
```

Then the endpoint:

```python
@router.post("/triples/trace-sources")
async def trace_sources(request: TraceSourcesRequest):
    """Trace edges back to source document chunks."""
    client = FalkorDBClient()
    await client.initialize()
    try:
        query_service = TripleQuery(client)
        sources = await query_service.trace_sources(
            edges=request.edges,
            user=request.tenant_id,
            collection=request.collection,
        )
        return {"sources": sources}
    finally:
        await client.close()
```

- [ ] **Step 3: Verify endpoint compiles**

Run: `cd backend/microservices/knowledge-tree-service && python3 -c "from app.api.triples import router; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/knowledge-tree-service/app/services/triple_query.py \
        backend/microservices/knowledge-tree-service/app/api/triples.py
git commit -m "feat(trustgraph): POST /triples/trace-sources endpoint for provenance resolution"
```

---

### Task 2: Emma KTS client trace_sources method

**Files:**
- Modify: `Emma/app/clients/knowledge_tree_client.py`

- [ ] **Step 1: Add trace_sources client method**

In `knowledge_tree_client.py`, add after the `batch_neighbors` method:

```python
    async def trace_sources(
        self,
        tenant_id: str,
        edges: List[Dict[str, str]],
        collection: str = "default",
    ) -> List[Dict[str, Any]]:
        """Trace graph edges back to source document chunks.

        Args:
            tenant_id: Tenant identifier.
            edges: List of edge dicts with subject_uri, predicate_uri, object_uri.
            collection: Collection scope.

        Returns:
            List of source dicts with document_id, chunk_offset, confidence.
        """
        url = f"{self.base_url}/triples/trace-sources"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    json={
                        "edges": edges,
                        "tenant_id": tenant_id,
                        "collection": collection,
                    },
                    headers=self._headers(tenant_id),
                )
                response.raise_for_status()
                data = response.json()
                return data.get("sources", [])
        except Exception as e:
            logger.warning(f"trace_sources failed: {e}")
            return []
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py', doraise=True); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/clients/knowledge_tree_client.py
git commit -m "feat(trustgraph): trace_sources client method in KTS client"
```

---

### Task 3: graph_rag source resolution + enriched context

**Files:**
- Modify: `Emma/app/agents/langgraph/tools/graph_rag.py`

- [ ] **Step 1: Add source resolution after Stage 6**

In `graph_rag.py`, in the `execute` method, after the `_format_context` call (currently the last line before `return`), add source resolution:

```python
        # ── Stage 7: Source provenance resolution ────────────────────────
        source_evidence = []
        try:
            # Build edge list for tracing
            trace_edges = []
            for edge in scored_final_edges:
                trace_edges.append({
                    "subject_uri": edge.get("subject_uri", ""),
                    "predicate_uri": edge.get("predicate_uri", ""),
                    "object_uri": edge.get("object_uri", ""),
                })

            if trace_edges:
                raw_sources = await kts_client.trace_sources(
                    tenant_id=tenant_id,
                    edges=trace_edges,
                )

                # Resolve document titles from labels cache
                for src in raw_sources:
                    doc_uri = f"nouxcube://document/default/{src['document_id']}"
                    doc_title = labels.get(doc_uri, src["document_id"][:12])
                    s_label = labels.get(src["subject_uri"], _humanize_uri(src["subject_uri"]))
                    p_name = _extract_predicate_name(src["predicate_uri"])
                    o_label = labels.get(src["object_uri"], _humanize_uri(src["object_uri"]))

                    source_evidence.append({
                        "document_id": src["document_id"],
                        "document_title": doc_title,
                        "chunk_offset": src["chunk_offset"],
                        "relationship": f"{s_label} {p_name} {o_label}",
                        "confidence": src.get("confidence"),
                    })
        except Exception as e:
            logger.warning(f"graph_rag: source resolution failed: {e}")
```

Then modify the return to include source_evidence in the ToolResult data. The current return is `return _format_context(...)`. Change it to:

```python
        result = _format_context(
            query=query,
            top_entities=top_entities,
            scored_edges=scored_final_edges,
            labels=labels,
        )

        # Enrich with source evidence
        if source_evidence:
            # Append sources section to context text for LLM
            sources_text = "\n\n### Fuentes\n"
            for src in source_evidence[:10]:
                conf_str = f" (conf: {src['confidence']:.2f})" if src.get('confidence') is not None else ""
                sources_text += f"- \"{src['relationship']}\" — {src['document_title']} chunk {src['chunk_offset']}{conf_str}\n"
            result.output += sources_text

            # Add to structured data for SSE event
            result.data["source_evidence"] = source_evidence

        return result
```

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py', doraise=True); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/graph_rag.py
git commit -m "feat(trustgraph): graph_rag Stage 7 — source provenance resolution + enriched context"
```

---

### Task 4: react_loop emits source_evidence reasoning step

**Files:**
- Modify: `Emma/app/agents/langgraph/nodes/react_loop.py`

- [ ] **Step 1: Emit source_evidence after graph_rag tool result**

In `react_loop.py`, find the section where tool results are processed (around line 830-850, the loop that builds `reasoning_steps`). After the existing `reasoning_steps.append` for `StepType.OBSERVATION`, add:

```python
        # Emit source_evidence from graph_rag
        if tc_name == "graph_rag" and result.data and result.data.get("source_evidence"):
            reasoning_steps.append({
                "type": "source_evidence",
                "content": json.dumps(result.data["source_evidence"], ensure_ascii=False),
                "source": "graph_rag",
            })
```

Make sure `json` is imported at the top of the file (it likely already is — check).

- [ ] **Step 2: Verify syntax**

Run: `python3 -c "import py_compile; py_compile.compile('backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py', doraise=True); print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py
git commit -m "feat(trustgraph): emit source_evidence reasoning step from graph_rag results"
```

---

### Task 5: Frontend types + useMessageConverter

**Files:**
- Modify: `frontend/src/components/emma-chat/types.ts` (via `frontend/src/lib/types/emma.ts` — check actual location)
- Modify: `frontend/src/components/emma-chat/hooks/useMessageConverter.ts`

- [ ] **Step 1: Add SourceEvidenceItem type**

In the types file (find where `Citation` is defined), add:

```typescript
export interface SourceEvidenceItem {
  document_id: string
  document_title: string
  chunk_offset: number
  relationship: string
  confidence?: number
}
```

And add `sourceEvidence?: SourceEvidenceItem[]` to the `EmmaMessage.metadata` interface.

- [ ] **Step 2: Extract source_evidence in useMessageConverter**

In `useMessageConverter.ts`, in the section that processes reasoning steps and attaches metadata to the AI message (around line 261-275), add extraction of source_evidence:

```typescript
    // Extract source evidence from reasoning steps
    const sourceEvidence = reasoningSteps
      .filter((s: any) => s.type === 'source_evidence')
      .flatMap((s: any) => {
        try { return JSON.parse(s.content) } catch { return [] }
      })
```

Then include it in the metadata:

```typescript
    if (sourceEvidence.length > 0) {
      stepsMetadata!.sourceEvidence = sourceEvidence
    }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/types/emma.ts \
        frontend/src/components/emma-chat/hooks/useMessageConverter.ts
git commit -m "feat(trustgraph): frontend types + converter for source_evidence"
```

---

### Task 6: SourceEvidence component + MessageBubble integration

**Files:**
- Create: `frontend/src/components/emma-chat/SourceEvidence.tsx`
- Modify: `frontend/src/components/emma-chat/messages/MessageBubble.tsx`

- [ ] **Step 1: Create SourceEvidence component**

```typescript
'use client'

import { useState } from 'react'
import { IconChevronDown, IconChevronRight, IconFileText } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { SourceEvidenceItem } from '@/lib/types/emma'

function ConfidenceBadge({ confidence }: { confidence?: number }) {
  if (confidence == null) return null
  const color = confidence >= 0.8
    ? 'bg-green-500/20 text-green-400 border-green-500/30'
    : confidence >= 0.5
      ? 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30'
      : 'bg-red-500/20 text-red-400 border-red-500/30'
  return (
    <span className={cn('text-[10px] px-1.5 py-0.5 rounded border font-mono', color)}>
      {(confidence * 100).toFixed(0)}%
    </span>
  )
}

interface SourceEvidenceProps {
  sources: SourceEvidenceItem[]
  onDocumentClick?: (documentId: string) => void
}

export function SourceEvidence({ sources, onDocumentClick }: SourceEvidenceProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  if (!sources || sources.length === 0) return null

  return (
    <div className="mt-2 rounded-lg border border-border/50 bg-muted/30">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        {isExpanded ? (
          <IconChevronDown className="h-3.5 w-3.5" />
        ) : (
          <IconChevronRight className="h-3.5 w-3.5" />
        )}
        <IconFileText className="h-3.5 w-3.5" />
        <span className="font-medium">Fuentes consultadas ({sources.length})</span>
      </button>

      {isExpanded && (
        <div className="px-3 pb-3 space-y-2">
          {sources.map((src, idx) => (
            <div key={idx} className="flex items-start gap-2 text-xs">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => onDocumentClick?.(src.document_id)}
                    className="font-medium text-primary hover:underline truncate"
                  >
                    {src.document_title}
                  </button>
                  <span className="text-muted-foreground shrink-0">chunk {src.chunk_offset}</span>
                  <ConfidenceBadge confidence={src.confidence} />
                </div>
                <p className="text-muted-foreground mt-0.5 line-clamp-1">
                  {src.relationship}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Add SourceEvidence to MessageBubble**

In `MessageBubble.tsx`, add the import:

```typescript
import { SourceEvidence } from '../SourceEvidence'
```

Then in the JSX, after the `InlineSourceCard` section (around line 210-220), add:

```tsx
      {message.metadata?.sourceEvidence && message.metadata.sourceEvidence.length > 0 && (
        <SourceEvidence
          sources={message.metadata.sourceEvidence}
          onDocumentClick={(docId) => {
            const doc = { name: docId, id: docId } as DocumentInfo
            onOpenFullscreen?.(doc)
          }}
        />
      )}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build 2>&1 | tail -10`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/emma-chat/SourceEvidence.tsx \
        frontend/src/components/emma-chat/messages/MessageBubble.tsx
git commit -m "feat(trustgraph): SourceEvidence component — collapsible provenance panel in chat"
```

---

### Task 7: Rebuild + integration test

- [ ] **Step 1: Rebuild services**

```bash
cd backend/docker && docker compose up -d --build knowledge-tree-service emma-agent-service
```

- [ ] **Step 2: Test trace-sources endpoint directly**

```bash
curl -s -X POST http://localhost:8011/triples/trace-sources \
  -H "Content-Type: application/json" \
  -d '{
    "edges": [{"subject_uri": "nouxcube://entity/default/juan-garcia", "predicate_uri": "nouxcube://predicate/legal/empleado-de", "object_uri": "nouxcube://entity/default/empresa-abc"}],
    "tenant_id": "00000000-0000-0000-0000-000000000001"
  }' | python3 -m json.tool
```

Expected: JSON with sources array containing document_id, chunk_offset, confidence.

- [ ] **Step 3: Test via Emma chat**

Query Emma with: "¿qué relaciones existen entre los empleados y las empresas?"
- Expect: graph_rag tool result includes "Fuentes" section in context
- Expect: SSE stream includes source_evidence reasoning step
- Expect: Frontend shows "Fuentes consultadas" collapsible panel below the response

- [ ] **Step 4: Frontend build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds with no type errors.
