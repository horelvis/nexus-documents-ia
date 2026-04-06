# Coherence Audit P3-P5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove ~15K LOC of dead code across 3 phases: orphan directories, ghost config, deprecated services.

**Architecture:** Pure deletion in Phases 1-2. Phase 3 migrates MCP connectors and channel services to use the indexing pipeline instead of calling textextract directly. Each phase is one commit.

**Tech Stack:** Python/FastAPI backend, Next.js frontend, Docker Compose

**Spec:** `docs/superpowers/specs/2026-03-26-coherence-audit-p3-p5-design.md`

---

## Phase 1: Low Risk Deletions

### Task 1: Delete 9 orphan microservice directories

**Files:**
- Delete: `backend/microservices/ollama-service/` (561 LOC)
- Delete: `backend/microservices/presentation-service/` (2,273 LOC)
- Delete: `backend/microservices/camunda-service/` (2,473 LOC)
- Delete: `backend/microservices/engine-template-service/` (~0 LOC)
- Delete: `backend/microservices/gotenberg-service/` (798 LOC)
- Delete: `backend/microservices/signature-service/` (1,360 LOC)
- Delete: `backend/microservices/template-editor-service/` (1,615 LOC)
- Delete: `backend/microservices/mcp-storage-server/` (0 LOC)
- Delete: `backend/microservices/mcp-external-servers/` (1,196 LOC)

- [ ] **Step 1: Delete all 9 directories**

```bash
cd /home/nexus/git/nexus-documents-ia
rm -rf backend/microservices/ollama-service
rm -rf backend/microservices/presentation-service
rm -rf backend/microservices/camunda-service
rm -rf backend/microservices/engine-template-service
rm -rf backend/microservices/gotenberg-service
rm -rf backend/microservices/signature-service
rm -rf backend/microservices/template-editor-service
rm -rf backend/microservices/mcp-storage-server
rm -rf backend/microservices/mcp-external-servers
```

- [ ] **Step 2: Verify no compose references**

```bash
grep -r "ollama-service\|presentation-service\|camunda-service\|engine-template\|signature-service\|template-editor\|mcp-storage-server\|mcp-external-servers" backend/docker/docker-compose*.yml | grep -v "^#\|REMOVED\|#.*:"
```
Expected: zero hits (or only comments).

Note: `gotenberg-service` reference in `document-forge-service` will be fixed in Task 7 (Phase 3).

---

### Task 2: Remove Stripe config + code

**Files:**
- Modify: `backend/app/core/config.py` — remove lines 21-28 (8 STRIPE_* settings)
- Delete: `backend/app/api/v1/stripe.py`
- Delete: `backend/app/services/subscription_service_v2.py`
- Modify: `backend/app/api/api.py` — remove stripe router (lines 44-46)
- Modify: `backend/app/core/features.py` — remove STRIPE_BILLING flag if present

- [ ] **Step 1: Remove STRIPE settings from config.py**

Open `backend/app/core/config.py` and delete these 8 lines (around lines 21-28):

```python
# DELETE these lines:
STRIPE_SECRET_KEY: Optional[str] = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLIC_KEY: Optional[str] = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_WEBHOOK_SECRET: Optional[str] = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_PORTAL_CONFIGURATION_ID: Optional[str] = None
STRIPE_BASIC_PRICE_ID: Optional[str] = os.getenv("STRIPE_BASIC_PRICE_ID")
STRIPE_PRO_PRICE_ID: Optional[str] = os.getenv("STRIPE_PRO_PRICE_ID")
STRIPE_PRO_YEARLY_PRICE_ID: Optional[str] = os.getenv("STRIPE_PRO_YEARLY_PRICE_ID")
STRIPE_ENTERPRISE_PRICE_ID: Optional[str] = os.getenv("STRIPE_ENTERPRISE_PRICE_ID")
```

- [ ] **Step 2: Remove stripe router from api.py**

Open `backend/app/api/api.py` and delete the conditional stripe block (around lines 44-46):

```python
# DELETE these lines:
if FeatureFlags.is_enabled(Feature.STRIPE_BILLING):
    from app.api.v1 import stripe
    api_router.include_router(stripe.router, prefix="/stripe", tags=["stripe"])
```

- [ ] **Step 3: Delete stripe endpoint and subscription service**

```bash
rm backend/app/api/v1/stripe.py
rm backend/app/services/subscription_service_v2.py
```

- [ ] **Step 4: Remove STRIPE_BILLING from features.py**

