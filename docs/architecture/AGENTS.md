# Admin-Curated Agents Catalog

> **Status:** Implemented 2026-05-07 (`feature/admin-curated-agents`).
> **Spec:** [`docs/superpowers/specs/2026-05-06-admin-curated-agents-design.md`](../superpowers/specs/2026-05-06-admin-curated-agents-design.md)
> **Plan:** [`docs/superpowers/plans/2026-05-07-admin-curated-agents.md`](../superpowers/plans/2026-05-07-admin-curated-agents.md)

## Overview

The agents catalog replaces the hardcoded 10-domain list that lived in
the `analyze_domain` tool. Administrators curate specialist agents from
`/admin/agents`; authenticated users invoke them with `@<slug>` from the
Emma chat. Each invocation is **strictly punctual** (Q5 design decision):
the next query without `@<slug>` falls back to `emma_general`.

## Database

`agents` table — see `backend/app/db/agent_models.py`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `name`, `slug` | String unique | slug pattern `^[a-z][a-z0-9_]{1,49}$` |
| `description`, `icon`, `color` | UI fields | |
| `persona` | JSONB | `{ style, language, instructions }` |
| `scope` | JSONB | 7 optional filter dimensions |
| `is_active` | Boolean | Visible to all users |
| `is_seed` | Boolean | Cannot be deleted or deactivated (409) |
| `model_role` | enum | PLANNER or CHAT (dual-model router) |
| `temperature` | Float | 0.0–2.0 |
| `usage_count` | BigInt | Bumped after each successful invoke_agent |
| `owner_id` | UUID FK users | |

Migration: `backend/alembic/versions/a7b8c9d0e1f2_add_agents_table.py`.

## Endpoints

All under `/api/v1/agents/`.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET    | `/` | user OR API key | List (filters: `?active=`, `?slug=`, `?order_by=`) |
| GET    | `/{id}` | user OR API key | Detail |
| POST   | `/` | superuser | Create |
| PUT    | `/{id}` | superuser | Update |
| DELETE | `/{id}` | superuser | Delete (409 if `is_seed=True`) |
| POST   | `/{id}/duplicate` | superuser | Copy |
| POST   | `/{id}/usage` | API key | Internal: bump usage_count |
| GET    | `/{id}/metrics` | user OR API key | Light metrics |

## Runtime Flow

```
User types "@contabilidad ¿qué clientes pagan peor?"
        ↓
EntitySearchMenu (frontend) renders 🤖 Asistentes section,
user picks the agent → tag <@agent:contabilidad:Contabilidad>
        ↓
useStreamSubmit extracts slug via parse-agent-mention
        ↓
LangGraph SDK submit → ReActState{agent_slug='contabilidad', ...}
        ↓
classify_node (emma-agent-service):
  - resolves agent_metadata from MainAPIClient
  - returns state update with agent_metadata + reasoning_step
        ↓
react_loop._build_system_message:
  - injects the active catalog as <available_agents>
  - appends "INVOCACIÓN DE AGENTE FORZADA: usa invoke_agent('contabilidad')"
        ↓
LLM emits invoke_agent tool call
        ↓
InvokeAgentTool.execute:
  - AgentLoader (60s Redis cache) resolves DB row + Langfuse persona
  - dual-model router (CHAT / PLANNER) executes one LLM call
  - usage_count bumped via MainAPIClient (best-effort)
        ↓
Result flows back through ReActState → SDK snapshot → MessageBubble
        ↓
MessageBubble reads metadata.agent_invocation → 🤖 Contabilidad chip
```

## Source of Truth

- **DB row** (`agents` table) — canonical replica. Admin writes here.
- **Langfuse `agent_<slug>_persona`** — runtime read by AgentLoader.
  Pushed automatically on every CRUD write via the
  `/internal/prompts/push-persona` endpoint inside `emma-agent-service`
  (X-API-Key auth). On Langfuse failure the DB transaction rolls back
  → 503 to the admin. Stores stay consistent.
- **Disaster recovery** — `python backend/scripts/sync_agents_to_langfuse.py`
  re-pushes every active agent.

## Files

### Backend Main API
- `app/db/agent_models.py` — `Agent` SQLAlchemy model
- `app/db/enums.py` — `ModelRole` enum (shared with microservice)
- `app/schemas/agent.py` — Pydantic schemas (`AgentCreate`, `AgentUpdate`, `AgentResponse`, `Persona`, `Scope`)
- `app/services/agent_service.py` — CRUD + Langfuse push hook
- `app/services/langfuse/persona.py` — HTTP adapter to emma-agent-service
- `app/api/v1/agents.py` — 8 endpoints (CRUD + duplicate + usage + metrics)
- `app/api/auth_helpers.py` — `get_user_or_internal` mixed-auth dependency
- `app/core/auth/superuser.py` — `require_superuser` dependency

### emma-agent-service
- `app/services/agent_loader.py` — slug → `LoadedAgent`
- `app/services/main_api_client.py` — MainAPI HTTP client
- `app/agents/langgraph/tools/invoke_agent.py` — replaces specialists.py
- `app/agents/langgraph/state.py` — `ReActState.agent_slug`, `agent_metadata`
- `app/agents/langgraph/nodes/classify.py` — short-circuit on agent_slug
- `app/agents/langgraph/nodes/react_loop.py` — `<available_agents>` block + forced-invocation directive
- `app/api/internal_prompts.py` — `POST /internal/prompts/push-persona`

### Frontend
- `app/admin/agents/{page,new/page,[id]/edit/page}.tsx` — admin CRUD
- `app/agents/page.tsx` — read-only gallery
- `components/agents/agent-builder-form.tsx` — shared form
- `components/documents/entity-search-menu.tsx` — 🤖 Asistentes section
- `components/emma-chat/messages/MessageBubble.tsx` — chip rendering
- `components/emma-chat/hooks/useMessageConverter.ts` — `agent_invocation` propagation
- `components/emma-chat/hooks/useStreamSubmit.ts` — `agent_slug` extraction
- `lib/services/agents.service.ts` — real API client
- `lib/types/agent.ts` — types
- `lib/utils/parse-agent-mention.ts` — slug extractor

### Scripts
- `backend/scripts/seed_default_agents.py` — emma_general (seed) + 3 starters
- `backend/scripts/sync_agents_to_langfuse.py` — disaster recovery

## Invariants

- Exactly one row with `is_seed=True AND slug='emma_general'`.
- `is_seed=True` rows: cannot be deleted (409), cannot be deactivated (409).
- Slug pattern `^[a-z][a-z0-9_]{1,49}$` — used as `@<slug>` token AND
  as the Langfuse prompt suffix.
- Langfuse and DB stay consistent via the rollback-on-push-failure flow.

## Non-Goals (v1)

Per spec §Non-Goals:
- No user-created agents — admin-only.
- No cross-thread routing or agent hand-off.
- No sticky agent state across queries.
- No per-user visibility / sharing.
- No lifecycle states beyond `is_active: bool`.
