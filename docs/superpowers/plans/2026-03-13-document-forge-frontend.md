# Document Forge Frontend UI — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add frontend UI for the document-forge-service — Main API proxy, chat component, detail page, and service client.

**Architecture:** Main API (8000) proxies 5 endpoints to document-forge-service (8013). ForgeResult component renders in chat. `/forge/[sessionId]` page provides field editing + preview + download. Client-side detector (like docgen) identifies forge results from `tools_used` in the `complete` SSE event.

**Tech Stack:** FastAPI (proxy), Next.js 15 App Router, TypeScript, shadcn/ui, Tailwind CSS, httpx

**Spec:** `docs/superpowers/specs/2026-03-13-document-forge-frontend-design.md`

---

## Chunk 1: Backend — Main API Proxy

### Task 1: Add forge config to Main API

**Files:**
- Modify: `backend/app/core/config.py:216-218` (after TEMPLATE_EDITOR_SERVICE_URL)

- [ ] **Step 1: Add config variables**

Add after line 218 in `backend/app/core/config.py`:

```python
# Document Forge Service (template-based document generation)
DOCUMENT_FORGE_SERVICE_URL: str = os.getenv(
    "DOCUMENT_FORGE_SERVICE_URL", "http://document-forge-service:8013"
)
DOCUMENT_FORGE_ENABLED: bool = os.getenv("DOCUMENT_FORGE_ENABLED", "true").lower() == "true"
```

- [ ] **Step 2: Verify config loads**

```bash
cd /home/nexus/git/nexus-documents-ia/backend
python -c "from app.core.config import settings; print(settings.DOCUMENT_FORGE_SERVICE_URL, settings.DOCUMENT_FORGE_ENABLED)"
```

Expected: `http://document-forge-service:8013 True`

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/config.py
git commit -m "feat(forge): add document forge config to Main API"
```

---

### Task 2: Create forge proxy router

**Files:**
- Create: `backend/app/api/v1/forge.py`

This file proxies 5 endpoints to document-forge-service. Follow the pattern from `backend/app/api/v1/emma.py`.

- [ ] **Step 1: Create the proxy router**

Create `backend/app/api/v1/forge.py`:

```python
"""Document Forge API proxy endpoints.

Proxies requests to document-forge-service (port 8013) for template-based
document generation with LLM-powered field detection.
"""

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import Response

from app.api.async_dependencies import get_current_tenant_id_async, get_current_user_async
from app.core.config import settings
from app.db.models import User

logger = logging.getLogger(__name__)
router = APIRouter()

FORGE_SERVICE_URL = settings.DOCUMENT_FORGE_SERVICE_URL.rstrip("/")
FORGE_TIMEOUT = httpx.Timeout(120.0)


def _forge_headers() -> dict:
    return {"X-API-Key": settings.MICROSERVICES_API_KEY or ""}


def _rewrite_download_urls(data: dict, prefix: str = "/api/v1/forge") -> dict:
    """Rewrite forge-relative download_url paths to Main API paths."""
    outputs = data.get("outputs", {})
    for fmt_key, info in outputs.items():
        url = info.get("download_url", "")
        if url and url.startswith("/sessions/"):
            info["download_url"] = f"{prefix}{url}"
    return data


