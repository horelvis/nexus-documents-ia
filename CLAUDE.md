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

**Flow**: `coordinator → context_tree → retrieve → graph_expand → [rlm/plan] → [agents] → synthesize → END`

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

### Multi-Tier RAG Caching

> **Full docs**: [`docs/architecture/RAG_CACHING.md`](docs/architecture/RAG_CACHING.md)

Tier 1 (Retrieval, 5min TTL) → Tier 2 (Context Assembly, 30min) → Tier 3 (Semantic, 1hr). Key files in `weaviate-service/app/services/rag/cache/`.

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
