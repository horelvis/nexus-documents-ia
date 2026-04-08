# Remove Multi-Tenancy — Plan 3: Microservices Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove every `tenant_id`, `X-Tenant-ID` header, and tenant-scoped namespace from all microservices in `backend/microservices/`. Replace tenant-based filtering with the role-based ACL model defined in Plan 1. Rename the FalkorDB graph property `user` → `role` in `knowledge-tree-service`. Update Weaviate and Elasticsearch schemas/filters to use `roles[]`. After this plan, every microservice imports cleanly and its internal queries filter by user roles, but the system is **still not runnable end-to-end** because the frontend (Plan 4) still sends `tenant_id`.

**Architecture:** This plan operates at the microservices layer. It depends on Plan 1's database schema (the `roles` columns exist) and Plan 2's backend API (the `roles` fields are in the request/response shapes). Microservices communicate with each other and with the main API via HTTP; this plan removes the `X-Tenant-ID` header from every client and adds the user role context propagation pattern (a JWT-extracted `user_roles: List[str]` parameter passed in the request body or headers, depending on the call site).

**Tech Stack:** Python 3.9+ / FastAPI / asyncpg / httpx / LangGraph 0.6+ / Weaviate v4 client / FalkorDB Cypher / Redis 7 (Streams). No new dependencies introduced.

**Spec reference:** `docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md` (Section 2.D "Microservice store changes" and Section 2.E "Microservices")
**Previous plan:** `docs/superpowers/plans/2026-04-06-remove-tenancy-02-backend-api.md`

**Plan boundaries:**
- ✅ Covers Commit 5 of Section 3.A of the spec.
- ✅ Outputs: every Python file in `backend/microservices/` either deleted or refactored to use roles instead of tenant. Schemas of `IndexedDocument`, `PublicKnowledge`, FalkorDB `:Node`/`:Literal`/`:Rel`, and the Elasticsearch index updated.
- ❌ Does NOT touch the frontend (Plan 4).
- ❌ Does NOT touch backend tests, diagnostics, or docs (Plan 5).
- ❌ Does NOT execute the database rebuild or re-extract the TrustGraph (Plan 5).

---

## Volume estimate (from grep against current codebase)

| Microservice | Files with `tenant_id`/`X-Tenant-ID` | Occurrences |
|---|---|---|
| `emma-agent-service` (incl. emma-reactive-worker at `app/workers/event_listener.py`) | 99 | 1233 |
| `weaviate-service` | 71 | 1101 |
| `mcp-onedrive-server` | 6 | 131 |
| `mcp-google-drive-server` | 6 | 129 |
| `mcp-alfresco-server` | 4 | 117 |
| `background-worker` | 10 | 117 |
| `knowledge-tree-service` | 9 | 79 |
| `document-forge-service` | 8 | 28 |
| `storage-service` | (low) | 8 |
| `intelligence-docs-service` | 0 | 0 |
| `engine-template-service`, `langextract-service`, `mcp-storage-server`, `ollama-service` | 0 | 0 |
| **Total (rough)** | **~213** | **~2943** |

Top emma-agent-service hot spots:

| File | Occurrences |
|---|---|
| `app/api/diagnostics.py` | 70 (deferred to Plan 5) |
| `app/api/emma.py` | 45 |
| `app/clients/weaviate_client.py` | 40 |
| `app/core/execution_context.py` | 35 |
| `app/api/prompts.py` | 32 |
| `app/api/channels_emma.py` | 31 |
| `app/clients/knowledge_tree_client.py` | 28 |
| `app/api/heartbeat.py` | 27 |
| `app/services/trigger_engine.py` | 26 |
| `app/services/notification_service.py` | 26 |
| `app/services/emma_persistence_service.py` | 26 |
| `app/api/triggers.py` | 23 |
| `app/api/notifications.py` | 22 |
| `app/api/learning.py` | 22 |
| `app/services/rule_engine.py` | 15 |

Top weaviate-service hot spots:

| File | Occurrences |
|---|---|
| `app/services/weaviate_service.py` | 121 |
| `app/api/weaviate.py` | 70 |
| `app/core/execution_context.py` | 45 |
| `app/services/tool_integration.py` | 32 |
| `app/services/sharing_insights_client.py` | 31 (DELETE — references deleted backend service) |
| `app/services/emma_service.py` | 31 |
| `app/clients/knowledge_tree_client.py` | 27 |

---

## File map (locked decisions)

**Files DELETED entirely:**
- `backend/microservices/emma-agent-service/app/services/tenant_knowledge_service.py` (if present — see Task 4)
- `backend/microservices/weaviate-service/app/services/sharing_insights_client.py` (calls a deleted backend endpoint)
- Any `tenant_*.py` middleware in any microservice

