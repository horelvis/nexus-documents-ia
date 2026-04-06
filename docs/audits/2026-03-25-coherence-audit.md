# Coherence Audit Report — 2026-03-25

## 1. Critical (blocks startup or causes runtime errors)

### C1. `vector_service_direct.py` imports `qdrant_client` — will crash on import
- **File**: `backend/app/services/vector_service_direct.py:7-8`
- `from qdrant_client import QdrantClient` — Qdrant is not in the architecture
- References `settings.QDRANT_HOST` and `settings.QDRANT_PORT` which do NOT exist in config.py
- **Imported by**: `virtual_assistant_agent.py`, `document_service.py` (via `EmbeddingService`)

### C2. `migration_service.py` instantiates at module level — crash risk
- **File**: `backend/app/services/migration_service.py:428`
- `migration_service = MigrationService()` runs at import time, Qdrant code throughout
- Used by `api/v1/migration.py:7`

### C3. `document-forge-service` references non-existent `gotenberg-service` container
- **File**: `docker-compose.onpremise.yml:676`
- `GOTENBERG_SERVICE_URL=http://gotenberg-service:8005` — compose defines `gotenberg` (bare container, port 3000), NOT `gotenberg-service` (FastAPI wrapper, port 8005)
- Directory `backend/microservices/gotenberg-service/` exists but is NOT in compose
- **Impact**: document-forge PDF conversion will fail

### C4. `notebooks.py` references non-existent services
- **File**: `backend/app/api/v1/notebooks.py:50-51`
- `PODCAST_SERVICE_URL = "http://podcast-service:8000"` — no podcast-service in compose
- `PRESENTATION_SERVICE_URL = "http://presentation-service:8000"` — presentation-service REMOVED

### C5. `LANGEXTRACT_SERVICE_URL` config field misleadingly named
- **File**: `backend/app/core/config.py:205`
- Variable says `LANGEXTRACT` but points to `intelligence-docs-service`
- `.env.example:89` still has old URL pointing to removed langextract-service

## 2. Dead Code (safe to delete)

| File | Lines | Reason |
|------|-------|--------|
| `app/services/vector_service_direct.py` | 164 | Pure Qdrant client, crashes on import |
| `app/services/migration_service.py` | 428 | Qdrant-to-Weaviate migration, completed |
| `app/api/v1/migration.py` | ~50 | API layer for dead migration service |
| `app/services/virtual_assistant_agent.py` | ~300 | CrewAI legacy, replaced by Emma LangGraph |
| `app/services/agent_router_service.py` | ~400 | Unused document routing agent |
| `app/services/elysia_insights_service.py` | ~30 | Explicit stub, marked "TODO: Remove" |
| `app/services/embedding_service.py` | ~100 | Legacy CAG embeddings, replaced by intelligence-docs |
| `app/services/document_service.py` | ~500 | Sync service, replaced by async_document_service |
| `app/services/subscription_service_v2.py` | ~200 | Stripe SaaS billing, SaaS deprecated |
| `app/api/v1/stripe.py` | ~150 | Stripe endpoints, SaaS deprecated |
| `frontend/.../temporalio.service.ts` | ~30 | Explicit deprecated stub |

**Total**: ~2,350+ lines of dead code

## 3. Duplicate Functionality

### F1. Document Classification (4 places)
1. `backend/app/services/document_classifier.py` — keyword matcher (primitive)
2. `intelligence-docs-service/app/pipeline/classifier.py` — filename regex
3. `weaviate-service/app/services/rag/semantic_type_classifier.py` — keyword + embedding (production)
4. `backend/app/api/v1/document_categorization.py` — API that calls intelligence-docs

### F2. Text extraction: textextract-service alongside intelligence-docs
- `textextract-service` + `tika` still in compose
- `intelligence-docs-service` has Docling + GLM-OCR and "replaces textextract-service"
- `weaviate-service` depends on BOTH

### F3. `document_type_detector.py` vs `document_classifier.py`
- YAML-based pattern detector vs hardcoded keyword matcher
- Both do same thing differently

### F4. Chat/Assistant endpoints overlap
- `chat.py` — legacy SearchService
- `assistant.py` — legacy CAGClient
- `emma.py` — current Emma AI (production)

## 4. Ghost References

| Location | References | Status |
|----------|-----------|--------|
| `.env.example:89` | `langextract-service:8000` | Service removed |
| `config.py:205` | `LANGEXTRACT_SERVICE_URL` name | Misleading name |
| `config.py:268-272` | Clerk config | SaaS deprecated |
| `config.py:21-28` | Stripe config (8 settings) | SaaS deprecated |
| `config.py:276` | `CAMUNDA_SERVICE_URL` | Not in compose |
| `config.py:277` | `TTS_SERVICE_URL` | Not in compose |
| `frontend agent-health-check.tsx` | `qdrant` health check | Qdrant removed |
| `weaviate_client.py:252` | `migrate_from_qdrant()` method | Migration completed |
| `compose:1268` | `ollama_data:` volume | No ollama service |

## 5. Orphan Microservice Directories (not in compose)

| Directory | Status |
|-----------|--------|
| `ollama-service/` | Dead — SGLang replaced it |
| `presentation-service/` | Compose says "REMOVED" but directory persists |
| `camunda-service/` | Not in compose, ghost config |
| `engine-template-service/` | Not in compose, unclear if needed |
| `gotenberg-service/` | Exists but not deployed (compose only has bare gotenberg) |
| `signature-service/` | Not in compose |
| `template-editor-service/` | Not in compose |
| `mcp-storage-server/` | Replaced by storage-service |
| `mcp-external-servers/` | Not in compose |

## 6. Recommendations (prioritized)

### Priority 1 — Fix runtime errors
1. Fix gotenberg-service reference in document-forge-service
2. Fix `.env.example` LANGEXTRACT_SERVICE_URL
3. Rename `LANGEXTRACT_SERVICE_URL` to `INTELLIGENCE_DOCS_SERVICE_URL` in config.py

### Priority 2 — Remove dead code (~2,350 lines)
4. Delete `vector_service_direct.py` (crashes on import)
5. Delete `migration_service.py` + `api/v1/migration.py`
6. Delete `virtual_assistant_agent.py`
7. Delete `agent_router_service.py`
8. Delete `elysia_insights_service.py`
9. Delete `embedding_service.py`
10. Remove `ollama_data` volume from compose

### Priority 3 — Consolidate duplicates
11. Deprecate `textextract-service` + `tika`, fully migrate to intelligence-docs
12. Consolidate classifiers: keep intelligence-docs + weaviate semantic_type_classifier
13. Deprecate `chat.py` and `assistant.py` in favor of `emma.py`

### Priority 4 — Clean ghost config
14. Remove Clerk, Stripe, Camunda, TTS config from config.py
15. Remove `weaviate_client.migrate_from_qdrant()` method
16. Clean frontend qdrant references

### Priority 5 — Directory cleanup
17. Delete orphan microservice directories (ollama-service, presentation-service, camunda-service, etc.)
