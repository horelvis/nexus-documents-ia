# Content Cache with MinIO — Implementation Plan (v2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache original files in MinIO during indexation so preview/download work when source connectors (Alfresco, Google Drive) are offline.

**Architecture:** New `storage-service` (FastAPI + MinIO SDK) replaces `mcp-storage-server`. MinIO container provides S3-compatible storage. Files cached during indexation with fallback in download/preview endpoints. `mcp-storage-server` deleted entirely.

**Tech Stack:** MinIO, FastAPI, minio Python SDK, asyncpg, httpx

**Spec:** `docs/superpowers/specs/2026-03-21-content-cache-design.md` (v4)

---

### Task 1: Create storage-service from scratch

**Files:**
- Create: `backend/microservices/storage-service/app/__init__.py`
- Create: `backend/microservices/storage-service/app/core/__init__.py`
- Create: `backend/microservices/storage-service/app/core/config.py`
- Create: `backend/microservices/storage-service/app/services/__init__.py`
- Create: `backend/microservices/storage-service/app/services/minio_service.py`
- Create: `backend/microservices/storage-service/app/main.py`
- Create: `backend/microservices/storage-service/Dockerfile`
- Create: `backend/microservices/storage-service/requirements.txt`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p backend/microservices/storage-service/app/core
mkdir -p backend/microservices/storage-service/app/services
touch backend/microservices/storage-service/app/__init__.py
touch backend/microservices/storage-service/app/core/__init__.py
touch backend/microservices/storage-service/app/services/__init__.py
```

- [ ] **Step 2: Create `requirements.txt`**

Write to `backend/microservices/storage-service/requirements.txt`:
```
fastapi>=0.104.0
uvicorn>=0.24.0
minio>=7.2.0
pydantic-settings>=2.0.0
```

- [ ] **Step 3: Create `Dockerfile`**

Write to `backend/microservices/storage-service/Dockerfile`:
```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
```

Note: `curl` needed for Docker healthcheck.

- [ ] **Step 4: Create `config.py`**

Write to `backend/microservices/storage-service/app/core/config.py` — exact code from spec Component 2 (config.py section).

- [ ] **Step 5: Create `minio_service.py`**

Write to `backend/microservices/storage-service/app/services/minio_service.py` — exact code from spec Component 2 (minio_service.py section).

- [ ] **Step 6: Create `main.py`**

Write to `backend/microservices/storage-service/app/main.py` — exact code from spec Component 2 (main.py section). Uses `lifespan` context manager (not deprecated `on_event`).

- [ ] **Step 7: Commit**

```bash
git add backend/microservices/storage-service/
git commit -m "feat: create storage-service (FastAPI + MinIO SDK, REST-only)"
```

---

### Task 2: Delete mcp-storage-server + Docker-compose atomic swap

This task is atomic — delete old service AND update all compose references in the same commit to avoid broken intermediate state.

**Files:**
- Delete: `backend/microservices/mcp-storage-server/` (entire directory)
- Modify: `backend/docker/docker-compose.onpremise.yml`
- Modify: `backend/docker/docker-compose.yml` (identical base file — same edits)
- Modify: `backend/docker/.env`
- Modify: `backend/microservices/presentation-service/app/core/config.py:36`

- [ ] **Step 1: Delete mcp-storage-server directory**

```bash
rm -rf backend/microservices/mcp-storage-server/
```

- [ ] **Step 2: Add MinIO env vars to `.env`**

Append to `backend/docker/.env`:
```
# MinIO (S3-compatible storage)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_ENDPOINT=minio:9000
MINIO_BUCKET=nexus-storage
MINIO_SECURE=false
```

- [ ] **Step 3: Replace `mcp-storage` service in `docker-compose.onpremise.yml`**

Find the `mcp-storage:` service block (~line 1076-1096). Replace entirely with:

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
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  storage-service:
    build:
      context: ../microservices/storage-service
    environment:
      - MINIO_ENDPOINT=minio:9000
      - MINIO_ROOT_USER=${MINIO_ROOT_USER:-minioadmin}
      - MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD:-minioadmin}
      - MINIO_BUCKET=${MINIO_BUCKET:-nexus-storage}
      - MINIO_SECURE=${MINIO_SECURE:-false}
    depends_on:
      minio:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8010/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped
```

- [ ] **Step 4: Update `api` service in compose**

Find `api` service (~line 830):
- `depends_on`: replace `mcp-storage: condition: service_healthy` with `storage-service: condition: service_healthy`
- Environment: replace `MCP_STORAGE_URL=${MCP_STORAGE_URL:-http://mcp-storage:8000}` with `STORAGE_SERVICE_URL=${STORAGE_SERVICE_URL:-http://storage-service:8010}`
- Volume: keep `local_storage_data:/app/storage`

