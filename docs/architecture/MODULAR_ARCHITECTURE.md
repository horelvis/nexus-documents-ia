# Modular Architecture — NouxCubeIA (On-Premise)

> **Deployment mode**: single-tenant on-premise only.
> Last updated: 2026-04-22 (replaces deleted doc from commit 9dd9ebc7 which described a non-existent SaaS/On-Premise dual mode).

---

## 1. Overview

NouxCubeIA is an **on-premise, single-tenant** intelligent document management system. All services run
as Docker Compose containers on a single machine (or private server), with no cloud control plane, no
per-tenant database isolation, and no SaaS path.

The system is split into a **core API** (`api` service) and several **specialised microservices** that
handle AI inference, vector storage, knowledge graph extraction, document processing, and reactive
events. Services communicate over an internal Docker bridge network (`backend-network`) using HTTP REST
and Redis Streams. TLS termination for browser-facing endpoints is handled by an nginx reverse proxy
(`tls-proxy`).

The only **security boundary** is authentication. Every request carries a KeyCloak-issued JWT
validated through `AuthProviderFactory.verify_token()`; once authenticated, all users can read every
document in the deployment. Admin/config endpoints additionally gate on `User.is_superuser` via
`Depends(require_superuser)` from `backend/app/core/auth/superuser.py`. Per-document role-based ACL
(`roles: ARRAY(String)` + `EVERYONE` wildcard + `filter_visible_to_user()`) was removed 2026-05-08;
see [ACL_SYSTEM.md](ACL_SYSTEM.md). There is no `tenant_id`, no per-organization database schema, and
no multi-tenancy middleware.

---

## 2. Service Topology

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          BROWSER / FRONTEND                             │
│                  Next.js 15 (port 3001 dev / prod via tls-proxy)        │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTPS (TLS terminated by nginx)
                    ┌───────────────▼──────────────────┐
                    │         tls-proxy (nginx)         │
                    │  :8000 → api                      │
                    │  :8009 → emma-agent-service        │
                    │  :8007 → weaviate-service          │
                    │  :8085 → keycloak                  │
                    └──┬────────────┬───────────────────┘
                       │            │
          ┌────────────▼──┐   ┌─────▼──────────────────────────────────┐
          │  Main API     │   │        Emma Agent Service               │
          │  (api :8000)  │   │  (emma-agent-service :8009 int)         │
          │  FastAPI      │   │  LangGraph ReAct — 8 nodes, 16 tools    │
          └──┬────────────┘   └─────┬──────────┬──────────┬────────────┘
             │                      │          │          │
     ┌───────┴──┐           ┌───────▼──┐  ┌────▼───┐  ┌──▼──────────────┐
     │ storage- │           │ weaviate-│  │ know-  │  │ intelligence-   │
     │ service  │           │ service  │  │ ledge- │  │ docs-service    │
     │ (:8010)  │           │ (:8007   │  │ tree-  │  │ (:8012)         │
     │ MinIO SDK│           │  via     │  │ svc    │  │ extract+embed   │
     └───┬──────┘           │  proxy)  │  │(:8011) │  └──┬──────────────┘
         │                  └───┬──────┘  └────┬───┘     │
         │                      │              │          │
 ┌───────▼────────────────────────────────────────────────▼──────────────┐
 │                       DATA STORES                                      │
 │                                                                        │
 │  PostgreSQL :5432   Redis :6379    FalkorDB :6380   Weaviate :8080     │
 │  (nouxcube +        (cache +       (TrustGraph       (5 collections)   │
 │   langfuse DBs)      streams +      knowledge_graph)                   │
 │                      Celery)                                           │
 │                                                                        │
 │  MinIO :9000/:9001                                                     │
 │  (nexus-storage bucket)                                                │
 └────────────────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────────────┐
 │                 WORKERS (no inbound HTTP port)                        │
 │  background-worker  — Celery (queue: celery, emma_reactive)           │
 │  emma-reactive-worker — Redis Streams consumer (event_listener.py)   │
 └──────────────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────────────┐
 │                 EXTERNAL / SUPPORTING SERVICES                        │
 │  sglang        — vLLM v0.18.0, Qwen3.5-27B-AWQ GPU inference         │
 │  keycloak      — OIDC/SAML auth (KeyCloak 26.0)                      │
 │  langfuse      — Prompt management + LLM observability (:3002)       │
 │  glm-ocr       — VLM-based OCR, SGLang, 0.9B                        │
 │  docling       — IBM Docling document extraction (profile: docling)  │
 │  tika          — Apache Tika 3.1 text extraction (fallback)          │
 │  gotenberg     — LibreOffice DOCX/XLSX → PDF conversion              │
 │  document-forge-service — Template-based DOCX/PDF generation (:8013) │
 └──────────────────────────────────────────────────────────────────────┘

 ┌──────────────────────────────────────────────────────────────────────┐
 │                     MCP CONNECTOR SERVERS                             │
 │  mcp-alfresco       — Alfresco sync + indexing                       │
 │  mcp-google-drive   — Google Drive sync + OAuth                      │
 │  mcp-onedrive       — OneDrive for Business sync + OAuth             │
 └──────────────────────────────────────────────────────────────────────┘