Open `backend/app/core/features.py` and search for `STRIPE_BILLING`. Remove the enum entry and any references in the SAAS/ON_PREMISE/CUSTOM defaults dicts.

---

### Task 3: Remove Clerk config + code

**Files:**
- Modify: `backend/app/core/config.py` — remove lines 269-272 (4 CLERK_* settings)
- Modify: `backend/app/core/features.py` — remove CLERK_AUTH (line 63) + 3 assignments in defaults
- Modify: `backend/app/services/lgpd_deletion_service.py` — remove Clerk import, client init, deletion methods
- Delete: `backend/app/auth/clerk.py` (if exists)
- Delete: `backend/app/auth/providers/clerk.py` (if exists)

- [ ] **Step 1: Remove CLERK settings from config.py**

Open `backend/app/core/config.py` and delete these 4 lines (around lines 269-272):

```python
# DELETE these lines:
CLERK_API_URL: str = os.getenv("CLERK_API_URL", "https://api.clerk.com/v1")
CLERK_SECRET_KEY: Optional[str] = os.getenv("CLERK_SECRET_KEY")
CLERK_PUBLISHABLE_KEY: Optional[str] = os.getenv("CLERK_PUBLISHABLE_KEY")
CLERK_JWT_VERIFICATION_KEY: Optional[str] = os.getenv("CLERK_JWT_VERIFICATION_KEY")
```

- [ ] **Step 2: Remove CLERK_AUTH from features.py**

Open `backend/app/core/features.py`:
- Remove `CLERK_AUTH = "clerk_auth"` (line 63)
- Remove `Feature.CLERK_AUTH: True,` from SAAS defaults (line 110)
- Remove `Feature.CLERK_AUTH: False,` from ON_PREMISE defaults (line 127)
- Remove `Feature.CLERK_AUTH: True,` from CUSTOM defaults (line 144)

- [ ] **Step 3: Clean lgpd_deletion_service.py**

Open `backend/app/services/lgpd_deletion_service.py`:
- Remove `import stripe` (line 18)
- Remove `from clerk_backend_api import Clerk` (line 19)
- Remove Clerk client init in `__init__` (line 49: `self.clerk_client: Optional[Clerk] = None`)
- Remove Stripe init in `__init__` (lines 50-51: `if settings.STRIPE_SECRET_KEY: stripe.api_key = ...`)
- Remove `_ensure_clerk_client()` method (lines 531-539)
- Remove `_delete_clerk_account()` method (lines 541-593)
- Remove `_delete_stripe_customer()` method (lines 595-618)
- In `_delete_from_external_services()` (lines 620-632): remove the Clerk and Stripe blocks, leave the method as empty (return `{}`) or remove it if nothing else calls it

- [ ] **Step 4: Delete Clerk auth files if they exist**

```bash
rm -f backend/app/auth/clerk.py
rm -f backend/app/auth/providers/clerk.py
```

---

### Task 4: Remove Camunda + TTS config + code

**Files:**
- Modify: `backend/app/core/config.py` — remove lines 276-277 (CAMUNDA_SERVICE_URL, TTS_SERVICE_URL)
- Delete: `backend/app/api/v1/workflows.py`
- Delete: `backend/app/services/workflow_service.py`
- Delete: `backend/app/api/v1/tts.py`
- Delete: `backend/app/services/tts_client.py`
- Modify: `backend/app/api/api.py` — remove workflows + tts routers

- [ ] **Step 1: Remove CAMUNDA and TTS settings from config.py**

Open `backend/app/core/config.py` and delete (around lines 276-277):

```python
# DELETE these lines:
CAMUNDA_SERVICE_URL: str = os.getenv("CAMUNDA_SERVICE_URL", "http://camunda-service:8000")
TTS_SERVICE_URL: str = os.getenv("TTS_SERVICE_URL", "http://tts-service:8000")
```

- [ ] **Step 2: Remove workflows router from api.py**

Open `backend/app/api/api.py`:
- Remove `workflows` from the import block (line ~16)
- Remove `api_router.include_router(workflows.router, ...)` (line 127)

- [ ] **Step 3: Remove tts router from api.py**

Open `backend/app/api/api.py`:
- Remove the tts import + include (lines 137-138):
```python
# DELETE these lines:
from app.api.v1 import tts
api_router.include_router(tts.router, prefix="/tts", tags=["tts"])
```

- [ ] **Step 4: Delete the endpoint and service files**

```bash
rm backend/app/api/v1/workflows.py
rm backend/app/services/workflow_service.py
rm backend/app/api/v1/tts.py
rm backend/app/services/tts_client.py
```

