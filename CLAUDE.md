# CLAUDE.md - NouxCubeIA Project Guidelines

This file provides guidance to Claude Code (claude.ai/code) when working with code in the NouxCubeIA repository.

## Development Commands

### Docker Compose (IMPORTANT)
- The **active compose** for on-premise is `docker-compose.onpremise.yml`, which **overrides** `docker-compose.yml`
- Both files are loaded together: `docker compose` auto-detects them via `docker-compose.yml` + `docker-compose.onpremise.yml`
- **Always edit `docker-compose.onpremise.yml`** for on-premise changes (vLLM config, services, etc.)
- `docker-compose.yml` is the base; `docker-compose.onpremise.yml` overrides/extends it
- vLLM config (model, quantization, GPU settings) lives in `docker-compose.onpremise.yml`

### Backend
- **Start dev (RECOMMENDED)**: `cd backend/docker && ./start-dev.sh`
- **Start prod**: `cd backend/docker && ./start-prod.sh`
- **Local API (no Docker)**: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Init database**: `cd backend && python -m scripts.init_db`
- **Migrations**: `cd backend && alembic upgrade head`
- **Run tests**: `cd backend/tests && ./run_tests.sh`
- **Tests (real GCS)**: `cd backend/docker && docker compose -f docker-compose.test.yml up`
- **Clean rebuild**: `./clean_and_rebuild.sh`

### Frontend
- **Requires**: Node.js 18+ (`nvm use 18` or `nvm use 20`)
- **Dev (all apps)**: `cd frontend && npm run dev` (Turbopack, all packages)
- **Dev (on-premise only)**: `cd frontend && npm run dev:on-premise` (port 3001, HTTPS)
- **Build**: `cd frontend && npm run build`
- **Build (on-premise only)**: `cd frontend && npm run build:on-premise`
- **Lint**: `cd frontend && npm run lint`
- **Install**: `cd frontend && npm install`

### Onboarding (New Tenant)
- **Full docs**: [`docs/on-premise/ONBOARDING.md`](docs/on-premise/ONBOARDING.md)
- **Onboarding mode**: `cd backend/docker && ./onboarding.sh start` (GPU → Docling, vLLM off)
- **Index all**: `./onboarding.sh sync-all` then `./onboarding.sh status` to monitor
- **Download BOE**: `./onboarding.sh boe` (13 presets, ~47 Spanish laws)
- **Go live**: `./onboarding.sh finish` (GPU → vLLM, Emma operational)
- **Compose override**: `docker-compose.onboarding.yml` (Docling GPU + disable RAG hierarchical)

### Full Stack
- Backend services: `cd backend/docker && ./start-dev.sh` (PostgreSQL, Redis, Weaviate, Elasticsearch, microservices with live reload)
- Frontend: `cd frontend && npm run dev:on-premise` (on-premise only, port 3001)
- API docs: `http://localhost:8000/docs`

## Architecture Overview

**NouxCubeIA** is a **multi-tenant intelligent document management system** with microservices architecture.

- **Backend**: FastAPI (Python 3.9+), async/await throughout
- **Frontend**: Next.js 15 App Router, TypeScript, OIDC/SAML auth
- **Database**: PostgreSQL + Weaviate (vectors) + Elasticsearch (full-text)
- **Storage**: Google Cloud Storage
- **AI/ML**: vLLM (dual-model: Qwen3.5-4B planner + Qwen3.5-9B chat) + LangGraph multi-agent orchestration

### Microservices

| Service | Port | Purpose |
|---------|------|---------|
| Main API | 8000 | Core business logic, auth, document management |
| Emma Agent Service | 8009 | LangGraph multi-agent RAG, Verified Generation |
| Weaviate Service | 8007 | Vector search, RAG pipeline, embedding (BGE-M3) |
| Knowledge Tree Service | 8011 | Apache AGE graph queries for entity expansion |
| Elasticsearch Service | 8008 | Full-text search, hybrid search |
| Background Worker | 8100 | Celery async task processing |
| Emma Reactive Worker | — | Event listener + trigger engine (Redis Streams consumer) |
| vLLM Chat | internal | GPU inference — quality generation (Qwen3.5-9B) |
| vLLM Planner | internal | GPU inference — fast tool calling (Qwen3.5-4B, dual-model only) |

### Modular Architecture (SaaS vs On-Premise)