```

---

## 3. Service Catalog

| Service | Internal port | Host exposure | Purpose | Key dependencies |
|---------|--------------|---------------|---------|-----------------|
| `api` | 8000 | :8002 (HTTP), :8000 (via tls-proxy HTTPS) | Main API — auth, document CRUD, connector management, Emma proxy | PostgreSQL, Redis, Weaviate, weaviate-service, emma-agent-service, storage-service |
| `emma-agent-service` | 8009 | :8019 localhost only (HTTP), :8009 via tls-proxy (HTTPS) | LangGraph ReAct agent, 8 nodes, 16 tools, Verified Generation, Reactive heartbeat | Redis, PostgreSQL, weaviate-service, knowledge-tree-service, sglang, langfuse |
| `weaviate-service` | 8000 | :8007 via tls-proxy | Vector search, hybrid RAG, document indexing, 5 Weaviate collections | Weaviate DB, intelligence-docs-service, knowledge-tree-service, storage-service |
| `knowledge-tree-service` | 8011 | :8011 direct | TrustGraph triple store — 4 LLM extractors, PROV-O provenance, FalkorDB CRUD | FalkorDB, PostgreSQL, sglang, langfuse |
| `intelligence-docs-service` | 8000 | :8012 localhost only | Text extraction (Docling/GLM-OCR/Tika), BGE-M3 embedding, NER entity extraction | docling, glm-ocr, tika, sglang (for langextract) |
| `storage-service` | 8010 | internal only | REST abstraction over MinIO S3 SDK — upload, download, presigned URLs | MinIO |
| `document-forge-service` | 8013 | :8013 localhost only | Template-based DOCX/PDF generation; LLM field detection + docxtpl rendering | Redis, sglang, gotenberg, weaviate-service |
| `background-worker` | 8100 (health) | internal only | Celery async tasks — claim verification, indexing retries, proactive analysis, heartbeat | Redis (broker), PostgreSQL, knowledge-tree-service |
| `emma-reactive-worker` | — | none | Redis Streams consumer — event listener, trigger engine, notification dispatch | Redis, PostgreSQL, emma-agent-service |
| `sglang` | 8000 | :8001 | vLLM v0.18.0 GPU inference — Qwen3.5-27B-AWQ, 128K context, OpenAI-compatible API | GPU (NVIDIA), HuggingFace cache |
| `weaviate` | 8080 | :8080 | Semtech Weaviate 1.28.3 vector DB — stores all collection data | — |
| `falkordb` | 6379 | :6380 (Redis protocol), :3003 (browser UI) | FalkorDB v4.2.0 OpenCypher graph DB — TrustGraph `knowledge_graph` | — |
| `db` | 5432 | :5432 | PostgreSQL 15 — `nouxcube` (business) + `langfuse` (prompts) databases | — |
| `redis` | 6379 | :6379 | Redis 7 — cache, LangGraph checkpointer, Celery broker, Redis Streams event bus | — |
| `minio` | 9000 | :9000 (API), :9001 (console) | S3-compatible object store — bucket `nexus-storage` (documents, forge templates) | — |
| `keycloak` | 8080 | :8085 via tls-proxy | KeyCloak 26.0 OIDC/SAML — JWT issuance, group management, custom theme | keycloak-db |
| `langfuse` | 3000 | :3002 | Langfuse v2 — prompt versioning, LLM observability, A/B testing | PostgreSQL (`langfuse` DB) |
| `tls-proxy` | — | :80, :443, :8000, :8007, :8009, :8085 | nginx 1.27 TLS termination + reverse proxy for browser-facing services | api, emma-agent-service, weaviate-service, keycloak |
| `glm-ocr` | 8000 | internal only | GLM-OCR 0.9B VLM — scanned doc OCR, tables, seals; served via SGLang | GPU |
| `mcp-alfresco` | 8000 | internal only | MCP server — Alfresco CMIS sync + indexing into weaviate-service | PostgreSQL, weaviate-service |
| `mcp-google-drive` | 8000 | internal only | MCP server — Google Drive sync + OAuth PKCE flow | PostgreSQL, weaviate-service |
| `mcp-onedrive` | 8000 | internal only | MCP server — OneDrive for Business sync + MS OAuth | PostgreSQL, weaviate-service |

**Optional / profile-gated services:**

| Service | Profile | Purpose |
|---------|---------|---------|
| `docling` | `--profile docling` | IBM Docling CPU document extraction (preferred over Tika for accuracy) |
| `frontend` | `--profile prod` | Next.js production build (dev uses `npm run dev` directly) |
| `ngrok` | `--profile webhooks` | Tunnel for Slack/Telegram/WhatsApp webhook callbacks |

---

## 4. Data Flow Examples

### 4.1 Document Upload

```
User (browser)
  │  POST /api/v1/documents  (multipart/form-data)
  ▼
