# Admin-Curated Agents — Design Spec

**Status:** Approved (brainstorm 2026-05-06)
**Date:** 2026-05-06
**Author:** H Castillo
**Replaces:** `docs/roadmap/user_agents.md` on branch `feature/user-agents-mock` (the "user-created agents" model is dropped — it does not match the operational requirement).

---

## Goals

Convert Emma's hardcoded list of 10 specialist domains (`legal, labor, fiscal, contract, compliance, privacy, realestate, education, general, docgen` in `analyze_domain` tool) into a **data-driven, admin-managed catalog** where:

1. The administrator (`User.is_superuser=True`) creates, edits, activates, deactivates, and deletes agents from a CRUD UI. Each agent has an identity (name, slug, icon, color), a persona (Langfuse prompt), a data scope (7 filter dimensions), and runtime parameters (model role, temperature).
2. Authenticated end users see a read-only gallery of active agents at `/agents` and invoke them inside the existing Emma chat by typing `@<slug>` (e.g. `@contabilidad ¿qué cliente nos paga peor?`).
3. The `@`-mention menu, already used for entity references, is extended with an "Asistentes" section above the existing entity sections.
4. The bubble that renders an assistant message displays a `🤖 <agent name>` badge when the response was produced by a non-default agent. The default seed agent `emma_general` produces no badge (renders as today).
5. Authorization rides on `User.is_superuser` (the same dependency `Depends(require_superuser)` introduced in commit `940a3460`). KeyCloak authentication is unchanged.

The feature ships **on the existing LangGraph + LangChain stack**. No migration to Deep Agents, no LangSmith dependency. Prompts live in Langfuse using the existing `langfuse_prompt_client` and follow the convention `agent_<slug>_persona`, label `production`.

---

## Non-Goals

- **User-created agents.** Only admins create agents. The end user has no creation surface.
- **Cross-thread routing or hand-off.** Emma stays the front of the chat; agents are tools she invokes. No "one conversation = one agent" model. No automatic LLM-based routing decisions (history shows that pattern is unreliable on Qwen-class models).
- **Sticky agent state across queries.** Each query is independent: `@contabilidad` invocation is **strictly punctual** (Q5 = G1). The next query without `@<slug>` falls back to `emma_general`. If a sticky-mode requirement emerges, it is added in v2 without breaking the v1 contract.
- **Per-user agent visibility / sharing semantics.** Every active agent is visible to every authenticated user. There is no `private`/`shared`/`shared_with_users` model.
- **Lifecycle states beyond `is_active: bool`.** No draft/published/archived state machine. The boolean covers the use case (admin tunes with `is_active=false`, flips to `true` to publish).
- **Migration of historical conversations.** The 10 hardcoded domains stop being callable as soon as the seed catalog is in place; old chat threads that referenced them remain readable but cannot be re-run with the legacy domain.
- **`analyze_domain` removal in the same change.** The tool is renamed/refactored to `invoke_agent`, but its signature surface and Langfuse prompt registry stay backward compatible enough that one prompt-migration script handles the rename.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 15)                                            │
│                                                                    │
│  /agents                /admin/agents/...        Chat (Emma)      │
│  (gallery, all users)   (CRUD, AdminGuard)       @-mention menu   │
│                                                  + bubble badge   │
└─────────┬─────────────────────┬────────────────────┬──────────────┘
          │                     │                    │
          ▼                     ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│  Main API (FastAPI)                                               │
│                                                                    │
│  GET    /api/v1/agents              (auth)                        │
│  GET    /api/v1/agents/{id}         (auth)                        │
│  POST   /api/v1/agents              (require_superuser)           │
│  PUT    /api/v1/agents/{id}         (require_superuser)           │
│  DELETE /api/v1/agents/{id}         (require_superuser)           │
│  POST   /api/v1/agents/{id}/duplicate (require_superuser)         │
│                                                                    │
│  POST   /emma/query/stream                                        │
│    body extends with: agent_slug?: string                         │
└─────────┬──────────────────────────────────────────┬──────────────┘
          │                                          │
          ▼                                          ▼
