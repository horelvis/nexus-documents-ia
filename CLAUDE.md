# CLAUDE.md - NouxCubeIA Project Guidelines

This file provides guidance to Claude Code (claude.ai/code) when working with code in the NouxCubeIA repository.

## Development Commands

### Docker Compose (IMPORTANT)
- The **active compose** for on-premise is `docker-compose.onpremise.yml`, which **overrides** `docker-compose.yml`
- Both files are loaded together: `docker compose` auto-detects them via `docker-compose.yml` + `docker-compose.onpremise.yml`
- **Always edit `docker-compose.onpremise.yml`** for on-premise changes (vLLM/LLM config, services, etc.)
- `docker-compose.yml` is the base; `docker-compose.onpremise.yml` overrides/extends it
- LLM config (model, quantization, GPU settings) lives in `docker-compose.onpremise.yml`

### Backend
- **Start dev**: `cd backend/docker && docker compose up -d`
- **Start dev (build first)**: `cd backend/docker && docker compose up -d --build`
- **Local API (no Docker)**: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Init database**: `cd backend && python -m scripts.init_db`
- **Migrations**: `cd backend && alembic upgrade head`
- **Run tests**: `cd backend/tests && ./run_tests.sh`
- **Tests (real stores)**: `cd backend/docker && docker compose -f docker-compose.test.yml up`
- **Stop**: `cd backend/docker && docker compose down`

### Frontend
- **Requires**: Node.js 18+ (`nvm use 18` or `nvm use 20`)
- **Dev**: `cd frontend && npm run dev` (port 3001, HTTPS)
- **Build**: `cd frontend && npm run build`
- **Lint**: `cd frontend && npm run lint`
- **Install**: `cd frontend && npm install`

### Onboarding
- **Full docs**: [`docs/on-premise/ONBOARDING.md`](docs/on-premise/ONBOARDING.md)
- **Onboarding mode**: `cd backend/docker && ./onboarding.sh start` (GPU → Docling, vLLM off)
- **Index all**: `./onboarding.sh sync-all` then `./onboarding.sh status` to monitor
- **Go live**: `./onboarding.sh finish` (GPU → vLLM, Emma operational)
- **Compose override**: `docker-compose.onboarding.yml` (Docling GPU)

### Full Stack
- Backend services: `cd backend/docker && docker compose up -d` (PostgreSQL, Redis, Weaviate, Elasticsearch, microservices with live reload)
- Frontend: `cd frontend && npm run dev` (port 3001)
- API docs: `http://localhost:8000/docs`

## Architecture Overview

**NouxCubeIA** is a **single-tenant intelligent document management system** with microservices architecture and role-based access control (KeyCloak OIDC/SAML + `roles: ARRAY(String)` on documents, `EVERYONE` wildcard).

- **Backend**: FastAPI (Python 3.9+), async/await throughout
- **Frontend**: Next.js 15 App Router, TypeScript, OIDC/SAML auth
- **Database**: PostgreSQL 15 + Weaviate (vectors) + FalkorDB (graph) + Elasticsearch (full-text)
- **Storage**: MinIO (on-premise, bucket `nexus-storage`). Legacy GCS support remains as dormant config.
- **AI/ML**: vLLM v0.18.0 (single-model: Qwen3.5-9B, dual-phase PLANNER/CHAT) + LangGraph multi-agent orchestration

### PostgreSQL

The `db` service uses vanilla `postgres:15`. Knowledge graph operations use **FalkorDB** (Redis-based, port 6380). Langfuse database is initialized via `init-scripts/02-init-langfuse.sql`.

### Microservices

| Service | Port | Purpose |
|---------|------|---------|
| Main API | 8000 | Core business logic, auth, document management |
| Emma Agent Service | 8019 (→8009 internal) | LangGraph multi-agent RAG, Verified Generation |
| Weaviate Service | 8007 | Vector search, document indexing (embeddings via intelligence-docs) |
| Intelligence Docs Service | 8012 | Text extraction (Docling/GLM-OCR), embedding (BGE-M3), entity extraction |
| Knowledge Tree Service | 8011 | TrustGraph triple store (:Node/:Literal/:Rel), 4 LLM extractors, PROV-O provenance |
| Background Worker | 8100 | Celery async task processing |
| Emma Reactive Worker | — | Event listener + trigger engine (Redis Streams consumer) |
| Storage Service | 8010 (internal only) | MinIO abstraction for document blobs |
| Document Forge Service | 8013 | PDF/DOCX generation (used by `forge_document` tool) |
| MinIO | 9000/9001 | S3-compatible object storage, bucket `nexus-storage` |
| vLLM | internal | GPU inference — Qwen3.5-9B (single-model, dual-phase PLANNER/CHAT) |