@router.post("/analyze")
async def forge_analyze(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
    file: Optional[UploadFile] = File(None),
    document_id: Optional[str] = Form(None),
    user_intent: str = Form("modification"),
    max_fields: int = Form(30),
):
    """Analyze a DOCX document to detect variable fields.

    Accepts either a file upload (multipart) or a document_id to fetch from storage.
    """
    if not settings.DOCUMENT_FORGE_ENABLED:
        raise HTTPException(status_code=503, detail="Document Forge is disabled")

    try:
        form_data = {
            "tenant_id": tenant_id,
            "user_id": str(current_user.id),
            "user_intent": user_intent,
            "max_fields": str(max_fields),
        }
        if document_id:
            form_data["document_id"] = document_id

        files = {}
        if file:
            content = await file.read()
            files["file"] = (file.filename, content, file.content_type or "application/octet-stream")

        async with httpx.AsyncClient(timeout=FORGE_TIMEOUT) as client:
            resp = await client.post(
                f"{FORGE_SERVICE_URL}/analyze",
                data=form_data,
                files=files if files else None,
                headers=_forge_headers(),
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Forge analyze proxy error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render")
async def forge_render(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """Render document with new field values."""
    if not settings.DOCUMENT_FORGE_ENABLED:
        raise HTTPException(status_code=503, detail="Document Forge is disabled")

    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)

        async with httpx.AsyncClient(timeout=FORGE_TIMEOUT) as client:
            resp = await client.post(
                f"{FORGE_SERVICE_URL}/render",
                json=body,
                headers={**_forge_headers(), "Content-Type": "application/json"},
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        data = resp.json()
        return _rewrite_download_urls(data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Forge render proxy error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persist")
async def forge_persist(
    request: Request,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """Persist generated document to GCS and index in Weaviate."""
    if not settings.DOCUMENT_FORGE_ENABLED:
        raise HTTPException(status_code=503, detail="Document Forge is disabled")

    try:
        body = await request.json()
        body["tenant_id"] = tenant_id
        body["user_id"] = str(current_user.id)

        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.post(
                f"{FORGE_SERVICE_URL}/persist",
                json=body,
                headers={**_forge_headers(), "Content-Type": "application/json"},
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Forge persist proxy error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/info")
async def forge_session_info(
    session_id: str,
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """Get forge session metadata."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.get(
                f"{FORGE_SERVICE_URL}/sessions/{session_id}/info",
                headers=_forge_headers(),
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Forge session info proxy error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}/download")
async def forge_session_download(
    session_id: str,
    format: str = "docx",
    tenant_id: str = Depends(get_current_tenant_id_async),
    current_user: User = Depends(get_current_user_async),
):
    """Download generated document (DOCX or PDF)."""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            resp = await client.get(
                f"{FORGE_SERVICE_URL}/sessions/{session_id}/download",
                params={"format": format},
                headers=_forge_headers(),
            )

        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        content_type = resp.headers.get("content-type", "application/octet-stream")
        return Response(
            content=resp.content,
            media_type=content_type,
            headers={
                k: v for k, v in resp.headers.items()
                if k.lower() in ("content-disposition", "content-length")
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Forge download proxy error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/nexus/git/nexus-documents-ia/backend
python -c "from app.api.v1.forge import router; print(f'{len(router.routes)} routes')"
```

Expected: `5 routes`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/forge.py
git commit -m "feat(forge): add Main API proxy router for document-forge-service"
```

---

### Task 3: Register forge router

**Files:**
- Modify: `backend/app/api/api.py:198-199` (after prompts router)

- [ ] **Step 1: Add import and router registration**

Add after line 199 in `backend/app/api/api.py` (after `logger.debug("Prompt management routes enabled")`):

```python
# Document Forge - Template-based document generation
from app.api.v1 import forge
api_router.include_router(forge.router, prefix="/forge", tags=["document-forge"])
logger.debug("Document Forge routes enabled")
```

- [ ] **Step 2: Verify router registration**

```bash
cd /home/nexus/git/nexus-documents-ia/backend
python -c "from app.api.api import api_router; print([r.path for r in api_router.routes if 'forge' in str(r.path)])"
```

Expected: paths containing `/forge/analyze`, `/forge/render`, etc.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/api.py
git commit -m "feat(forge): register forge proxy router in Main API"
```

---

## Chunk 2: Frontend — Types, Service, Config

### Task 4: Add forge types

**Files:**
- Modify: `frontend/apps/on-premise/src/lib/types/emma.ts:17` (add to EmmaMessageType)
- Modify: `frontend/apps/on-premise/src/lib/types/emma.ts:251` (after DocGenMetadata)

- [ ] **Step 1: Add `forge_result` to EmmaMessageType**

In `frontend/apps/on-premise/src/lib/types/emma.ts`, add `'forge_result'` to the `EmmaMessageType` union (after line 17 `'docgen_result'`):

```typescript
  | 'forge_result'
```

- [ ] **Step 2: Add forge interfaces after DocGenMetadata (after line 251)**

```typescript
// --- Document Forge (template-based document modification) ---

export type ForgeFieldType = 'text' | 'date' | 'number' | 'currency' | 'name' | 'address' | 'email' | 'phone' | 'enum'
export type ForgeSessionStatus = 'analyzed' | 'prepared' | 'rendered' | 'persisted'
export type ForgeAction = 'analyze' | 'render' | 'persist'

export interface ForgeField {
  field_name: string
  label: string
  field_type: ForgeFieldType
  current_value: string
  required: boolean
  description?: string
  context_hint?: string
  suggested_value?: string
  options?: string[]
}

export interface ForgeOutputInfo {
  download_url: string
  size_bytes: number
  format: string
}

export interface ForgeMetadata {
  action: ForgeAction
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
  status: ForgeSessionStatus
  field_values?: Record<string, string>
  outputs?: Record<string, ForgeOutputInfo>
  created_at?: string
  updated_at?: string
  fields_filled?: number
  document_title?: string
  // persist results
  document_id?: string
  gcs_paths?: Record<string, string>
  weaviate_indexed?: boolean
}
```

- [ ] **Step 3: Add `forge` field to EmmaMessage interface**

In the `EmmaMessage` interface (around line 260), add after `docgen?: DocGenMetadata`:

```typescript
  forge?: ForgeMetadata
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npx tsc --noEmit --project apps/on-premise/tsconfig.json 2>&1 | head -20
```

Expected: No errors related to forge types.

- [ ] **Step 5: Commit**

```bash
git add frontend/apps/on-premise/src/lib/types/emma.ts
git commit -m "feat(forge): add Document Forge types to emma.ts"
```

---

### Task 5: Add forge endpoints to config

**Files:**
- Modify: `frontend/apps/on-premise/src/lib/config.ts:78` (after EMMA_NOTIFICATIONS_READ_ALL)

- [ ] **Step 1: Add forge endpoint constants**

Add after line 78 (`EMMA_NOTIFICATIONS_READ_ALL`) in `config.ts`:

```typescript
    // Document Forge
    FORGE_ANALYZE: '/forge/analyze',
    FORGE_RENDER: '/forge/render',
    FORGE_PERSIST: '/forge/persist',
    FORGE_SESSION_INFO: (id: string) => `/forge/sessions/${id}/info`,
    FORGE_SESSION_DOWNLOAD: (id: string, format: string) => `/forge/sessions/${id}/download?format=${format}`,
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/lib/config.ts
git commit -m "feat(forge): add forge endpoint URLs to frontend config"
```

---

### Task 6: Create forge service

**Files:**
- Create: `frontend/apps/on-premise/src/lib/services/forge.service.ts`

- [ ] **Step 1: Create the service file**

```typescript
/**
 * Document Forge Service
 * Client for template-based document modification via Main API proxy.
 *
 * IMPORTANT: apiClient returns { data, error, status } — it never throws.
 * Always check response.error, never use try/catch around apiClient calls.
 */

import { apiClient } from '@/lib/api-client'
import { API_CONFIG } from '@/lib/config'
import type { ForgeMetadata, ForgeField, ForgeOutputInfo, ForgeSessionStatus } from '@/lib/types/emma'

// --- Response types (from forge-service, proxied through Main API) ---

export interface ForgeAnalyzeResponse {
  session_id: string
  source_title: string
  document_type: string
  confidence: number
  fields: ForgeField[]
}

export interface ForgeRenderResponse {
  session_id: string
  outputs: Record<string, ForgeOutputInfo>
  document_title: string
  fields_filled: number
}

export interface ForgePersistResponse {
  document_id: string
  gcs_paths: Record<string, string>
  weaviate_indexed: boolean
  indexed_document_id?: string
}

export interface ForgeSessionInfo {
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

// --- Service functions ---
// apiClient never throws — check response.error after each call.

export async function analyzeDocument(
  documentId: string,
  userIntent: string = 'modification',
): Promise<{ data: ForgeAnalyzeResponse | null; error: string | null }> {
  const formData = new FormData()
  formData.append('document_id', documentId)
  formData.append('user_intent', userIntent)

  // NOTE: apiClient sets Content-Type: application/json by default.
  // Passing FormData makes axios auto-detect multipart/form-data.
  const response = await apiClient.post<ForgeAnalyzeResponse>(
    API_CONFIG.ENDPOINTS.FORGE_ANALYZE,
    formData,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function renderDocument(
  sessionId: string,
  fieldValues: Record<string, string>,
  outputFormats: string[] = ['docx', 'pdf'],
  documentTitle?: string,
): Promise<{ data: ForgeRenderResponse | null; error: string | null }> {
  const body: Record<string, any> = {
    session_id: sessionId,
    field_values: fieldValues,
    output_formats: outputFormats,
  }
  if (documentTitle) body.document_title = documentTitle

  const response = await apiClient.post<ForgeRenderResponse>(
    API_CONFIG.ENDPOINTS.FORGE_RENDER,
    body,
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function persistDocument(
  sessionId: string,
  options?: {
    persist_formats?: string[]
    folder_path?: string
    index_in_weaviate?: boolean
  },
): Promise<{ data: ForgePersistResponse | null; error: string | null }> {
  const body: Record<string, any> = { session_id: sessionId, ...options }
  const response = await apiClient.post<ForgePersistResponse>(
    API_CONFIG.ENDPOINTS.FORGE_PERSIST,
    body,
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function getSessionInfo(
  sessionId: string,
): Promise<{ data: ForgeSessionInfo | null; error: string | null }> {
  const response = await apiClient.get<ForgeSessionInfo>(
    API_CONFIG.ENDPOINTS.FORGE_SESSION_INFO(sessionId),
  )
  if (response.error) return { data: null, error: response.error }
  return { data: response.data, error: null }
}

export async function downloadDocument(
  sessionId: string,
  format: 'docx' | 'pdf' = 'docx',
): Promise<void> {
  const response = await apiClient.get(
    API_CONFIG.ENDPOINTS.FORGE_SESSION_DOWNLOAD(sessionId, format),
    { responseType: 'blob' },
  )
  if (response.error || !response.data) {
    console.error('Download failed:', response.error)
    return
  }
  const blob = new Blob([response.data as BlobPart])
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `document.${format}`
  document.body.appendChild(a)
  a.click()
  window.URL.revokeObjectURL(url)
  document.body.removeChild(a)
}

/**
 * Save forge metadata to sessionStorage for detail page recovery.
 * Called by ForgeResult before navigating to /forge/[sessionId].
 */
export function cacheForgeSession(sessionId: string, data: ForgeMetadata): void {
  if (typeof window === 'undefined') return
  sessionStorage.setItem(`forge_session_${sessionId}`, JSON.stringify(data))
}

/**
 * Recover forge session from sessionStorage (fast) or API (fallback).
 */
export function getCachedForgeSession(sessionId: string): ForgeMetadata | null {
  if (typeof window === 'undefined') return null
  const cached = sessionStorage.getItem(`forge_session_${sessionId}`)
  if (!cached) return null
  try {
    return JSON.parse(cached)
  } catch {
    return null
  }
}
```

- [ ] **Step 2: Verify imports resolve**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npx tsc --noEmit --project apps/on-premise/tsconfig.json 2>&1 | grep -i forge | head -10
```

Expected: No forge-related errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/lib/services/forge.service.ts
git commit -m "feat(forge): add forge service client with session caching"
```

---

## Chunk 3: Frontend — ForgeResult Chat Component

### Task 7: Create ForgeResult component

**Files:**
- Create: `frontend/apps/on-premise/src/components/emma-chat/ForgeResult.tsx`

This component renders forge tool results inline in the chat. Informative only — links to `/forge/[sessionId]` for editing.

- [ ] **Step 1: Create the component**

```typescript
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconFileText, IconDownload, IconEdit, IconCheck,
  IconAlertCircle, IconChevronDown, IconChevronUp,
} from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import type { ForgeMetadata, ForgeField } from '@/lib/types/emma'
import { cacheForgeSession, downloadDocument } from '@/lib/services/forge.service'

interface ForgeResultProps {
  metadata: ForgeMetadata
}

function getConfidenceColor(confidence: number): string {
  if (confidence >= 0.8) return 'text-emerald-600'
  if (confidence >= 0.6) return 'text-amber-500'
  return 'text-red-500'
}

function getConfidenceBadge(confidence: number) {
  if (confidence >= 0.8) return { variant: 'default' as const, label: 'Alta' }
  if (confidence >= 0.6) return { variant: 'secondary' as const, label: 'Media' }
  return { variant: 'destructive' as const, label: 'Baja' }
}

function getStatusBadge(status: string) {
  switch (status) {
    case 'analyzed': return { variant: 'outline' as const, label: 'Analizado' }
    case 'prepared': return { variant: 'outline' as const, label: 'Preparado' }
    case 'rendered': return { variant: 'default' as const, label: 'Generado' }
    case 'persisted': return { variant: 'default' as const, label: 'Guardado' }
    default: return { variant: 'secondary' as const, label: status }
  }
}

const MAX_FIELDS_SHOWN = 8

export function ForgeResult({ metadata }: ForgeResultProps) {
  const router = useRouter()
  const [showAllFields, setShowAllFields] = useState(false)

  const {
    action, session_id, source_title, document_type,
    confidence, fields, status, outputs, fields_filled,
    document_id, gcs_paths, weaviate_indexed,
  } = metadata

  const confidenceBadge = getConfidenceBadge(confidence)
  const statusBadge = getStatusBadge(status)

  const handleEditClick = () => {
    cacheForgeSession(session_id, metadata)
    router.push(`/forge/${session_id}`)
  }

  const handleDownload = (format: 'docx' | 'pdf') => {
    downloadDocument(session_id, format)
  }

  // --- Persist result (simple success message) ---
  if (action === 'persist') {
    return (
      <Card className="border-emerald-200 bg-emerald-50/50">
        <CardContent className="p-4">
          <div className="flex items-center gap-2">
            <IconCheck className="h-5 w-5 text-emerald-600" />
            <span className="font-medium text-emerald-800">Documento guardado permanentemente</span>
          </div>
          {gcs_paths && Object.keys(gcs_paths).length > 0 && (
            <div className="mt-2 text-sm text-muted-foreground">
              {Object.entries(gcs_paths).map(([fmt, path]) => (
                <div key={fmt}>{fmt.toUpperCase()}: <code className="text-xs">{path}</code></div>
              ))}
            </div>
          )}
          {weaviate_indexed && (
            <Badge variant="outline" className="mt-2">Indexado en busqueda</Badge>
          )}
        </CardContent>
      </Card>
    )
  }

  // --- Render result (download available) ---
  if (action === 'render' && outputs) {
    return (
      <Card>
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IconFileText className="h-5 w-5 text-primary" />
              <span className="font-medium">{metadata.document_title || source_title}</span>
            </div>
            <Badge {...statusBadge}>{statusBadge.label}</Badge>
          </div>

          {fields_filled != null && (
            <p className="text-sm text-muted-foreground">
              {fields_filled} campos rellenados
            </p>
          )}

          <div className="flex gap-2 flex-wrap">
            {outputs.docx && (
              <Button size="sm" variant="outline" onClick={() => handleDownload('docx')}>
                <IconDownload className="h-4 w-4 mr-1" /> DOCX ({(outputs.docx.size_bytes / 1024).toFixed(0)} KB)
              </Button>
            )}
            {outputs.pdf && (
              <Button size="sm" variant="outline" onClick={() => handleDownload('pdf')}>
                <IconDownload className="h-4 w-4 mr-1" /> PDF ({(outputs.pdf.size_bytes / 1024).toFixed(0)} KB)
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={handleEditClick}>
              <IconEdit className="h-4 w-4 mr-1" /> Ver detalle
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  // --- Analyze result (fields detected, link to edit) ---
  const visibleFields = showAllFields ? fields : fields.slice(0, MAX_FIELDS_SHOWN)
  const hiddenCount = fields.length - MAX_FIELDS_SHOWN

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <IconFileText className="h-5 w-5 text-primary" />
            <span className="font-medium">{source_title}</span>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline">{document_type}</Badge>
            <Badge variant={confidenceBadge.variant}>
              {(confidence * 100).toFixed(0)}% {confidenceBadge.label}
            </Badge>
          </div>
        </div>

        {/* Fields list */}
        <div className="space-y-1">
          <p className="text-sm font-medium text-muted-foreground">
            Campos detectados ({fields.length}):
          </p>
          <div className="grid gap-1">
            {visibleFields.map((field) => (
              <div key={field.field_name} className="flex items-center justify-between text-sm px-2 py-1 rounded bg-muted/50">
                <span className="font-medium">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-1">*</span>}
                </span>
                <code className="text-xs text-muted-foreground max-w-[200px] truncate">
                  {field.current_value}
                </code>
              </div>
            ))}
          </div>
          {hiddenCount > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="text-xs"
              onClick={() => setShowAllFields(!showAllFields)}
            >
              {showAllFields ? (
                <><IconChevronUp className="h-3 w-3 mr-1" /> Mostrar menos</>
              ) : (
                <><IconChevronDown className="h-3 w-3 mr-1" /> +{hiddenCount} campos mas</>
              )}
            </Button>
          )}
        </div>

        {/* Action */}
        <Button size="sm" onClick={handleEditClick}>
          <IconEdit className="h-4 w-4 mr-1" /> Editar campos
        </Button>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/ForgeResult.tsx
git commit -m "feat(forge): add ForgeResult chat component"
```

---

### Task 8: Wire ForgeResult into EmmaRenderChat

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx:16` (add import)
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx:178` (add rendering case)

- [ ] **Step 1: Add import**

After line 16 (`import { DocGenResult } from './DocGenResult'`), add:

```typescript
import { ForgeResult } from './ForgeResult'
```

- [ ] **Step 2: Add rendering case**

After the `docgen_result` block (around line 220, after the closing of the docgen conditional), add:

```typescript
  // Document Forge result — analyze/render/persist
  if (message.type === 'forge_result' && message.forge) {
    const forgeSlmSteps = message.metadata?.slmThinkingSteps || []
    return (
      <div className="w-full">
        <div className="space-y-2 p-3 bg-primary/5 rounded-lg border border-primary/20">
          <div className="flex items-center gap-2">
            <img src="/emma-avatar.png" alt="Emma" className="h-5 w-5 rounded-full object-cover object-top" />
            <span className="text-xs font-mono text-primary uppercase tracking-wide">EMMA:</span>
          </div>
          {forgeSlmSteps.length > 0 && (
            <ReasoningCollapsible
              steps={forgeSlmSteps.map((s: SLMThinkingStep) => ({
                type: s.type as ReasoningStep['type'],
                content: s.content,
                detail: s.detail,
                entities: s.entities,
                confidence: s.confidence,
              }))}
              isActive={false}
            />
          )}
          <ForgeResult metadata={message.forge} />
        </div>
      </div>
    )
  }
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npx tsc --noEmit --project apps/on-premise/tsconfig.json 2>&1 | grep -i "forge\|RenderChat" | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaRenderChat.tsx
git commit -m "feat(forge): wire ForgeResult into EmmaRenderChat"
```

---

## Chunk 4: Frontend — Forge Detail Page

### Task 9: Create forge detail page

**Files:**
- Create: `frontend/apps/on-premise/src/app/forge/[sessionId]/page.tsx`

Full-page view for editing fields and generating documents. Follows the pattern from `/app/verified/[sessionId]/page.tsx`.

- [ ] **Step 1: Create the page component**

```typescript
'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  IconFileText, IconDownload, IconDeviceFloppy, IconArrowLeft,
  IconRefresh, IconAlertCircle, IconCheck, IconClock,
} from '@tabler/icons-react'
import {
  SidebarProvider, SidebarInset,
} from '@nexus/shared/ui'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { AppSidebar } from '@/components/layout/app-sidebar'
import { PageHeader } from '@/components/layout/page-header'
import {
  getCachedForgeSession,
  getSessionInfo,
  renderDocument,
  persistDocument,
  downloadDocument,
} from '@/lib/services/forge.service'
import type { ForgeField, ForgeMetadata, ForgeOutputInfo } from '@/lib/types/emma'

type PageState = 'loading' | 'editing' | 'rendering' | 'rendered' | 'persisting' | 'persisted' | 'error' | 'expired'

function getInputType(fieldType: string): string {
  switch (fieldType) {
    case 'date': return 'date'
    case 'number':
    case 'currency': return 'number'
    case 'email': return 'email'
    case 'phone': return 'tel'
    default: return 'text'
  }
}

function getConfidenceColor(c: number): string {
  if (c >= 0.8) return 'text-emerald-600'
  if (c >= 0.6) return 'text-amber-500'
  return 'text-red-500'
}

export default function ForgeDetailPage() {
  const params = useParams()
  const sessionId = params.sessionId as string

  const [pageState, setPageState] = useState<PageState>('loading')
  const [error, setError] = useState<string | null>(null)

  // Session data
  const [sourceTitle, setSourceTitle] = useState('')
  const [documentType, setDocumentType] = useState('')
  const [confidence, setConfidence] = useState(0)
  const [fields, setFields] = useState<ForgeField[]>([])
  const [outputs, setOutputs] = useState<Record<string, ForgeOutputInfo>>({})

  // Form state: field_name → value
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({})

  // Load session
  useEffect(() => {
    async function loadSession() {
      setPageState('loading')
      setError(null)

      // Try sessionStorage first (fast)
      const cached = getCachedForgeSession(sessionId)
      if (cached) {
        applySessionData(cached)
        return
      }

      // Fallback: API
      const response = await getSessionInfo(sessionId)
      if (response.error) {
        if (response.error.includes('404') || response.error.includes('not found')) {
          setPageState('expired')
        } else {
          setError(response.error)
          setPageState('error')
        }
        return
      }

      if (response.data) {
        applySessionData({
          action: 'analyze',
          session_id: sessionId,
          source_title: response.data.source_title,
          document_type: response.data.document_type,
          confidence: response.data.confidence,
          fields: response.data.fields,
          status: response.data.status as any,
          field_values: response.data.field_values,
          outputs: response.data.outputs,
        })
      }
    }

    loadSession()
  }, [sessionId])

  function applySessionData(data: ForgeMetadata) {
    setSourceTitle(data.source_title)
    setDocumentType(data.document_type)
    setConfidence(data.confidence)
    setFields(data.fields || [])

    // Pre-populate form: use suggested_value > current_value
    const initial: Record<string, string> = {}
    for (const f of data.fields || []) {
      initial[f.field_name] = f.suggested_value || f.current_value || ''
    }
    if (data.field_values) {
      Object.assign(initial, data.field_values)
    }
    setFieldValues(initial)

    if (data.outputs && Object.keys(data.outputs).length > 0) {
      setOutputs(data.outputs)
      setPageState(data.status === 'persisted' ? 'persisted' : 'rendered')
    } else {
      setPageState('editing')
    }
  }

  function handleFieldChange(fieldName: string, value: string) {
    setFieldValues(prev => ({ ...prev, [fieldName]: value }))
  }

  async function handleRender() {
    setPageState('rendering')
    setError(null)
    try {
      const response = await renderDocument(sessionId, fieldValues, ['docx', 'pdf'])
      if (response.error) {
        setError(response.error)
      } else if (response.data) {
        setOutputs(response.data.outputs)
        setPageState('rendered')
        return
      }
    } catch (err: any) {
      setError(err.message || 'Error inesperado')
    }
    // If we get here, there was an error — restore editing state
    if (pageState === 'rendering') setPageState('editing')
  }

  async function handlePersist() {
    setPageState('persisting')
    setError(null)
    try {
      const response = await persistDocument(sessionId)
      if (response.error) {
        setError(response.error)
      } else {
        setPageState('persisted')
        return
      }
    } catch (err: any) {
      setError(err.message || 'Error inesperado')
    }
    // If we get here, there was an error — restore rendered state
    if (pageState === 'persisting') setPageState('rendered')
  }

  function handleDownload(format: 'docx' | 'pdf') {
    downloadDocument(sessionId, format)
  }

  // --- Expired state ---
  if (pageState === 'expired') {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PageHeader title="Document Forge" />
          <div className="flex flex-col items-center justify-center p-12 text-center">
            <IconClock className="h-12 w-12 text-muted-foreground mb-4" />
            <h2 className="text-lg font-semibold mb-2">Sesion expirada</h2>
            <p className="text-muted-foreground mb-4">
              La sesion ha expirado (TTL 30 min). Vuelve al chat para analizar el documento de nuevo.
            </p>
            <Link href="/">
              <Button><IconArrowLeft className="h-4 w-4 mr-2" /> Volver al chat</Button>
            </Link>
          </div>
        </SidebarInset>
      </SidebarProvider>
    )
  }

  // --- Loading state ---
  if (pageState === 'loading') {
    return (
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset>
          <PageHeader title="Document Forge" />
          <div className="flex items-center justify-center p-12">
            <IconRefresh className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">Cargando sesion...</span>
          </div>
        </SidebarInset>
      </SidebarProvider>
    )
  }

  // --- Main layout ---
  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <PageHeader title="Document Forge" />
        <div className="p-6 max-w-4xl mx-auto space-y-6">

          {/* Header Card */}
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <IconFileText className="h-6 w-6 text-primary" />
                  <div>
                    <h1 className="text-lg font-semibold">{sourceTitle}</h1>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="outline">{documentType}</Badge>
                      <span className={`text-sm font-medium ${getConfidenceColor(confidence)}`}>
                        {(confidence * 100).toFixed(0)}% confianza
                      </span>
                    </div>
                  </div>
                </div>
                <Link href="/">
                  <Button variant="ghost" size="sm">
                    <IconArrowLeft className="h-4 w-4 mr-1" /> Chat
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <Card className="border-red-200 bg-red-50/50">
              <CardContent className="p-4 flex items-center gap-2">
                <IconAlertCircle className="h-5 w-5 text-red-500" />
                <span className="text-red-700">{error}</span>
              </CardContent>
            </Card>
          )}

          {/* Fields Form */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Campos del documento ({fields.length})</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {fields.map((field) => (
                <div key={field.field_name} className="space-y-1.5">
                  <Label htmlFor={field.field_name} className="flex items-center gap-1">
                    {field.label}
                    {field.required && <span className="text-red-500">*</span>}
                    <Badge variant="outline" className="ml-2 text-[10px]">{field.field_type}</Badge>
                  </Label>
                  {field.context_hint && (
                    <p className="text-xs text-muted-foreground">{field.context_hint}</p>
                  )}
                  {field.field_type === 'enum' && field.options ? (
                    <Select
                      value={fieldValues[field.field_name] || ''}
                      onValueChange={(value) => handleFieldChange(field.field_name, value)}
                      disabled={pageState === 'rendering' || pageState === 'persisting'}
                    >
                      <SelectTrigger id={field.field_name}>
                        <SelectValue placeholder={field.current_value || 'Seleccionar...'} />
                      </SelectTrigger>
                      <SelectContent>
                        {field.options.map((opt) => (
                          <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Input
                      id={field.field_name}
                      type={getInputType(field.field_type)}
                      value={fieldValues[field.field_name] || ''}
                      placeholder={field.current_value}
                      onChange={(e) => handleFieldChange(field.field_name, e.target.value)}
                      disabled={pageState === 'rendering' || pageState === 'persisting'}
                    />
                  )}
                </div>
              ))}
            </CardContent>
          </Card>

          {/* Persisted success */}
          {pageState === 'persisted' && (
            <Card className="border-emerald-200 bg-emerald-50/50">
              <CardContent className="p-4 flex items-center gap-2">
                <IconCheck className="h-5 w-5 text-emerald-600" />
                <span className="text-emerald-800 font-medium">
                  Documento guardado permanentemente e indexado en el sistema.
                </span>
              </CardContent>
            </Card>
          )}

          {/* Action Bar */}
          <div className="flex items-center gap-3 flex-wrap sticky bottom-4 bg-background/95 backdrop-blur p-4 rounded-lg border shadow-sm">
            <Button
              onClick={handleRender}
              disabled={pageState === 'rendering' || pageState === 'persisting'}
            >
              {pageState === 'rendering' ? (
                <><IconRefresh className="h-4 w-4 mr-2 animate-spin" /> Generando...</>
              ) : (
                <><IconFileText className="h-4 w-4 mr-2" /> Generar documento</>
              )}
            </Button>

            {(pageState === 'rendered' || pageState === 'persisted') && (
              <>
                <Separator orientation="vertical" className="h-8" />
                {outputs.docx && (
                  <Button variant="outline" size="sm" onClick={() => handleDownload('docx')}>
                    <IconDownload className="h-4 w-4 mr-1" /> DOCX
                  </Button>
                )}
                {outputs.pdf && (
                  <Button variant="outline" size="sm" onClick={() => handleDownload('pdf')}>
                    <IconDownload className="h-4 w-4 mr-1" /> PDF
                  </Button>
                )}
                {pageState !== 'persisted' && (
                  <>
                    <Separator orientation="vertical" className="h-8" />
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={handlePersist}
                      disabled={pageState === 'persisting'}
                    >
                      {pageState === 'persisting' ? (
                        <><IconRefresh className="h-4 w-4 mr-1 animate-spin" /> Guardando...</>
                      ) : (
                        <><IconDeviceFloppy className="h-4 w-4 mr-1" /> Guardar en sistema</>
                      )}
                    </Button>
                  </>
                )}
              </>
            )}
          </div>

        </div>
      </SidebarInset>
    </SidebarProvider>
  )
}
```

- [ ] **Step 2: Verify page renders without errors**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npx tsc --noEmit --project apps/on-premise/tsconfig.json 2>&1 | grep -i forge | head -10
```

- [ ] **Step 3: Commit**

```bash
git add frontend/apps/on-premise/src/app/forge/
git commit -m "feat(forge): add /forge/[sessionId] detail page with field editor"
```

---

## Chunk 5: Client-Side Forge Detection

The existing docgen detection pattern uses a **client-side detector** (`lib/utils/docgen-detector.ts`).
The `complete` SSE event carries `tools_used` — we check if `forge_document` is in that list.
No backend SSE changes needed.

### Task 10: Create forge detector utility

**Files:**
- Create: `frontend/apps/on-premise/src/lib/utils/forge-detector.ts`

- [ ] **Step 1: Create the forge detector**

```typescript
/**
 * Document Forge Detection Utility
 *
 * Detects whether an Emma response contains a forge_document tool result
 * and extracts the session_id from the answer text for API fetching.
 *
 * Pattern mirrors docgen-detector.ts but simpler: we detect by tool name
 * and extract the session_id from the synthesized answer text.
 */
import type { ForgeMetadata, ForgeAction } from '@/lib/types/emma'

// Session ID pattern: `abc123-def456` or similar UUID format in backticks
const SESSION_ID_PATTERN = /Session ID:\s*`([^`]+)`/i

// Forge action detection from answer text
const ANALYZE_MARKERS = /campos detectados|campos modificables|he detectado/i
const RENDER_MARKERS = /documento generado|campos rellenados|descargar/i
const PERSIST_MARKERS = /guardado permanentemente|indexado en/i

interface ForgeDetectionInput {
  content: string
  toolsUsed?: string[]
}

/**
 * Checks if the response is a forge_document result.
 * Primary detection: `forge_document` in tools_used.
 */
export function isForgeResult({ content, toolsUsed = [] }: ForgeDetectionInput): boolean {
  return toolsUsed.includes('forge_document')
}

/**
 * Extracts forge metadata from the synthesized answer text.
 * The session_id is extracted from text, then the full data
 * should be fetched via GET /forge/sessions/{id}/info.
 */
export function extractForgeMetadata(content: string, executionTimeMs?: number): ForgeMetadata | null {
  const sessionMatch = content.match(SESSION_ID_PATTERN)
  if (!sessionMatch) return null

  const sessionId = sessionMatch[1]

  // Detect action from answer text markers
  let action: ForgeAction = 'analyze'
  if (PERSIST_MARKERS.test(content)) action = 'persist'
  else if (RENDER_MARKERS.test(content)) action = 'render'

  // Extract basic info from text (will be enriched by API call)
  const titleMatch = content.match(/Documento (?:analizado|generado):\s*\*\*([^*]+)\*\*/i)
  const confidenceMatch = content.match(/Confianza:\s*(\d+)%/i)
  const typeMatch = content.match(/Tipo:\s*(\S+)/i)

  return {
    action,
    session_id: sessionId,
    source_title: titleMatch?.[1] || '',
    document_type: typeMatch?.[1] || '',
    confidence: confidenceMatch ? parseInt(confidenceMatch[1]) / 100 : 0,
    fields: [], // Will be populated by API call
    status: action === 'render' ? 'rendered' : action === 'persist' ? 'persisted' : 'analyzed',
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/apps/on-premise/src/lib/utils/forge-detector.ts
git commit -m "feat(forge): add client-side forge result detector"
```

---

### Task 11: Wire forge detection into EmmaChat.tsx

**Files:**
- Modify: `frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx`

The docgen detection happens at line ~783 in EmmaChat.tsx, inside the `complete` event handler.
Add forge detection **before** the docgen check (since forge_document is more specific).

- [ ] **Step 1: Add import**

Find the `isDocGenResult` import (near top of file) and add:

```typescript
import { isForgeResult, extractForgeMetadata } from '@/lib/utils/forge-detector'
```

- [ ] **Step 2: Add forge detection before docgen detection**

In the `complete` event handler (around line 782), before the `if (isDocGenResult(...))` block, add:

```typescript
                  // Detect forge_document tool result
                  if (isForgeResult({
                    content: finalContent,
                    toolsUsed: (data.final_result as any)?.tools_used,
                  })) {
                    const forgeMeta = extractForgeMetadata(finalContent, data.execution_time_ms)
                    if (forgeMeta) {
                      // Enrich with full session data via API (fire-and-forget)
                      getSessionInfo(forgeMeta.session_id).then(resp => {
                        if (resp.data) {
                          // Update message in place with enriched data
                          setMessages(prev => prev.map(m =>
                            m.id === msg.id ? {
                              ...m,
                              forge: {
                                ...forgeMeta,
                                fields: resp.data!.fields,
                                source_title: resp.data!.source_title || forgeMeta.source_title,
                                document_type: resp.data!.document_type || forgeMeta.document_type,
                                confidence: resp.data!.confidence || forgeMeta.confidence,
                                outputs: resp.data!.outputs,
                                status: resp.data!.status as any,
                              },
                            } : m
                          ))
                        }
                      })

                      return {
                        ...msg,
                        type: 'forge_result' as const,
                        content: finalContent,
                        forge: forgeMeta,
                        metadata: {
                          processing_time: data.execution_time_ms,
                          execution_time_ms: data.execution_time_ms,
                          tools_used: (data.final_result as any)?.tools_used || [],
                          slmThinkingSteps: finalSlmSteps.length > 0 ? finalSlmSteps : undefined,
                          slmIsThinking: false,
                          isStreaming: false,
                        },
                        suggestions: finalSuggestions,
                      }
                    }
                  }
```

Also add the import at the top of the file:

```typescript
import { getSessionInfo } from '@/lib/services/forge.service'
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npx tsc --noEmit --project apps/on-premise/tsconfig.json 2>&1 | grep -i "forge\|EmmaChat" | head -10
```

- [ ] **Step 4: Commit**

```bash
git add frontend/apps/on-premise/src/components/emma-chat/EmmaChat.tsx
git commit -m "feat(forge): wire forge detection into EmmaChat SSE handler"
```

---

## Chunk 6: Integration Testing

### Task 12: End-to-end verification

- [ ] **Step 1: Start services**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/docker
./start-dev.sh
```

Wait for all services to be healthy.

- [ ] **Step 2: Test Main API proxy — health check**

```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)

# Test forge service health via direct call
curl -s http://localhost:8013/health | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'])"

# Test Main API proxy (if forge health endpoint is exposed, otherwise test analyze)
curl -s -X POST http://localhost:8000/api/v1/forge/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: multipart/form-data" \
  -F "document_id=test" \
  -F "user_intent=modification" \
  > /tmp/forge_test.json
cat /tmp/forge_test.json
```

- [ ] **Step 3: Test frontend builds**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npm run build:on-premise 2>&1 | tail -20
```

Expected: Build succeeds with no forge-related errors.

- [ ] **Step 4: Test forge detail page loads**

Start frontend dev server and navigate to `/forge/test-session-id`. Should show "Sesion expirada" (since test-session-id doesn't exist). This confirms the page route works.

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
npm run dev:on-premise &
sleep 5
curl -s -k https://localhost:3001/forge/test-session-id | head -5
```

- [ ] **Step 5: Final commit**

```bash
git add -A
git status
# If there are any remaining changes, commit them
git commit -m "feat(forge): complete frontend integration for document-forge-service"
```

---

## Summary

| Task | Component | Files |
|------|-----------|-------|
| 1 | Main API config | `backend/app/core/config.py` |
| 2 | Forge proxy router | `backend/app/api/v1/forge.py` (new) |
| 3 | Register router | `backend/app/api/api.py` |
| 4 | Frontend types | `frontend/.../types/emma.ts` |
| 5 | Frontend config | `frontend/.../lib/config.ts` |
| 6 | Forge service | `frontend/.../services/forge.service.ts` (new) |
| 7 | ForgeResult component | `frontend/.../components/emma-chat/ForgeResult.tsx` (new) |
| 8 | Wire into EmmaRenderChat | `frontend/.../components/emma-chat/EmmaRenderChat.tsx` |
| 9 | Detail page | `frontend/.../app/forge/[sessionId]/page.tsx` (new) |
| 10 | Forge detector | `frontend/.../lib/utils/forge-detector.ts` (new) |
| 11 | Wire into EmmaChat SSE | `frontend/.../components/emma-chat/EmmaChat.tsx` |
| 12 | Integration testing | Manual verification |