┌─────────────────────────┐    ┌──────────────────────────────────┐
│ PostgreSQL              │    │ Emma Agent Service               │
│                         │    │ (LangGraph 1.0 ReAct)            │
│ table: agents           │    │                                  │
│ (UUID PK, slug unique,  │    │ - System prompt extended with    │
│  persona JSON,          │    │   <available_agents> from /agents│
│  scope JSON,            │    │ - Tool: invoke_agent(slug,       │
│  is_active, is_seed,    │    │   question, context)             │
│  ...)                   │    │ - AgentLoader fetches:           │
│                         │    │   * Agent row from Main API      │
│ + Alembic migration     │    │   * Persona prompt from Langfuse │
└─────────────────────────┘    │     (agent_<slug>_persona)       │
                                │ - Scope injected into            │
┌─────────────────────────┐    │   smart_search / graph_rag /     │
│ Langfuse                │◄───┤   get_document_content sub-tools │
│                         │    │   for the duration of the call   │
│ prompts:                │    └──────────────────────────────────┘
│   agent_<slug>_persona  │
│   (label: production)   │
└─────────────────────────┘
```

The end-user request path:

1. User types `@con` in chat input. `RichInputWithMentions` opens `EntitySearchMenu` with the new "Asistentes" section. User selects `@contabilidad`. The component inserts a tag and exposes `agent_slug = "contabilidad"` on the parsed payload.
2. Frontend POSTs `/emma/query/stream` with `{ message, agent_slug: "contabilidad", thread_id }`. If no `@<slug>` was present in the input, `agent_slug` is omitted; backend defaults to `emma_general`.
3. Emma's classify node receives the request. The selected agent is resolved by `AgentLoader.load_by_slug(agent_slug)`. The loaded `LoadedAgent` carries persona, scope, and runtime parameters.
4. Emma's ReAct loop calls `invoke_agent(agent_id, question, context)` exactly once. Internally that tool wraps a single LLM call with the agent's persona as system prompt and the scope filters injected into any sub-tool it transitively triggers (`smart_search`, `graph_rag`).
5. The streamed response carries `agent_id` and `agent_slug` in the SSE metadata so the frontend can render the badge `🤖 Contabilidad` on the bubble.

---

## Data Model

```python
# backend/app/db/agent_models.py (rewritten — orphan model deleted in Phase 0)

class Agent(Base):
    __tablename__ = "agents"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name          = Column(String(100), nullable=False, unique=True, index=True)
    slug          = Column(String(50), nullable=False, unique=True, index=True)
    description   = Column(Text, nullable=True)
    icon          = Column(String(50), nullable=False, default="IconRobot")
    color         = Column(String(20), nullable=False, default="blue")
    persona       = Column(JSONB, nullable=False, default=dict)
    scope         = Column(JSONB, nullable=False, default=dict)
    is_active     = Column(Boolean, nullable=False, default=False, index=True)
    is_seed       = Column(Boolean, nullable=False, default=False)
    model_role    = Column(SQLEnum(ModelRole), nullable=False, default=ModelRole.CHAT)
    temperature   = Column(Float, nullable=False, default=0.5)
    usage_count   = Column(BigInteger, nullable=False, default=0)
    owner_id      = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at    = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_agents_slug_active", "slug", "is_active"),
    )
