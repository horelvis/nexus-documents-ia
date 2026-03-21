# Content Cache — Design Spec (v3)

**Date:** 2026-03-21
**Status:** Approved (v3 — MinIO from scratch)
**Scope:** Cache original files during indexation via new MinIO-based storage-service; offline preview/download fallback

---

## Context

NouxCubeIA indexes documents from external sources (Alfresco, Google Drive, OneDrive, databases) via MCP connectors. The original files live exclusively on the source — no local copy is stored. When the source is unavailable:

- **Preview fails** — cannot render the PDF/DOCX
- **Download fails** — cannot serve the file to the user
- **RAG still works** — chunks are already in Weaviate with embeddings

### What changes

- Delete `mcp-storage-server` entirely (MCP protocol for file storage was unnecessary)
- New `storage-service` from scratch: FastAPI + MinIO SDK, REST-only
- MinIO container in docker-compose (S3-compatible, on-premise, client can point to their own S3/NAS)
- Cache original files during indexation
- Fallback to cache for preview/download when source is down

---

## Architecture

### New service: storage-service

```
storage-service (FastAPI, port 8010)
├── POST   /files/{path}?tenant_id=X     — upload file bytes
├── GET    /files/{path}?tenant_id=X     — download file bytes
├── DELETE /files/{path}?tenant_id=X     — delete file
├── HEAD   /files/{path}?tenant_id=X     — check if file exists
├── GET    /health                        — health check
└── Uses MinIO SDK (minio Python package) for S3 operations
```

MinIO bucket structure:
```
nexus-storage/
├── {tenant_id}/
│   └── originals/
│       ├── {document_id}/{filename}          — file connector docs
│       └── {document_id}/extracted.txt       — database connector docs
```

### Indexation flow

```
MCP Connector downloads file -> file_bytes -> weaviate-service
  -> storage-service POST /files/originals/{doc_id}/{filename}?tenant_id=X
  -> Direct DB: UPDATE indexed_documents SET cached_path = 'originals/{doc_id}/{filename}'
  -> Existing pipeline: Docling -> chunks -> Weaviate -> AGE -> legal refs
```

### Download fallback

```
Frontend -> GET /api/v1/documents/{id}/content
  -> Try 1: adapter.download_content(unified_doc)  [Alfresco/GDrive, line ~447]
  -> Catch exception (source unavailable):
     -> If indexed_doc.cached_path:
        -> storage-service GET /files/{cached_path}?tenant_id=X
     -> Else:
        -> 503 "Source unavailable and no cached copy"
```

### Connector type handling

| Connector type | Has file? | What to cache |
|---------------|-----------|---------------|
| `alfresco` | Yes | Original binary (PDF, DOCX) |
| `google_drive` | Yes | Original binary |
| `onedrive` | Yes | Original binary |
| `database` | No | Extracted text as `.txt` |

---

## Component 1: MinIO in docker-compose

**File:** `backend/docker/docker-compose.onpremise.yml`

```yaml
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"    # S3 API
      - "9001:9001"    # Console (optional, for debugging)
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  minio_data:
```

The client can mount `minio_data` to their NAS/SAN for massive storage.

Env vars in `.env`:
```
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_ENDPOINT=minio:9000
MINIO_BUCKET=nexus-storage
MINIO_SECURE=false
```

---

## Component 2: storage-service (new, from scratch)

**Directory:** `backend/microservices/storage-service/`

```
storage-service/
├── app/
│   ├── main.py           — FastAPI app, REST endpoints
│   ├── core/
│   │   └── config.py     — Settings (MinIO endpoint, bucket, credentials)
│   └── services/
│       └── minio_service.py — MinIO client wrapper (upload, download, delete, exists)
├── Dockerfile
└── requirements.txt      — fastapi, uvicorn, minio
```

### main.py

