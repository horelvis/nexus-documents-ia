# Knowledge Report Panel + Document Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display knowledge reports as inline panels in EmmaChat with on-demand DOCX generation (new or using existing document as template).

**Architecture:** `KnowledgeReportTool` stores report text + metadata in Redis after LLM generation, emits `report.complete` SSE. Frontend renders `ReportPanel` inline with trust summary. "Generar documento" button calls a new endpoint that uses `_render_document_docx()` or routes to forge service for template-based generation.

**Tech Stack:** Python (FastAPI, redis.asyncio, python-docx), TypeScript (React, Next.js 15, Tailwind, shadcn/ui), LangGraph SSE streaming

**Spec:** `docs/superpowers/specs/2026-04-02-knowledge-report-panel-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/microservices/emma-agent-service/app/api/report_downloads.py` | `/emma/reports/{id}/generate-document` + `/emma/reports/{id}/download` endpoints |
| `frontend/src/components/emma-chat/ReportPanel.tsx` | Inline collapsible report panel with trust bar + document generation button |

### Modified Files
| File | Change |
|------|--------|
| `backend/microservices/emma-agent-service/app/agents/langgraph/tools/knowledge_report.py` | Store report in Redis, emit report.complete SSE, add report_id to result |
| `backend/microservices/emma-agent-service/app/api/emma.py` | Handle report.complete SSE event |
| `backend/microservices/emma-agent-service/app/main.py` | Register report_downloads router |
| `frontend/src/lib/types/emma.ts` | Add ReportMetadata type + report field to EmmaMessage |
| `frontend/src/components/emma-chat/hooks/useMessageConverter.ts` | Extract report metadata from tool results |
| `frontend/src/components/emma-chat/messages/MessageBubble.tsx` | Render ReportPanel when report metadata present |
| `frontend/src/components/emma-chat/utils/humanizeStep.ts` | Map generate_knowledge_report to ActivityTimeline |
| `frontend/src/lib/services/emma.service.ts` | Add generateReportDocument + downloadReport API calls |

---

## Task 1: Store report in Redis + emit report.complete SSE

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/knowledge_report.py`

- [ ] **Step 1: Add Redis storage after LLM generation**

In `knowledge_report.py`, add Redis storage before the return statement (after line 173, before line 175). Add `uuid` and `json` imports are already present:

```python
        # ── Stage 5: Store report in Redis for on-demand document generation ──
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        try:
            import redis.asyncio as aioredis

            r = aioredis.from_url(settings.redis_url)
            await r.setex(
                f"emma:report:{report_id}:text",
                3600,
                report_text,
            )
            await r.setex(
                f"emma:report:{report_id}:meta",
                3600,
                json.dumps({
                    "entity_uri": entity_uri,
                    "entity_label": entity_label,
                    "report_type": report_type,
                    "tenant_id": tenant_id,
                    "sources": sources,
                    "trust_summary": trust,
                }),
            )
            await r.aclose()
        except Exception as exc:
            logger.warning(f"Failed to store report in Redis: {exc}")
            report_id = ""
```

- [ ] **Step 2: Emit report.complete SSE event**

After Redis storage, before the return, add:

```python
        # ── Stage 6: Emit report.complete for frontend panel ──
        if emit_sse and report_id:
            emit_sse({
                "event_type": "report.complete",
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "report_id": report_id,
                    "entity_label": entity_label,
                    "report_type": report_type,
                    "trust_summary": trust,
                    "source_count": len(sources),
                },
            })
```

- [ ] **Step 3: Add report_id to ToolResult.data**

Replace the existing return statement (lines 175-185) with:

```python
        return ToolResult(
            output=report_text,
            data={
                "report_type": report_type,
                "report_id": report_id,
                "entity_uri": entity_uri,
                "entity_label": entity_label,
                "kpis": kpis,
                "sources": sources,
                "trust_summary": trust,
            },
            success=True,
        )
```

- [ ] **Step 4: Verify service starts**

```bash
cd backend/docker && docker compose restart emma-agent-service && sleep 8 && docker compose ps emma-agent-service --format "{{.Status}}"
```

Expected: `Up X seconds (healthy)`

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/knowledge_report.py
git commit -m "feat(emma): store knowledge report in Redis + emit report.complete SSE"
```

---