```

**Validation rules** (enforced in Pydantic schemas, not at DB level):

- `slug` matches `^[a-z][a-z0-9_]{1,49}$` (lowercase, starts with letter, underscore separator allowed). Used as the `@<slug>` token and as the Langfuse prompt suffix.
- `name` is human-friendly, used in UI badges and the gallery.
- `is_seed=True` rows cannot be deleted via `DELETE /api/v1/agents/{id}` (returns 409 Conflict).
- `is_seed=True` rows cannot have `is_active=False` (the default agent must always be available).
- `temperature` ∈ `[0.0, 2.0]`.
- `model_role` ∈ {PLANNER, CHAT}, mapping to the existing dual-model router (CHAT for response generation, PLANNER for cheap routing-style invocations).

**`persona` JSON shape:**

```json
{
  "style": "concise|detailed|conversational",
  "language": "es|en|auto",
  "instructions": "Eres el asistente de Contabilidad. Especialízate en facturas, pagos y conciliaciones. Cita siempre la factura origen."
}
```

The `instructions` field is the **input content** that the admin authors in the UI; it lives in the DB row. The CRUD handler pushes that content to Langfuse as `agent_<slug>_persona` (label `production`) on every successful create/update. The other fields (`style`, `language`) are NOT pushed to Langfuse — they are runtime modifiers applied by the `AgentLoader` on top of the Langfuse-fetched content.

**Source of truth contract:**
- **Authoring**: the DB row is the only place admin writes to. The CRUD UI never edits Langfuse directly.
- **Runtime**: `AgentLoader` reads the persona content from Langfuse (which gives versioning, label-pinning, and trace integration for free). The DB content of `persona.instructions` is the **canonical replica**; if Langfuse is unreachable on a CRUD write, the API returns 503 and the DB write is rolled back so the two stores stay consistent.
- **Recovery**: a one-shot script `backend/scripts/sync_agents_to_langfuse.py` re-pushes every active agent's `persona.instructions` to Langfuse (idempotent, used for disaster recovery or initial environment setup).

**`scope` JSON shape** (every key optional, missing/empty = no filter on that dimension):

```json
{
  "folders":         ["uuid1", "uuid2"],
  "semantic_types":  ["factura", "contrato"],
  "person_filter":   ["uuid_persona1"],
  "entity_filters":  ["uuid_entidad_acme"],
  "date_range":      {"from": "2024-01-01", "to": null},
  "quality_min":     0.7,
  "connector_ids":   ["uuid_connector_alfresco"]
}
```

Scope dimensions correspond to existing Weaviate properties + filters in `smart_search` and `graph_rag`. No new filter is added at the storage layer; the agent's scope is a **narrowing of what the existing tools already accept**.

---

## Tool Refactor: `analyze_domain` → `invoke_agent`

**Before** (`backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py`):

```python
AVAILABLE_DOMAINS = ["legal", "labor", "fiscal", "contract", "compliance",
                     "privacy", "realestate", "education", "general", "docgen"]

class AnalyzeDomainInput(BaseModel):
    domain: str = Field(description="...")  # one of AVAILABLE_DOMAINS
    question: str
    context: Optional[str] = None
```

**After**:

```python
class InvokeAgentInput(BaseModel):
    agent_slug: str = Field(
        description="Slug of the agent to invoke (e.g. 'contabilidad'). "
                    "See <available_agents> in the system prompt."
    )
    question: str
    context: Optional[str] = None


class InvokeAgentTool(EmmaTool):
    name = "invoke_agent"
    description = "Delegate a focused question to a specialist agent..."

    async def _execute(self, input: InvokeAgentInput) -> ToolResult:
        agent = await self.loader.load_by_slug(input.agent_slug)
        if agent is None or not agent.is_active:
            return ToolResult.error(f"Agent '{input.agent_slug}' not found or inactive")

        # Build prompt: persona.instructions + style/language modifiers
        system_prompt = self._compose_persona(agent)
        # Apply scope filters to the sub-context
        scoped_context = self._apply_scope(agent.scope, input.context)

        response = await self.llm_router.chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{scoped_context}\n\n{input.question}"},
            ],
            role=agent.model_role,
            temperature=agent.temperature,
        )
        await self.usage_counter.increment(agent.id)
        return ToolResult.ok({"agent_slug": agent.slug, "answer": response.content})