> **Full docs**: [`docs/architecture/MODULAR_ARCHITECTURE.md`](docs/architecture/MODULAR_ARCHITECTURE.md)

| Feature | SaaS | On-Premise |
|---------|------|------------|
| Auth | Clerk | OIDC/SAML |
| ACL | DocumentACL table | JSONB in IndexedDocument |
| Documents | `documents` table | `indexed_documents` table |
| Config | `DEPLOYMENT_MODE=saas` | `DEPLOYMENT_MODE=on_premise` |

### Multi-Pipeline RAG Sectors

One sector active per deployment via `ACTIVE_SECTOR` env var. Changing sector requires data re-ingestion.

| Sector | Agents | hybrid_alpha | top_k | Chunk Strategy |
|--------|--------|-------------|-------|----------------|
| `legal` | legal, labor, fiscal, contract, compliance, privacy | 0.7 | 12 | legal_sections (1500/200) |
| `medical` | general | 0.6 | 15 | paragraph (1200/150) |
| `documental` | general, education, realestate | 0.5 | 10 | semantic (1000/100) |

**Key files**: `emma-agent-service/app/agents/langgraph/sectors/` (config.py, registry.py, entity_extractor.py, graph_expander.py)

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
- **SmartSearch**: Unified multi-store search replacing `search_documents` + `search_legislation` (see below)
- **Social Agent**: Conversational agent for social channels (see below)
- **Emma Reactive**: Event-driven proactive system (see below)
- **Prompt Management**: Dynamic prompts, rules, guardrails (see below)

### LLM Router — Dual-Model Architecture

MemoRAG-inspired dual-model routing where a fast planner model handles tool calling/routing and a quality chat model handles final response generation.

**Architecture**:
```
                    ┌─────────────────────────────────────┐
                    │            LLMRouter                │
                    │                                     │
User Query ──────►  │  role=PLANNER → vLLM (4B, fast)    │
                    │  role=CHAT    → vLLM (9B, quality)  │
                    │                                     │
                    │  Fallback chain per role+provider    │
                    └─────────────────────────────────────┘
```

**Role Assignment**:
| Role | Model | Used By | Purpose |
|------|-------|---------|---------|
| `PLANNER` | Qwen3.5-4B-AWQ (~3-4GB) | classify, memory_recall, react_loop, decompose, swarm_worker, intent_router, verified eval, heartbeat, fact_extractor | Tool calling, JSON extraction, routing |
| `CHAT` | Qwen3.5-9B-AWQ (~8-10GB) | synthesize, synthesize_swarm, rlm_processor, writer_agent, specialists, prediction_synthesizer | User-facing text generation |

**Usage**:
```python
from app.agents.llm_router import get_llm_router
from app.agents.llm_client import ModelRole

router = await get_llm_router()
# Tool calling (fast 4B model)
response = await router.chat(messages, tools=tools, role=ModelRole.PLANNER)
# Text generation (quality 9B model)
response = await router.chat(messages, role=ModelRole.CHAT)
```

**Backwards Compatible**: `VLLM_DUAL_MODEL=false` (default) — both roles use the same model/endpoint. All existing callers default to `ModelRole.CHAT`.

**Activation**: Set `VLLM_DUAL_MODEL=true` in `.env` and start with `docker compose --profile dual-model up -d`.

**Environment Variables**:

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_DUAL_MODEL` | `false` | Enable dual-model routing |
| `VLLM_PLANNER_URL` | `VLLM_BASE_URL` | Planner vLLM endpoint |
| `VLLM_PLANNER_MODEL` | `Qwen/Qwen3.5-4B-AWQ` | Planner model name |
| `VLLM_PLANNER_MAX_TOKENS` | `4096` | Planner max output tokens |
| `VLLM_PLANNER_TEMPERATURE` | `0.3` | Planner temperature |
| `VLLM_PLANNER_GPU_UTIL` | `0.20` | Planner GPU memory fraction |
| `VLLM_PLANNER_TOOL_PARSER` | `qwen3_coder` | Planner tool call parser (Qwen3.5 uses XML) |

**Key files**:
- `emma-agent-service/app/agents/llm_router.py` — LLMRouter with `(provider, role)` client pool
- `emma-agent-service/app/agents/llm_client.py` — `ModelRole` enum, `create_llm_config_for_provider(role=)`
- `emma-agent-service/app/core/config.py` — Dual-model settings
- `docker-compose.onpremise.yml` — `vllm-planner` service (profiles: [dual-model])

### SmartSearch — Unified Multi-Store Search

The `smart_search` tool replaces the separate `search_documents` and `search_legislation` tools. It orchestrates 3 data stores automatically so the LLM doesn't have to choose which tool to call.

**Pipeline** (~200ms total):
```
Entity Extraction (regex ~3ms) → Scope Detection (rules) → Filter Enrichment
    → Graph Expansion (~20-50ms) → Parallel Search (asyncio.gather ~100ms)
    → Merge + Dedup → Multi-Signal Re-Rank (~1ms) → Format for LLM