Main API (api :8000)
  │  Validate JWT roles; persist document metadata → PostgreSQL (nouxcube)
  │  PUT /objects/{key}  (X-API-Key)
  ▼
storage-service (:8010)
  │  minio.put_object() → MinIO nexus-storage bucket
  │
  │  (returns storage key back to Main API)
  ▼
Main API
  │  POST /index  (X-API-Key, document_id, storage_key)
  ▼
weaviate-service (:8007)
  │  GET file content from storage-service
  │  POST /extract  → intelligence-docs-service (:8012)
  │     ├─ Text extraction: Docling → GLM-OCR → Tika (provider chain)
  │     ├─ Embedding: BGE-M3 (1024 dims, CPU)
  │     └─ NER entity extraction
  │  Index chunks + embeddings → Weaviate DB (Nouxcube_documents)
  │  POST /extract/triples  → knowledge-tree-service (:8011)
  │     ├─ 4 LLM extractors in parallel (definitions, relationships, objects, topics)
  │     ├─ Dedup + blacklist filter + entity linking
  │     └─ MERGE triples → FalkorDB (knowledge_graph) + PROV-O provenance
  ▼
Done — document visible in search, graph, and UI
```

### 4.2 Emma Query (Chat)

```
User (browser)
  │  POST /api/v1/emma/query/stream  (SSE, JWT in Authorization header)
  ▼
Main API (api :8000)
  │  Validate JWT; extract user_id (roles preserved as informational metadata only)
  │  Proxy → emma-agent-service  (X-User-Id, X-API-Key headers)
  ▼