**Files MODIFIED (high density, ≥30 occurrences) — emma-agent-service:**
- `app/api/emma.py`
- `app/clients/weaviate_client.py`
- `app/core/execution_context.py`
- `app/api/prompts.py`
- `app/api/channels_emma.py`

**Files MODIFIED (high density, ≥30 occurrences) — weaviate-service:**
- `app/services/weaviate_service.py`
- `app/api/weaviate.py`
- `app/core/execution_context.py`
- `app/services/tool_integration.py`
- `app/services/emma_service.py`

**Files MODIFIED (semantic-only `user` → `role` rename) — knowledge-tree-service:**
- `app/services/triple_store.py`
- `app/services/triple_query.py`
- `app/services/graph_assembler.py`
- `app/services/template_executor.py`
- `app/services/provenance.py`
- `app/services/uri_builder.py`
- `app/api/triples.py`
- `app/api/extract.py`
- `app/api/reports.py`
- `app/schemas/triples.py`
- `app/schemas/reports.py`
- `scripts/reindex_trustgraph.py` (consumes the new schema)

**LangGraph state files (emma-agent-service):**
- `app/agents/langgraph/state.py`
- `app/agents/langgraph/api.py`
- `app/agents/langgraph/tools/{base,registry,search,smart_search,graph,graph_rag,verified_generation,document_generator,forge_document,knowledge_report,connectors,concept_extractor,predictive_analysis}.py`

**MCP servers (3 files each):**
- `mcp-alfresco-server`, `mcp-onedrive-server`, `mcp-google-drive-server`: drop tenant from configs, drop from request handlers, OAuth tokens stay per-user.

**Workers:**
- `background-worker/worker_app/tasks/*.py` — drop `tenant_id` from Celery task signatures
- `emma-agent-service/app/workers/event_listener.py` — drop `tenant_id` from Redis Streams consumer logic and notification namespaces

**Configs:**
- All `backend/microservices/*/app/core/config.py` — drop any leftover tenant defaults (already touched in Plan 1 for the DB rename, but verify here)

---

## The canonical refactor patterns

### Pattern A — HTTP endpoint in a microservice

```python
# BEFORE (emma-agent-service/app/api/emma.py)
@router.post("/query")
async def query_emma(
    request: QueryRequest,
    tenant_id: str = Header(..., alias="X-Tenant-ID"),
):
    result = await emma_pipeline(query=request.query, tenant_id=tenant_id)
    return result
```

```python
# AFTER
@router.post("/query")
async def query_emma(
    request: QueryRequest,
    user_roles: List[str] = Header(default_factory=list, alias="X-User-Roles"),
    user_id: str = Header(..., alias="X-User-Id"),
):
    result = await emma_pipeline(
        query=request.query,
        user_roles=user_roles,
        user_id=user_id,
    )
    return result
```

The microservices do NOT validate the JWT themselves — the main API and the TLS proxy already do that. The microservices receive `X-User-Id` and `X-User-Roles` (comma-separated) as trusted headers from the API gateway.

### Pattern B — Inter-service HTTP client

```python
# BEFORE (weaviate_client.py)
async def hybrid_search(self, query: str, tenant_id: str, ...):
    headers = {"X-Tenant-ID": tenant_id}
    return await self._http.post("/search", headers=headers, json={...})
```

```python
# AFTER
async def hybrid_search(self, query: str, user_roles: List[str], user_id: str, ...):
    headers = {
        "X-User-Roles": ",".join(user_roles),
        "X-User-Id": user_id,
    }
    return await self._http.post("/search", headers=headers, json={...})
```

### Pattern C — Weaviate filter

```python
# BEFORE
where_filter = Filter.by_property("tenant_id").equal(tenant_id)
```

```python
# AFTER
from weaviate.classes.query import Filter

where_filter = Filter.any_of([
    Filter.by_property("roles").contains_any(["EVERYONE"]),
    Filter.by_property("roles").contains_any(user_roles),
])
```

### Pattern D — FalkorDB / TrustGraph (knowledge-tree-service)

The `user` parameter on `:Node`, `:Literal`, and `:Rel` is renamed to `role`. The semantics change: instead of holding a `tenant_id`, it holds a role identifier (`EVERYONE`, `LEGAL`, `SALES`, …). For users with multiple roles, the application layer issues one query per role plus `EVERYONE` and dedupes the results.

```cypher
-- BEFORE
MATCH (n:Node {user: $tenant_id, collection: $col}) ...

-- AFTER
MATCH (n:Node)
WHERE n.role IN $allowed_roles AND n.collection = $col
...
-- where $allowed_roles = user.roles + ['EVERYONE']
```

```python
# Helper added in app/services/triple_store.py
def allowed_roles(user_roles: List[str]) -> List[str]:
    return list({*user_roles, "EVERYONE"})
```