```

**3 Data Stores**:
| Store | What | How |
|-------|------|-----|
| Weaviate | Tenant documents (hybrid search) | `WeaviateClient.hybrid_search()` with enrichment filters |
| PublicKnowledge | BOE legislation (hybrid search) | `WeaviateClient.search_public_knowledge()` |
| Apache AGE | Entity relationships (knowledge graph) | `KnowledgeTreeClient.get_documents_by_person()` |

**Enrichment Properties** (first-class Weaviate properties, not JSONB):
- `domain` — Business domain (legal, fiscal, medical)
- `semantic_type` — Document type (factura, contrato, nomina)
- `quality_score` — Quality 0.0-1.0 from DocumentIntelligence
- `associated_person` — Person from folder hierarchy or entity extraction

**5-Signal Re-Ranking** (sector-tunable weights):
| Signal | Default | Legal | Medical | Documental |
|--------|---------|-------|---------|------------|
| similarity | 0.40 | 0.35 | 0.40 | 0.35 |
| quality | 0.20 | 0.15 | 0.25 | 0.15 |
| graph | 0.20 | 0.30 | 0.15 | 0.20 |
| recency | 0.10 | 0.05 | 0.10 | 0.15 |
| entity | 0.10 | 0.15 | 0.10 | 0.15 |

**Config**: `SMART_SEARCH_RERANK_ENABLED=true`, `SMART_SEARCH_GRAPH_ENABLED=true`

**Key files**:
- `emma-agent-service/app/agents/langgraph/tools/smart_search.py` — SmartSearchTool implementation
- `emma-agent-service/app/agents/langgraph/tools/registry.py` — Tool registration
- `emma-agent-service/app/agents/langgraph/sectors/config.py` — `rerank_weights` per sector
- `weaviate-service/app/services/weaviate_service.py` — Enrichment properties + filters
- `knowledge-tree-service/app/api/tree.py` — `/graph/documents-by-entity` endpoint

**ReAct Agent Tools** (9 total):
| Tool | Purpose |
|------|---------|
| `smart_search` | Unified document + legislation search (auto-detects scope) |
| `get_document_content` | Read full document by ID |
| `structural_query` | Count, list, filter via Apache AGE graph |
| `analyze_domain` | Specialist domain analysis |
| `web_search` | Internet search (DuckDuckGo) |
| `search_jurisprudence` | CENDOJ jurisprudence search |
| `list_sources` | Discover available data sources |
| `query_connector` | Query external connectors (SharePoint, etc.) |
| `terminate` | Signal completion with response |

### Prompt Management System

> **Full docs**: [`docs/architecture/PROMPT_MANAGEMENT.md`](docs/architecture/PROMPT_MANAGEMENT.md)
> **Langfuse Setup**: [`docs/guides/LANGFUSE_SETUP.md`](docs/guides/LANGFUSE_SETUP.md)

Dynamic prompt management with Langfuse integration:

| Component | Description | API Endpoint |
|-----------|-------------|--------------|
| **Langfuse** | Prompt versioning, A/B testing, rollback | Web UI: http://localhost:3002 (admin@nouxcube.com / LangfuseAdmin2024!) |
| **Rules** | Dynamic prompt injection by context | `/prompts/rules` |
| **Guardrails** | Post-LLM validation (PII, keywords) | `/prompts/guardrails` |
| **Few-Shot** | Semantic example retrieval | `/prompts/few-shot` |

**Architecture**: Emma Service (8009) → HTTP Proxy → Main API (8000) → PostgreSQL

**Key files**:
- `emma-agent-service/app/api/prompts.py` — API endpoints (proxy to Main API)
- `emma-agent-service/app/services/rule_engine.py` — Rule evaluation
- `emma-agent-service/app/services/guardrail_service.py` — Output validation
- `emma-agent-service/app/services/langfuse_prompt_client.py` — Langfuse client
- `backend/app/api/v1/prompts.py` — Main API CRUD endpoints

### User Memory (Cross-Session Persistent Facts)

> **Full docs**: [`docs/architecture/USER_MEMORY.md`](docs/architecture/USER_MEMORY.md)

Persistent user facts (name, department, preferences) that survive session expiry and are injected into LLM prompts for personalization.

**Architecture (Phase 2 — LangGraph Store)**:
- **PRIMARY**: AsyncPostgresStore (cross-thread memory, shared psycopg3 pool with checkpointer)
- **FALLBACK**: asyncpg + Redis (legacy, used when Store unavailable)
- Store namespace: `("user_facts", tenant_id, user_id)` → key: `"category/fact_key"`
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

**API Endpoints** (Emma Agent Service, port 8009):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/emma/memory/facts` | GET | List active facts (`?user_id=X&tenant_id=Y`) |
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
| Weather/News | `web_search` (DuckDuckGo) | Proactively for clima/tiempo/noticias queries |
| Document Search | `quick_document_search` (proactive) | When user asks about their files (regex-detected, calls hybrid_search with enrichment filters) |
| Conversational | — | Greetings, identity, general chat |