Full-text search is planned (an `elasticsearch-service` microservice is scaffolded but not wired into docker-compose).

### Deployment Mode (On-Premise Only)

Single-tenant, on-premise only. Multi-tenancy and SaaS mode have been fully removed.

| Feature | Details |
|---------|---------|
| Auth | OIDC/SAML (KeyCloak) |
| ACL | `roles: ARRAY(String)` on IndexedDocument, `EVERYONE` wildcard for public docs |
| Documents | `indexed_documents` table |
| Config | `DEPLOYMENT_MODE=on_premise` |

### Unified Config (Sectors Removed)

Sectors were removed (2026-03-31). `ACTIVE_SECTOR` is ignored. All 14 entity patterns are merged into a single unified configuration. `get_active_sector_config()` always returns the same config.

**Key files**: `emma-agent-service/app/agents/langgraph/sectors/config.py` (unified config — directory name `sectors/` is historical from the pre-2026-03-31 multi-sector architecture; the module itself is now a single merged config)

### Emma Agent Service (LangGraph)

**Flow** (ReAct Agent — 8 nodes, two paths):
```
START → classify → [fast_path → END]
                 → rewrite → memory_recall → react_loop ⟲ → synthesize → END           (simple)
                 → rewrite → memory_recall → decompose → Send[swarm_worker × N] →       (complex)
                   synthesize_swarm → END
```

**Persistence** (LangGraph Level 3):
- **AsyncPostgresSaver** checkpointer — conversation continuity across turns (thread-scoped)
- **AsyncPostgresStore** — cross-thread user memory (facts, preferences)
- Both share a single psycopg3 `AsyncConnectionPool` (min=1, max=5)
- Config: `LANGGRAPH_CHECKPOINTER_ENABLED=true` (default), uses `DATABASE_URL`
- Key file: `emma-agent-service/app/core/checkpointer.py`

**Structure**:
- `agents/langgraph/graph.py` — StateGraph definition (compiled with checkpointer + Store)
- `agents/langgraph/nodes/` — All pipeline nodes (classify, rewrite, memory_recall, react_loop, synthesize_react, decompose, swarm_worker, synthesize_swarm)
- `agents/langgraph/sectors/` — Sector configuration
- `services/verified_generation/` — Claim-by-claim verification with SSE
- `config/prompts/emma_prompts.yaml` — All prompts

**Key features**:
- **Intent Router**: FastEmbed semantic (~3ms) → LLM fallback (~200ms) → default document_query
- **RLM Processor**: Recursive pipeline for large docs (>16K tokens), Redis cached
- **Verified Generation**: Claim-by-claim verification with SSE streaming
- **LLM Router**: Dual-model architecture with automatic fallback (see below)
- **SmartSearch**: Unified multi-store search (Weaviate + FalkorDB) (see below)
- **Social Agent**: Conversational agent for social channels (see below)
- **Emma Reactive**: Event-driven proactive system (see below)
- **Prompt Management**: Dynamic prompts, rules, guardrails (see below)

### LLM Router — Dual-Model Architecture

MemoRAG-inspired dual-model routing where a fast planner model handles tool calling/routing and a quality chat model handles final response generation.

**Architecture**:
```
                    ┌──────────────────────────────────────────┐
                    │            LLMRouter                     │
                    │                                          │
User Query ──────►  │  role=PLANNER → vLLM (9B, temp=0.3)     │
                    │  role=CHAT    → vLLM (9B, temp=0.6)      │
                    │                                          │
                    │  Fallback chain per role+provider         │
                    └──────────────────────────────────────────┘
```

**Role Assignment**:
| Role | Model | Used By | Purpose |
|------|-------|---------|---------|
| `PLANNER` | Qwen3.5-9B (temp=0.3) | classify, memory_recall, react_loop, decompose, swarm_worker, intent_router, verified eval, heartbeat, fact_extractor | Tool calling, JSON extraction, routing |
| `CHAT` | Qwen3.5-9B (temp=0.6) | synthesize, synthesize_swarm, rlm_processor, writer_agent, specialists, prediction_synthesizer | User-facing text generation |