### Pattern E — LangGraph state

```python
# BEFORE
class EmmaState(TypedDict):
    query: str
    tenant_id: str
    user_id: str
    ...
```

```python
# AFTER
class EmmaState(TypedDict):
    query: str
    user_roles: List[str]
    user_id: str
    ...
```

The checkpointer/store namespaces (currently `("user_facts", tenant_id, user_id)`) become `("user_facts", user_id)` (Plan 1 already updated `emma_memory_models.py`; this plan updates the runtime namespaces in `app/core/checkpointer.py`).

### Pattern F — Redis Streams namespaces

```python
# BEFORE (event_listener.py)
stream_key = f"emma:events:{tenant_id}"
consumer_group = f"emma_reactive_{tenant_id}"
```

```python
# AFTER
stream_key = "emma:events"
consumer_group = "emma_reactive"
```

A single global stream replaces per-tenant streams. Redis is ephemeral; old streams are dropped during the rebuild (Plan 5).

---

## Task 1: Verify Plans 1 and 2 are in place

**Files:** none (verification only)

- [ ] **Step 1: Confirm branch and previous commits**

```bash
git status
git log --oneline -5
```

Expected: branch `refactor/remove-multi-tenancy`. Recent commits include the Plan 1 commit (`feat(foundation): rename DB to nouxcube + introduce role-based ACL helpers`) and the Plan 2 commit (`refactor(api): replace tenant filter with role-based ACL`).

- [ ] **Step 2: Confirm Plan 1 outputs are importable**

```bash
cd backend && python -c "
from app.core.auth.acl import filter_visible_to_user, require_role, EVERYONE_ROLE
from app.db.models import Document, Connector
assert hasattr(Document, 'roles')
assert hasattr(Connector, 'default_document_roles')
print('foundation ok')
"
```

Expected: prints `foundation ok`.

- [ ] **Step 3: Confirm Plan 2 deletions**

```bash
test ! -f backend/app/api/v1/tenants.py && \
test ! -f backend/app/api/v1/document_shares.py && \
test ! -f backend/app/api/v1/document_acl.py && \
echo "plan 2 deletions ok"
```

Expected: prints `plan 2 deletions ok`. If anything is missing, finish Plan 2 first.

---

## Task 2: Add the user-roles header convention to a shared helper

**Files:**
- Create: `backend/microservices/_shared/auth_headers.py` (new) — OR if no shared package exists, replicate the same minimal helper into each microservice's `app/core/` directory.

- [ ] **Step 1: Decide whether shared package exists**

```bash
ls backend/microservices/_shared 2>/dev/null
```

If the directory exists, create the helper there. If not, the helper is replicated per-microservice.

- [ ] **Step 2: Write the helper**

```python
# auth_headers.py
from typing import List, Optional
from fastapi import Header

async def extract_user_roles(
    x_user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
) -> List[str]:
    """Parse the X-User-Roles header (comma-separated) into a list."""
    if not x_user_roles:
        return []
    return [r.strip() for r in x_user_roles.split(",") if r.strip()]

EVERYONE_ROLE = "EVERYONE"

def allowed_roles(user_roles: List[str]) -> List[str]:
    """User's roles plus the EVERYONE wildcard."""
    return list({*user_roles, EVERYONE_ROLE})
```

- [ ] **Step 3: Add a tiny test**

Either in `backend/microservices/_shared/tests/test_auth_headers.py` or alongside the file:

```python
def test_allowed_roles_includes_everyone():
    from app.core.auth_headers import allowed_roles, EVERYONE_ROLE
    assert EVERYONE_ROLE in allowed_roles(["LEGAL"])
    assert EVERYONE_ROLE in allowed_roles([])
```

---

## Task 3: Refactor `emma-agent-service/app/core/execution_context.py`

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/core/execution_context.py` (35 occurrences)

This file is the central context object used everywhere in emma-agent-service. Refactoring it first cascades through the rest of the service.

- [ ] **Step 1: Read the file**

Read the full file. Note all places where `tenant_id` appears (constructor args, dataclass fields, helper methods, serialization).

- [ ] **Step 2: Replace fields**

Replace `tenant_id: str` with `user_roles: List[str]`. Keep `user_id: str`.

- [ ] **Step 3: Update factory functions**

Any function that constructs an `ExecutionContext` from a request — usually `from_request(request: Request)` — must read `X-User-Roles` and `X-User-Id` instead of `X-Tenant-ID`.

- [ ] **Step 4: Update serialization**

If the context is serialized to JSON for inter-service calls, the JSON keys change from `tenant_id` to `user_roles` (list) and `user_id`.

- [ ] **Step 5: Verify it imports**

```bash
cd backend/microservices/emma-agent-service && python -c "from app.core.execution_context import ExecutionContext; print('ok')"
```

Expected: prints `ok`.

---

## Task 4: Refactor `emma-agent-service/app/api/emma.py`

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py` (45 occurrences)
- Possibly delete: `backend/microservices/emma-agent-service/app/services/tenant_knowledge_service.py` (if present)