```

**`AgentLoader`** lives in `emma-agent-service/app/services/agent_loader.py`. Three responsibilities:

1. Fetch agent by slug from Main API (`GET /api/v1/agents?slug=<slug>`), cache 60s in Redis.
2. Fetch persona prompt from Langfuse (`agent_<slug>_persona`, label `production`). Raises `PromptNotFoundError` on miss — no YAML fallback (consistent with the `langfuse_prompt_client` policy).
3. Compose the final system prompt = `instructions` + style/language modifiers from `persona`.

**Emma's system prompt extension** — the existing `emma_react_system` Langfuse prompt is updated to include a templated section that the Emma graph fills with the active agent catalog at request time:

```
<available_agents>
{% for agent in active_agents %}
- {{ agent.slug }}: {{ agent.description | truncate(80) }}
{% endfor %}
</available_agents>

If the user mentions @<slug>, use invoke_agent(agent_slug=<slug>, ...).
Otherwise, answer as Emma general (no agent invocation).
```

The catalog is fetched at the start of each request (cache 60s in Redis). The `agent_slug` parameter on `/emma/query/stream` overrides any LLM decision: when set, Emma's ReAct loop is constrained to call `invoke_agent` with that slug exactly once (no retry-with-different-agent loops).

---

## Frontend

### `/agents` (read-only gallery)

Layout: card grid showing every `is_active=True` agent. Each card displays icon, name, description, and a "Probar" button that pre-fills the chat input with `@<slug> ` and focuses it.

The page is accessible to every authenticated user. There is no "Create new" button on this page — the corresponding button on `/admin/agents` is rendered only behind `<AdminGuard>`.

### `/admin/agents`, `/admin/agents/new`, `/admin/agents/[id]/edit`

Three pages wrapped in the existing `<AdminGuard>` (gates on `isAdmin` from `auth-context`, which derives from `User.is_superuser` after commit `f268c207`).

**Source code:** ported from `feature/user-agents-mock` branch (option **a** from the brainstorm — port the 3 pages and their dependencies tal cual). Specifically:

- `frontend/src/app/admin/agents/page.tsx` (gallery + filters + search + activate/deactivate toggle)
- `frontend/src/app/admin/agents/new/page.tsx` (builder)
- `frontend/src/app/admin/agents/[id]/edit/page.tsx` (builder with delete/duplicate)
- `frontend/src/components/agents/agent-builder-form.tsx` (shared form)
- `frontend/src/components/agents/agent-playground-mock.tsx` (the simulated SSE preview, **renamed and rewired** to call the real `/emma/query/stream` once Phase 2 lands)
- `frontend/src/lib/services/agents.service.ts` (real backend client — replaces the localStorage mock)

The mock layer (`frontend/src/lib/mocks/agents-mock.ts`) is **not** ported — the UI binds directly to the real API from day one. Phase 0 deletes the orphan equivalents in development that the port would otherwise collide with.

### Chat — `@`-mention menu extension

`frontend/src/components/documents/entity-search-menu.tsx` gains a new section **above** existing entity sections:

```
🤖 Asistentes
  @contabilidad — Análisis de facturas, pagos, conciliaciones
  @ventas       — Análisis de pipeline, leads, cuentas
  @legal        — Contratos, cumplimiento normativo

👤 Personas
  ...

🏢 Organizaciones
  ...