**Proactive Tool Calling**: Since Qwen 7B doesn't reliably call tools, `social_node` detects weather/news queries via regex patterns and calls `web_search` **proactively** before LLM generation. Results are injected into context.

**Key files**:
- `agents/langgraph/nodes/specialists/social.py` — Social agent node with proactive web search
- `agents/langgraph/nodes/specialists/base.py` — Special user_content for social_agent
- `agents/langgraph/nodes/plan.py` — Early exit for social_channel_mode (before identity fast-path)
- `services/web_search.py` — DuckDuckGo async client

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
- **Context Gatherer**: Collects tenant data (documents, contracts, activity)
- **Insight Evaluator**: LLM Router + Langfuse prompt (`emma_heartbeat_evaluator`) with YAML fallback
- **Priority Scorer**: Configurable per-tenant weights via `type_priorities` (merged with `DEFAULT_TYPE_PRIORITIES`)
- **Delivery Manager**: Rate limiting (5/day, 2/hour) + quiet hours (22:00-08:00)
- **Insight Types**: Dynamic (string-based). Built-in: `contract_expiration`, `compliance_alert`, `risk_alert`, `anomaly_detected`, `task_reminder`, `deadline_approaching`, `document_update`, `activity_summary`. New types added via Langfuse prompt, no code changes needed.

**Events**: `document.indexed`, `document.updated`, `connector.synced`, `knowledge.graph_updated`, `analysis.completed`

**Channels**: Telegram, WhatsApp (Twilio), Slack, Email — all via `channels/` package with `BaseChannel` ABC

**Slack Notification Channel**: Configure a dedicated Slack channel to receive automatic notifications:
```bash
# Create a Slack channel for notifications (via API or UI)
curl -X POST "http://localhost:8009/channels" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-ID: $TENANT_ID" \
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

### Multi-Tier RAG Caching

> **Full docs**: [`docs/architecture/RAG_CACHING.md`](docs/architecture/RAG_CACHING.md)

Tier 1 (Retrieval, 5min TTL) → Tier 2 (Context Assembly, 30min) → Tier 3 (Semantic, 1hr). Key files in `weaviate-service/app/services/rag/cache/`.

### Public Knowledge & BOE Legislation

> **Full docs**: [`docs/architecture/PUBLIC_KNOWLEDGE.md`](docs/architecture/PUBLIC_KNOWLEDGE.md)

The **PublicKnowledge** system provides shared Spanish legislation across all tenants. It consists of:

1. **Weaviate Collection** (`PublicKnowledge`): Chunked legislation with embeddings for RAG retrieval
2. **Legal Knowledge Graph** (Apache AGE `knowledge_graph_public`): Law nodes + relationship edges (MODIFIES, REFERENCES, DEROGATES)
3. **BOE Download API**: Endpoints to download and index legislation from BOE

**Architecture**:
```
BOE API → Download & Parse → IndexingPipeline (chunks) → PublicKnowledge (Weaviate)
                                    ↓
                          LegalGraphService → Apache AGE graph