- [ ] **Step 1: Check for tenant_knowledge_service**

```bash
ls backend/microservices/emma-agent-service/app/services/tenant_knowledge_service.py 2>&1
```

If present, read it. If its only purpose was tenant scoping, delete it. If it has knowledge-graph logic worth keeping, rename it to `knowledge_service.py` and remove the tenant scoping internally.

- [ ] **Step 2: Refactor every endpoint in emma.py**

Apply Pattern A (HTTP endpoint refactor) to each route. Replace the `tenant_id` header dependency with `extract_user_roles` and `Header(..., alias="X-User-Id")`.

- [ ] **Step 3: Verify no `tenant_id` left**

```bash
grep -n "tenant_id\|X-Tenant-ID" backend/microservices/emma-agent-service/app/api/emma.py
```

Expected: zero matches.

- [ ] **Step 4: Run the import smoke test**

```bash
cd backend/microservices/emma-agent-service && python -c "from app.api.emma import router; print('ok')"
```

---

## Task 5: Refactor `emma-agent-service/app/clients/`

**Files:**
- Modify: `app/clients/weaviate_client.py` (40)
- Modify: `app/clients/knowledge_tree_client.py` (28)
- Modify: any other client file in the same directory

- [ ] **Step 1: Apply Pattern B (inter-service HTTP client)**

Every method that currently sends `X-Tenant-ID` must instead send `X-User-Roles` (comma-joined) and `X-User-Id`.

- [ ] **Step 2: Update method signatures**

`async def hybrid_search(self, query: str, tenant_id: str, ...)` → `async def hybrid_search(self, query: str, user_roles: List[str], user_id: str, ...)`.

- [ ] **Step 3: Verify**

```bash
grep -n "tenant_id\|X-Tenant-ID" backend/microservices/emma-agent-service/app/clients/*.py
```

Expected: zero matches.

---

## Task 6: Refactor remaining emma-agent-service files (api/services, batched)

**Files:**
- `app/api/prompts.py` (32)
- `app/api/channels_emma.py` (31)
- `app/api/heartbeat.py` (27)
- `app/api/triggers.py` (23)
- `app/api/notifications.py` (22)
- `app/api/learning.py` (22)
- `app/services/trigger_engine.py` (26)
- `app/services/notification_service.py` (26)
- `app/services/emma_persistence_service.py` (26)
- `app/services/rule_engine.py` (15)
- All remaining files under `app/api/` and `app/services/` containing `tenant_id`

- [ ] **Step 1: Generate the working list**

```bash
grep -rln "tenant_id" backend/microservices/emma-agent-service/app/api backend/microservices/emma-agent-service/app/services 2>/dev/null > /tmp/emma_remaining.txt
wc -l /tmp/emma_remaining.txt
```

- [ ] **Step 2: Apply patterns A and B file-by-file**