**Usage**:
```python
from app.agents.llm_router import get_llm_router
from app.agents.llm_client import ModelRole

router = await get_llm_router()
# Tool calling (Qwen3.5-9B, temp=0.3, greedy for tool selection)
response = await router.chat(messages, tools=tools, role=ModelRole.PLANNER)
# Text generation (quality 9B model)
response = await router.chat(messages, role=ModelRole.CHAT)
```

**Backwards Compatible**: `SGLANG_DUAL_MODEL=false` (default) — both roles use the same model/endpoint. All existing callers default to `ModelRole.CHAT`. Legacy `VLLM_*` env vars are accepted as fallback.

**Activation**: Set `SGLANG_DUAL_MODEL=true` in `.env` and start with `docker compose --profile dual-model up -d`.

**Environment Variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `SGLANG_DUAL_MODEL` | `false` | Enable dual-model routing |
| `SGLANG_PLANNER_URL` | `SGLANG_BASE_URL` | Planner SGLang endpoint |
| `SGLANG_PLANNER_MODEL` | `Qwen/Qwen3.5-4B` | Planner model name |
| `SGLANG_PLANNER_MAX_TOKENS` | `4096` | Planner max output tokens |
| `SGLANG_PLANNER_TEMPERATURE` | `0.3` | Planner temperature |
| `SGLANG_PLANNER_GPU_UTIL` | `0.18` | Planner GPU memory fraction |
| `SGLANG_TOOL_PARSER` | `qwen3_coder` | Tool call parser (Qwen3.5 uses XML) |

**Key files**:
- `emma-agent-service/app/agents/llm_router.py` — LLMRouter with `(provider, role)` client pool
- `emma-agent-service/app/agents/llm_client.py` — `ModelRole` enum, `create_llm_config_for_provider(role=)`
- `emma-agent-service/app/core/config.py` — Dual-model settings (`sglang_*` attrs, `VLLM_*` fallback)
- `docker-compose.onpremise.yml` — `sglang-planner` service (profiles: [dual-model])

### TrustGraph — Knowledge Graph Triple Store

> **Full docs**: [`docs/architecture/TRUSTGRAPH.md`](docs/architecture/TRUSTGRAPH.md)

The knowledge graph uses a **TrustGraph-model RDF-style triple store** (`:Node`/`:Literal`/`:Rel`) on FalkorDB. Documents are processed by 4 parallel LLM extractors (definitions, relationships, objects, topics) producing semantic triples with PROV-O provenance and automatic contradiction detection.

**Schema**: Everything is a `:Node` (entities, documents, folders) or `:Literal` (values), connected by `:Rel` edges carrying URI predicates (e.g., `nouxcube://predicate/legal/empleado-de`). 72 predicates seeded across `core/`, `legal/`, `trust/`, `medical/`, `documental/`, `prov/` namespaces.

**Pipeline**: `weaviate-service` → `POST /extract/triples` → `ExtractionCoordinator` → 4 extractors in parallel via `asyncio.gather` → dedup → blacklist filter → entity linking → FalkorDB MERGE → PROV-O → contradiction detection → consensus scoring.

**Key files**:
- `knowledge-tree-service/app/services/triple_store.py` — CRUD (MERGE Node/Literal, CREATE Rel)
- `knowledge-tree-service/app/services/triple_query.py` — 8 SPO query patterns + `build_context()`
- `knowledge-tree-service/app/services/extractors/coordinator.py` — Orchestrates 4 extractors + blacklist + consensus
- `knowledge-tree-service/app/services/provenance.py` — PROV-O triples per extraction
- `knowledge-tree-service/app/services/contradiction.py` — Batch contradiction detection
- `knowledge-tree-service/app/services/consensus.py` — Cross-source agreement counting
- `knowledge-tree-service/app/services/entity_blacklist.py` — Filter generic concepts from extraction
- `knowledge-tree-service/app/services/ontology_search.py` — Semantic predicate resolution via Weaviate OntologyTerms
- `knowledge-tree-service/app/services/template_executor.py` — Cypher template registry + execution
- `knowledge-tree-service/app/services/graph_assembler.py` — Assemble graph data for reports (KPIs, sources, trust)
- `knowledge-tree-service/scripts/reindex_trustgraph.py` — Full graph rebuild

**graph_rag pipeline** (8 stages): Entity retrieval → BFS subgraph → **LLM-guided expansion** → Label resolution → Semantic pre-filter with **composite 5-signal scoring** (semantic + confidence + authority + consensus + recency) → LLM edge scoring → Context formatting with **chain-of-thought paths** → Source provenance.