emma-agent-service (:8009)
  │  LangGraph StateGraph:
  │    classify → intent router (FastEmbed ~3ms → LLM fallback)
  │    rewrite → memory_recall (AsyncPostgresStore user facts)
  │    react_loop:
  │      ├─ smart_search tool
  │      │    ├─ hybrid_search → weaviate-service (Nouxcube_documents)
  │      │    └─ graph expansion → knowledge-tree-service (FalkorDB triples)
  │      ├─ graph_rag tool → knowledge-tree-service (8-stage pipeline)
  │      └─ [other tools: web_search, forge_document, send_email, ...]
  │    synthesize → CHAT model (sglang Qwen3.5-27B)
  │  SSE events: agent_reasoning, tool_call, tool_result, message
  ▼
Main API SSE proxy → User browser
```

### 4.3 Reactive Event (Emma Reactive)

```
Trigger source (e.g. weaviate-service after indexing)
  │  XADD emma_events  {event_type: "document.indexed", document_id: "..."}
  ▼
Redis Streams (emma_events)
  ▼
emma-reactive-worker (event_listener.py, consumer group: emma_reactive)
  │  Trigger Engine — match event → configured trigger rules
  │  If match:
  │    background-worker (Celery) ← emit task  emma.analyze_new_document
  │    OR
  │    Direct notification → notification-service
  │       └─ WebSocket / email / Slack / Telegram / WhatsApp
  ▼
User receives proactive notification or insight
```

---

## 5. Directory Layout

```
backend/
├── app/                                # Main API (FastAPI)
│   ├── api/v1/                         # REST endpoints (one file per domain)
│   ├── core/
│   │   ├── auth/
│   │   │   ├── superuser.py            # require_superuser() — admin gate (replaced acl.py 2026-05-08)
│   │   │   └── keycloak.py             # OIDC JWT validation + group extraction
│   │   └── config.py
│   ├── config/
│   │   └── role_mapping.yaml           # KeyCloak group → informational role label (ADMIN, LEGAL, ...) — no longer enforced
│   ├── db/                             # SQLAlchemy models
│   ├── schemas/                        # Pydantic request/response models
│   └── services/                       # Business logic
├── microservices/
│   ├── emma-agent-service/             # LangGraph ReAct agent
│   │   ├── app/
│   │   │   ├── agents/langgraph/
│   │   │   │   ├── graph.py            # StateGraph definition
│   │   │   │   ├── nodes/              # classify, rewrite, react_loop, synthesize, ...
│   │   │   │   ├── tools/              # 16 tools (smart_search, graph_rag, forge_document, ...)
│   │   │   │   └── sectors/config.py   # Unified config (sectors removed 2026-03-31)
│   │   │   ├── core/checkpointer.py    # AsyncPostgresSaver + AsyncPostgresStore
│   │   │   ├── services/
│   │   │   │   ├── memory/             # UserFactsService, FactExtractor
│   │   │   │   ├── heartbeat/          # Proactive insight engine
│   │   │   │   └── verified_generation/# Claim-by-claim verification sub-graph
│   │   │   └── workers/event_listener.py # Emma Reactive consumer
│   │   ├── config/prompts/emma_prompts.yaml
│   │   └── scripts/seed_langfuse_prompts.py
│   ├── weaviate-service/               # Vector search + RAG pipeline
│   │   └── app/services/weaviate_service.py
│   ├── intelligence-docs-service/      # Text extraction + BGE-M3 embedding + NER
│   ├── knowledge-tree-service/         # TrustGraph (FalkorDB) — extractors, PROV-O
│   │   └── app/services/
│   │       ├── triple_store.py         # FalkorDB CRUD
│   │       ├── extractors/coordinator.py
│   │       └── graph_assembler.py
│   ├── storage-service/                # MinIO REST abstraction
│   ├── document-forge-service/         # Template DOCX/PDF generation
│   ├── background-worker/              # Celery worker + Celery Beat schedules
│   ├── mcp-alfresco-server/            # MCP connector — Alfresco
│   ├── mcp-google-drive-server/        # MCP connector — Google Drive
│   └── mcp-onedrive-server/            # MCP connector — OneDrive
├── docker/
│   ├── docker-compose.yml              # Base compose (shared service definitions)
│   ├── docker-compose.onpremise.yml    # Active override — ALWAYS edit this for on-premise
│   ├── docker-compose.test.yml         # CI test environment
│   ├── .env                            # Single source of all runtime configuration
│   └── nginx/                          # tls-proxy config + certbot scripts
├── alembic/                            # PostgreSQL migrations
│   └── versions/
└── scripts/                            # Ops scripts
    ├── init_db.py
    ├── create_migration.py
    └── alembic_safe_migrate.py