- [ ] **Step 5: Update `weaviate-service` in compose**

Add to `depends_on`:
```yaml
      storage-service:
        condition: service_healthy
```
Add to environment:
```yaml
      - STORAGE_SERVICE_URL=${STORAGE_SERVICE_URL:-http://storage-service:8010}
```

- [ ] **Step 6: Update `presentation-service` in compose**

Find `presentation-service` block (~line 1100):
- `depends_on`: replace `mcp-storage: condition: service_healthy` with `storage-service: condition: service_healthy`
- Environment: replace `PRESENTATION_STORAGE_SERVICE_URL=${MCP_STORAGE_URL:-http://mcp-storage:8000}` with `PRESENTATION_STORAGE_SERVICE_URL=${STORAGE_SERVICE_URL:-http://storage-service:8010}`
- Volume: keep `local_storage_data:/app/storage`

- [ ] **Step 7: Add `minio_data` to volumes section**

Add to the `volumes:` block at bottom:
```yaml
  minio_data:
```
Keep `local_storage_data:` for backward compat with existing presentation files.

- [ ] **Step 8: Apply same edits to `docker-compose.yml` (base file)**

The base `docker-compose.yml` is identical to `docker-compose.onpremise.yml`. Apply the exact same changes (steps 3-7) to `backend/docker/docker-compose.yml`.

- [ ] **Step 9: Update `presentation-service` config default**

In `backend/microservices/presentation-service/app/core/config.py` line 36, change:
```python
    storage_service_url: str = "http://mcp-storage:8000"
```
To:
```python
    storage_service_url: str = "http://storage-service:8010"
```

- [ ] **Step 10: Global grep for remaining `mcp-storage` references**

```bash
grep -rn "mcp.storage\|mcp-storage\|mcp_storage" backend/docker/ backend/microservices/ backend/app/ --include="*.py" --include="*.yml" --include="*.yaml" --include="*.md" | grep -v ".pyc" | grep -v "__pycache__"
```

Fix any remaining references. Known files that may have stale refs:
- `backend/microservices/weaviate-service/app/mcp/config.py` — MCP config with `MCP_STORAGE_URL`
- `backend/microservices/weaviate-service/config/mcp_servers.yaml` — storage server MCP entry
- `backend/app/services/async_storage_client.py` — comment "mcp-storage compatible"

For MCP config files: remove or comment out the storage server entry (MCP protocol for storage is deleted). For comments: update to reference `storage-service`.

- [ ] **Step 11: Handle `docker-compose.yml.saas`**

```bash
grep -n "mcp-storage\|mcp_storage" backend/docker/docker-compose.yml.saas
```

If references exist, update them. SaaS mode may need different handling (GCS instead of MinIO) — at minimum update service names to avoid referencing a deleted service.

- [ ] **Step 12: Verify compose is valid**

```bash
cd backend/docker && docker compose config --quiet && echo "VALID" || echo "INVALID"
```

- [ ] **Step 13: Commit (atomic — delete + compose fix together)**

```bash
git add -A
git commit -m "refactor: replace mcp-storage-server with MinIO + storage-service

- Delete mcp-storage-server/ (MCP protocol unnecessary for file storage)
- Add minio container (S3-compatible, NAS-mountable volume)
- Add storage-service (FastAPI + MinIO SDK, REST-only)
- Update api, weaviate-service, presentation-service dependencies
- Clean up all mcp-storage references across compose + configs"
```

---

### Task 3: Alembic migration + model update

**Files:**
- Modify: `backend/app/db/models.py:2302`
- Create: Alembic migration file

- [ ] **Step 1: Add `cached_path` to IndexedDocument model**

In `backend/app/db/models.py`, after `updated_at` (line 2302), add:
```python
    # Content cache path in MinIO (e.g., "originals/{doc_id}/{filename}")
    cached_path = Column(Text, nullable=True)
```

- [ ] **Step 2: Create Alembic migration**

```bash
cd backend && python scripts/create_migration.py -m "add_cached_path_to_indexed_documents" --autogenerate
```

If that fails, create manually and edit:
```python
def upgrade() -> None:
    op.add_column('indexed_documents', sa.Column('cached_path', sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column('indexed_documents', 'cached_path')
```

- [ ] **Step 3: Run migration**

```bash
docker compose exec api alembic upgrade head
```

- [ ] **Step 4: Verify**

