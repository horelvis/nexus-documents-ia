# Document Forge — Frontend UI Design Spec

**Date**: 2026-03-13
**Status**: Approved (v1)
**Scope**: Frontend UI + Main API proxy for document-forge-service

## Problem

The document-forge-service backend is fully implemented (analyze, prepare, render, convert, persist) but has no frontend UI. Users can only access it via Emma chat tool calls. A visual interface is needed for field editing, document preview, and download.

## Solution

Integration into the existing chat + dedicated detail page pattern (same as Verified Generation):

- **ForgeResult** component in chat — informative, shows detected fields and links to detail page
- **`/forge/[sessionId]`** page — interactive field editing, preview, download, persist
- **Main API proxy** — all requests go through Main API (8000), never directly to microservices

## Architecture

```
Frontend (Next.js)           Main API (8000)               document-forge-service (8013)
─────────────────           ────────────────               ─────────────────────────────
ForgeResult (chat)   ──→  POST /api/v1/forge/analyze  ──→  POST /analyze
/forge/[sessionId]   ──→  POST /api/v1/forge/render   ──→  POST /render
                     ──→  POST /api/v1/forge/persist   ──→  POST /persist
                     ──→  GET  /api/v1/forge/sessions  ──→  GET  /sessions/*
```

## Main API Proxy

**File**: `backend/app/api/v1/forge.py`

Router prefix: `/api/v1/forge`

All endpoints require authentication (Bearer token) and inject `tenant_id` + `user_id` from the authenticated session. The proxy forwards requests to `DOCUMENT_FORGE_SERVICE_URL` (env var, already configured in docker-compose.onpremise.yml).

### Endpoints

| Method | Path | Proxies To | Content-Type | Description |
|--------|------|-----------|--------------|-------------|
| POST | `/forge/analyze` | `POST /analyze` | multipart/form-data | Upload DOCX or pass `document_id` for field detection |
| POST | `/forge/render` | `POST /render` | application/json | Render document with new field values |
| POST | `/forge/persist` | `POST /persist` | application/json | Save to GCS + index in Weaviate |
| GET | `/forge/sessions/{session_id}/info` | `GET /sessions/{id}/info` | — | Session metadata (fields, status) |
| GET | `/forge/sessions/{session_id}/download` | `GET /sessions/{id}/download` | — | Stream DOCX/PDF bytes |

### Endpoints Not Proxied

- **`POST /prepare`** — not proxied. The `render` endpoint auto-prepares from `analyzed` state, so explicit prepare is unnecessary for the frontend flow.
- **`POST /convert`** — not proxied. PDF conversion is handled server-side during render when `output_formats` includes `"pdf"`.

### Proxy Implementation Pattern

```python
# Follow existing proxy patterns in the codebase
# Auth: get_current_user dependency → tenant_id, user_id
# Forward: httpx.AsyncClient to DOCUMENT_FORGE_SERVICE_URL
# Inject: tenant_id and user_id into request body/params
# Headers: X-API-Key for inter-service auth
#
# Analyze endpoint: accepts JSON from frontend (document_id + user_intent),
# proxy converts to multipart/form-data when forwarding to forge service.
# File upload path: frontend sends multipart directly, proxy forwards as-is.
#
# Download URLs: proxy rewrites download_url in render responses
# from forge-relative paths (/sessions/...) to Main API paths (/api/v1/forge/sessions/...).
```

### Configuration

Already present in `docker-compose.onpremise.yml`:
- `DOCUMENT_FORGE_SERVICE_URL=http://document-forge-service:8013`
- `DOCUMENT_FORGE_ENABLED=true`

Need to add to Main API `config.py`:
- `document_forge_service_url: str`
- `document_forge_enabled: bool`

## Frontend Components

### 1. ForgeResult (Chat Component)

**File**: `frontend/apps/on-premise/src/components/emma-chat/ForgeResult.tsx`

Informative component rendered in the chat when Emma's `forge_document` tool returns results. Follows the same pattern as `VerifiedDocumentResult.tsx` and `DocGenResult.tsx`.

**Displays**:
- Document title + type badge
- Confidence indicator (color-coded: emerald ≥80%, amber ≥60%, red <60%)
- List of detected fields with current values (truncated if >8 fields)
- Session status badge (analyzed, rendered, persisted)

**Actions**:
- "Editar campos" button → navigates to `/forge/{sessionId}`
- "Descargar" buttons (DOCX/PDF) — only visible after render

