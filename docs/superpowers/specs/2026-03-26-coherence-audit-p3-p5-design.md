# Coherence Audit P3-P5: Dead Code Elimination

**Date**: 2026-03-26
**Status**: Approved
**Approach**: 3-phase cleanup by risk level
**Estimated removal**: ~15K LOC across ~170 files

## Context

The coherence audit (2026-03-25) identified three priority tiers of dead/duplicate code remaining after the LangExtract consolidation. SaaS mode is deprecated — only on-premise is supported. All decisions resolved: eliminate everything dead, no deprecation periods.

Prior cleanup already removed: langextract-service, legacy NER code, Qdrant migration code, presentation-service from compose (-3,929 lines).

This session already removed: 6 start scripts, textextract-service from docker-compose (-579 lines).

## Design Decisions

| Item | Decision | Rationale |
|------|----------|-----------|
| Camunda (BPM) | **Remove** all code + directory | Not deployed, code calls non-existent service |
| TTS | **Remove** endpoints + client | Not deployed, silent failure |
| Gotenberg wrapper | **Remove** directory, forge calls `gotenberg:3000` direct | Wrapper is dead, bare container works |
| chat.py + assistant.py | **Remove** immediately | On-premise only uses `/emma/query` |
| textextract-service | **Remove** directory + all callers | Replaced by intelligence-docs-service |
| MCP connectors | **Migrate** to indexing pipeline | Must not call extraction services directly |
| Clerk/Stripe config | **Remove** | SaaS deprecated |

---

## Phase 1: Low Risk Deletions

Zero functional impact. Pure dead code removal.

### P5: Orphan Directories (9 directories)

| Directory | LOC | Notes |
|-----------|-----|-------|
| `backend/microservices/ollama-service/` | 561 | Replaced by SGLang |
| `backend/microservices/presentation-service/` | 2,273 | Already commented "REMOVED" in compose |
| `backend/microservices/camunda-service/` | 2,473 | Not in compose, code references removed in this phase |
| `backend/microservices/engine-template-service/` | ~0 | Empty/config only |
| `backend/microservices/gotenberg-service/` | 798 | Dead wrapper, bare gotenberg in compose |
| `backend/microservices/signature-service/` | 1,360 | Feature not active |
| `backend/microservices/template-editor-service/` | 1,615 | Feature not active |
| `backend/microservices/mcp-storage-server/` | 0 | Empty |
| `backend/microservices/mcp-external-servers/` | 1,196 | Not deployed |

### P4: Ghost Config

**config.py removals**:
- `CLERK_API_URL`, `CLERK_SECRET_KEY`, `CLERK_PUBLISHABLE_KEY`, `CLERK_JWT_VERIFICATION_KEY` (4 settings)
- `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, `STRIPE_WEBHOOK_SECRET`, 5 price IDs (8 settings)
- `CAMUNDA_SERVICE_URL` (1 setting)
- `TTS_SERVICE_URL` (1 setting)

**Associated code removals**:
- `backend/app/auth/clerk.py`, `backend/app/auth/providers/clerk.py` — Clerk auth provider
- `backend/app/api/v1/stripe.py` — Stripe webhook endpoint
- `backend/app/services/subscription_service_v2.py` — Stripe subscription logic
- `backend/app/api/v1/tts.py` — TTS endpoint
- `backend/app/services/tts_client.py` — TTS HTTP client
- `backend/app/api/v1/workflows.py` — Camunda workflows endpoint
- `backend/app/services/workflow_service.py` — Camunda workflow service
- Feature flags in `backend/app/core/features.py`: `CLERK_AUTH`, `WORKFLOW_MANAGEMENT`
- `backend/app/services/lgpd_deletion_service.py` — remove Clerk/Stripe deletion calls (keep GDPR core if it serves other purposes)

**Frontend**:
- `frontend/src/components/agents/agent-health-check.tsx` — remove "qdrant" references

**Router deregistration**:
- Remove imports and `include_router` calls for: `stripe`, `tts`, `workflows` in `backend/app/api/v1/api.py`

### P3: Dead Classifiers + Deprecated Endpoints

- Delete `backend/app/services/document_classifier.py` (17 LOC, obsolete keyword matcher)
- Delete `backend/app/services/ml/document_classifier.py` (400+ LOC, unused NLP patterns)
- Delete `backend/app/api/v1/chat.py` (78 LOC)
- Delete `backend/app/api/v1/assistant.py` (500+ LOC)
- Deregister `chat` and `assistant` routers from `backend/app/api/v1/api.py`

### Phase 1 Verification

```bash
# Compose still valid
docker compose config --services

