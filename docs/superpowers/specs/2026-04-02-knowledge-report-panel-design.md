# Knowledge Report Panel + Document Generation — Design Spec

**Date**: 2026-04-02
**Branch**: `feat/trustgraph-phase2`
**Depends on**: Phase 3c Knowledge Expert (COMPLETE), document-forge-service (running)
**Goal**: Display knowledge reports as structured inline panels in EmmaChat with on-demand document generation (DOCX/PDF) using existing documents as templates.

---

## Overview

When `generate_knowledge_report` executes, the frontend renders an inline **ReportPanel** in the chat (like SourceEvidence) instead of raw markdown. The panel displays the LLM-generated report text with a trust summary and a "Generar documento" action that lets the user create a DOCX/PDF — either from scratch or using an existing document as a template.

KPIs are a separate feature and are NOT included in this design.

---

## Architecture

```
generate_knowledge_report tool
  → GraphAssembler (KTS) → structured data
  → LLM generates markdown report
  → ToolResult { output: report_text, data: { report_id, sources, trust_summary } }
  → SSE: report.complete event with structured metadata
  → Frontend: ReportPanel inline in chat
      ├── Header (entity name + type + confidence badge)
      ├── Report body (LLM markdown via EmmaMarkdown)
      ├── Trust bar (avg confidence, source count, contradictions)
      └── "Generar documento" button
            → Modal/dropdown:
              a) "Documento nuevo" → document_generator (markdown → DOCX)
              b) "Usar plantilla" → user picks existing doc
                 → forge_document(analyze) → detect fields
                 → inject report data into fields
                 → forge_document(render) → DOCX/PDF download
```

---

## Backend Changes

### 1. KnowledgeReportTool — Store report in Redis for later PDF generation

**File**: `emma-agent-service/app/agents/langgraph/tools/knowledge_report.py`

After LLM generation, store the report text + metadata in Redis with a unique `report_id`:

```python
report_id = f"report_{uuid.uuid4().hex[:12]}"
await redis.setex(f"emma:report:{report_id}:text", 3600, report_text)
await redis.setex(f"emma:report:{report_id}:meta", 3600, json.dumps({
    "entity_uri": entity_uri,
    "entity_label": entity_label,
    "report_type": report_type,
    "tenant_id": tenant_id,
    "sources": sources,
    "trust_summary": trust,
}))
```

Include `report_id` in ToolResult.data so the frontend can reference it later.

### 2. SSE event — report.complete

**File**: `emma-agent-service/app/api/emma.py`

The existing `report.*` SSE events already flow via the stream_writer bridge. Add a `report.complete` event emitted by the tool after generation:

```python
emit_sse({
    "event_type": "report.complete",
    "payload": {
        "report_id": report_id,
        "entity_label": entity_label,
        "report_type": report_type,
        "trust_summary": trust,
        "source_count": len(sources),
    },
})
```

Handle in `emma.py` SSE handler alongside existing `report.*` events.

### 3. Document generation endpoint

**File**: `emma-agent-service/app/api/emma.py` (or new `app/api/reports.py`)

`POST /emma/reports/{report_id}/generate-document`

Request body:
```json
{
  "mode": "new" | "template",
  "template_document_id": "optional — existing doc ID to use as template",
  "title": "optional — custom title for the generated document"
}
```

**Mode "new"**:
1. Fetch report text from Redis (`emma:report:{report_id}:text`)
2. Use `_render_document_docx()` from document_generator to create DOCX from markdown
3. Store in Redis, return download URL (same pattern as generate_document)

**Mode "template"**:
1. Fetch report metadata from Redis
2. Call forge_document service:
   - `POST /analyze` with the template document → detect fields
   - Map report facts to detected fields (best-effort via field name matching)
   - `POST /render` with field_values from the report data
3. Return session_id + download URL

Response:
```json
{
  "download_url": "/emma/reports/{report_id}/download",
  "format": "docx",
  "size_bytes": 12345
}
```

### 4. Download endpoint

`GET /emma/reports/{report_id}/download`

Serves the generated DOCX/PDF bytes from Redis. Same pattern as `/emma/generated/{doc_id}/download`.

---

## Frontend Changes

### 1. ReportPanel component

**File**: `frontend/src/components/emma-chat/ReportPanel.tsx`

Inline collapsible panel (same pattern as SourceEvidence):