```python
"""
Storage Service — REST API for file storage via MinIO (S3-compatible).

Replaces mcp-storage-server. No MCP protocol — pure REST for
service-to-service file operations.
"""

from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.minio_service import minio_storage

app = FastAPI(title="Storage Service", version="1.0.0")


@app.on_event("startup")
async def startup():
    await minio_storage.initialize()


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "storage-service"}


@app.post("/files/{path:path}")
async def upload_file(path: str, request: Request, tenant_id: str = "default"):
    """Upload file bytes to MinIO."""
    content = await request.body()
    if not content:
        raise HTTPException(400, "Empty body")

    object_name = f"{tenant_id}/{path}"
    content_type = request.headers.get("content-type", "application/octet-stream")

    result = await minio_storage.upload(object_name, content, content_type)
    return JSONResponse(result)


@app.get("/files/{path:path}")
async def download_file(path: str, tenant_id: str = "default"):
    """Download file bytes from MinIO."""
    object_name = f"{tenant_id}/{path}"
    content = await minio_storage.download(object_name)
    if content is None:
        raise HTTPException(404, "File not found")
    return Response(content=content, media_type="application/octet-stream")


@app.delete("/files/{path:path}")
async def delete_file(path: str, tenant_id: str = "default"):
    """Delete file from MinIO."""
    object_name = f"{tenant_id}/{path}"
    success = await minio_storage.delete(object_name)
    if not success:
        raise HTTPException(404, "File not found")
    return {"deleted": True}


@app.head("/files/{path:path}")
async def file_exists(path: str, tenant_id: str = "default"):
    """Check if file exists in MinIO."""
    object_name = f"{tenant_id}/{path}"
    exists = await minio_storage.exists(object_name)
    if not exists:
        raise HTTPException(404)
    return Response(status_code=200)
```

### minio_service.py

```python
"""
MinIO storage service — S3-compatible object storage.

Uses the official minio Python SDK for synchronous operations
wrapped in asyncio.to_thread() for non-blocking calls.
"""

import io
import logging
from typing import Any, Dict, Optional

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

logger = logging.getLogger(__name__)


class MinIOStorageService:
    """MinIO S3-compatible storage client."""

    def __init__(self):
        self._client: Optional[Minio] = None
        self._bucket = settings.minio_bucket

    async def initialize(self) -> None:
        """Initialize MinIO client and ensure bucket exists."""
        import asyncio
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=settings.minio_secure,
        )
        # Ensure bucket exists
        def _ensure_bucket():
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info(f"Created MinIO bucket: {self._bucket}")
        await asyncio.to_thread(_ensure_bucket)
        logger.info(f"MinIO storage initialized: {settings.minio_endpoint}/{self._bucket}")

    async def upload(self, object_name: str, data: bytes, content_type: str = "application/octet-stream") -> Dict[str, Any]:
        """Upload bytes to MinIO."""
        import asyncio
        def _upload():
            self._client.put_object(
                self._bucket, object_name,
                io.BytesIO(data), len(data),
                content_type=content_type,
            )
        await asyncio.to_thread(_upload)
        logger.info(f"Uploaded: {object_name} ({len(data)} bytes)")
        return {"object_name": object_name, "size": len(data), "bucket": self._bucket}

    async def download(self, object_name: str) -> Optional[bytes]:
        """Download bytes from MinIO."""
        import asyncio
        def _download():
            try:
                response = self._client.get_object(self._bucket, object_name)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except S3Error as e:
                if e.code == "NoSuchKey":
                    return None
                raise
        return await asyncio.to_thread(_download)

    async def delete(self, object_name: str) -> bool:
        """Delete object from MinIO."""
        import asyncio
        def _delete():
            try:
                self._client.remove_object(self._bucket, object_name)
                return True
            except S3Error:
                return False
        return await asyncio.to_thread(_delete)

    async def exists(self, object_name: str) -> bool:
        """Check if object exists in MinIO."""
        import asyncio
        def _exists():
            try:
                self._client.stat_object(self._bucket, object_name)
                return True
            except S3Error:
                return False
        return await asyncio.to_thread(_exists)


# Singleton
minio_storage = MinIOStorageService()
```

### config.py

```python
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "storage-service"
    service_port: int = int(os.getenv("SERVICE_PORT", "8010"))

    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    minio_root_user: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    minio_root_password: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "nexus-storage")
    minio_secure: bool = os.getenv("MINIO_SECURE", "false").lower() == "true"

    class Config:
        env_file = ".env"


settings = Settings()
```

### Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

### requirements.txt