# Python imports OK (from backend/)
python -c "from app.main import app; print('OK')"

# No dangling references
grep -r "textextract\|camunda\|clerk\|stripe\|tts_client" backend/app/ --include="*.py" -l
# Expected: zero hits (or only comments)
```

---

## Phase 2: textextract-service Cleanup

Remove the service directory and its legacy clients in weaviate-service.

### Deletions

| File/Directory | LOC | Reason |
|---|---|---|
| `backend/microservices/textextract-service/` | 1,653 | Entire service — replaced by intelligence-docs |
| `weaviate-service/app/services/rag/textextract_client.py` | ~240 | Legacy HTTP client — replaced by `intelligence_client.py` |
| `weaviate-service/app/services/rag/ocr_client.py` | ~150 | Pointed to textextract for OCR — `ENHANCED_OCR_ENABLED=false` permanently |
| `weaviate-service/app/services/rag/__init__.py` | imports | Clean re-exports of `textextract_client`, `TextExtractClient`, `TextExtractResult` |

### What stays

- `intelligence_client.py` — already the active replacement with connection pooling
- `indexing_pipeline.py` — already uses `intelligence_extract_client`
- `tika` container in compose — intelligence-docs uses it as fallback via `TIKA_URL`

### Phase 2 Verification

```bash
# No textextract references in weaviate-service (excluding comments)
grep -r "textextract" backend/microservices/weaviate-service/ --include="*.py" | grep -v "^#\|#.*textextract\|REMOVED\|replaced\|Drop-in"

# Indexing pipeline import check
docker compose exec weaviate-service python -c "from app.services.rag.indexing_pipeline import IndexingPipeline; print('OK')"
```

---

## Phase 3: MCP Connector Migration + Forge

Migrate remaining callers from direct textextract calls to the indexing pipeline.

### MCP Connectors (3 services)

`mcp-google-drive`, `mcp-onedrive`, `mcp-alfresco` currently download files and call textextract-service directly for extraction. This is architecturally wrong — they should feed files through the weaviate-service indexing pipeline.

**Migration pattern**:
- Remove direct calls to `TEXT_EXTRACTION_SERVICE_URL`
- Route file bytes through weaviate-service indexing endpoint (the pipeline handles: extraction via intelligence-docs → chunking → embedding → Weaviate insert)
- Remove `TEXT_EXTRACTION_SERVICE_URL` env vars from docker-compose.onpremise.yml for each MCP service

**Investigation needed before implementation**: Read each MCP connector to understand its current extraction call pattern and determine the correct weaviate-service indexing endpoint to use.

### Channel Services (2 files)

- `backend/app/services/channels/gdrive_channel_service.py`
- `backend/app/services/channels/gmail_channel_service.py`

Same pattern: redirect to indexing pipeline instead of calling extraction directly.

### Forge → gotenberg direct

- Update `document-forge-service` config: `gotenberg-service:8005` → `gotenberg:3000`
- The `gotenberg-service/` directory deletion is already handled in Phase 1

### Phase 3 Verification

```bash
# Zero textextract references in entire backend
grep -r "textextract" backend/ --include="*.py" -l | grep -v __pycache__
# Expected: zero (or only historical comments)

# Zero gotenberg-service references
grep -r "gotenberg-service" backend/ --include="*.py" --include="*.yml" -l
# Expected: zero

# MCP connector health
docker compose exec mcp-google-drive python -c "print('import OK')"
```

---

## Risk Mitigation

- **Phase 1** is pure deletion of unreferenced code — lowest risk, highest LOC impact
- **Phase 2** removes code that is already unreachable (textextract not in compose)
- **Phase 3** changes behavior (MCP connector routing) — requires reading each connector's current flow before implementing
- Each phase is independently committable and verifiable
- If Phase 3 reveals unexpected complexity, it can be deferred without blocking Phases 1-2

## Success Criteria

- `grep -r "textextract\|camunda\|clerk\|stripe\|tts_client\|qdrant" backend/ --include="*.py" -l` → zero active code hits
- `docker compose config --services` → no errors
- All existing services start and pass health checks
- Net deletion: ~15,000 LOC