**Props**:
```typescript
interface ForgeResultProps {
  action: 'analyze' | 'render' | 'persist'  // determines what to display
  sessionId: string
  sourceTitle: string
  documentType: string
  confidence: number
  fields: ForgeField[]
  status: ForgeSessionStatus
  outputs?: Record<string, { download_url: string; size_bytes: number }>
}
// analyze → show fields list + "Editar campos" link
// render  → show download buttons + field count
// persist → show success message + indexed badge
```

### 2. Forge Detail Page

**File**: `frontend/apps/on-premise/src/app/forge/[sessionId]/page.tsx`

Full-page view for editing fields and generating documents. Accessed from ForgeResult link or direct URL.

**Layout** (top to bottom):
1. **Header card**: Document title, type badge, confidence gauge, creation timestamp
2. **Fields form**: Dynamic form generated from detected fields
   - Each field rendered by type: `text` → Input, `date` → date picker, `number` → number input, `currency` → number input with currency suffix, `enum` → Select
   - Current value shown as placeholder
   - Required fields marked
   - Label from `field.label`, help text from `field.description`
3. **Action bar** (sticky bottom):
   - "Generar documento" button (primary) → calls render
   - "Descargar DOCX" / "Descargar PDF" → visible after render
   - "Guardar en sistema" → calls persist (with confirmation dialog)
4. **Document preview** (after render): DocumentViewer component showing the generated DOCX/PDF

**States**:
- `loading` — fetching session info
- `editing` — form visible, user editing fields
- `rendering` — spinner while render API call in progress (~2-5s)
- `rendered` — preview visible, download buttons enabled
- `persisting` — saving to GCS/Weaviate
- `persisted` — success message, indexed badge

**Data loading**:
```typescript
// 1. Try sessionStorage (fast, set by ForgeResult on navigation)
// 2. Fallback: GET /api/v1/forge/sessions/{sessionId}/info
// 3. If 404 or session expired: show error state with "re-analyze" guidance
```

**Session expiry handling**:
- Forge sessions have 30min Redis TTL
- If `GET /sessions/{id}/info` returns 404, show: "La sesion ha expirado. Vuelve al chat para analizar el documento de nuevo."
- No polling or heartbeat — sessions are short-lived by design

### 3. Forge Service

**File**: `frontend/apps/on-premise/src/lib/services/forge.service.ts`

```typescript
export const forgeService = {
  analyzeDocument: async (documentId: string, userIntent?: string) => {
    // POST /api/v1/forge/analyze
    // Body: { document_id, user_intent }
    // Returns: { session_id, source_title, fields[], confidence, document_type }
  },

  renderDocument: async (sessionId: string, fieldValues: Record<string, string>, outputFormats?: string[]) => {
    // POST /api/v1/forge/render
    // Body: { session_id, field_values, output_formats }
    // Returns: { session_id, outputs: { docx?: OutputInfo, pdf?: OutputInfo }, document_title }
  },

  persistDocument: async (sessionId: string, options?: {
    persist_formats?: string[],    // default: ["docx"]
    folder_path?: string,          // target folder in GCS
    index_in_weaviate?: boolean,   // default: true
  }) => {
    // POST /api/v1/forge/persist
    // Body: { session_id, ...options } — proxy injects tenant_id + user_id
    // Returns: { document_id, gcs_paths, weaviate_indexed, indexed_document_id? }
  },

  getSessionInfo: async (sessionId: string) => {
    // GET /api/v1/forge/sessions/{sessionId}/info
    // Returns: ForgeSession
  },

  downloadDocument: async (sessionId: string, format: 'docx' | 'pdf') => {
    // GET /api/v1/forge/sessions/{sessionId}/download?format={format}
    // Returns: Blob
  },
}
```

### 4. Types

**File**: `frontend/apps/on-premise/src/lib/types/emma.ts` (extend existing)

```typescript
// --- Document Forge ---

// Matches backend FieldType enum + frontend-only 'enum' extension
type ForgeFieldType = 'text' | 'date' | 'number' | 'currency' | 'name' | 'address' | 'email' | 'phone' | 'enum'
type ForgeSessionStatus = 'analyzed' | 'prepared' | 'rendered' | 'persisted'

interface ForgeField {
  field_name: string
  label: string
  field_type: ForgeFieldType
  current_value: string
  required: boolean
  description?: string
  context_hint?: string       // surrounding text showing where the field appears (tooltip/help)
  suggested_value?: string    // LLM suggestion based on user intent (pre-populate form)
  options?: string[]          // for enum type (frontend-only)
}

// Form rendering: name/address/phone → text input, email → email input,
// date → date picker, number/currency → number input, enum → Select

interface ForgeSession {
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
  status: ForgeSessionStatus
  field_values?: Record<string, string>
  outputs?: Record<string, ForgeOutputInfo>
  created_at: string
  updated_at?: string
}

interface ForgeOutputInfo {
  download_url: string
  size_bytes: number
  format: string
}

interface ForgeAnalyzeResponse {
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
}

interface ForgeRenderResponse {
  session_id: string
  outputs: Record<string, ForgeOutputInfo>
  document_title: string
  fields_filled: number
}

interface ForgePersistResponse {
  document_id: string
  gcs_paths: Record<string, string>
  weaviate_indexed: boolean
  indexed_document_id?: string
}
```