## Task 2: Handle report.complete SSE in emma.py

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py`

- [ ] **Step 1: Add report.complete handler**

In `emma.py`, inside the existing `elif event_type.startswith("report."):` block (around line 649), add handling for `report.complete` within the `stage_labels` dict and add a new elif branch:

Find the existing block:
```python
            elif event_type.startswith("report."):
                # Knowledge report progressive events (report.assembling, report.generating, report.kpi)
                stage_labels = {
                    "report.assembling": "Recopilando datos del grafo...",
                    "report.generating": "Generando informe...",
                    "report.kpi": None,
                }
```

Replace with:
```python
            elif event_type.startswith("report."):
                # Knowledge report progressive events
                stage_labels = {
                    "report.assembling": "Recopilando datos del grafo...",
                    "report.generating": "Generando informe...",
                    "report.kpi": None,
                    "report.complete": None,
                }
```

Then after the existing `report.kpi` elif block, before `elif label:`, add:

```python
                if event_type == "report.complete":
                    step_counter += 1
                    _track_step("report_complete", "Informe generado")
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_complete', 'content': 'Informe generado', 'isThinking': True})}\n\n"
                    yield f"event: report_complete\ndata: {_dumps(data)}\n\n"
                elif event_type == "report.kpi":
```

The full rewritten block should be:
```python
            elif event_type.startswith("report."):
                # Knowledge report progressive events
                stage_labels = {
                    "report.assembling": "Recopilando datos del grafo...",
                    "report.generating": "Generando informe...",
                    "report.kpi": None,
                    "report.complete": None,
                }
                if event_type == "report.complete":
                    step_counter += 1
                    _track_step("report_complete", "Informe generado")
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_complete', 'content': 'Informe generado', 'isThinking': True})}\n\n"
                    yield f"event: report_complete\ndata: {_dumps(data)}\n\n"
                elif event_type == "report.kpi":
                    kpi_name = data.get("description") or data.get("name", "")
                    kpi_value = data.get("value", "")
                    step_counter += 1
                    _track_step("report_kpi", f"{kpi_name}: {kpi_value}")
                    yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_kpi', 'content': f'KPI: {kpi_name} = {kpi_value}', 'isThinking': True})}\n\n"
                    yield f"event: report_kpi\ndata: {_dumps(data)}\n\n"
                else:
                    label = stage_labels.get(event_type)
                    if label:
                        step_counter += 1
                        _track_step("report_progress", label)
                        yield f"event: agent_reasoning\ndata: {_dumps({'step': step_counter, 'type': 'report_progress', 'content': label, 'isThinking': True})}\n\n"
```

- [ ] **Step 2: Commit**

```bash
git add backend/microservices/emma-agent-service/app/api/emma.py
git commit -m "feat(emma): handle report.complete SSE event in streaming"
```

---

## Task 3: Report download endpoints

**Files:**
- Create: `backend/microservices/emma-agent-service/app/api/report_downloads.py`
- Modify: `backend/microservices/emma-agent-service/app/main.py`

- [ ] **Step 1: Create report_downloads.py**

Create `backend/microservices/emma-agent-service/app/api/report_downloads.py`:

```python
"""
Endpoints for on-demand knowledge report document generation and download.

POST /emma/reports/{report_id}/generate-document  — generate DOCX from stored report
GET  /emma/reports/{report_id}/download            — download generated DOCX
"""

import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import verify_api_key_or_bearer as verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/emma/reports",
    tags=["reports"],
    dependencies=[Depends(verify_api_key)],
)

REPORT_KEY_PREFIX = "emma:report:"
REPORT_DOC_TTL = 3600


class GenerateDocumentRequest(BaseModel):
    mode: str = Field(
        default="new",
        description="'new' = DOCX from markdown, 'template' = use existing doc as base",
    )
    template_document_id: Optional[str] = Field(
        default=None,
        description="Document ID to use as template (mode=template only)",
    )
    title: Optional[str] = Field(
        default=None,
        description="Custom title for the generated document",
    )