**Phases**: Phase 1 (Automated Ingest) — COMPLETE. Phase 2 (Semantic Similarity Retrieval) — COMPLETE. Phase 3a (Clean Graph) — COMPLETE. Phase 3b (Smart Traversal) — COMPLETE. Phase 3c (Knowledge Expert) — COMPLETE.

### SmartSearch — Unified Multi-Store Search

The `smart_search` tool provides unified document search across 2 data stores so the LLM doesn't have to choose which tool to call.

**Pipeline** (~200ms total):
```
Entity Extraction (regex ~3ms) → Scope Detection (rules) → Filter Enrichment
    → Graph Expansion (~20-50ms) → Parallel Search (asyncio.gather ~100ms)
    → Merge + Dedup → Multi-Signal Re-Rank (~1ms) → Format for LLM
```

**2 Data Stores**:
| Store | What | How |
|-------|------|-----|
| Weaviate | Documents (hybrid search) | `WeaviateClient.hybrid_search()` with enrichment filters |
| FalkorDB | Entity relationships (TrustGraph triples) | `KnowledgeTreeClient.query_triples()` via graph_expander |

**Enrichment Properties** (first-class Weaviate properties, not JSONB):
- `semantic_type` — Document type (factura, contrato, nomina, sentencia, etc.) — sole taxonomy
- `quality_score` — Quality 0.0-1.0 from DocumentIntelligence
- `associated_person` — Person from folder hierarchy or entity extraction

**5-Signal Re-Ranking**:
| Signal | Weight |
|--------|--------|
| similarity | 0.40 |
| quality | 0.20 |
| graph | 0.20 |
| recency | 0.10 |
| entity | 0.10 |

**Config**: `SMART_SEARCH_RERANK_ENABLED=true`, `SMART_SEARCH_GRAPH_ENABLED=true`

**Key files**:
- `emma-agent-service/app/agents/langgraph/tools/smart_search.py` — SmartSearchTool implementation
- `emma-agent-service/app/agents/langgraph/tools/registry.py` — Tool registration
- `emma-agent-service/app/agents/langgraph/sectors/config.py` — Unified rerank weights
- `weaviate-service/app/services/weaviate_service.py` — Enrichment properties + filters
- `knowledge-tree-service/app/api/triples.py` — `/triples/query` endpoint (graph expansion)

**ReAct Agent Tools** (16 total):
| Tool | Purpose |
|------|---------|
| `smart_search` | Unified document search (hybrid Weaviate + graph expansion) |
| `graph_rag` | Knowledge graph retrieval with 8-stage pipeline (entity → BFS → guided expansion → scoring → provenance) |
| `get_document_content` | Read full document by ID |
| `structural_query` | Count, list, filter via FalkorDB TrustGraph |
| `invoke_agent` | Delegate to a specialist from the admin-curated agents catalog (replaces `analyze_domain`) |
| `web_search` | Internet search (Tavily primary, DuckDuckGo fallback) |
| `search_jurisprudence` | CENDOJ jurisprudence search |
| `list_sources` | Discover available data sources |
| `query_connector` | Query external connectors (SharePoint, etc.) |
| `generate_document` | Generate document from template |
| `forge_document` | Create PDF documents |
| `send_email` | Send email notifications |
| `verified_generation` | Claim-by-claim verification sub-graph |
| `predictive_analysis` | Predictive analysis sub-graph |
| `generate_knowledge_report` | Generate structured reports with KPIs and verified citations from knowledge graph |
| `terminate` | Signal completion with response |

### Agents Catalog (admin-curated)

> **Full docs**: [`docs/architecture/AGENTS.md`](docs/architecture/AGENTS.md)

Admin-curated specialist agents replace the legacy hardcoded
`analyze_domain` list. Each agent has identity (name/slug/icon/color),
persona (Langfuse prompt + style/language modifiers), data scope
(7 filter dimensions), and runtime params (model_role, temperature).

Invocation: end users type `@<slug>` in the Emma chat. The
@-mention menu (`entity-search-menu.tsx`) renders the active catalog
under a "🤖 Asistentes" section. The selected slug travels through
`useStreamSubmit` → ReActState.agent_slug → classify_node short-circuit
→ react_loop forced-invocation directive → `invoke_agent` tool call.
The bubble shows a 🤖 chip when the response came from a non-default
agent.

Source of truth:
- DB row in `agents` table (admin-only writes via `/api/v1/agents/`).
- Langfuse `agent_<slug>_persona` prompt (label `production`), pushed
  on every CRUD write via `emma-agent-service /internal/prompts/push-persona`.
- Disaster recovery: `python backend/scripts/sync_agents_to_langfuse.py`.