```

The menu fetches active agents from `GET /api/v1/agents?active=true` once on mount (cached 60s client-side). When the user selects an agent from the menu, the existing `createEntityTag` machinery is extended to mark the tag as type `agent` (vs the current `person`/`organization`/`document`). On submit, the input parser walks the tags and extracts the **first** agent tag's slug as `agent_slug` for the request payload. If multiple agent tags appear, the first wins and the rest are sent as plain text (we do not support multi-agent fan-out in v1).

### Chat — bubble badge

`frontend/src/components/emma-chat/MessageBubble.tsx` (or equivalent) reads `agent_slug` and `agent_name` from the message metadata. If both are present and `agent_slug !== "emma_general"`, render a small chip below the message content: `🤖 Contabilidad`. Otherwise, render as today.

---

## Phases

Six commits on a feature branch `feature/admin-curated-agents` off `development`. Each phase = one commit.

### Phase 0 — Cleanup orphan agent code

Delete (no replacement, the new code is in later phases under different paths):

- `backend/app/api/v1/agents.py` (the existing 13-route stub on dead model)
- `backend/app/db/agent_models.py` (orphan `AgentType` enum)
- `backend/app/db/models_with_agents.backup` (literal backup file)
- `backend/app/schemas/agent_management.py`
- `backend/scripts/seed_agents.py`, `init_agent_definitions.py`, `init_agents.py`
- `backend/alembic/versions/_archived/60341decaf9a_add_agent_management_tables.py` (the archived migration — already excluded from the chain)
- `frontend/src/app/agents/page.tsx` (the orphan dashboard)
- `frontend/src/components/agents/` (9 components: dashboard, router, assignment, details-dialog, health-check, dynamic-agent, digital-signature-assistant, use-case-card, thinking-display)
- `frontend/src/lib/services/agent.service.ts` and `agents.service.ts` (the dead services)
- `frontend/src/lib/agent-use-cases.ts`
- `frontend/src/components/layout/agents-sidebar.tsx`, `agents-main-sidebar.tsx`
- `frontend/src/components/navigation/nav-agents.tsx`
- `frontend/src/components/chat/agent-message-renderer.tsx`

Smoke test after deletion: `python -c "from app.main import app; print('imports OK')"` and `npx tsc --noEmit` (errors must not regress beyond the existing baseline).

### Phase 1 — Backend: model + migration + CRUD API

- Create `backend/app/db/agent_models.py` with the `Agent` SQLAlchemy model from §Data Model.
- Create Alembic migration `<rev>_add_agents_table.py` adding the `agents` table + indexes. Downgrade is `op.drop_table("agents")` (reversible — unlike the role-based ACL drop, this is purely additive).
- Create `backend/app/schemas/agent.py` with Pydantic models: `AgentBase`, `AgentCreate`, `AgentUpdate`, `AgentResponse`, plus `Persona` and `Scope` nested models with their validations. All use `model_config = ConfigDict(extra='forbid')` (matching the policy from commit `36e1e267`).
- Create `backend/app/services/agent_service.py` with CRUD operations.
- Create `backend/app/api/v1/agents.py` (under the same path as the deleted orphan, but a fresh module) with the 6 endpoints:
  - `GET /` — list (auth, optional `?active=true` filter)
  - `GET /{id}` — detail (auth)
  - `POST /` — create (`Depends(require_superuser)`)
  - `PUT /{id}` — update (`Depends(require_superuser)`, also pushes new Langfuse version)
  - `DELETE /{id}` — delete (`Depends(require_superuser)`, 409 if `is_seed=True`)
  - `POST /{id}/duplicate` — copy (`Depends(require_superuser)`)
- Wire into `backend/app/api/v1/__init__.py` router include.

### Phase 2 — Tool refactor: `invoke_agent` + `AgentLoader` + Emma system prompt extension

- Create `backend/microservices/emma-agent-service/app/services/agent_loader.py` with `AgentLoader.load_by_slug(slug)`, Redis cache 60s, calls `GET /api/v1/agents?slug=<slug>` against Main API + `LangfusePromptClient.get_prompt("agent_<slug>_persona")`.
- Refactor `backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py` → rename to `invoke_agent.py`, replace `AnalyzeDomainInput` / `analyze_domain` with `InvokeAgentInput` / `invoke_agent`. Drop the `AVAILABLE_DOMAINS` constant. The tool reads agent config via the loader.
- Update `backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py` — remove `analyze_domain` registration, add `invoke_agent`.
- Update Emma's `emma_react_system` Langfuse prompt: add the `<available_agents>` template block. Migration script `migrate_admin_curated_agents_prompt.py` pushes the new version with label `production`.
- Update `/emma/query/stream` request schema to accept `agent_slug?: string`. When present, the `classify` node bypasses LLM-based agent selection and constrains the ReAct loop to call `invoke_agent` exactly once with that slug.
- Seed the catalog: a one-shot script `backend/scripts/seed_default_agents.py` inserts:
  - `emma_general` (`is_seed=True`, `is_active=True`, `scope={}`, persona = current Emma general system prompt).
  - 3 starter examples (`contabilidad`, `ventas`, `legal`) with sensible default personas and empty scopes (admin tunes them post-seed). All three are `is_active=False` so the admin reviews them before publishing.
- Each starter persona is also pushed to Langfuse via the migration script.

### Phase 3 — Frontend: `/admin/agents` (CRUD)

- Cherry-pick or rewrite (whichever is cheaper given drift) the 3 mock pages from `feature/user-agents-mock`:
  - `frontend/src/app/admin/agents/page.tsx`
  - `frontend/src/app/admin/agents/new/page.tsx`
  - `frontend/src/app/admin/agents/[id]/edit/page.tsx`
- Cherry-pick or rewrite `frontend/src/components/agents/agent-builder-form.tsx`.
- Replace the localStorage mock with a real `agentsService` calling the new API.
- Wrap each page in `<AdminGuard>`. Update the sidebar (`AppSidebar`) to add an "Agentes" admin entry, gated.
- The builder form fields:
  - Identity: `name`, `slug` (auto-generated from name with override), `description`, `icon` (Tabler icon picker), `color` (color swatch).
  - Persona: textarea for `instructions`, dropdowns for `style` and `language`.
  - Scope: 7 sections, each collapsible. Folders use the existing folder-tree picker. `semantic_types` and `connector_ids` fetch their option lists from existing endpoints. `entity_filters` and `person_filter` use the same `EntitySearchMenu` component.
  - Runtime: `model_role` dropdown (PLANNER/CHAT), `temperature` slider 0.0–2.0.
  - Status: `is_active` toggle.
- The builder's "Vista previa" panel calls `POST /emma/query/stream` with `agent_slug` set to the agent being edited (if it exists) or to `emma_general` with the current draft persona injected client-side.

### Phase 4 — Frontend: `/agents` gallery + `@`-mention menu extension

- Create `frontend/src/app/agents/page.tsx` (read-only gallery, accessible to every authenticated user). Card grid, "Probar" button per card pre-fills chat with `@<slug> `.
- Extend `frontend/src/components/documents/entity-search-menu.tsx` — add an "Asistentes" section sourced from `GET /api/v1/agents?active=true` (60s client cache).
- Extend `frontend/src/components/ui/entity-renderer.ts` — `createEntityTag` learns a new `agent` type. The tag renders with the agent's color and `IconRobot` (or the agent's chosen icon).
- Extend `frontend/src/components/ui/rich-input-with-mentions.tsx` — `parseEntityTags` returns the first `agent`-typed tag separately as `agent_slug`. The chat sender places that on the request payload.

### Phase 5 — Bubble badge + SSE metadata plumbing

- Backend: `/emma/query/stream` SSE adds the event `agent_metadata` with `{ agent_id, agent_slug, agent_name, agent_color, agent_icon }` once per response, sent after `classify` completes. If the request used `emma_general`, the event is emitted but `agent_slug === "emma_general"` so the frontend can suppress the badge.
- Frontend: extend the SSE consumer in `useEmmaStream` (or equivalent) to capture `agent_metadata` and attach it to the message object.
- Frontend: update `MessageBubble` to render `🤖 <agent_name>` chip below the message content when the metadata is present and the slug is not `emma_general`.

### Phase 6 — Polish + telemetry

- Backend: `usage_count` increments on every successful `invoke_agent` call. Endpoint `GET /api/v1/agents?order_by=usage_count` for the gallery to default-sort by popularity.
- Backend: `GET /api/v1/agents/{id}/metrics` returns `{ usage_count, last_used_at, avg_latency_ms }` (the last two computed from existing Langfuse traces — no new logging surface).
- Frontend `/agents` and `/admin/agents` show a "Más usados" sort option.
- Documentation:
  - Update `CLAUDE.md` to mention the agents catalog and where it lives.
  - Add `docs/architecture/AGENTS.md` describing the system at architecture level (replaces the obsolete `docs/roadmap/user_agents.md` reference, which never landed in `development`).

---

## Migration / Backwards Compatibility

- The legacy `analyze_domain` tool **disappears in Phase 2**. Any in-flight conversation that previously had Emma calling `analyze_domain` was already done by the end of that turn; there is no persisted state that calls it across turns.
- The legacy `emma_domain_<slug>` prompts in Langfuse (10 of them) are **kept as historical reference** but their content is duplicated into `agent_<slug>_persona` for the matching seed slugs (`legal`, `compliance`, etc.). The migration script handles the rename.
- No data migration is needed for end users. The `agents` table starts empty and is populated by the seed script + admin actions.

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Admin creates an agent whose scope returns 0 documents — confusing for end users | Builder shows a live "Corpus preview: ~N documents" indicator (uses existing `corpus-preview` endpoint pattern from the spec writeup). Warn if N < 10. |
| User mentions `@<slug>` for an inactive or deleted agent | Backend resolves slug → `is_active=False` or 404 → returns a graceful "Agent not available" event in the SSE stream; chat shows a soft error. |
| Emma's `<available_agents>` block grows unboundedly as admin adds agents | Cap at 50 active agents in the system prompt, sorted by `usage_count` desc. The full catalog is still discoverable via `/agents` page. |
| Langfuse drift: admin edits persona, but Langfuse fetch hits a stale `production` label | The PUT endpoint pushes the new prompt content + immediately promotes to `production` label in the same transaction. Loader cache TTL is 60s, so worst-case staleness is bounded. |
| Slug collision with existing entity names | `EntitySearchMenu` renders agents in their own section above entities. The parser uses tag types (`agent` vs `person`) — slug as raw text is never the disambiguator. |
| Phase 0 orphan deletion breaks an unknown caller | Pre-deletion grep across `frontend/src/` and `backend/app/`. If any active import remains, it is replaced with the new code in the same phase. Smoke tests gate the commit. |
| `is_seed=True` flag ignored by an admin SQL hand-fix | DB-level: a partial unique index ensures exactly one row with `is_seed=True AND slug='emma_general'`. API-level: `DELETE` and `UPDATE is_active=False` return 409 on seed rows. Belt + suspenders. |

---

## Self-Review Checklist

- [x] **Placeholders**: no TBD, TODO, or `<rev>` left other than the Alembic revision filename which is generated at Phase 1 task time (intentional).
- [x] **Internal consistency**: architecture, data model, tool refactor, and frontend sections cross-reference the same field names and slugs.
- [x] **Scope check**: 6 phases on a single PR is consistent with the project's recent pattern (role-based ACL removal had 6+1; remove-multi-tenancy had 5). Each phase = one commit, leaves the system functional.
- [x] **Ambiguity**: `@<slug>` is strictly punctual (not sticky); single-agent per query (multiple `@`-tags → first wins, rest plain text); `is_seed` is one-row guarded.
- [x] **Decision provenance**: Q5 decision (G1 punctual) is recorded in Non-Goals; Deep Agents rejection is recorded in Goals; admin-only CRUD is recorded throughout.

---

## References

- Brainstorm session: 2026-05-06 (this document is the validated output).
- Predecessor (superseded): `docs/roadmap/user_agents.md` on branch `feature/user-agents-mock` (256 LOC, 9-phase user-created model).
- Related cleanups that unblock this work:
  - `f5ac7478` `refactor(backend+connectors): drop domain from models, schemas, adapters` (eliminates the prescriptive taxonomy that would have contaminated the scope dimensions).
  - `940a3460` `feat(db)!: drop roles columns + Weaviate property + KTS user property` (eliminates role-based ACL, simplifying the visibility model).
  - `f268c207` `chore(frontend): remove role-based ACL surface` (introduces `is_superuser`-based admin gating in the frontend).
- LangChain Deep Agents documentation reviewed: https://docs.langchain.com/oss/python/deepagents/cli/overview — see Goals for why we don't use it.
- Existing `analyze_domain` tool: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py`.
- Existing `@`-mention infrastructure: `frontend/src/components/ui/input-with-mentions.tsx`, `rich-input-with-mentions.tsx`, `entity-search-menu.tsx`, `entity-renderer.ts`.