@router.post("/{report_id}/generate-document")
async def generate_report_document(report_id: str, body: GenerateDocumentRequest):
    """Generate a DOCX from a stored knowledge report."""
    r = aioredis.from_url(settings.redis_url)

    try:
        report_text = await r.get(f"{REPORT_KEY_PREFIX}{report_id}:text")
        report_meta_raw = await r.get(f"{REPORT_KEY_PREFIX}{report_id}:meta")

        if not report_text:
            raise HTTPException(status_code=404, detail="Report not found or expired")

        report_text = report_text.decode() if isinstance(report_text, bytes) else report_text
        report_meta = json.loads(report_meta_raw) if report_meta_raw else {}

        entity_label = report_meta.get("entity_label", "Informe")
        report_type = report_meta.get("report_type", "entity_profile")
        doc_title = body.title or f"Informe: {entity_label}"

        if body.mode == "template" and body.template_document_id:
            # Route to forge service for template-based generation
            docx_bytes = await _generate_from_template(
                report_text=report_text,
                report_meta=report_meta,
                template_document_id=body.template_document_id,
            )
        else:
            # Generate DOCX from markdown directly
            from app.agents.langgraph.tools.document_generator import _render_document_docx

            docx_bytes = _render_document_docx(
                title=doc_title,
                content=report_text,
                source_title=f"Knowledge Graph — {report_type}",
            )

        # Store generated DOCX in Redis
        doc_key = f"{REPORT_KEY_PREFIX}{report_id}:docx"
        await r.setex(doc_key, REPORT_DOC_TTL, docx_bytes)

        size_bytes = len(docx_bytes)
        logger.info(f"Report {report_id}: DOCX generated ({size_bytes} bytes)")

        return {
            "download_url": f"/emma/reports/{report_id}/download",
            "format": "docx",
            "size_bytes": size_bytes,
            "title": doc_title,
        }

    finally:
        await r.aclose()


@router.get("/{report_id}/download")
async def download_report(report_id: str):
    """Download a generated report DOCX."""
    r = aioredis.from_url(settings.redis_url)

    try:
        docx_bytes = await r.get(f"{REPORT_KEY_PREFIX}{report_id}:docx")
        if not docx_bytes:
            raise HTTPException(
                status_code=404,
                detail="Document not found. Generate it first via POST /generate-document",
            )

        report_meta_raw = await r.get(f"{REPORT_KEY_PREFIX}{report_id}:meta")
        meta = json.loads(report_meta_raw) if report_meta_raw else {}
        entity_label = meta.get("entity_label", "informe")
        filename = f"informe_{entity_label.lower().replace(' ', '_')}.docx"

        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    finally:
        await r.aclose()


async def _generate_from_template(
    report_text: str,
    report_meta: dict,
    template_document_id: str,
) -> bytes:
    """Generate DOCX by injecting report data into an existing document template.

    Uses the forge service to analyze the template, detect fields,
    and render with report data.
    """
    import httpx

    forge_url = settings.document_forge_service_url.rstrip("/")
    api_key = settings.MICROSERVICES_API_KEY
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
        # Step 1: Analyze template to detect fields
        analyze_resp = await client.post(
            f"{forge_url}/analyze",
            json={
                "document_id": template_document_id,
                "tenant_id": report_meta.get("tenant_id", ""),
                "user_intent": f"Inject knowledge report data for {report_meta.get('entity_label', '')}",
            },
        )
        if analyze_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Forge analyze failed: {analyze_resp.text[:200]}",
            )
        analyze_data = analyze_resp.json()
        session_id = analyze_data.get("session_id", "")
        fields = analyze_data.get("fields", [])

        if not fields:
            # No fields detected — fall back to new document mode
            from app.agents.langgraph.tools.document_generator import _render_document_docx

            return _render_document_docx(
                title=f"Informe: {report_meta.get('entity_label', '')}",
                content=report_text,
                source_title=f"Knowledge Graph — {report_meta.get('report_type', '')}",
            )

        # Step 2: Map report text to detected fields (inject full report as content field)
        field_values = {}
        for field in fields:
            name = field.get("field_name", "")
            field_type = field.get("field_type", "")
            # Map entity label to name/title fields
            if field_type in ("name", "title", "texto") or "nombre" in name.lower() or "titulo" in name.lower():
                field_values[name] = report_meta.get("entity_label", "")
            elif "contenido" in name.lower() or "cuerpo" in name.lower() or "texto" in name.lower():
                field_values[name] = report_text
            elif "fecha" in name.lower():
                from datetime import date
                field_values[name] = date.today().isoformat()

        # Step 3: Render with field values
        render_resp = await client.post(
            f"{forge_url}/render",
            json={
                "session_id": session_id,
                "field_values": field_values,
                "output_formats": ["docx"],
            },
        )
        if render_resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Forge render failed: {render_resp.text[:200]}",
            )
        render_data = render_resp.json()

        # Step 4: Download rendered DOCX from forge
        download_url = render_data.get("outputs", {}).get("docx", {}).get("download_url", "")
        if not download_url:
            raise HTTPException(status_code=502, detail="Forge render returned no DOCX URL")

        doc_resp = await client.get(f"{forge_url}{download_url}")
        if doc_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to download rendered DOCX")

        return doc_resp.content