```
fastapi>=0.104.0
uvicorn>=0.24.0
minio>=7.2.0
pydantic-settings>=2.0.0
```

---

## Component 3: Database Migration

```sql
ALTER TABLE indexed_documents ADD COLUMN cached_path TEXT;
```

- `NULL` = no cache
- `originals/{document_id}/{filename}` = object path (tenant_id prepended by service)

---

## Component 4: Cache during indexation

**File:** `backend/microservices/weaviate-service/app/api/weaviate.py`

After `file_bytes = base64.b64decode(...)` (~line 829), before Docling processing:

```python
async def _cache_original_file(
    tenant_id: str, document_id: str, filename: str, file_bytes: bytes,
) -> Optional[str]:
    """Cache original file in storage-service (MinIO) for offline access."""
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

For database connectors (no file, only text):

```python
async def _cache_extracted_text(
    tenant_id: str, document_id: str, extracted_text: str,
) -> Optional[str]:
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

```python
async def _update_cached_path(tenant_id: str, document_id: str, cached_path: str) -> None:
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

## Component 5: Download fallback

**File:** `backend/app/api/v1/documents.py`

Wrap `adapter.download_content(unified_doc)` at line ~447:

```python
    try:
        content = await adapter.download_content(unified_doc)
    except Exception as source_error:
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
            raise HTTPException(503, "Source unavailable and no cached copy")
```

Same pattern applies to the preview call site in `documents.py` — get bytes from cache, write to temp, pass to Gotenberg.

---

## Component 6: Docker-compose changes

**File:** `backend/docker/docker-compose.onpremise.yml`

1. **Delete** `mcp-storage` service definition
2. **Add** `minio` + `storage-service`:

```yaml
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 5

  storage-service:
    build:
      context: ../microservices/storage-service
    environment:
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
      - MINIO_BUCKET=${MINIO_BUCKET:-nexus-storage}
    depends_on:
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      interval: 10s
      timeout: 5s
      retries: 3
```

3. **Add** `storage-service` to `weaviate-service.depends_on` and env:

```yaml
  weaviate-service:
    depends_on:
      ...
      storage-service:
        condition: service_healthy
    environment:
      ...
      - STORAGE_SERVICE_URL=${STORAGE_SERVICE_URL:-http://storage-service:8010}
```

4. **Add** `STORAGE_SERVICE_URL` to `api` service env for download fallback

5. **Update** all `mcp-storage` references to `storage-service`

---

## Deleted files

| Path | Reason |
|------|--------|
| `backend/microservices/mcp-storage-server/` (entire directory) | MCP protocol unnecessary for file storage; replaced by MinIO-based storage-service |

---

## Files Changed Summary

### New (1 directory + 1 migration)

| File | Purpose |
|------|---------|
| `backend/microservices/storage-service/` | New service: FastAPI + MinIO SDK |
| `backend/alembic/versions/xxx_add_cached_path.py` | Migration: `cached_path` column |

### Modified (4)

| File | Change |
|------|--------|
| `backend/microservices/weaviate-service/app/api/weaviate.py` | Cache during indexation + DB update |
| `backend/microservices/weaviate-service/app/core/config.py` | `storage_service_url` setting |
| `backend/app/api/v1/documents.py` | Download + preview fallback |
| `backend/docker/docker-compose.onpremise.yml` | Delete mcp-storage, add minio + storage-service |

### Deleted (1)

| File | Reason |
|------|--------|
| `backend/microservices/mcp-storage-server/` | Replaced by storage-service |

### Implementation order

1. Delete `mcp-storage-server/`
2. Create `storage-service/` (FastAPI + MinIO)
3. Docker-compose (minio + storage-service, remove mcp-storage)
4. Alembic migration + model update
5. Config `storage_service_url` in weaviate-service
6. Cache during indexation
7. Download fallback
8. Preview fallback

---

## Storage estimation

| Metric | Value |
|--------|-------|
| Overhead per document | = original file size |
| 30 docs (~5MB avg) | ~150MB |
| 1000 docs | ~5GB |
| MinIO data | Docker volume `minio_data` (mountable to NAS/SAN) |
| MinIO console | `http://localhost:9001` (admin UI for debugging) |