```

---

## 6. Inter-Service Communication

### HTTP REST

Most service-to-service calls are synchronous HTTP with a shared API key header:

```
X-API-Key: <MICROSERVICES_API_KEY>   # Internal service auth
X-User-Id: <uuid>                    # Propagated from authenticated request
```

`X-User-Roles` was removed 2026-05-08 along with role-based ACL — microservices no longer scope
queries by user role; all authenticated users see everything.

The `MICROSERVICES_API_KEY` secret is set once in `backend/docker/.env` and injected into every
service via `env_file`. Services that receive requests from other services validate this header
before processing.

### Redis Streams (Emma Reactive)

Asynchronous event bus for reactive triggers:

```
Producer (weaviate-service, api, etc.)
  → XADD emma_events {event_type, document_id, user_id, payload}

Consumer (emma-reactive-worker)
  → XREADGROUP GROUP emma_reactive (blocking)
  → Trigger Engine → actions (Celery tasks, notifications)
```

Events: `document.indexed`, `document.updated`, `connector.synced`,
`knowledge.graph_updated`, `analysis.completed`.

### LangGraph Persistence (PostgreSQL / psycopg3)

Emma Agent Service maintains a shared psycopg3 `AsyncConnectionPool` (min=1, max=5):

- **AsyncPostgresSaver** — per-thread conversation checkpointing (cross-turn continuity)
- **AsyncPostgresStore** — cross-thread user memory (facts namespace `("user_facts", user_id)`)

Both share the same pool. Initialised via `emma-agent-service/app/core/checkpointer.py`.

### Celery (Background Worker)

Redis (`redis://redis:6379`) is used as both Celery broker and result backend.
Registered queues: `celery` (default), `emma_reactive`.
Celery Beat schedules: `emma.daily_summary` at 08:00, `emma.heartbeat_check` every 30 min,
`emma.heartbeat_digest` at 09:00.

---

## 7. Configuration Strategy

All runtime configuration is in **one file**: `backend/docker/.env`.

**Compose override pattern:**
```
docker compose \
  -f backend/docker/docker-compose.yml \       # base definitions
  -f backend/docker/docker-compose.onpremise.yml  # active override
  up -d
```

Both files are auto-detected when running `docker compose` from `backend/docker/`.
**Always edit `docker-compose.onpremise.yml`** for on-premise changes (LLM model, GPU settings,
port mappings, service toggles). The base file defines shared structure.

**Key environment variables:**

| Variable | Value | Notes |
|----------|-------|-------|
| `DEPLOYMENT_MODE` | `on_premise` | Single value supported |
| `MICROSERVICES_API_KEY` | secret | Internal service auth |
| `SGLANG_MODEL` | `QuantTrio/Qwen3.5-27B-AWQ` | Must match `LLM_MODEL` |
| `SGLANG_DUAL_MODEL` | `false` | Enable split PLANNER/CHAT endpoints |
| `USE_LANGFUSE_PROMPTS` | `true` | Langfuse is the primary prompt source |
| `LANGGRAPH_CHECKPOINTER_ENABLED` | `true` | AsyncPostgresSaver for conversation continuity |
| `DATABASE_URL` | `postgresql+asyncpg://...` | Shared across backend + microservices |
| `CREDENTIALS_ENCRYPTION_KEY` | Fernet key | Channel credential encryption |

