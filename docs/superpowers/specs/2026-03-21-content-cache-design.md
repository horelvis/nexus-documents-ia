# Content Cache — Design Spec (v2)

**Date:** 2026-03-21
**Status:** Approved (v2 — post-review)
**Scope:** Cache original files during indexation for offline preview/download when source connectors are unavailable
**Also:** Convert mcp-storage-server from MCP protocol to REST API (storage-service)

---

## Context

NouxCubeIA indexes documents from external sources (Alfresco, Google Drive, OneDrive, databases) via MCP connectors. The original files live exclusively on the source — no local copy is stored. When the source is unavailable (server down, network issue, credentials expired):

- **Preview fails** — cannot render the PDF/DOCX
- **Download fails** — cannot serve the file to the user
- **Re-indexing fails** — cannot re-process the document
- **RAG still works** — chunks are already in Weaviate with embeddings

This spec adds a content cache layer that stores original files during indexation. Preview and download fall back to cache when the source is unavailable.

---

## Important Notes

### mcp-storage-server -> storage-service conversion

The current `mcp-storage-server` speaks MCP protocol (SSE transport), not REST. It has no `POST /upload` or `GET /download` endpoints — only MCP tool calls. For service-to-service file operations (upload during indexation, download for fallback), MCP protocol is overkill.

This spec converts `mcp-storage-server` into `storage-service` — a standard FastAPI REST service that exposes `POST /files/{path}` and `GET /files/{path}` endpoints. The MCP protocol layer (`/sse`, `/messages/`) is removed entirely — it served no purpose for binary file storage. The underlying `LocalStorageService` and `GCSStorageService` remain unchanged.

### Path convention

`LocalStorageService._get_full_path()` automatically prepends `tenant-{tenant_id}/` to object names. To avoid double-prefixing, the `cached_path` stored in the database uses the object name WITHOUT the tenant prefix:

```
cached_path = "originals/{document_id}/{filename}"
Actual disk path = /app/storage/tenant-{tenant_id}/originals/{document_id}/{filename}
```

### Database updates from weaviate-service

weaviate-service has `DATABASE_URL` configured and can write directly to PostgreSQL. No need for an HTTP round-trip to main API to update `cached_path`.

---

## Architecture

### Indexation flow (new cache step)

```
MCP Connector downloads file
  -> file_bytes -> weaviate-service (index_from_connector)
    -> NEW: storage-service REST POST /files/originals/{doc_id}/{filename}
    -> NEW: Direct DB UPDATE indexed_documents SET cached_path = '...'
    -> existing: Docling extract -> chunks -> Weaviate -> AGE -> legal refs
```

### Preview/Download flow (fallback)

The download endpoint for connector documents is in `documents.py` at line ~447:

```python
content = await adapter.download_content(unified_doc)
```

This calls the MCP connector which proxies to Alfresco/GDrive. When the source is down, this raises an exception. The fallback wraps this call:

```
Frontend -> GET /api/v1/documents/{id}/content
  -> indexed_doc = get from DB
  -> Try 1: adapter.download_content(unified_doc)  [line ~447]
  -> Catch (source unavailable):
     -> Try 2: If indexed_doc.cached_path:
          -> storage-service GET /files/{cached_path}?tenant_id={tid}
     -> Try 3: 503 "Source unavailable and no cached copy"
```

### Connector type handling

| Connector type | Has file? | What to cache | Cache format |
|---------------|-----------|---------------|-------------|
| `alfresco` | Yes (PDF, DOCX) | Original file bytes | Binary as-is |
| `google_drive` | Yes (PDF, DOCX, Sheets) | Original file bytes | Binary as-is |
| `onedrive` | Yes (PDF, DOCX) | Original file bytes | Binary as-is |
| `database` | No (SQL query -> text) | Extracted text snapshot | `.txt` file |

---

## Component 1: Convert mcp-storage-server to storage-service

### Rename

```
backend/microservices/mcp-storage-server/ -> backend/microservices/storage-service/
docker-compose: service name mcp-storage -> storage-service
```

### New REST endpoints in main.py

Add to the Starlette app alongside existing `/health` and `/tools`:

```python
async def upload_file(request: Request):
    """REST endpoint: upload file bytes."""
    path = request.path_params["path"]
    tenant_id = request.query_params.get("tenant_id", "default")
    content = await request.body()

    from app.services.local_service import LocalStorageService
    storage = LocalStorageService()
    storage.initialize()
    result = await storage.upload_file(
        content=content,
        object_name=path,
        tenant_id=tenant_id,
    )
    return JSONResponse(result)


async def download_file(request: Request):
    """REST endpoint: download file bytes."""
    path = request.path_params["path"]
    tenant_id = request.query_params.get("tenant_id", "default")

    from app.services.local_service import LocalStorageService
    storage = LocalStorageService()
    storage.initialize()
    content = storage.download_file(
        object_name=path,
        tenant_id=tenant_id,
    )
    if content is None:
        return Response(status_code=404)
    return Response(content=content, media_type="application/octet-stream")


routes = [
    Route("/health", health_check, methods=["GET"]),
    Route("/files/{path:path}", upload_file, methods=["POST"]),
    Route("/files/{path:path}", download_file, methods=["GET"]),
]
```

The MCP protocol layer (`/sse`, `/messages/`, `/tools`) is removed entirely. The `app/server.py` (MCP server definition) and `app/tools/` (MCP tool definitions) can be deleted. Only `app/services/` (LocalStorageService, GCSStorageService) is kept.

---

## Component 2: Database Migration

New column on `indexed_documents`:

```sql
ALTER TABLE indexed_documents ADD COLUMN cached_path TEXT;
```

- `NULL` = no cache (legacy docs, or cache failed)
- `originals/{document_id}/{filename}` = object name (without tenant prefix — service adds it)

---

## Component 3: Cache during indexation

**File:** `backend/microservices/weaviate-service/app/api/weaviate.py`

New function called after `file_bytes = base64.b64decode(...)` (~line 829), before processing:

```python
async def _cache_original_file(
    tenant_id: str,
    document_id: str,
    filename: str,
    file_bytes: bytes,
) -> Optional[str]:
    """Cache original file in storage-service for offline access.

    Returns the cached_path (object_name without tenant prefix) or None if failed.
    """
    try:
        object_name = f"originals/{document_id}/{filename}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.storage_service_url}/files/{object_name}",
                params={"tenant_id": tenant_id},
                content=file_bytes,
            )
            response.raise_for_status()
        return object_name
    except Exception as e:
        logger.warning(f"Content cache failed for {document_id}: {e}")
        return None
```

For database connectors:

```python
async def _cache_extracted_text(
    tenant_id: str,
    document_id: str,
    extracted_text: str,
) -> Optional[str]:
    """Cache extracted text for database connector documents."""
    try:
        object_name = f"originals/{document_id}/extracted.txt"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{settings.storage_service_url}/files/{object_name}",
                params={"tenant_id": tenant_id},
                content=extracted_text.encode("utf-8"),
            )
            response.raise_for_status()
        return object_name
    except Exception as e:
        logger.warning(f"Text cache failed for {document_id}: {e}")
        return None
```

### Persisting cached_path (direct DB write)

weaviate-service already has `DATABASE_URL` configured. Direct SQL update:

```python
async def _update_cached_path(tenant_id: str, document_id: str, cached_path: str) -> None:
    """Update cached_path on indexed_documents via direct DB write."""
    try:
        import asyncpg
        conn = await asyncpg.connect(settings.database_url)
        await conn.execute(
            "UPDATE indexed_documents SET cached_path = $1 WHERE id = $2 AND tenant_id = $3",
            cached_path, uuid.UUID(document_id), uuid.UUID(tenant_id),
        )
        await conn.close()
    except Exception as e:
        logger.debug(f"Failed to update cached_path for {document_id}: {e}")
```

---

## Component 4: Download fallback

**File:** `backend/app/api/v1/documents.py`

In the connector download block (lines 418-471), wrap `adapter.download_content()` at line 447:

```python
    try:
        # Existing: download from source (Alfresco/GDrive)
        content = await adapter.download_content(unified_doc)
    except Exception as source_error:
        # NEW: Fallback to cached copy
        if indexed_doc.cached_path:
            logger.info(f"Source unavailable, falling back to cache: {indexed_doc.cached_path}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                cache_response = await client.get(
                    f"{settings.storage_service_url}/files/{indexed_doc.cached_path}",
                    params={"tenant_id": str(indexed_doc.tenant_id)},
                )
                if cache_response.status_code == 200:
                    content = cache_response.content
                else:
                    raise HTTPException(503, "Source unavailable and cache not found")
        else:
            logger.error(f"Source unavailable and no cache for {doc_id}: {source_error}")
            raise HTTPException(503, "Source unavailable and no cached copy available")
```

---

## Component 5: Preview fallback

**File:** `backend/app/api/v1/documents.py`

The preview endpoint (`/{doc_id}/preview`, line ~531) calls `DocumentPreviewService.generate_preview()` which expects a **local file path**. The preview flow is:

1. Download file bytes (from connector or cache)
2. Write to temp file
3. Pass temp path to Gotenberg for PDF conversion

The fallback logic is the same as Component 4 — get file bytes from cache when source fails. The preview service itself does not need modification. The fallback is at the call site where bytes are obtained, before passing to the preview service.

---

## Component 6: Docker-compose changes

**File:** `backend/docker/docker-compose.onpremise.yml`

### Rename service

```yaml
# OLD
mcp-storage:
    build:
      context: ../microservices/mcp-storage-server

# NEW
storage-service:
    build:
      context: ../microservices/storage-service
```

### Add dependency to weaviate-service

```yaml
weaviate-service:
    depends_on:
      ...
      storage-service:
        condition: service_healthy
    environment:
      ...
      - STORAGE_SERVICE_URL=${STORAGE_SERVICE_URL:-http://storage-service:8000}
```

### Add dependency to api service

Update existing `mcp-storage` references to `storage-service`.

### Config in weaviate-service

Add to `weaviate-service/app/core/config.py`:

```python
storage_service_url: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8000")
```

---

## Files Changed Summary

### Renamed (1)

| From | To |
|------|-----|
| `backend/microservices/mcp-storage-server/` | `backend/microservices/storage-service/` |

### New files (2)

| File | Purpose |
|------|---------|
| `backend/alembic/versions/xxx_add_cached_path.py` | Migration: add `cached_path` column |
| (REST endpoints added to existing `storage-service/app/main.py`) | |

### Modified files (5)

| File | Change |
|------|--------|
| `backend/microservices/storage-service/app/main.py` | Add REST endpoints `POST/GET /files/{path}` |
| `backend/microservices/weaviate-service/app/api/weaviate.py` | `_cache_original_file()` + `_cache_extracted_text()` + `_update_cached_path()` |
| `backend/microservices/weaviate-service/app/core/config.py` | Add `storage_service_url` setting |
| `backend/app/api/v1/documents.py` | Download + preview fallback to cache |
| `backend/app/db/models.py` | Add `cached_path` to IndexedDocument model |
| `backend/docker/docker-compose.onpremise.yml` | Rename mcp-storage, add depends_on + env vars |

### Implementation order

1. Rename `mcp-storage-server` to `storage-service` + add REST endpoints
2. Docker-compose updates (rename, depends_on, env vars)
3. Alembic migration — add `cached_path` column + model update
4. Config — `storage_service_url` in weaviate-service
5. Cache during indexation — `_cache_original_file()` + direct DB update
6. Download fallback — try adapter, fallback to cache
7. Preview fallback — same pattern at call site
8. Backfill (optional) — background task for existing docs when source available

---

## Storage estimation

| Metric | Value |
|--------|-------|
| Overhead per document | = original file size |
| 30 docs (~5MB avg) | ~150MB |
| 1000 docs | ~5GB |
| Disk path on-premise | `/app/storage/tenant-{id}/originals/` (Docker volume) |
| SaaS path | GCS bucket (via storage-service GCS provider) |

---

## What this does NOT include

- New Docker service (renames existing one, adds REST endpoints)
- Frontend changes (fallback is transparent)
- Cache TTL/expiration (kept indefinitely)
- File deduplication (each doc has its own copy)
- MCP protocol support removed (was unnecessary for binary file storage)