Seed: `python backend/scripts/seed_default_agents.py` inserts
`emma_general` (is_seed=True, is_active=True) + 3 starters
(contabilidad, ventas, legal — is_active=False, admin reviews
before publishing).

### Prompt Management System

> **Full docs**: [`docs/architecture/PROMPT_MANAGEMENT.md`](docs/architecture/PROMPT_MANAGEMENT.md)
> **Langfuse Setup**: [`docs/guides/LANGFUSE_SETUP.md`](docs/guides/LANGFUSE_SETUP.md)

Langfuse is the **only** prompt source. Missing prompts raise `PromptNotFoundError` — there is no YAML fallback.

| Component | Description | API Endpoint |
|-----------|-------------|--------------|
| **Langfuse** | Prompt versioning, A/B testing, rollback | Web UI: http://localhost:3002 (admin@nouxcube.com / LangfuseAdmin2024!) |
| **Prompt Registry** | Single source of truth for all 91 prompt names | `prompt_registry.py` |
| **Rules** | Dynamic prompt injection by context | `/prompts/rules` |
| **Guardrails** | Post-LLM validation (PII, keywords) | `/prompts/guardrails` |
| **Few-Shot** | Semantic example retrieval | `/prompts/few-shot` |

**Prompt source**: Langfuse is the ONLY source (label=`"production"` by default via `LANGFUSE_PROMPT_LABEL`). Missing prompts raise `PromptNotFoundError` — there is no YAML fallback. The YAML file `config/prompts/emma_prompts.yaml` persists as historical reference only.

**Architecture**: Emma Service (8019/8009) → HTTP Proxy → Main API (8000) → PostgreSQL

**Seeding prompts**: There is no aggregate seed script. Each prompt (or coherent set of prompts) has its own one-off migration script under `emma-agent-service/scripts/` that pushes inline content to Langfuse via `langfuse.create_prompt()`. Adding a new prompt means: (1) add a name entry to `PROMPT_REGISTRY`, (2) write a `migrate_<feature>_prompts.py` script with the text inline, (3) run it inside the container.

Current migration scripts:

| Script | What it seeds |
|---|---|
| `migrate_9b_prompt_optimization.py` | Streamlined `emma_react_system` for Qwen3.5-9B |
| `migrate_explain_prompts.py` | `emma_explain_system` + `emma_explain_user` (humanized trace) |
| `migrate_knowledge_report_prompt.py` | Adds `generate_knowledge_report` routing to `emma_react_system` |
| `migrate_ner_prompts.py` | `ner_system` + NER few-shot prompts (intelligence-docs OpenAI NER) |
| `migrate_retrieval_intelligence_prompts.py` | Phase 1 filter guidance + `emma_smart_search_decompose` |
| `migrate_trustgraph_phase2_prompts.py` | `trustgraph_extract_concepts` + `trustgraph_edge_scoring` |

Most scripts support `--dry-run` and `--force`; check each script's docstring for exact flags.

**Production label pinning**: All `get_prompt()` calls default to `label="production"` (`LANGFUSE_PROMPT_LABEL`). Admin edits in Langfuse UI become "latest" but NOT "production" until explicitly promoted. This prevents draft/test prompts from accidentally going live.

**Key files**:
- `emma-agent-service/app/services/prompt_registry.py` — Unified registry (91 entries — names + descriptions only, no inline content)
- `emma-agent-service/app/services/langfuse_prompt_client.py` — Langfuse client with production label pinning; raises `PromptNotFoundError` on miss
- `emma-agent-service/scripts/migrate_*_prompts.py` — one-off migration scripts; each owns its prompts' content inline
- `emma-agent-service/app/api/prompts.py` — API endpoints (proxy to Main API)
- `emma-agent-service/app/services/rule_engine.py` — Rule evaluation
- `emma-agent-service/app/services/guardrail_service.py` — Output validation
- `backend/app/api/v1/prompts.py` — Main API CRUD endpoints

### User Memory (Cross-Session Persistent Facts)

> **Full docs**: [`docs/architecture/USER_MEMORY.md`](docs/architecture/USER_MEMORY.md)

Persistent user facts (name, department, preferences) that survive session expiry and are injected into LLM prompts for personalization.

**Architecture (Phase 2 — LangGraph Store)**:
- **PRIMARY**: AsyncPostgresStore (cross-thread memory, shared psycopg3 pool with checkpointer)
- **FALLBACK**: asyncpg + Redis (legacy, used when Store unavailable)
- Store namespace: `("user_facts", user_id)` → key: `"category/fact_key"`
- Write: fire-and-forget after each response → regex/LLM extraction → Store `aput()` (or legacy UPSERT)
- Read: Store `asearch()` (or legacy Redis cache → PostgreSQL) → format → inject into system prompt