```

**API Endpoints** (`weaviate-service:8007/boe/`):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/boe/presets` | GET | List available preset categories (13 domains) |
| `/boe/download/preset` | POST | Download all laws in a preset |
| `/boe/download` | POST | Download single law by BOE ID |
| `/boe/all-legislation-ids` | GET | Get all unique BOE IDs (47 laws) |
| `/boe/sync/{boe_id}` | POST | Sync law and detect article-level changes |

**Presets disponibles** (13 categorías, ~47 leyes):
- `laboral` (7): ET, LTD, LPRL, LISOS, LOI, LETA, LGSS
- `fiscal` (5): LGT, LIRPF, LIS, LIVA, Reglamento Facturación
- `mercantil` (3): LSC, CCom, LSP
- `civil` (2): CC, LEC
- `administrativo` (3): LPACAP, LRJSP, LCSP
- `compliance` (5): LPBC, CP, LC, LSE, Auditoría
- `propiedad_intelectual` (3): LPI, LM, LP
- `comercio_consumidores` (5): LGDCU, LCD, LOCM, LGUM, LSSI
- `emprendimiento` (3): LE, LCC, LS
- `inmobiliario` (5): LAU, LPH, LH, Crédito Inmobiliario
- `contabilidad` (2): PGC, PGC Pymes
- `educacion` (3): LOMLOE, LOE, LOU
- `proteccion_datos` (1): LOPDGDD

**Client Onboarding** — Use the onboarding script (recommended) or manual curl:
```bash
# Recommended: use the onboarding script
cd backend/docker && ./onboarding.sh boe           # All 13 presets
cd backend/docker && ./onboarding.sh boe laboral    # Single preset

# Manual alternative:
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)
curl -X POST "http://localhost:8007/boe/download/preset" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"preset": "laboral", "index_to_weaviate": true}'
```

> See [`docs/on-premise/ONBOARDING.md`](docs/on-premise/ONBOARDING.md) for the complete onboarding guide.

**Legal Graph Management**:
```bash
# View graph stats
curl "http://localhost:8007/legal/stats" -H "X-API-Key: $API_KEY"

# Get graph structure (nodes + edges for D3 visualization)
curl "http://localhost:8007/legal/graph/structure" -H "X-API-Key: $API_KEY"

# Connect orphan laws (if any exist without connections)
docker compose exec weaviate-service bash -c \
  'cd /app && PYTHONPATH=/app python scripts/connect_orphan_laws.py'
```

**Key files**:
- `weaviate-service/app/api/boe_legislation.py` — BOE download endpoints
- `weaviate-service/app/api/legal_graph.py` — Legal graph CRUD
- `weaviate-service/app/services/sil/legal_graph_service.py` — Apache AGE graph operations
- `weaviate-service/app/services/public_knowledge_service.py` — Weaviate PublicKnowledge CRUD
- `weaviate-service/scripts/seed_legal_graph.py` — Initial graph population
- `weaviate-service/scripts/connect_orphan_laws.py` — Connect orphan laws to hub laws
- `weaviate-service/scripts/populate_legal_edges.py` — Create REFERENCES/MODIFIES edges from BOE analysis

**Note**: 5 laws (LSP, LC, LP, LS, LAU Reform) aren't available in BOE's `/legislacion-consolidada` API and require manual seeding or alternative download methods.

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
- Always use tenant isolation: `filter(Model.tenant_id == current_tenant.id)`
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
- Tenant-based authorization for data access
- Never log secrets (API keys, tokens, passwords)
- Environment variables for all secrets

### LLM Prompts (IMPORTANT)
- **Always prefer Langfuse** for LLM prompts — use `_resolve_prompts()` (or `get_langfuse_prompt_client().get_prompt()`) with hardcoded/YAML fallbacks
- Pattern: Langfuse prompt (primary, versioned, A/B testable) → YAML fallback (`config/prompts/`) → hardcoded constant
- Never hardcode prompts directly in LLM calls without a Langfuse lookup layer
- Langfuse prompt keys follow convention: `emma_{feature}_{system|user}` (e.g., `emma_verified_faithfulness_system`)
- See `verified.py` `_resolve_prompts()` for reference implementation

### Testing
- Isolated PostgreSQL via Docker Compose
- Run: `cd backend/tests && ./run_tests.sh`
- Coverage in `backend/tests/coverage_report/`
- Test environment uses **real GCS** (credentials at `./credentials`)

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