```

- [ ] **Step 2: Register router in main.py**

In `backend/microservices/emma-agent-service/app/main.py`, add import and registration.

After the existing import block (around line 46), add:
```python
from app.api.report_downloads import router as report_downloads_router
```

After the existing `app.include_router(emma_router, ...)` line (around line 219), add:
```python
    app.include_router(report_downloads_router, tags=["reports"])
```

- [ ] **Step 3: Verify service starts**

```bash
cd backend/docker && docker compose restart emma-agent-service && sleep 8 && docker compose ps emma-agent-service --format "{{.Status}}"
```

Expected: `Up X seconds (healthy)`

- [ ] **Step 4: Test endpoint manually**

First, run a report to populate Redis:
```bash
API_KEY=$(grep -m1 'MICROSERVICES_API_KEY=' .env | cut -d= -f2)
curl -sN "http://127.0.0.1:8019/emma/query/stream" -X POST \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"query":"Genera un informe de perfil sobre Carlos Ruiz Fernández","tenant_id":"00000000-0000-0000-0000-000000000001","user_id":"a060f046-9992-4d1a-87c4-fa5c6f8c066c","conversation_id":"test-report-panel","stream":true}' > /tmp/report_panel_test.txt 2>/dev/null
```

Extract report_id from SSE events:
```bash
grep "report_complete" /tmp/report_panel_test.txt
```

Then generate document:
```bash
REPORT_ID="<extracted_report_id>"
curl -s "http://127.0.0.1:8019/emma/reports/$REPORT_ID/generate-document" -X POST \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"mode":"new"}' | python3 -m json.tool
```

Expected: `{"download_url": "/emma/reports/.../download", "format": "docx", "size_bytes": ...}`

Then download:
```bash
curl -s "http://127.0.0.1:8019/emma/reports/$REPORT_ID/download" \
  -H "X-API-Key: $API_KEY" -o /tmp/test_report.docx
file /tmp/test_report.docx
```

Expected: `Microsoft Word 2007+`

- [ ] **Step 5: Commit**

```bash
git add backend/microservices/emma-agent-service/app/api/report_downloads.py \
        backend/microservices/emma-agent-service/app/main.py
git commit -m "feat(emma): report document generation + download endpoints"
```

---

## Task 4: Frontend types + service

**Files:**
- Modify: `frontend/src/lib/types/emma.ts`
- Modify: `frontend/src/lib/services/emma.service.ts`

- [ ] **Step 1: Add ReportMetadata type**

In `frontend/src/lib/types/emma.ts`, after `ForgeMetadata` (after line 349), add:

```typescript
export interface ReportTrustSummary {
  avg_confidence: number
  min_confidence: number
  total_facts: number
  total_sources: number
}

export interface ReportMetadata {
  report_id: string
  entity_label: string
  report_type: string
  trust_summary: ReportTrustSummary
  source_count: number
}
```

- [ ] **Step 2: Add report field to EmmaMessage**

In the `EmmaMessage` interface (around line 359), after `forge?: ForgeMetadata`, add:

```typescript
  report?: ReportMetadata
```

- [ ] **Step 3: Add API calls in emma.service.ts**

In `frontend/src/lib/services/emma.service.ts`, add:

```typescript
export async function generateReportDocument(
  reportId: string,
  mode: 'new' | 'template' = 'new',
  templateDocumentId?: string,
  title?: string,
): Promise<{ download_url: string; format: string; size_bytes: number; title: string }> {
  const token = sessionStorage.getItem('nexus_sso_tokens')
    ? JSON.parse(sessionStorage.getItem('nexus_sso_tokens')!).access_token
    : ''
  const resp = await fetch(`${EMMA_SERVICE_URL}/emma/reports/${reportId}/generate-document`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      mode,
      template_document_id: templateDocumentId,
      title,
    }),
  })
  if (!resp.ok) throw new Error(`Failed to generate report document: ${resp.status}`)
  return resp.json()
}

export function getReportDownloadUrl(reportId: string): string {
  return `${EMMA_SERVICE_URL}/emma/reports/${reportId}/download`
}
```

Note: `EMMA_SERVICE_URL` should match the existing pattern in the file — check for the existing base URL constant (likely from `API_CONFIG` or `NEXT_PUBLIC_EMMA_SERVICE_URL`).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types/emma.ts frontend/src/lib/services/emma.service.ts
git commit -m "feat(frontend): ReportMetadata types + report document API calls"
```