**Components**:

| Component | File | Purpose |
|-----------|------|---------|
| UserFactsService | `emma-agent-service/app/services/memory/user_facts.py` | Store-primary CRUD with legacy fallback |
| FactExtractor | `emma-agent-service/app/services/memory/fact_extractor.py` | Two-stage: regex (~1ms) + optional LLM (~200ms) |
| MemoryService | `emma-agent-service/app/services/memory/service.py` | Unified memory interface (wraps all memory stores) |
| Checkpointer/Store | `emma-agent-service/app/core/checkpointer.py` | Shared psycopg3 pool, singleton init |
| DB Model | `backend/app/db/emma_memory_models.py` | `emma_user_memory_facts` table (legacy) |

**LangGraph injection** (2 points):
- `classify_node`: Fast-path greeting with `user_memory` in system prompt → "¡Hola, Carlos! ¿Cómo va todo en Legal?"
- `react_loop_node`: `user_memory` appended to ReAct system prompt for context-aware tool use

**Fact categories**: `identity` (name, age), `work` (department, role, company), `preference` (language, style), `interest` (inferred topics)

**API Endpoints** (Emma Agent Service, external port 8019 → internal 8009):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/emma/memory/facts` | GET | List active facts (`?user_id=X`) |
| `/emma/memory/facts` | DELETE | Hard-delete ALL facts (GDPR right-to-erasure) |
| `/emma/memory/facts/{id:path}` | DELETE | Delete single fact (Store key contains `/`) |

**GDPR**: `DELETE /facts` = hard DELETE (permanent). `DELETE /facts/{id}` = Store `adelete()` (or legacy soft-delete). Natural language: "olvida todo lo que sabes" triggers hard DELETE.

**Configuration**:

| Variable | Default | Description |
|----------|---------|-------------|
| `USER_MEMORY_ENABLED` | `true` | Master switch |
| `USER_MEMORY_LLM_EXTRACTION` | `false` | Enable LLM-based fact inference |
| `USER_MEMORY_MAX_FACTS` | `50` | Max active facts per user |
| `USER_MEMORY_CACHE_TTL` | `3600` | Redis cache TTL (seconds) |

### Social Agent (Slack, Telegram, WhatsApp)

The `social_agent` provides conversational, emoji-rich responses for social channel interactions.

**Activation**: Set `social_channel_mode: true` in request context:
```python
context = {
    "social_channel_mode": True,
    "location": {"city": "Molina de Segura", "region": "Región de Murcia", "country": "España", "timezone": "Europe/Madrid"}
}
```

**Capabilities**:
| Feature | Tool | When Used |
|---------|------|-----------|
| Weather/News | `web_search` (Tavily/DuckDuckGo) | Proactively for clima/tiempo/noticias queries |
| Document Search | `quick_document_search` (proactive) | When user asks about their files (regex-detected, calls hybrid_search with enrichment filters) |
| Conversational | — | Greetings, identity, general chat |

**Proactive Tool Calling**: Since Qwen 7B doesn't reliably call tools, `social_node` detects weather/news queries via regex patterns and calls `web_search` **proactively** before LLM generation. Results are injected into context.

**Key files**:
- `agents/langgraph/nodes/specialists/social.py` — Social agent node with proactive web search
- `agents/langgraph/nodes/specialists/base.py` — Special user_content for social_agent
- `agents/langgraph/nodes/plan.py` — Early exit for social_channel_mode (before identity fast-path)
- `services/web_search.py` — Tavily + DuckDuckGo async client

**Response style**:
- Brief (2-3 sentences max, chat-style)
- Emojis with moderation (1-2 per message)
- Conversational tone, never robotic
- Same language as user query

### Emma Reactive System

> **Full docs**: [`docs/architecture/EMMA_REACTIVE.md`](docs/architecture/EMMA_REACTIVE.md)

Emma Reactive transforms Emma from request-response to an **event-driven, proactive, multi-channel** assistant.

**Architecture**:
```
Events (Redis Streams) → Event Listener → Trigger Engine → Emma Background Service → Notifications / Channels
                                              ↑
                        Celery Beat → Heartbeat Service → Proactive Insights