- **Header**: Entity name + report type badge + avg confidence badge + chevron toggle
- **Body** (expanded by default):
  - LLM report text rendered via `EmmaMarkdown` (mode="chat")
- **Trust bar**: Compact row showing:
  - Avg confidence (color-coded badge)
  - Source count: "11 documentos fuente"
  - Contradictions: "Sin contradicciones" or "N contradicciones" (red)
- **Footer action**: "Generar documento" button
  - Dropdown with two options:
    - "Documento nuevo (DOCX)" → calls POST /emma/reports/{id}/generate-document { mode: "new" }
    - "Usar documento como plantilla..." → opens document picker, then calls with mode: "template"
  - Loading state while generating
  - When ready: download button with file size

**Props**:
```typescript
interface ReportPanelProps {
  reportId: string
  entityLabel: string
  reportType: string
  reportContent: string        // LLM markdown
  trustSummary: {
    avg_confidence: number
    min_confidence: number
    total_facts: number
    total_sources: number
  }
  sourceCount: number
}
```

### 2. Type definitions

**File**: `frontend/src/lib/types/emma.ts`

```typescript
interface ReportMetadata {
  report_id: string
  entity_label: string
  report_type: string
  trust_summary: TrustSummary
  source_count: number
}

interface TrustSummary {
  avg_confidence: number
  min_confidence: number
  total_facts: number
  total_sources: number
}
```

Add `report?: ReportMetadata` to `EmmaMessage`.

### 3. useMessageConverter — detect report metadata

**File**: `frontend/src/components/emma-chat/hooks/useMessageConverter.ts`

In the message conversion pipeline, detect `report.complete` reasoning step or tool result containing `report_id`. Extract `ReportMetadata` and attach to the message.

### 4. MessageBubble — render ReportPanel

**File**: `frontend/src/components/emma-chat/messages/MessageBubble.tsx`

When `message.report` exists, render `<ReportPanel>` below the message content (or replacing it, since the report IS the content).

### 5. humanizeStep — map report events to ActivityTimeline

**File**: `frontend/src/components/emma-chat/utils/humanizeStep.ts`

Map `report_progress` and `report_kpi` step types to ActivityTimeline steps with appropriate icons (document icon for report_progress).

### 6. emma.service — generate document API call

**File**: `frontend/src/lib/services/emma.service.ts`

```typescript
async generateReportDocument(
  reportId: string,
  mode: 'new' | 'template',
  templateDocumentId?: string,
  title?: string,
): Promise<{ download_url: string; format: string; size_bytes: number }>
```

---

## SSE Event Flow (Complete)

```
event: agent_reasoning  → "Recopilando datos del grafo..."     (report.assembling)
event: agent_reasoning  → "Generando informe..."               (report.generating)
event: report_complete  → { report_id, entity_label, trust }   (report.complete — NEW)
event: token            → streaming report text                 (synthesize)
event: complete         → { answer, tools_used, report_metadata }
```

---

## Files Summary

### New Files
| File | Purpose |
|------|---------|
| `frontend/src/components/emma-chat/ReportPanel.tsx` | Inline report panel component |
| `emma-agent-service/app/api/report_downloads.py` | PDF generation + download endpoints |

### Modified Files
| File | Change |
|------|--------|
| `emma-agent-service/app/agents/langgraph/tools/knowledge_report.py` | Store report in Redis, emit report.complete SSE, include report_id in result |
| `emma-agent-service/app/api/emma.py` | Handle report.complete SSE event |
| `emma-agent-service/app/main.py` | Register report_downloads router |
| `frontend/src/lib/types/emma.ts` | Add ReportMetadata type |
| `frontend/src/components/emma-chat/hooks/useMessageConverter.ts` | Extract report metadata from tool results |
| `frontend/src/components/emma-chat/messages/MessageBubble.tsx` | Render ReportPanel when report metadata present |
| `frontend/src/components/emma-chat/utils/humanizeStep.ts` | Map report_progress steps to ActivityTimeline |
| `frontend/src/lib/services/emma.service.ts` | Add generateReportDocument API call |

---

## Out of Scope

- KPIs (separate feature)
- Report template management UI (templates are existing documents)
- Report history/persistence (reports are ephemeral in Redis, 1h TTL)
- PDF preview in browser (user downloads and opens locally)