---

## Task 5: ReportPanel component

**Files:**
- Create: `frontend/src/components/emma-chat/ReportPanel.tsx`

- [ ] **Step 1: Create ReportPanel.tsx**

Create `frontend/src/components/emma-chat/ReportPanel.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { IconChevronDown, IconChevronRight, IconFileText, IconDownload, IconLoader2 } from '@tabler/icons-react'
import { EmmaMarkdown } from './EmmaMarkdown'
import { generateReportDocument, getReportDownloadUrl } from '@/lib/services/emma.service'
import type { ReportMetadata } from '@/lib/types/emma'

interface ReportPanelProps {
  report: ReportMetadata
  content: string
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color = pct >= 80 ? 'text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-950'
    : pct >= 50 ? 'text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-950'
    : 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-950'
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {pct}%
    </span>
  )
}

export function ReportPanel({ report, content }: ReportPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const trust = report.trust_summary

  async function handleGenerateDocument() {
    setIsGenerating(true)
    setError(null)
    try {
      const result = await generateReportDocument(report.report_id, 'new')
      setDownloadUrl(getReportDownloadUrl(report.report_id))
    } catch (err: any) {
      setError(err.message || 'Error generando documento')
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div className="mt-3 rounded-xl border border-border/50 bg-card/60 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left hover:bg-muted/30 transition-colors"
      >
        {isExpanded ? (
          <IconChevronDown className="h-4 w-4 text-muted-foreground shrink-0" />
        ) : (
          <IconChevronRight className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <IconFileText className="h-4 w-4 text-primary shrink-0" />
        <span className="font-medium text-sm flex-1">
          Informe: {report.entity_label}
        </span>
        <ConfidenceBadge value={trust.avg_confidence} />
      </button>

      {isExpanded && (
        <div className="px-4 pb-4">
          {/* Report body */}
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <EmmaMarkdown content={content} />
          </div>

          {/* Trust bar */}
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground border-t border-border/30 pt-3">
            <span>Confianza media: <ConfidenceBadge value={trust.avg_confidence} /></span>
            <span>Min: <ConfidenceBadge value={trust.min_confidence} /></span>
            <span>{trust.total_sources} fuentes documentales</span>
            <span>{trust.total_facts} hechos verificados</span>
          </div>

          {/* Document generation action */}
          <div className="mt-4 flex items-center gap-3 border-t border-border/30 pt-3">
            {downloadUrl ? (
              <a
                href={downloadUrl}
                download
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
              >
                <IconDownload className="h-4 w-4" />
                Descargar DOCX
              </a>
            ) : (
              <button
                onClick={handleGenerateDocument}
                disabled={isGenerating}
                className="inline-flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-medium hover:bg-muted/50 transition-colors disabled:opacity-50"
              >
                {isGenerating ? (
                  <>
                    <IconLoader2 className="h-4 w-4 animate-spin" />
                    Generando...
                  </>
                ) : (
                  <>
                    <IconFileText className="h-4 w-4" />
                    Generar documento
                  </>
                )}
              </button>
            )}
            {error && <span className="text-xs text-red-500">{error}</span>}
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd frontend && npx tsc --noEmit src/components/emma-chat/ReportPanel.tsx 2>&1 | head -10
```

If there are import path issues, adjust based on the actual project aliases.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/emma-chat/ReportPanel.tsx
git commit -m "feat(frontend): ReportPanel inline component with trust bar + DOCX generation"
```

---

## Task 6: Wire ReportPanel into chat message flow

**Files:**
- Modify: `frontend/src/components/emma-chat/hooks/useMessageConverter.ts`
- Modify: `frontend/src/components/emma-chat/messages/MessageBubble.tsx`
- Modify: `frontend/src/components/emma-chat/utils/humanizeStep.ts`

- [ ] **Step 1: Extract report metadata in useMessageConverter**

In `frontend/src/components/emma-chat/hooks/useMessageConverter.ts`, find where `sourceEvidence` is extracted (around line 264). After that block, add:

```typescript
    // Extract report metadata from reasoning steps
    const reportStep = reasoningSteps.find(
      (s: any) => s.type === 'report_complete' || s.type === 'report.complete'
    )
    let reportMetadata: ReportMetadata | undefined
    if (reportStep) {
      try {
        const parsed = typeof reportStep.content === 'string'
          ? JSON.parse(reportStep.content)
          : reportStep.content
        reportMetadata = {
          report_id: parsed.report_id,
          entity_label: parsed.entity_label,
          report_type: parsed.report_type,
          trust_summary: parsed.trust_summary,
          source_count: parsed.source_count,
        }
      } catch { /* ignore parse errors */ }
    }