There is no per-tenant config, no `ACTIVE_SECTOR`, and no deployment mode branching in code.

---

## 8. Persistence and State

### PostgreSQL (`db` service)

Two logical databases on the same PostgreSQL 15 instance:

| Database | Owner | Content |
|----------|-------|---------|
| `nouxcube` | nexus_user | Business data: `indexed_documents`, `folders`, `connectors`, `emma_sessions`, `emma_user_memory_facts`, reactive tables, knowledge report cache |
| `langfuse` | nexus_user | Prompt versions, traces, scores — managed exclusively by the Langfuse service |

Migrations managed by Alembic (`backend/alembic/versions/`).

### Weaviate (vector DB)

Five active collections (no `PublicKnowledge` — deleted 2026-04-22):

| Collection | Purpose |
|-----------|---------|
| `Nouxcube_documents` | Document chunks with role ACL + enrichment properties (domain, semantic_type, quality_score, associated_person) |
| `Nouxcube_knowledge` | Knowledge snippets extracted during indexing |
| `Nouxcube_visual` | Visual/image embeddings for multimodal search |
| `TrustGraphEntities` | Entity embeddings for semantic entity lookup in graph_rag |
| `OntologyTerms` | 72 predicate definitions for semantic predicate resolution (ontology RAG) |

All collections use BGE-M3 (1024-dim) embeddings computed by `intelligence-docs-service`.

### FalkorDB (`falkordb` service, port 6380)

Single graph: `knowledge_graph`.

Schema: `:Node` (entities, documents, folders), `:Literal` (values), `:Rel` (edges).
Each `:Rel` carries `confidence`, `source_doc_id`, `extractor`, and PROV-O metadata.
72 predicates across 6 namespaces: `core/`, `legal/`, `trust/`, `medical/`, `documental/`, `prov/`.

Not scoped by role — the graph is organisation-wide. Sensitive document content should be restricted
at the document ACL layer before triple extraction writes to the graph.

### Redis (`redis` service, port 6379)

- Application cache (user sessions, search results)
- LangGraph checkpointer backing store (via psycopg3 pool on PostgreSQL, but Redis used for session TTL)
- Celery broker + result backend
- Redis Streams event bus (`emma_events` stream)

### MinIO (`minio` service, port 9000)

S3-compatible object store. Single bucket: `nexus-storage`.
Stores raw uploaded files, forge templates, and generated documents.
Accessed exclusively through `storage-service` — no direct MinIO access from other services.

### KeyCloak (`keycloak-db` service)

Separate PostgreSQL 16 container (`keycloak_data` volume). Stores user identities, group
memberships, OAuth clients, and sessions. The application never writes to this database directly.

---

## 9. Extensibility Points

### Add a new microservice

1. Create directory under `backend/microservices/<name>/`.
2. Implement FastAPI app with `/health` endpoint.
3. Add service definition to `docker-compose.onpremise.yml`.
4. Set `MICROSERVICES_API_KEY` in the service's `environment`.
5. Update `CLAUDE.md` service catalog table.

### Add a new external connector

1. Implement the `BaseConnector` interface in `backend/app/core/connectors/adapters/`.
2. Add the new type to `ConnectorType` enum.
3. Create a new MCP server under `backend/microservices/mcp-<name>-server/`.
4. Register the MCP URL in the `api` service environment and in `backend/app/api/v1/connectors.py`.
5. Update `docs/on-premise/CONNECTORS.md`.

### Add a new Emma tool

1. Implement a class inheriting from `BaseTool` in
   `emma-agent-service/app/agents/langgraph/tools/`.
2. Register in `emma-agent-service/app/agents/langgraph/tools/registry.py`.
3. Add a routing hint to the `emma_react_system` prompt in Langfuse (promote to `production` label).
4. Update `CLAUDE.md` tools table.

### Add a new KeyCloak role

1. Create the group in KeyCloak admin UI.
2. Add a mapping line in `backend/app/config/role_mapping.yaml`.
3. Restart the `api` service. No code change required.

