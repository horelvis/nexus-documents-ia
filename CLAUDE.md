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
- **Dev**: `cd frontend && npm run dev` (Turbopack, port 3000)
- **Build**: `cd frontend && npm run build`
- **Lint**: `cd frontend && npm run lint`
- **Install**: `cd frontend && npm install`

### Full Stack
- Backend services: `cd backend/docker && ./start-dev.sh` (PostgreSQL, Redis, Weaviate, Elasticsearch, microservices with live reload)
- Frontend: `cd frontend && npm run dev`
- API docs: `http://localhost:8000/docs`

## Architecture Overview

**NouxCubeIA** is a **multi-tenant intelligent document management system** with microservices architecture.

- **Backend**: FastAPI (Python 3.9+), async/await throughout
- **Frontend**: Next.js 15 App Router, TypeScript, OIDC/SAML auth
- **Database**: PostgreSQL + Weaviate (vectors) + Elasticsearch (full-text)
- **Storage**: Google Cloud Storage
- **AI/ML**: vLLM (Qwen3-4B GPU inference) + LangGraph multi-agent orchestration

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
| vLLM Server | internal | GPU inference (OpenAI-compatible API) |

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

**Flow**: `coordinator → [context_tree || graph_expand] → retrieve → [rlm/plan] → [agents] → synthesize → END`

Note: `context_tree` and `graph_expand` run in **parallel**. `graph_expand` populates `expanded_boe_ids` (from QA matches and Apache AGE graph) that `retrieve` uses to filter PublicKnowledge searches.

**Structure**:
- `agents/langgraph/graph.py` — StateGraph definition
- `agents/langgraph/nodes/` — All pipeline nodes (coordinator, retrieve, intent_router, rlm_processor, plan, synthesize, specialists/)
- `agents/langgraph/sectors/` — Sector configuration
- `services/verified_generation/` — Claim-by-claim verification with SSE
- `config/prompts/emma_prompts.yaml` — All prompts

**Key features**:
- **Intent Router**: FastEmbed semantic (~3ms) → LLM fallback (~200ms) → default document_query
- **RLM Processor**: Recursive pipeline for large docs (>16K tokens), Redis cached
- **Verified Generation**: Claim-by-claim verification with SSE streaming
- **LLM Providers**: vLLM (primary), OpenAI, Anthropic, Google (fallbacks)
- **Social Agent**: Conversational agent for social channels (see below)
- **Emma Reactive**: Event-driven proactive system (see below)

### Social Agent (Slack, Telegram, WhatsApp)

The `social_agent` provides conversational, emoji-rich responses for social channel interactions.

**Activation**: Set `social_channel_mode: true` in request context:
```python
context = {
    "social_channel_mode": True,
    "location": {"city": "Madrid", "country": "España", "timezone": "Europe/Madrid"}
}
```

**Capabilities**:
| Feature | Tool | When Used |
|---------|------|-----------|
| Weather/News | `web_search` (DuckDuckGo) | Proactively for clima/tiempo/noticias queries |
| Document Search | `quick_document_search` | When user asks about their files |
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
- **Notification Service** (`services/notification_service.py`): In-app (WebSocket) + email + webhook
- **Channel Router** (`services/channel_router.py`): Multi-channel inbound→Emma→outbound
- **Pairing Service** (`services/pairing_service.py`): Links external users (Telegram, WhatsApp) to KeyCloak
- **Heartbeat Service** (`services/heartbeat/`): Proactive context evaluation + insight generation

**Heartbeat System** (Phase 6):
- **Context Gatherer**: Collects tenant data (documents, contracts, activity)
- **Insight Evaluator**: LLM-based analysis to generate insights
- **Priority Scorer**: Multi-factor scoring (type × urgency × confidence)
- **Delivery Manager**: Rate limiting (5/day, 2/hour) + quiet hours (22:00-08:00)
- **Insight Types**: `contract_expiration`, `compliance_alert`, `risk_alert`, `anomaly_detected`, `task_reminder`

**Events**: `document.indexed`, `document.updated`, `connector.synced`, `knowledge.graph_updated`, `analysis.completed`

**Channels**: Telegram, WhatsApp (Twilio), Slack, Email — all via `channels/` package with `BaseChannel` ABC

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

**Client Onboarding** — Download all legislation:
```bash
API_KEY=$(grep MICROSERVICES_API_KEY backend/docker/.env | cut -d= -f2)

# Option 1: Download all presets (recommended for full onboarding)
for preset in laboral fiscal mercantil civil administrativo compliance \
              propiedad_intelectual comercio_consumidores emprendimiento \
              inmobiliario contabilidad educacion proteccion_datos; do
  curl -X POST "http://localhost:8007/boe/download/preset" \
    -H "Content-Type: application/json" \
    -H "X-API-Key: $API_KEY" \
    -d "{\"preset\": \"$preset\", \"index_to_weaviate\": true}"
done

# Option 2: Download single preset
curl -X POST "http://localhost:8007/boe/download/preset" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"preset": "laboral", "index_to_weaviate": true}'
```

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