---

### Task 5: Remove dead classifiers + deprecated endpoints

**Files:**
- Delete: `backend/app/services/document_classifier.py` (17 LOC)
- Delete: `backend/app/services/ml/document_classifier.py` (400+ LOC)
- Delete: `backend/app/api/v1/chat.py` (78 LOC)
- Delete: `backend/app/api/v1/assistant.py` (500+ LOC)
- Modify: `backend/app/api/api.py` — remove chat + assistant routers

- [ ] **Step 1: Delete classifier files**

```bash
rm backend/app/services/document_classifier.py
rm backend/app/services/ml/document_classifier.py
```

- [ ] **Step 2: Verify no active imports of deleted classifiers**

```bash
grep -r "from app.services.document_classifier import\|from app.services.ml.document_classifier import" backend/app/ --include="*.py"
```
Expected: zero hits. If hits found, remove those import lines too.

- [ ] **Step 3: Remove chat + assistant routers from api.py**

Open `backend/app/api/api.py`:
- Remove `chat` and `assistant` from the import block (lines 14-20)
- Remove `api_router.include_router(chat.router, prefix="/chat", tags=["chat"])` (line 54)
- Remove `api_router.include_router(assistant.router, tags=["assistant"])` (line 55)

- [ ] **Step 4: Delete chat and assistant endpoint files**

```bash
rm backend/app/api/v1/chat.py
rm backend/app/api/v1/assistant.py
```

---

### Task 6: Clean frontend qdrant references

**Files:**
- Modify: `frontend/src/components/agents/agent-health-check.tsx`

- [ ] **Step 1: Remove qdrant from health check**

Open `frontend/src/components/agents/agent-health-check.tsx`:
- Remove the Qdrant entry from the services array (around lines 44-47):
```typescript
// DELETE this object from the array:
{
  name: 'Qdrant Vector DB',
  status: 'unknown',
},
```
- Remove qdrant status check (around line 85):
```typescript
// Fix this line to remove qdrant reference:
status: cagHealth.checks?.qdrant || cagHealth.checks?.embeddings ? 'healthy' : 'unhealthy',
// Replace with:
status: cagHealth.checks?.embeddings ? 'healthy' : 'unhealthy',
```

---

### Task 7: Phase 1 verification + commit

- [ ] **Step 1: Verify compose is valid**

```bash
cd backend/docker && docker compose config --services 2>&1 | head -30
```
Expected: list of services, no errors.

- [ ] **Step 2: Verify Python syntax on modified files**

```bash
cd /home/nexus/git/nexus-documents-ia
python3 -c "import ast; ast.parse(open('backend/app/core/config.py').read()); print('OK: config.py')"
python3 -c "import ast; ast.parse(open('backend/app/api/api.py').read()); print('OK: api.py')"
python3 -c "import ast; ast.parse(open('backend/app/core/features.py').read()); print('OK: features.py')"
python3 -c "import ast; ast.parse(open('backend/app/services/lgpd_deletion_service.py').read()); print('OK: lgpd.py')"
```
Expected: all OK.

- [ ] **Step 3: Scan for dangling references**

```bash
grep -r "camunda\|clerk\|stripe\|tts_client\|tts_service\|workflow_service\|document_classifier" backend/app/ --include="*.py" -l | grep -v __pycache__ | grep -v lgpd
```
Expected: zero hits (lgpd excluded because we already cleaned it).

- [ ] **Step 4: Commit Phase 1**