```

**Phases**:
| Phase | Feature | Key Component |
|-------|---------|---------------|
| 1 | Event Bus | Redis Streams pub/sub |
| 2 | Background Tasks | Celery + LangGraph |
| 3 | Triggers | Event → Action rules |
| 4 | Notifications | WebSocket + email |
| 5 | Multi-Channel | Telegram, WhatsApp, Slack |
| 6 | **Heartbeat** | Proactive intelligence |

**Components**:
- **Event Bus** (`services/event_bus.py`): Redis Streams publish/subscribe between microservices
- **Event Listener** (`workers/event_listener.py`): Standalone async consumer process
- **Trigger Engine** (`services/trigger_engine.py`): Rules engine matching events → actions
- **Background Service** (`services/emma_background_service.py`): LangGraph execution without HTTP
- **Notification Service** (`services/notification_service.py`): In-app (WebSocket) + email + webhook + Slack
- **Channel Router** (`services/channel_router.py`): Multi-channel inbound→Emma→outbound
- **Pairing Service** (`services/pairing_service.py`): Links external users (Telegram, WhatsApp) to KeyCloak
- **Heartbeat Service** (`services/heartbeat/`): Proactive context evaluation + insight generation

**Heartbeat System** (Phase 6):
- **Context Gatherer**: Collects data (documents, contracts, activity)
- **Insight Evaluator**: LLM Router + Langfuse prompt (`emma_heartbeat_evaluator`) — no YAML fallback; raises `PromptNotFoundError` if missing
- **Priority Scorer**: Configurable weights via `type_priorities` (merged with `DEFAULT_TYPE_PRIORITIES`)
- **Delivery Manager**: Rate limiting (5/day, 2/hour) + quiet hours (22:00-08:00)
- **Insight Types**: Dynamic (string-based). Built-in: `contract_expiration`, `compliance_alert`, `risk_alert`, `anomaly_detected`, `task_reminder`, `deadline_approaching`, `document_update`, `activity_summary`. New types added via Langfuse prompt, no code changes needed.

**Events**: `document.indexed`, `document.updated`, `connector.synced`, `knowledge.graph_updated`, `analysis.completed`

**Channels**: Telegram, WhatsApp (Twilio), Slack, Email — all via `channels/` package with `BaseChannel` ABC

**Slack Notification Channel**: Configure a dedicated Slack channel to receive automatic notifications:
```bash
# Create a Slack channel for notifications (via API or UI)
curl -X POST "http://localhost:8009/channels" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_type": "slack",
    "channel_name": "Emma Alerts",
    "config": {
      "is_notification_channel": true,
      "default_channel": "#emma-alerts"
    },
    "credentials": "xoxb-your-slack-bot-token"
  }'