## SSE Event Mapping

**File**: `backend/microservices/emma-agent-service/app/api/emma.py`

When the `forge_document` tool returns a result in the ReAct loop, the SSE mapper needs to emit a `forge_result` event type so the frontend renders `ForgeResult` instead of plain text.

The forge tool has three actions (`analyze`, `render`, `persist`) returning different data shapes. The SSE mapper differentiates by including the `action` field in the event data.

```python
# In _generate_langgraph_sse or equivalent SSE mapper:
if tool_name == "forge_document" and "session_id" in tool_data:
    # action is "analyze", "render", or "persist"
    yield {"event": "forge_result", "data": {**tool_data, "action": action}}
```

**Frontend mapping** (in `EmmaRenderChat.tsx`):
```typescript
case 'forge_result':
  // ForgeResult reads action from metadata to show fields list (analyze),
  // download buttons (render), or success message (persist)
  return <ForgeResult {...metadata.forge} />
```

## API Config Updates

**File**: `frontend/apps/on-premise/src/lib/config.ts`

Add forge endpoints to `API_CONFIG.ENDPOINTS`:
```typescript
FORGE_ANALYZE: '/forge/analyze',
FORGE_RENDER: '/forge/render',
FORGE_PERSIST: '/forge/persist',
FORGE_SESSION_INFO: (id: string) => `/forge/sessions/${id}/info`,
FORGE_SESSION_DOWNLOAD: (id: string, format: string) => `/forge/sessions/${id}/download?format=${format}`,
```

## User Flow

### Via Chat (primary)
1. User: "Renueva el contrato de Juan García"
2. Emma: smart_search → finds document → forge_document(action=analyze)
3. Chat renders `ForgeResult`: title, 8 detected fields, confidence 92%, link to `/forge/abc123`
4. User clicks "Editar campos" → navigates to `/forge/abc123`
5. User changes `fecha_fin` to 31/12/2026, `salario_anual` to 35000
6. User clicks "Generar documento" → loading spinner → preview appears
7. User clicks "Descargar PDF" or "Guardar en sistema"

### Via Chat (quick, no page visit)
1. User: "Renueva el contrato de Juan, cambia fecha fin a 31/12/2026"
2. Emma: smart_search → forge_document(analyze) → forge_document(render, field_values)
3. Chat renders `ForgeResult` with download buttons directly (status=rendered)
4. User downloads without visiting the detail page

## Out of Scope (v1)

- Standalone wizard (without chat) — future v2
- Batch document generation
- Template library/catalog
- SSE streaming for render (synchronous, ~2-5s)
- Field validation rules (beyond required/optional)
- Document diff view (before/after)
- Sidebar navigation entry (no dedicated section, accessed via chat)

## Dependencies

- `document-forge-service` running on :8013 (already in docker-compose)
- `DocumentViewer` component (already exists)
- `apiClient` from `lib/api-client.ts` (already exists)
- shadcn/ui components: Card, Badge, Button, Input, Select, Dialog (already available)

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `backend/app/api/v1/forge.py` | Main API proxy endpoints |
| `frontend/.../components/emma-chat/ForgeResult.tsx` | Chat result component |
| `frontend/.../app/forge/[sessionId]/page.tsx` | Detail page with field editor |
| `frontend/.../lib/services/forge.service.ts` | API service client |

### Modified Files
| File | Change |
|------|--------|
| `backend/app/main.py` or router registration | Register forge router |
| `backend/app/core/config.py` | Add forge config vars |
| `frontend/.../lib/types/emma.ts` | Add Forge types |
| `frontend/.../lib/config.ts` | Add forge endpoint URLs |
| `frontend/.../components/emma-chat/EmmaRenderChat.tsx` | Map `forge_result` → ForgeResult |
| `emma-agent-service/app/api/emma.py` | SSE event mapping for forge_result |