```bash
git add -A
git status
git commit -m "cleanup(P3-P5): remove 9 orphan dirs, ghost config, dead classifiers, deprecated endpoints

Phase 1 of coherence audit:
- P5: Delete ollama, presentation, camunda, engine-template, gotenberg,
  signature, template-editor, mcp-storage, mcp-external directories
- P4: Remove Clerk (4), Stripe (8), Camunda, TTS config + all associated
  endpoints, services, feature flags, LGPD Clerk/Stripe calls
- P3: Delete document_classifier.py, ml/document_classifier.py (dead code)
- P3: Delete chat.py, assistant.py endpoints (replaced by emma.py)
- Frontend: Remove qdrant from agent-health-check.tsx

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2: textextract-service Cleanup

### Task 8: Delete textextract-service and legacy clients

**Files:**
- Delete: `backend/microservices/textextract-service/` (1,653 LOC)
- Delete: `backend/microservices/weaviate-service/app/services/rag/textextract_client.py` (~240 LOC)
- Delete: `backend/microservices/weaviate-service/app/services/rag/ocr_client.py` (~150 LOC)
- Modify: `backend/microservices/weaviate-service/app/services/rag/__init__.py` — remove textextract re-exports

- [ ] **Step 1: Delete textextract-service directory**

```bash
rm -rf backend/microservices/textextract-service
```

- [ ] **Step 2: Delete legacy clients in weaviate-service**

```bash
rm backend/microservices/weaviate-service/app/services/rag/textextract_client.py
rm backend/microservices/weaviate-service/app/services/rag/ocr_client.py
```

- [ ] **Step 3: Clean rag/__init__.py re-exports**

Open `backend/microservices/weaviate-service/app/services/rag/__init__.py`:
- Remove the import line: `from .textextract_client import TextExtractClient, TextExtractResult, textextract_client`
- Remove `"textextract_client"` from `__all__` list (if present)
- Remove any `ocr_client` imports

- [ ] **Step 4: Verify no dangling imports in weaviate-service**

```bash
grep -r "textextract_client\|ocr_client\|TextExtractClient\|OCRClient" backend/microservices/weaviate-service/ --include="*.py" | grep -v __pycache__ | grep -v "# "
```
Expected: zero hits (excluding comments). If hits found in `indexing_pipeline.py`, remove those imports too (the pipeline already uses `intelligence_extract_client`).

- [ ] **Step 5: Verify indexing_pipeline.py still uses intelligence client**

```bash
grep "intelligence_client\|intelligence_extract_client\|IntelligenceExtractClient" backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py
```
Expected: hits confirming intelligence-docs is the active client.

- [ ] **Step 6: Commit Phase 2**

```bash
git add -A
git status
git commit -m "cleanup(P3): remove textextract-service + legacy weaviate clients

Phase 2 of coherence audit:
- Delete textextract-service/ directory (1,653 LOC)
- Delete rag/textextract_client.py and rag/ocr_client.py (legacy clients)
- Clean rag/__init__.py re-exports
- Indexing pipeline already uses intelligence_extract_client

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3: MCP Connector Migration + Forge

### Task 9: Investigate MCP connector extraction patterns

Before changing code, read each connector to understand the current flow.

**Files to read:**
- `backend/microservices/mcp-google-drive-server/app/services/sync_service.py`
- `backend/microservices/mcp-onedrive-server/app/services/sync_service.py`
- `backend/microservices/mcp-alfresco-server/app/services/sync_service.py`
- `backend/app/services/channels/gdrive_channel_service.py` (line 399: hardcoded textextract URL)
- `backend/app/services/channels/gmail_channel_service.py` (line 526: uses config URL)

- [ ] **Step 1: Read each MCP connector's sync_service.py**

For each connector, find:
1. How it downloads files (bytes or URL?)
2. Where it calls textextract-service (direct HTTP? client wrapper?)
3. What it does with the extracted text (stores in DB? sends to weaviate?)
4. What weaviate-service indexing endpoint it should use instead

Document findings before proceeding. The MCP connectors should send files to the weaviate-service indexing pipeline, NOT call extraction directly.

- [ ] **Step 2: Read the weaviate-service indexing endpoint**

Find the HTTP endpoint that accepts file bytes for indexing. Check:
```bash
grep -r "def.*index\|/index\|/documents/index" backend/microservices/weaviate-service/app/api/ --include="*.py" -n
```

Document the endpoint signature (URL, method, payload format).

---

### Task 10: Migrate MCP connectors to indexing pipeline

**Files:** (exact files depend on Task 9 findings)
- Modify: `mcp-google-drive-server/app/services/sync_service.py`
- Modify: `mcp-onedrive-server/app/services/sync_service.py`
- Modify: `mcp-alfresco-server/app/services/sync_service.py`
- Modify: `docker-compose.onpremise.yml` — remove TEXT_EXTRACTION_SERVICE_URL from MCP services

- [ ] **Step 1: Migrate each MCP connector**

For each connector (google-drive, onedrive, alfresco):
1. Replace the textextract HTTP call with a call to weaviate-service's indexing endpoint
2. Remove `TEXT_EXTRACTION_SERVICE_URL` env var usage
3. The indexing pipeline handles: extraction (via intelligence-docs) -> chunking -> embedding -> Weaviate insert

Implementation depends on Task 9 findings. Each connector may have a different call pattern.

- [ ] **Step 2: Remove TEXT_EXTRACTION_SERVICE_URL from docker-compose.onpremise.yml**