```
Then add `"slack"` to the `notification_channels` array in your triggers to receive alerts.

**Key files**:
- `emma-agent-service/app/schemas/events.py` — EmmaEvent model
- `emma-agent-service/app/schemas/triggers.py` — Trigger schemas
- `emma-agent-service/app/schemas/heartbeat.py` — Heartbeat schemas
- `emma-agent-service/app/api/triggers.py` — Triggers CRUD
- `emma-agent-service/app/api/notifications.py` — Notifications API
- `emma-agent-service/app/api/channels_emma.py` — Channels CRUD + webhooks
- `emma-agent-service/app/api/heartbeat.py` — Heartbeat API (run, status, insights)
- `emma-agent-service/app/channels/` — Channel implementations
- `emma-agent-service/app/services/heartbeat/` — Heartbeat system (5 modules)
- `backend/app/db/emma_reactive_models.py` — DB models (8 tables)
- `backend/alembic/versions/a1b2c3d4e5f6_add_emma_reactive_tables.py` — Migration Phases 3-5
- `backend/alembic/versions/b2c3d4e5f6g7_add_emma_heartbeat_tables.py` — Migration Phase 6

**Docker**: `emma-reactive-worker` service in `docker-compose.onpremise.yml`

**Celery**: `emma_reactive` queue with tasks in `background-worker/worker_app/tasks/emma_tasks.py`
- `emma.analyze_new_document` — Triggered by document.indexed
- `emma.daily_summary` — Celery Beat at 8 AM daily
- `emma.proactive_analysis` — Custom analysis via triggers
- `emma.heartbeat_check` — Celery Beat every 30 min
- `emma.heartbeat_digest` — Celery Beat at 9 AM daily

**Environment variables**:
- `EVENT_BUS_ENABLED` — Enable/disable event bus (default: true)
- `EVENT_CONSUMER_GROUP` — Redis consumer group name
- `CREDENTIALS_ENCRYPTION_KEY` — Fernet key for channel credential encryption

## File Structure Conventions

### Backend (`/backend/app/`)
- `api/v1/`: Versioned REST endpoints, one file per domain
- `core/`: Configuration, security, logging
- `db/`: SQLAlchemy models and database config
- `schemas/`: Pydantic request/response models
- `services/`: Business logic, one service per domain

### Frontend (`/frontend/src/`)
- `app/`: Next.js App Router with nested layouts
- `components/`: UI components organized by domain
- `lib/`: Utilities, API client, types, services
- `contexts/`: React Context for global state

## Development Guidelines

### Database Operations
- Use role-based access: `filter(Document.roles.overlap(user.roles))` (no tenant_id — single-tenant)
- Use async sessions: `async with get_async_db() as db:`
- Create migrations safely: `cd backend && python scripts/create_migration.py -m "description" --autogenerate`
- Fix multiple heads: `python scripts/create_migration.py --fix-heads`
- Safe migration with conflict detection: `python scripts/alembic_safe_migrate.py`

### API Development
- Follow REST conventions in `/api/v1/` endpoints
- Use dependency injection for DB sessions and auth
- Proper error handling with custom exception classes
- Comprehensive Pydantic schema validation

### Security
- All endpoints require auth except public ones
- Role-based authorization for data access (KeyCloak roles, `EVERYONE` wildcard)
- Never log secrets (API keys, tokens, passwords)
- Environment variables for all secrets

### LLM Prompts (IMPORTANT)
- **Langfuse is the ONLY prompt source**. Missing prompts raise `PromptNotFoundError` — there is no YAML fallback (the file `config/prompts/emma_prompts.yaml` persists only as historical reference).
- All prompt names are defined in `app/services/prompt_registry.py` (91 entries) — add new prompts there
- `get_prompt()` defaults to `label="production"` — admin edits in Langfuse UI must be promoted to "production" to take effect
- Never hardcode prompts directly in LLM calls without a Langfuse lookup layer
- Langfuse prompt keys follow convention: `emma_{feature}_{system|user}` (e.g., `emma_verified_faithfulness_system`)
- To add or update a prompt: register the name in `prompt_registry.py`, then write a `migrate_<feature>_prompts.py` script with the content inline and run it inside the container
- See `verified.py` `_resolve_prompts()` for reference implementation

### Testing
- Isolated PostgreSQL via Docker Compose
- Run: `cd backend/tests && ./run_tests.sh`
- Coverage in `backend/tests/coverage_report/`
- Test environment uses the same on-premise stack (MinIO, PostgreSQL, Weaviate, FalkorDB)

### Testing Best Practices (IMPORTANT)
- **NEVER validate tests based only on server logs** — always verify the complete HTTP response (status code + body)
- Bash pipes (`curl ... | python3 -c "..."`) can fail silently due to buffering issues
- **Always save responses to a file first**, then parse:
  ```bash
  # ❌ WRONG - can fail silently
  curl -s http://api/endpoint | python3 -c "import json,sys; print(json.load(sys.stdin))"

  # ✅ CORRECT - verifiable
  curl -s http://api/endpoint > /tmp/response.json
  python3 -c "import json; print(json.load(open('/tmp/response.json')))"
  ```
- For API tests, use Python `httpx`/`requests` directly instead of bash+curl for reliable results
- Server logs showing "success" ≠ client receiving correct response

## Troubleshooting

### Next.js Errors
1. Clear cache: `rm -rf frontend/.next`
2. Check Node: `nvm current` (must be 18+)
3. Reinstall: `rm -rf node_modules && npm install`
4. Restart: `npm run dev`

### Docker Issues
- **Permission denied**: `sudo usermod -aG docker $USER`
- **Port in use**: `docker ps` and stop conflicts
- **Out of space**: `docker system prune -a`

## Simple UI Pattern (MANDATORY)

**ALWAYS follow this pattern for data loading in React components:**

```typescript
setIsLoading(true)
setError(null)
try {
  const response = await service.getData(params)
  if (response.error) { setError(response.error) } else { setData(response.data) }
} catch (err) {
  setError(err.message)
} finally {
  setIsLoading(false)
}
```

### Rules
✅ Simple async functions, `useEffect(() => { loadData() }, [dep])`, manual search (button/Enter), try/catch/finally
❌ **NEVER**: `useCallback` for loaders, `useMemo` for simple transforms, complex `useEffect` deps, debounce auto-search, intervals/timers, multiple simultaneous API calls