---

## 10. What Was Removed (Historical Context)

This section documents architectural layers that were removed to simplify the system. They no longer
exist in code or configuration.

| Feature | Removed | What it was |
|---------|---------|-------------|
| **Multi-tenancy layer** | 2026-04-21 (commit 973f0797) | `tenant_id` column on every business table, `TenantMiddleware` filtering all queries, per-tenant Weaviate class prefixes. Replaced by flat single-org data model. |
| **SaaS mode** | 2026-04-21 | `DEPLOYMENT_MODE=saas` code path, Clerk auth integration, Stripe billing hooks, `modules/saas/` directory. No SaaS infrastructure ever went live. |
| **Sectors** | 2026-03-31 | `ACTIVE_SECTOR` env var selecting from per-deployment RAG configs (legal, medical, financial). Now a single unified config in `sectors/config.py` with all 14 entity patterns merged. `get_active_sector_config()` always returns the same config. |
| **SIL / SLM Router** | 2026-04-22 (docs deleted) | A TOON-based query planning layer that sat in front of the ReAct agent. Replaced entirely by the LangGraph `classify` node + FastEmbed intent router. |
| **PublicKnowledge collection** | 2026-04-22 | Separate Weaviate collection for BOE (Spanish Official Gazette) corpus. BOE legal knowledge now lives in TrustGraph (FalkorDB) as triples rather than as a parallel vector collection. |
| **ACLProviderFactory / JSONBACLProvider** | 2026-04-21 | Legacy ACL abstraction that toggled between tenant-scoped and flat filters. Was replaced briefly by direct `filter_visible_to_user()` in `backend/app/core/auth/acl.py` — itself removed 2026-05-08 (see next row). |
| **Role-based ACL** | 2026-05-08 (PR #2, merge `dc718acd`) | `roles: ARRAY(String)` on Document/IndexedDocument, `EVERYONE` wildcard, `default_document_roles` on Connector, `filter_visible_to_user()` in `backend/app/core/auth/acl.py`, the entire `acl.py` module, `EVERYONE_ROLE` + `allowed_roles()` helpers in 8 microservice `auth_headers.py` copies, `_roles_filter()` in weaviate-service, `_graph_scope()` + `user` Cypher property in knowledge-tree-service, `roles` property in 6 Weaviate collections, frontend `document-acl.service.ts` + "User Access" tab in ShareDocumentDialog. Authorization now consolidated onto `User.is_superuser` via `Depends(require_superuser)` from `backend/app/core/auth/superuser.py`. All authenticated users read every document. |
| **textextract-service** | Pre-2026 | Standalone text extraction service. Functionality merged into `intelligence-docs-service`. |
| **langextract-service** | Pre-2026 | Standalone entity extraction service. Functionality merged into `intelligence-docs-service` as `LangExtractProvider`. |
| **presentation-service** | Pre-2026 | Directory no longer exists. Presentation generation now handled by `document-forge-service`. |

---

## Related Documentation

- [`docs/architecture/ACL_SYSTEM.md`](ACL_SYSTEM.md) — Authorization model (deprecation notice for the legacy role-based ACL + current `is_superuser` gate)
- [`docs/architecture/TRUSTGRAPH.md`](TRUSTGRAPH.md) — TrustGraph triple store and graph_rag pipeline
- [`docs/architecture/EMMA_AI.md`](EMMA_AI.md) — LangGraph ReAct agent internals
- [`docs/architecture/EMMA_REACTIVE.md`](EMMA_REACTIVE.md) — Event-driven reactive system
- [`docs/architecture/PROMPT_MANAGEMENT.md`](PROMPT_MANAGEMENT.md) — Langfuse prompt lifecycle
- [`docs/architecture/USER_MEMORY.md`](USER_MEMORY.md) — Cross-session user fact persistence
- [`docs/on-premise/ONBOARDING.md`](../on-premise/ONBOARDING.md) — Deployment walkthrough