```bash
docker exec docker-db-1 psql -U nexus_user -d nexus_db -c "\d indexed_documents" | grep cached_path
```
Expected: `cached_path | text |  |  |`

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py backend/alembic/versions/
git commit -m "feat(db): add cached_path column to indexed_documents"
```

---

### Task 4: Config updates in weaviate-service + main API

**Files:**
- Modify: `backend/microservices/weaviate-service/app/core/config.py:274-275`
- Modify: `backend/app/core/config.py` (existing `STORAGE_SERVICE_URL`)

- [ ] **Step 1: Update weaviate-service config**

In `backend/microservices/weaviate-service/app/core/config.py`:
- Line 274: remove or update the comment `# LEGACY - Use MCP storage server instead` to `# Storage service URL (MinIO-backed)`
- Line 275: change default port from `8003` to `8010`:
```python
    storage_service_url: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8010")
```

- [ ] **Step 2: Update main API config**

In `backend/app/core/config.py`, find the existing `STORAGE_SERVICE_URL` setting. Update its default port from `8003` to `8010`:
```python
    STORAGE_SERVICE_URL: str = os.getenv("STORAGE_SERVICE_URL", "http://storage-service:8010")
```

If it doesn't exist yet, add it to the Settings class.

- [ ] **Step 3: Commit**

```bash
git add backend/microservices/weaviate-service/app/core/config.py backend/app/core/config.py
git commit -m "fix(config): update storage_service_url defaults to port 8010"
```

---

### Task 5: Cache during indexation (file + database connectors)

**Files:**
- Modify: `backend/microservices/weaviate-service/app/api/weaviate.py`

- [ ] **Step 1: Add cache helper functions**

Add near the existing `_generate_document_memory` helper (~line 730):

```python
async def _cache_original_file(
    tenant_id: str, document_id: str, filename: str, file_bytes: bytes,
) -> Optional[str]:
    """Cache original file in storage-service (MinIO) for offline access.
    Returns the object_name (cached_path) or None if caching failed."""
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


async def _cache_extracted_text(
    tenant_id: str, document_id: str, extracted_text: str,
) -> Optional[str]:
    """Cache extracted text for database connector documents (no file bytes)."""
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


async def _update_cached_path(tenant_id: str, document_id: str, cached_path: str) -> None:
    """Direct DB update for cached_path using asyncpg."""
    try:
        import asyncpg
        import uuid as _uuid
        dsn = f"postgresql://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
        conn = await asyncpg.connect(dsn)
        await conn.execute(
            "UPDATE indexed_documents SET cached_path = $1 WHERE id = $2 AND tenant_id = $3",
            cached_path, _uuid.UUID(document_id), _uuid.UUID(tenant_id),
        )
        await conn.close()
    except Exception as e:
        logger.debug(f"Failed to update cached_path for {document_id}: {e}")
```

- [ ] **Step 2: Wire file cache into `index_from_connector`**

Find `file_bytes = base64.b64decode(request.file_bytes_base64)` (~line 829). After that line, add:

```python
        # Cache original file in MinIO for offline access
        cached_path = await _cache_original_file(
            tenant_id=request.tenant_id,
            document_id=request.document_id,
            filename=request.filename,
            file_bytes=file_bytes,
        )
```

Then after the successful indexing (after `weaviate_result`, before the return), add:

```python
        # Persist cached_path to DB (fire-and-forget)
        if cached_path:
            import asyncio
            asyncio.create_task(
                _update_cached_path(request.tenant_id, request.document_id, cached_path)
            )
```

- [ ] **Step 3: Wire text cache for database connectors**

Find where database connector documents are indexed (they have `extracted_text` but no `file_bytes_base64`). If the connector type is `database`, call `_cache_extracted_text` instead of `_cache_original_file`:

```python
        # For database connectors: cache extracted text instead of file bytes
        connector_type = request.metadata.get("connector_type", "") if request.metadata else ""
        if connector_type == "database" and result.extracted_text:
            cached_path = await _cache_extracted_text(
                tenant_id=request.tenant_id,
                document_id=request.document_id,
                extracted_text=result.extracted_text,
            )
```

If the database connector uses a different indexation endpoint, find it and add the same pattern there.

- [ ] **Step 4: Commit**

```bash
git add backend/microservices/weaviate-service/app/api/weaviate.py
git commit -m "feat(cache): cache original files + extracted text in MinIO during indexation"
```

---

### Task 6: Download fallback

**Files:**
- Modify: `backend/app/api/v1/documents.py:418-471`

- [ ] **Step 1: Add download fallback**

In `backend/app/api/v1/documents.py`, find `content = await adapter.download_content(unified_doc)` (~line 447). Wrap it with cache fallback:

```python
        # Try source first, fallback to cache
        try:
            content = await adapter.download_content(unified_doc)
        except Exception as source_error:
            if hasattr(indexed_doc, 'cached_path') and indexed_doc.cached_path:
                logger.info(f"Source unavailable for {doc_id}, falling back to cache: {indexed_doc.cached_path}")
                import httpx
                async with httpx.AsyncClient(timeout=30.0) as http_client:
                    cache_response = await http_client.get(
                        f"{settings.STORAGE_SERVICE_URL}/files/{indexed_doc.cached_path}",
                        params={"tenant_id": str(indexed_doc.tenant_id)},
                    )
                    if cache_response.status_code == 200:
                        content = cache_response.content
                    else:
                        raise HTTPException(503, "Source unavailable and cache not found")
            else:
                logger.error(f"Source unavailable for {doc_id} and no cache: {source_error}")
                raise HTTPException(503, "Source unavailable and no cached copy")
```

Replace the existing `content = await adapter.download_content(unified_doc)` line with this block. Keep the rest of the endpoint (response construction, error handling) unchanged.

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/v1/documents.py
git commit -m "feat(fallback): download fallback to MinIO cache when source unavailable"
```

---

### Task 7: Preview fallback

**Files:**
- Modify: `backend/app/api/v1/documents.py` (preview endpoint)

- [ ] **Step 1: Read the preview endpoint**

Find the preview endpoint (`/{doc_id}/preview` or similar). Identify where file bytes are obtained before being passed to Gotenberg/DocumentPreviewService. Apply the same try/cache pattern as Task 6.

The preview service (`DocumentPreviewService.generate_preview()`) expects a local file path. The fallback is:
1. Try download from source → write to temp → pass to preview service
2. If source fails → download from cache → write to temp → pass to preview service
3. If no cache → 503

- [ ] **Step 2: Apply fallback at the call site**

The fallback goes where bytes are obtained (before preview service call), NOT inside `generate_preview()`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/documents.py
git commit -m "feat(preview): preview fallback to MinIO cache when source unavailable"
```

---

### Task 8: README + cleanup

**Files:**
- Modify: `README-ONPREMISE.md`

- [ ] **Step 1: Update README**

```bash
grep -n "mcp-storage\|mcp_storage" README-ONPREMISE.md
```

Replace all occurrences:
- Service name: `mcp-storage` → `storage-service`
- Add MinIO to services list/architecture diagram
- Update port if mentioned (8000 → 8010)

- [ ] **Step 2: Final global grep**

```bash
grep -rn "mcp.storage\|mcp-storage\|mcp_storage" . --include="*.py" --include="*.yml" --include="*.yaml" --include="*.md" --include="*.json" | grep -v node_modules | grep -v .git | grep -v __pycache__
```

Should return 0 results (or only in git history/changelogs).

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: update README + final mcp-storage reference cleanup"
```

---

### Task 9: Verification

- [ ] **Step 1: Build and start new services**

```bash
cd backend/docker
docker compose build storage-service
docker compose up -d minio storage-service
sleep 10
docker compose logs minio --tail 5
docker compose logs storage-service --tail 5
```

Expected: MinIO healthy, storage-service healthy, bucket `nexus-storage` created.

- [ ] **Step 2: Test REST endpoints**

```bash
# Upload
echo "Hello MinIO" | curl -s -X POST "http://localhost:8010/files/test/hello.txt?tenant_id=test" --data-binary @-
# Download
curl -s "http://localhost:8010/files/test/hello.txt?tenant_id=test"
# Exists
curl -s -o /dev/null -w "%{http_code}" -I "http://localhost:8010/files/test/hello.txt?tenant_id=test"
# Delete
curl -s -X DELETE "http://localhost:8010/files/test/hello.txt?tenant_id=test"
```

Expected: Upload returns JSON, download returns "Hello MinIO", HEAD returns 200, DELETE returns `{"deleted": true}`.

- [ ] **Step 3: MinIO console**

Open `http://localhost:9001`, login `minioadmin`/`minioadmin`. Verify `nexus-storage` bucket exists.

- [ ] **Step 4: Rebuild weaviate-service and test cache**

```bash
docker compose build weaviate-service
docker compose restart weaviate-service
```

Reset one doc to pending:
```bash
docker exec docker-db-1 psql -U nexus_user -d nexus_db -c \
  "UPDATE indexed_documents SET indexing_status = 'pending', cached_path = NULL WHERE id = (SELECT id FROM indexed_documents WHERE tenant_id = '00000000-0000-0000-0000-000000000001' AND indexing_status = 'indexed' LIMIT 1);"
```

Trigger re-index, then verify:
```bash
docker exec docker-db-1 psql -U nexus_user -d nexus_db -c \
  "SELECT id, title, cached_path FROM indexed_documents WHERE cached_path IS NOT NULL LIMIT 5;"
```

Expected: `cached_path` populated with `originals/{doc_id}/{filename}`.

- [ ] **Step 5: Verify file in MinIO**

Using the `cached_path` from step 4:
```bash
curl -s "http://localhost:8010/files/{cached_path}?tenant_id={tenant_id}" | file -
```

Expected: shows file type (e.g., `PDF document`).