```

Then where metadata is attached to the message (around line 315-320), add `report: reportMetadata` to the spread:

Find the pattern that attaches metadata and add the report field alongside existing ones.

Add import at top:
```typescript
import type { ReportMetadata } from '@/lib/types/emma'
```

- [ ] **Step 2: Render ReportPanel in MessageBubble**

In `frontend/src/components/emma-chat/messages/MessageBubble.tsx`, after the DocGenResult block (around line 95), before HITL Review, add:

```tsx
    // Knowledge Report result
    if (message.report) {
      return (
        <EmmaMessageFlow>
          <div className="max-w-none">
            <EmmaMarkdown content={message.content} />
            <ReportPanel report={message.report} content={message.content} />
          </div>
          {message.metadata?.explanation && (
            <ExplanationPanel explanation={message.metadata.explanation} />
          )}
          {renderSuggestions?.()}
        </EmmaMessageFlow>
      )
    }
```

Add import at top:
```tsx
import { ReportPanel } from '../ReportPanel'
```

- [ ] **Step 3: Add report tool to humanizeStep**

In `frontend/src/components/emma-chat/utils/humanizeStep.ts`, add to the `TOOL_CONFIGS` object (around line 150):

```typescript
  generate_knowledge_report: {
    icon: 'write' as ActivityIcon,
    activeText: () => 'Generando informe de conocimiento...',
    resultText: () => 'Informe generado',
  },
```

- [ ] **Step 4: Verify frontend compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors (or only pre-existing warnings).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/emma-chat/hooks/useMessageConverter.ts \
        frontend/src/components/emma-chat/messages/MessageBubble.tsx \
        frontend/src/components/emma-chat/utils/humanizeStep.ts
git commit -m "feat(frontend): wire ReportPanel into chat message flow + ActivityTimeline"
```

---

## Task 7: E2E verification

**Files:** None (testing only)

- [ ] **Step 1: Run E2E via curl to verify report_id and report.complete SSE**

```bash
cd backend/docker
API_KEY=$(grep -m1 'MICROSERVICES_API_KEY=' .env | cut -d= -f2)
curl -sN "http://127.0.0.1:8019/emma/query/stream" -X POST \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"query":"Genera un informe de perfil sobre Carlos Ruiz Fernández","tenant_id":"00000000-0000-0000-0000-000000000001","user_id":"a060f046-9992-4d1a-87c4-fa5c6f8c066c","conversation_id":"test-e2e-panel-final","stream":true}' > /tmp/e2e_panel.txt 2>/dev/null
```

Wait ~40s, then:

```bash
grep "report_complete" /tmp/e2e_panel.txt
```

Expected: SSE event with `report_id`, `entity_label`, `trust_summary`.

- [ ] **Step 2: Verify document generation endpoint**

```bash
REPORT_ID=$(python3 -c "
import json
with open('/tmp/e2e_panel.txt') as f:
    for line in f:
        if 'report_complete' in line and line.startswith('data:'):
            data = json.loads(line[5:])
            print(data.get('report_id', '')); break
")
echo "Report ID: $REPORT_ID"

curl -s "http://127.0.0.1:8019/emma/reports/$REPORT_ID/generate-document" -X POST \
  -H "Content-Type: application/json" -H "X-API-Key: $API_KEY" \
  -d '{"mode":"new"}' | python3 -m json.tool
```

Expected: JSON with download_url, format, size_bytes.

- [ ] **Step 3: Verify DOCX download**

```bash
curl -s "http://127.0.0.1:8019/emma/reports/$REPORT_ID/download" \
  -H "X-API-Key: $API_KEY" -o /tmp/final_report.docx
file /tmp/final_report.docx
```

Expected: `Microsoft Word 2007+`

- [ ] **Step 4: Test from UI**

Open a new chat in EmmaChat and type:
"Genera un informe de perfil sobre Carlos Ruiz Fernández"

Verify:
- ActivityTimeline shows "Generando informe de conocimiento..."
- ReportPanel renders inline with trust summary
- "Generar documento" button appears
- Clicking it generates DOCX and shows "Descargar DOCX" link

- [ ] **Step 5: Commit any remaining adjustments**

```bash
git add -A
git commit -m "test: E2E verification of knowledge report panel + DOCX generation"
```