Search for and remove any remaining `TEXT_EXTRACTION_SERVICE_URL` env vars:
```bash
grep -n "TEXT_EXTRACTION_SERVICE_URL" backend/docker/docker-compose.onpremise.yml
```
Delete each matching line.

---

### Task 11: Migrate channel services

**Files:**
- Modify: `backend/app/services/channels/gdrive_channel_service.py` — line 399 hardcoded URL
- Modify: `backend/app/services/channels/gmail_channel_service.py` — line 526 config URL

- [ ] **Step 1: Read gdrive_channel_service.py _extract_text() method**

Read lines 375-409 to understand:
- What it sends to textextract (file bytes? URL?)
- What it does with the response (stores text where?)

- [ ] **Step 2: Redirect gdrive to indexing pipeline**

Replace the hardcoded `"http://textextract-service:8004/extract"` call (line 399) with a call to the weaviate-service indexing endpoint identified in Task 9.

- [ ] **Step 3: Read gmail_channel_service.py _extract_text_from_attachment()**

Read lines 510-539 to understand the same.

- [ ] **Step 4: Redirect gmail to indexing pipeline**

Replace the `settings.TEXT_EXTRACTION_SERVICE_URL` call (line 526) with the indexing pipeline call.

---

### Task 12: Fix forge gotenberg reference

**Files:**
- Modify: `backend/microservices/document-forge-service/app/core/config.py` — line 29

- [ ] **Step 1: Update gotenberg URL**

Open `backend/microservices/document-forge-service/app/core/config.py` and change line 29:

```python
# FROM:
"GOTENBERG_SERVICE_URL", "http://gotenberg-service:8005"
# TO:
"GOTENBERG_SERVICE_URL", "http://gotenberg:3000"
```

---

### Task 13: Phase 3 verification + commit

- [ ] **Step 1: Verify zero textextract references**

```bash
grep -r "textextract" backend/ --include="*.py" --include="*.yml" -l | grep -v __pycache__
```
Expected: zero hits (or only historical comments in committed docs).

- [ ] **Step 2: Verify zero gotenberg-service references**

```bash
grep -r "gotenberg-service" backend/ --include="*.py" --include="*.yml" -l | grep -v __pycache__
```
Expected: zero hits.

- [ ] **Step 3: Verify compose is valid**

```bash
cd backend/docker && docker compose config --services 2>&1 | head -30
```

- [ ] **Step 4: Commit Phase 3**

```bash
git add -A
git status
git commit -m "cleanup(P3): migrate MCP connectors to indexing pipeline, fix forge gotenberg

Phase 3 of coherence audit:
- MCP connectors (google-drive, onedrive, alfresco): route through
  weaviate-service indexing pipeline instead of calling textextract
- Channel services (gdrive, gmail): same migration
- Forge: gotenberg-service:8005 -> gotenberg:3000 (bare container)
- Remove all TEXT_EXTRACTION_SERVICE_URL env vars from compose

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Final Verification

### Task 14: Full codebase scan

- [ ] **Step 1: Run comprehensive dead reference scan**

```bash
cd /home/nexus/git/nexus-documents-ia
echo "=== textextract ===" && grep -r "textextract" backend/ --include="*.py" -l | grep -v __pycache__ | wc -l
echo "=== camunda ===" && grep -r "camunda" backend/ --include="*.py" -l | grep -v __pycache__ | wc -l
echo "=== clerk ===" && grep -r "clerk" backend/ --include="*.py" -l | grep -v __pycache__ | wc -l
echo "=== stripe ===" && grep -r "stripe" backend/ --include="*.py" -l | grep -v __pycache__ | wc -l
echo "=== tts_client ===" && grep -r "tts_client\|tts_service\|TTS_SERVICE" backend/ --include="*.py" -l | grep -v __pycache__ | wc -l
echo "=== qdrant ===" && grep -r "qdrant" frontend/src/ --include="*.tsx" --include="*.ts" -l | wc -l
echo "=== gotenberg-service ===" && grep -r "gotenberg-service" backend/ --include="*.py" --include="*.yml" -l | wc -l
```
Expected: all zeros.

- [ ] **Step 2: Count total lines removed**

```bash
git log --oneline --since="2026-03-26" --format="%h %s" | head -10
git diff --stat HEAD~3..HEAD  # Adjust based on number of phase commits
```

- [ ] **Step 3: Update memory**

Update `project_pending_tasks.md` and `project_langextract_consolidation.md` to mark P3-P5 as COMPLETED.