For each file in the working list, apply Pattern A (if it's an endpoint) or the equivalent service-function refactor (Pattern B without the HTTP layer). Service signatures change from `(tenant_id: str, ...)` to `(user_roles: List[str], user_id: str, ...)`.

- [ ] **Step 3: Verify the working list shrinks to zero**

```bash
grep -rln "tenant_id" backend/microservices/emma-agent-service/app/api backend/microservices/emma-agent-service/app/services 2>/dev/null
```

Expected: zero matches. Only `app/api/diagnostics.py` is allowed to still have `tenant_id` references — that file is deferred to Plan 5.

---

## Task 7: Refactor LangGraph state and tools

**Files:**
- `app/agents/langgraph/state.py`
- `app/agents/langgraph/api.py`
- `app/agents/langgraph/tools/base.py`
- `app/agents/langgraph/tools/registry.py`
- `app/agents/langgraph/tools/search.py`
- `app/agents/langgraph/tools/smart_search.py`
- `app/agents/langgraph/tools/graph.py`
- `app/agents/langgraph/tools/graph_rag.py`
- `app/agents/langgraph/tools/verified_generation.py`
- `app/agents/langgraph/tools/document_generator.py`
- `app/agents/langgraph/tools/forge_document.py`
- `app/agents/langgraph/tools/knowledge_report.py`
- `app/agents/langgraph/tools/connectors.py`
- `app/agents/langgraph/tools/concept_extractor.py`
- `app/agents/langgraph/tools/predictive_analysis.py`

- [ ] **Step 1: Update `EmmaState` (Pattern E)**

In `state.py`, replace the `tenant_id: str` field with `user_roles: List[str]`. Keep `user_id`.

- [ ] **Step 2: Update tool input/output schemas**

Each tool has a Pydantic schema for its input. Replace any `tenant_id` field with `user_roles: List[str]`. Tools never accept `tenant_id` from the LLM directly; they read `user_roles` from the LangGraph state.

- [ ] **Step 3: Update tool implementations**

Each tool's `_arun` method reads from state. Update the read to `user_roles = state.get("user_roles", [])` instead of `tenant_id = state["tenant_id"]`. Pass `user_roles` to the underlying client call.

- [ ] **Step 4: Update the graph assembly in `api.py`**

The function that builds the initial state from an HTTP request now reads `X-User-Roles` and `X-User-Id` and writes them into state.

- [ ] **Step 5: Verify**

```bash
cd backend/microservices/emma-agent-service && python -c "
from app.agents.langgraph.state import EmmaState
from app.agents.langgraph.api import build_initial_state
print('langgraph ok')
"
```

---

## Task 8: Refactor checkpointer/store namespaces

**Files:**
- `backend/microservices/emma-agent-service/app/core/checkpointer.py`

The checkpointer/store namespaces currently include `tenant_id`. Per the spec (Section 2.E), the namespace becomes `("user_facts", user_id)`.

- [ ] **Step 1: Find the namespace builders**

```bash
grep -n "user_facts\|namespace\|tenant" backend/microservices/emma-agent-service/app/core/checkpointer.py
```

- [ ] **Step 2: Update them**

Replace `("user_facts", tenant_id, user_id)` with `("user_facts", user_id)` in every place that constructs a Store key.

- [ ] **Step 3: Verify**

```bash
grep -n "tenant" backend/microservices/emma-agent-service/app/core/checkpointer.py
```

Expected: zero matches.

---

## Task 9: Refactor `emma-agent-service/app/workers/event_listener.py`

**Files:**
- `backend/microservices/emma-agent-service/app/workers/event_listener.py`

This is the emma-reactive-worker entry point.

- [ ] **Step 1: Read the file**

- [ ] **Step 2: Apply Pattern F (Redis Streams namespaces)**

Replace per-tenant stream keys and consumer groups with single global ones. The event payload still carries `user_id`, but no longer `tenant_id`.

- [ ] **Step 3: Update event-handling logic**

Any switch on `tenant_id` (e.g. for routing notifications to a per-tenant channel) is removed. Notifications are routed by `user_id` and by the configured global notification channels.

- [ ] **Step 4: Verify**

```bash
grep -n "tenant" backend/microservices/emma-agent-service/app/workers/event_listener.py
```

Expected: zero matches.

---

## Task 10: Refactor `weaviate-service` — schema and queries

**Files:**
- `backend/microservices/weaviate-service/app/services/weaviate_service.py` (121)
- `backend/microservices/weaviate-service/app/api/weaviate.py` (70)
- `backend/microservices/weaviate-service/app/core/execution_context.py` (45)

- [ ] **Step 1: Update the `IndexedDocument` collection schema**

Find the schema definition (typically a `_create_collection` or `_ensure_schema` method). Drop the `tenant_id` property if present. Add a `roles: TEXT_ARRAY` property indexed for filtering.

- [ ] **Step 2: Update the `PublicKnowledge` collection schema**

Same change. PublicKnowledge documents are always seeded with `roles: ["EVERYONE"]`.

- [ ] **Step 3: Update `hybrid_search()` to filter by roles (Pattern C)**

Replace the `tenant_id` filter with the OR-of-contains-any filter from the spec.

- [ ] **Step 4: Update every other query method**

Apply the same filter to `keyword_search`, `vector_search`, `bm25`, and any retrieval helper.

- [ ] **Step 5: Refactor the API layer**

`app/api/weaviate.py` follows Pattern A. `app/core/execution_context.py` follows the same shape as Task 3.

- [ ] **Step 6: Verify**

```bash
grep -n "tenant_id" backend/microservices/weaviate-service/app/services/weaviate_service.py backend/microservices/weaviate-service/app/api/weaviate.py backend/microservices/weaviate-service/app/core/execution_context.py
```

Expected: zero matches.

---

## Task 11: Delete weaviate-service tenant artifacts and refactor remaining files

**Files:**
- DELETE: `backend/microservices/weaviate-service/app/services/sharing_insights_client.py`
- Modify: `app/services/tool_integration.py` (32)
- Modify: `app/services/emma_service.py` (31)
- Modify: `app/clients/knowledge_tree_client.py` (27)
- Modify: `app/tools/registry.py` (24)
- Modify: `app/api/learning.py` (22)
- Modify: `app/api/emma.py` (22)
- Modify: all remaining files under `app/` containing `tenant_id`

- [ ] **Step 1: Delete the orphaned client**

```bash
git rm backend/microservices/weaviate-service/app/services/sharing_insights_client.py
```

The corresponding backend endpoint was deleted in Plan 2; this client is dead code.

- [ ] **Step 2: Find every importer of the deleted file**

```bash
grep -rln "sharing_insights_client" backend/microservices/weaviate-service 2>/dev/null
```

Delete the import lines and any code that called it.

- [ ] **Step 3: Generate the working list**

```bash
grep -rln "tenant_id" backend/microservices/weaviate-service/app 2>/dev/null > /tmp/weaviate_remaining.txt
wc -l /tmp/weaviate_remaining.txt
```

- [ ] **Step 4: Refactor file-by-file**

Apply Patterns A, B, C as appropriate. Service signatures change to take `user_roles: List[str]`.

- [ ] **Step 5: Update BOE indexing to write `roles: ["EVERYONE"]`**

```bash
grep -rn "boe\|public_knowledge" backend/microservices/weaviate-service/app/services 2>/dev/null
```

In every BOE/PublicKnowledge index call, set `roles=["EVERYONE"]`.

- [ ] **Step 6: Update `seed_legal_graph.py` and `connect_orphan_laws.py`**

```bash
ls backend/microservices/weaviate-service/scripts/
```

Update these scripts to write `roles: ["EVERYONE"]` for all seeded data.

- [ ] **Step 7: Verify**

```bash
grep -rln "tenant_id\|X-Tenant-ID" backend/microservices/weaviate-service 2>/dev/null
```

Expected: zero matches.

---

## Task 12: Refactor `knowledge-tree-service` — `user` → `role` rename (Pattern D)

**Files:**
- `app/services/triple_store.py`
- `app/services/triple_query.py`
- `app/services/graph_assembler.py`
- `app/services/template_executor.py`
- `app/services/provenance.py`
- `app/services/uri_builder.py`
- `app/api/triples.py` (20)
- `app/api/extract.py` (2)
- `app/api/reports.py` (1)
- `app/schemas/triples.py` (8)
- `app/schemas/reports.py` (1)
- `scripts/reindex_trustgraph.py`

- [ ] **Step 1: Rename the parameter in `triple_store.py`**

Find every function that takes `user: str` (which currently holds a tenant id) and rename it to `role: str`. Update the Cypher templates to use `role` instead of `user` in `:Node {user: $user}` style patterns.

- [ ] **Step 2: Add the `allowed_roles` helper**

```python
# In triple_store.py
def allowed_roles(user_roles: list[str]) -> list[str]:
    """Return user roles plus the EVERYONE wildcard."""
    return list({*user_roles, "EVERYONE"})
```

- [ ] **Step 3: Update query methods to filter by `role IN $allowed_roles`**

```cypher
MATCH (n:Node)
WHERE n.role IN $allowed_roles AND n.collection = $col
RETURN n
```

For multi-role queries, the application layer dedupes the results.

- [ ] **Step 4: Update the schemas**

`app/schemas/triples.py` and `app/schemas/reports.py` change `tenant_id: str` to `user_roles: List[str]`.

- [ ] **Step 5: Update the API endpoints**

`app/api/triples.py`, `extract.py`, `reports.py` apply Pattern A and pass `user_roles` to the service layer.

- [ ] **Step 6: Update `reindex_trustgraph.py`**

The reindex script writes the new schema (`role` property instead of `user`). When invoked without an explicit role, it uses `EVERYONE`.

- [ ] **Step 7: Verify**

```bash
grep -rn "tenant_id" backend/microservices/knowledge-tree-service 2>/dev/null
grep -rn "{user:\|user=\$user" backend/microservices/knowledge-tree-service/app/services 2>/dev/null
```

Expected: zero matches in both.

---

## Task 13: Refactor MCP servers (alfresco, onedrive, google-drive)

**Files:**
- `backend/microservices/mcp-alfresco-server/app/**/*.py` (4 files)
- `backend/microservices/mcp-onedrive-server/app/**/*.py` (6 files)
- `backend/microservices/mcp-google-drive-server/app/**/*.py` (6 files)

- [ ] **Step 1: For each MCP server, generate the working list**

```bash
for srv in mcp-alfresco-server mcp-onedrive-server mcp-google-drive-server; do
  echo "=== $srv ==="
  grep -rln "tenant_id\|X-Tenant-ID" backend/microservices/$srv 2>/dev/null
done
```

- [ ] **Step 2: Refactor each file**

Apply Pattern A (endpoints) and Pattern B (clients). The OAuth tokens stay per-user — the `user_id` in the token storage table remains the unique key.

- [ ] **Step 3: Drop tenant from connector configs**

If any MCP server stores configuration in a JSON/YAML file keyed by `tenant_id`, restructure as a flat single-config layout (one config per MCP server per deployment).

- [ ] **Step 4: Verify each server**

```bash
for srv in mcp-alfresco-server mcp-onedrive-server mcp-google-drive-server; do
  echo "=== $srv ==="
  grep -rn "tenant_id\|X-Tenant-ID" backend/microservices/$srv 2>/dev/null
done
```

Expected: zero matches in all three.

---

## Task 14: Refactor `background-worker`

**Files:**
- `backend/microservices/background-worker/worker_app/tasks/*.py`
- `backend/microservices/background-worker/worker_app/celery_app.py` (if it has tenant config)
- `backend/microservices/background-worker/worker_app/clients/*.py`

- [ ] **Step 1: Generate the working list**

```bash
grep -rln "tenant_id\|X-Tenant-ID" backend/microservices/background-worker 2>/dev/null
```

- [ ] **Step 2: Refactor Celery task signatures**

Every `@celery_app.task` whose first arg is `tenant_id: str` becomes either:
- Drop the arg if the task is global (e.g. periodic re-index).
- Replace with `user_id: str, user_roles: List[str]` if the task is user-scoped (e.g. emma-reactive notifications).

- [ ] **Step 3: Update connector_tasks.py**

Connector sync tasks read the `default_document_roles` from the connector record (added in Plan 1) and propagate them when indexing each document.

- [ ] **Step 4: Verify**

```bash
grep -rn "tenant_id" backend/microservices/background-worker 2>/dev/null
```

Expected: zero matches.

---

## Task 15: Refactor `document-forge-service`, `storage-service`

**Files:**
- `backend/microservices/document-forge-service/**/*.py` (8 files, 28 occurrences)
- `backend/microservices/storage-service/**/*.py` (low, 8 occurrences)

- [ ] **Step 1: Generate working lists**

```bash
grep -rln "tenant_id\|X-Tenant-ID" backend/microservices/document-forge-service backend/microservices/storage-service 2>/dev/null
```

- [ ] **Step 2: Apply Pattern A/B**

Both services are low-density. Drop tenant from request handlers and clients. Drop tenant from any GCS path templates (storage paths are now `gs://nouxcube-documents-dev/{document_id}/...` without tenant prefix).

- [ ] **Step 3: Verify**

```bash
grep -rn "tenant_id" backend/microservices/document-forge-service backend/microservices/storage-service 2>/dev/null
```

Expected: zero matches.

---

## Task 16: Verify `intelligence-docs-service` is already clean

**Files:** none (verification only)

- [ ] **Step 1: Check**

```bash
grep -rn "tenant_id\|X-Tenant-ID" backend/microservices/intelligence-docs-service 2>/dev/null
```

Expected: zero matches (the service is already tenant-free per the audit).

If matches appear, refactor with Patterns A and B before proceeding.

---

## Task 17: Update microservice tests

**Files:**
- `backend/microservices/*/tests/**/*.py`

- [ ] **Step 1: Generate the working list**

```bash
grep -rln "tenant_id\|X-Tenant-ID" backend/microservices/*/tests 2>/dev/null
```

- [ ] **Step 2: Update fixtures**

Any pytest fixture that yields a `tenant_id` is replaced by one that yields `user_roles: List[str]` and `user_id: str`.

- [ ] **Step 3: Update test bodies**

Replace assertions on `tenant_id=...` with assertions on `user_roles=[...]`. Replace `headers={"X-Tenant-ID": ...}` with `headers={"X-User-Roles": "...", "X-User-Id": "..."}`.

- [ ] **Step 4: Run microservice tests one service at a time**

```bash
cd backend/microservices/emma-agent-service && python -m pytest tests/ -x --no-header 2>&1 | tail -20
cd backend/microservices/weaviate-service   && python -m pytest tests/ -x --no-header 2>&1 | tail -20
cd backend/microservices/knowledge-tree-service && python -m pytest tests/ -x --no-header 2>&1 | tail -20
```

Expected: tests pass (or fail only because they need Plan 5's diagnostics rewrite — note these failures and expect them in Plan 5).

---

## Task 18: Run an import smoke test on every microservice

**Files:** none (verification only)

- [ ] **Step 1: For each microservice, attempt a clean import**

```bash
for srv in emma-agent-service weaviate-service knowledge-tree-service intelligence-docs-service document-forge-service mcp-alfresco-server mcp-onedrive-server mcp-google-drive-server background-worker storage-service; do
  echo "=== $srv ==="
  cd backend/microservices/$srv && python -c "import app.main" 2>&1 | tail -5
  cd - >/dev/null
done
```

Expected: each service imports cleanly. Failures here mean a refactor was incomplete; trace the import error and fix the offending file.

- [ ] **Step 2: Final repo-wide grep**

```bash
grep -rln "tenant_id\|X-Tenant-ID" backend/microservices 2>/dev/null \
  | grep -v "diagnostics.py" \
  | grep -v "__pycache__"
```

Expected: zero matches. The only allowed remaining file is `emma-agent-service/app/api/diagnostics.py`, which is rewritten in Plan 5.

---

## Task 19: Commit Plan 3

**Files:** none (git operation)

- [ ] **Step 1: Stage all microservice changes**

```bash
git add backend/microservices
```

- [ ] **Step 2: Verify the diff is sane**

```bash
git status --short
git diff --stat HEAD
```

Expected: ~213 files modified, several deletions, no additions outside the planned set.

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(microservices): drop tenant_id from all clients and schemas

Implements Plan 3 of the multi-tenancy removal refactor.

- emma-agent-service: drop tenant_id from execution_context, all API
  endpoints, all service methods, all LangGraph state and tools, the
  weaviate/knowledge-tree clients, the checkpointer namespaces, and the
  emma-reactive-worker (event_listener.py). Diagnostics are deferred to
  Plan 5.
- weaviate-service: replace tenant_id filter with role-based ContainsAny
  filter on the new IndexedDocument.roles and PublicKnowledge.roles
  properties. Delete sharing_insights_client.py (orphaned by Plan 2).
  BOE/PublicKnowledge seeders write roles=['EVERYONE'].
- knowledge-tree-service: rename the FalkorDB :Node/:Literal/:Rel
  property `user` -> `role` (semantic change, not just a rename — the
  value is now a role identifier from KeyCloak, not a tenant id).
  Multi-role queries dedupe at the application layer. reindex_trustgraph
  rewrites with the new schema.
- mcp-alfresco/onedrive/google-drive: drop tenant from request handlers
  and configs. OAuth tokens stay per-user.
- background-worker: drop tenant from Celery task signatures. Connector
  sync reads default_document_roles from the connector record.
- document-forge-service, storage-service: drop tenant from clients and
  GCS path templates.
- All inter-service HTTP calls now propagate X-User-Roles (comma joined)
  and X-User-Id headers instead of X-Tenant-ID.

The system is still not runnable end-to-end: the frontend (Plan 4) still
sends X-Tenant-ID and the diagnostics endpoint (Plan 5) still hardcodes
_DEFAULT_TENANT.

Spec: docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
Plan: docs/superpowers/plans/2026-04-06-remove-tenancy-03-microservices.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify the commit**

```bash
git log -1 --stat | tail -20
```

---

## Task 20: Self-check before handing off to Plan 4

**Files:** none (verification only)

- [ ] **Step 1: Confirm zero residual `tenant_id` outside diagnostics**

```bash
grep -rln "tenant_id" backend/microservices 2>/dev/null \
  | grep -v "diagnostics.py" \
  | grep -v "__pycache__"
```

Expected: zero matches.

- [ ] **Step 2: Confirm zero `X-Tenant-ID` headers anywhere**

```bash
grep -rn "X-Tenant-ID" backend/microservices 2>/dev/null
```

Expected: zero matches (no exception — even diagnostics doesn't need it).

- [ ] **Step 3: Confirm every microservice imports cleanly**

Re-run Task 18 Step 1.

- [ ] **Step 4: Confirm Weaviate schemas have `roles`**

```bash
grep -rn 'roles' backend/microservices/weaviate-service/app/services/weaviate_service.py | grep -i "property\|create"
```

Expected: at least one match showing the `roles` property is in the schema definition.

- [ ] **Step 5: Confirm KTS uses `role` not `user` in Cypher**

```bash
grep -rn '{user:' backend/microservices/knowledge-tree-service/app/services 2>/dev/null
grep -rn '{role:\|n.role IN' backend/microservices/knowledge-tree-service/app/services 2>/dev/null
```

Expected: zero matches for `{user:`, several matches for `{role:` or `n.role IN`.

- [ ] **Step 6: Mark Plan 3 complete**

Plan 3 is done. The codebase now has:
- Every microservice query filtering by user roles instead of tenant id.
- Weaviate schemas with the `roles` property and the OR filter.
- FalkorDB schema with the `role` property and multi-role queries.
- All inter-service HTTP calls propagating `X-User-Roles` + `X-User-Id`.
- LangGraph state and tools using `user_roles` instead of `tenant_id`.

**The application stack will not start cleanly yet** because the frontend (Plan 4) still sends `tenant_id` and the diagnostics endpoint (Plan 5) still hardcodes `_DEFAULT_TENANT`. Plans 4 and 5 finish the work.

Hand off to `docs/superpowers/plans/2026-04-06-remove-tenancy-04-frontend.md`.
