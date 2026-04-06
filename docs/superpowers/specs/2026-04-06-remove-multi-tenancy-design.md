# Remove Multi-Tenancy + Claims-Based RBAC — Design Spec

**Status**: Approved for implementation
**Author**: Brainstorming session 2026-04-06
**Branch**: `refactor/remove-multi-tenancy`
**Target merge**: `development`

## Motivation

The system is deployed exclusively on-premise as a single-tenant application (the SaaS deployment mode was deprecated). Despite that, the codebase still carries the full multi-tenant abstraction layer inherited from the original SaaS design: a `tenants` table, `tenant_id` columns on ~30 tables, tenant-scoped roles/permissions, document sharing flows, and `X-Tenant-ID` headers across every microservice. This is **conceptual debt**: an abstraction that no longer maps to the deployment reality.

Removing it pursues three concrete benefits:

1. **Simpler data handling**: every query loses one filter; many composite indexes shrink; ~12 tables vanish from the schema entirely.
2. **Simpler ACL**: access control becomes a single mechanism — KeyCloak roles checked against per-document role labels — instead of the current mix of tenant scoping + local roles + per-document ACL JSONB + sharing tables.
3. **Lower long-term cost**: less code to maintain, simpler mental model for new developers, less surface area for bugs.

This is a refactor with no new user-facing features. Its success criterion is **functional parity** with the current system after a clean rebuild against the new schema.

## Scope and Decomposition

This document covers the design for a **single deliverable**: the entire removal of multi-tenancy in one atomic refactor on the branch `refactor/remove-multi-tenancy`. The reasons for treating it as atomic instead of incremental:

- The new ACL model has no coherent intermediate state. Either all queries filter by `roles[]`, or none do.
- The database is recreated from scratch (no incremental migration), so there is no concept of "deploy phase 1, leave phase 2 for later".
- End-to-end tests only pass with the model fully in place.

Sub-areas covered:

- Section 1: ACL model (the foundational decision).
- Section 2: Schema changes (tables removed, modified, added; database rename to `nouxcube`).
- Section 3: Implementation sequence, validation, rollback.

Out of scope (explicit non-goals):

- Authentication provider migration. KeyCloak stays. The OIDC provider code in `backend/app/core/auth/providers/oidc.py` is **reused, not rewritten**.
- New permission features beyond the role-label model (e.g. ABAC, time-bounded access, delegation). These can be added later if needed.
- Frontend visual redesign. Only the data flow changes; UI components are updated mechanically.
- Migration of historical data. Data is regenerated from primary sources (GCS files, KeyCloak users, BOE API).

---

## Section 1 — ACL Model

### Three concepts, one mechanism

**Documents** carry an array column `roles: ARRAY(String)` containing the names of KeyCloak roles authorized to see them. The value `EVERYONE` is reserved as a wildcard meaning "any authenticated user".

**Users** have no roles stored locally. The KeyCloak JWT (validated by the existing OIDC middleware in `backend/app/core/auth/providers/oidc.py`) carries the role array in `realm_access.roles`. The existing `map_groups_to_roles()` function in `backend/app/core/auth/base.py:219` translates KeyCloak group names to application role identifiers via a config YAML. The result lives in `UserProfile.roles: List[str]` for the duration of the request and is never persisted.

**Connectors** carry a new column `default_document_roles: ARRAY(String)`. The admin sets this value when creating the connector (e.g. the "SharePoint Comercial" connector is created with `["SALES"]`). When the connector ingests documents, those roles are copied to each new document's `roles` field.

### Document model change

```python
# backend/app/db/models.py
class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True)
    # ... existing columns ...
    # NO tenant_id
    # NO owner_user_id
    roles = Column(ARRAY(String), nullable=False, default=["EVERYONE"])

    __table_args__ = (
        Index('idx_documents_roles', 'roles', postgresql_using='gin'),
        # ... other indexes (without tenant_id) ...
    )
```

The same `roles` column is added to `IndexedDocument` in the Weaviate schema (see Section 2).

### Connector model change

```python
class Connector(Base):
    __tablename__ = "connectors"
    id = Column(UUID(as_uuid=True), primary_key=True)
    # ... existing columns ...
    # NO tenant_id
    default_document_roles = Column(ARRAY(String), nullable=False)
```

### Universal query filter

A single helper replaces every `filter(Model.tenant_id == ...)` call in the codebase:

```python
# backend/app/core/auth/acl.py (new file)
from sqlalchemy import or_
from app.db.models import Document
from app.core.auth.base import UserProfile

def filter_visible_to_user(query, user: UserProfile):
    """Apply role-based ACL filter to a Document query."""
    return query.filter(
        or_(
            Document.roles.contains(["EVERYONE"]),
            Document.roles.overlap(user.roles),  # PostgreSQL && operator on text[]
        )
    )
```

For non-Document models that need ACL (e.g. `IndexedDocument` in Weaviate, `:Node` in FalkorDB), an equivalent filter is constructed in each store's native query language. See Section 2.B for details per store.

### Role naming convention

All role identifiers in code, database values, JWT claims, config files, and the wire protocol are **English uppercase identifiers** (`SALES`, `LEGAL`, `HR`, `ADMIN`, `EVERYONE`). The KeyCloak admin UI may use Spanish group names (`Comercial`, `Departamento Legal`, `Recursos Humanos`); the `map_groups_to_roles()` function translates them to the canonical English identifiers via a YAML config. This separation prevents identifier instability across i18n changes and avoids parsing issues with accented characters or spaces.

#### Canonical role catalog (reference, not enforced)

| Identifier | Meaning | KeyCloak group example |
|---|---|---|
| `EVERYONE` | Wildcard, authentication suffices | (reserved, never assigned to users) |
| `ADMIN` | Platform administration | `/Administradores` |
| `SALES` | Sales / commercial | `/Comercial` |
| `LEGAL` | Legal department | `/Departamento Legal` |
| `HR` | Human resources | `/Recursos Humanos` |
| `FINANCE` | Finance / accounting | `/Finanzas` |
| `MEDICAL` | Medical staff | `/Médicos` |

This catalog is documented as the **starting set**. Each deployment can extend it by adding entries to the YAML mapping; no code changes are required.

#### Role mapping config

```yaml
# backend/app/config/role_mapping.yaml (new file)
group_to_role:
  "/Administradores": ADMIN
  "/Comercial": SALES
  "/Departamento Legal": LEGAL
  "/Recursos Humanos": HR
  "/Finanzas": FINANCE
  "/Médicos": MEDICAL
```

This file is loaded at application startup and consumed by `map_groups_to_roles()`. Adding a new role for a deployment means editing this YAML and restarting the backend — no code change, no migration.

### Wildcard semantics

The `EVERYONE` value is a **reserved literal** with these properties:

- Never assigned to a user as a role (it would defeat the purpose).
- Always included in the SQL filter via the `OR` branch of `filter_visible_to_user`.
- Documented in `role_mapping.yaml` as a comment, not as a mapping target.
- Validated as not appearing in `UserProfile.roles` after `map_groups_to_roles()` runs (defensive check).

### What this model explicitly does NOT include

| Feature | Why it is rejected |
|---|---|
| Per-user document sharing | Concept inherited from SaaS multi-user collaboration. Single-tenant orgs don't need it — content belongs to the organization, not individuals. |
| Document owner (`owner_user_id`) | No ownership concept. Documents belong to the organization. |
| Folder-level ACL | Folders are visual organization, like filesystem directories. Permissions are on documents, not on paths. |
| Local `roles` table | KeyCloak is the source of truth. Duplicating defeats the purpose. |
| Local `permissions` / `capabilities` table | Capabilities are encoded as `require_role(*)` decorators in endpoints. No indirection table. |
| Tenant-scoped uniqueness constraints (e.g. `UNIQUE(name, tenant_id)`) | Replaced by global uniqueness where applicable, or removed where it doesn't apply. |

---

## Section 2 — Schema Changes

### A. Database rename

The main application database is renamed from `nexus_db` to `nouxcube`. The Postgres user (`nexus_user`) **does not change** — it remains the owner of both `nouxcube` and the `langfuse` database that lives in the same Postgres instance.

The `langfuse` database is **untouched** by this refactor. All Langfuse prompts (54+ entries), traces, evaluations, and configurations are preserved.

#### Files updated for the rename

| File | Change |
|---|---|
| `backend/docker/.env` | `POSTGRES_DB`, `DATABASE_URL` |
| `backend/docker/docker-compose.yml` | `POSTGRES_DB` env (if hardcoded fallback) |
| `backend/docker/docker-compose.onpremise.yml` | Idem |
| `backend/docker/docker-compose.test.yml` | Test DB renamed to `nouxcube_test` |
| `backend/app/core/config.py` | `DATABASE_URL` fallback |
| `backend/microservices/*/app/core/config.py` | All microservice configs (KTS, Emma, Weaviate, Forge, Intelligence, MCPs) |
| `backend/scripts/init_db.py` | Any DB name reference |
| `backend/tests/conftest.py` | Test setup |
| `backend/docker/init-scripts/01-init-langfuse.sql` | **No change** — langfuse stays as-is |
| `README.md`, `CLAUDE.md`, `docs/on-premise/ONBOARDING.md` | Documentation |
| `backend/docker/onboarding.sh` | Any DB name reference in scripts |

A new `02-init-nouxcube.sql` init script is added so that future first-time deployments correctly create both `nouxcube` and `langfuse`.

### B. Tables dropped completely

Twelve tables are removed from the schema. All their indexes, foreign keys, sequences, and ORM models are also removed.

| Table | Reason for removal |
|---|---|
| `tenants` | Multi-tenancy concept eliminated |
| `tenant_auth_configs` | Single global config via env vars |
| `roles` | KeyCloak is the source of truth |
| `permissions` | Capabilities encoded as endpoint decorators |
| `role_assignments` | Lives in KeyCloak |
| `role_assignment_audits` | Audited by KeyCloak |
| `permission_assignment_audits` | Audited by KeyCloak |
| `tag_audits` | Tenant-scoped audit no longer needed |
| `document_shares` | Sharing concept eliminated |
| `document_share_recipients` | Idem |
| `document_share_access_logs` | Idem |
| `team_invitations` | Tenant-bound concept |

### C. Tables modified (drop `tenant_id`, add `roles` where applicable)

| Table | Changes |
|---|---|
| `users` | Drop `tenant_id` + FK + composite indexes. The `email` column gains a global unique constraint if it doesn't have one. |
| `documents` | Drop `tenant_id` + FK + `idx_documents_tenant_*` indexes. **Add** `roles ARRAY(String) NOT NULL DEFAULT ['EVERYONE']` with a GIN index. |
| `folder_markers` | Drop `tenant_id`. Replace `UNIQUE(folder_path, tenant_id)` with `UNIQUE(folder_path)`. |
| `document_views` | Drop `tenant_id`. Replace `idx_document_views_tenant_date` with `idx_document_views_user_date`. |
| `document_metrics` | Drop `tenant_id` + associated indexes |
| `tags` | Drop `tenant_id`. Replace `UNIQUE(name, tenant_id)` with `UNIQUE(name)`. |
| `signature_providers` | Drop `tenant_id`. Single global signing config. |
| `signature_requests` | Drop `tenant_id`. Ownership inferred from `created_by`. |
| `google_drive_tokens` | Drop `tenant_id`. Tokens are per-user. |
| `connectors` | Drop `tenant_id`. **Add** `default_document_roles ARRAY(String) NOT NULL`. |
| `indexed_documents` | (Weaviate, not Postgres) Drop `tenant_id` filter property. **Add** `roles` as an indexed property in the schema. |
| `emma_user_memory_facts` | Drop `tenant_id`. Key remains `(user_id, fact_key)`. |
| Emma reactive tables (8 tables) | Drop `tenant_id` from `triggers`, `notifications`, `channels`, `pairings`, `heartbeat_*`. Ownership inferred from `user_id` or marked global. |

### D. Microservice store changes

#### KnowledgeTreeService (FalkorDB)

The `triple_store.py` module currently uses a `user` parameter that, in practice, was an alias for `tenant_id`. After this refactor, the parameter still exists but takes a **role identifier** instead — typically `EVERYONE` for organization-wide content or a specific role like `LEGAL` for restricted content. The graph queries continue to filter by this property; the change is purely semantic.

```cypher
-- Before:
MATCH (n:Node {user: $tenant_id, collection: $col}) ...

-- After:
MATCH (n:Node {role: $role, collection: $col}) ...
-- where $role is one of the user's KeyCloak roles or 'EVERYONE'
```

The `:Node`, `:Literal`, and `:Rel` schemas all change `user` → `role`. The `reindex_trustgraph.py` script propagates this change during the rebuild.

For users with multiple roles, the graph query is run as a UNION across all the user's roles plus `EVERYONE`, deduped at the application layer.

#### WeaviateService

The `IndexedDocument` and `PublicKnowledge` collection schemas gain a `roles: text[]` property. The `WeaviateClient.hybrid_search()` method gains a filter:

```python
where_filter = {
    "operator": "Or",
    "operands": [
        {"path": ["roles"], "operator": "ContainsAny", "valueText": ["EVERYONE"]},
        {"path": ["roles"], "operator": "ContainsAny", "valueText": user_roles},
    ]
}
```

This replaces the current `tenant_id` filter. `PublicKnowledge` (BOE legislation) is always indexed with `roles: ["EVERYONE"]` because Spanish law is publicly available content.

#### ElasticsearchService

The full-text search index gains a `roles` field with the same semantics. Filter at query time using a `terms` query combined with `EVERYONE`.

### E. Code changes by area

#### Backend (`backend/app/`)

- Delete: `core/auth/tenant_*.py`, any tenant-extraction middleware, `services/tenant_service.py`, `services/role_service.py`, `services/permission_service.py`.
- Delete dependencies: `get_current_tenant`, `require_tenant`.
- Delete endpoints: `/api/v1/tenants/*`, `/api/v1/auth_configs/*`, `/api/v1/roles/*`, `/api/v1/permissions/*`, `/api/v1/document-shares/*`.
- Replace every `filter(Model.tenant_id == ...)` with `filter_visible_to_user(query, user)` from `core/auth/acl.py`.
- Add new dependency `require_role(*roles)` in `core/auth/acl.py`:

```python
def require_role(*allowed_roles: str):
    def dep(user: UserProfile = Depends(get_current_user)):
        if not any(r in user.roles for r in allowed_roles):
            raise HTTPException(status_code=403, detail="forbidden")
        return user
    return dep
```

- Add `roles: List[str]` to `DocumentCreate` and `DocumentResponse` Pydantic schemas.
- Add `default_document_roles: List[str]` to `ConnectorCreate`, `ConnectorUpdate`, `ConnectorResponse`.
- All endpoints under `/api/v1/connectors/*` gain `Depends(require_role("ADMIN"))`.

#### Microservices

| Service | Changes |
|---|---|
| `emma-agent-service` | Drop `tenant_id` from LangGraph state, from checkpointer/store namespaces (now `("user_facts", user_id)`), from HTTP headers in all clients. Update `prompt_composer`, `rule_engine`, `guardrail_service`. The `tenant_knowledge_service.py` is renamed or its tenant logic removed. |
| `knowledge-tree-service` | Update `triple_store.py` to use `role` parameter. Update `graph_assembler.py`, `triple_query.py`, `template_executor.py`. Update `reindex_trustgraph.py` to write the new schema. |
| `weaviate-service` | Update `WeaviateClient.hybrid_search()` to filter by `roles`. Update `IndexedDocument` and `PublicKnowledge` schemas. Update `seed_legal_graph.py` and BOE indexing to write `roles: ["EVERYONE"]`. |
| `intelligence-docs-service` | Drop `tenant_id` from extraction payloads, propagate `roles` from the source connector. |
| `document-forge-service` | Drop `tenant_id` from clients and storage paths. |
| `mcp-alfresco-server`, `mcp-onedrive-server`, `mcp-google-drive-server` | Drop `tenant_id` from configs. OAuth tokens remain per-user. |
| `background-worker` | Drop `tenant_id` from Celery task signatures and connector_tasks. |
| `emma-reactive-worker` | Drop `tenant_id` from Redis Streams consumer logic and notification namespaces. |

#### Frontend (`frontend/src/`)

- Delete `lib/services/tenant.service.ts`.
- Drop `tenant_id` from `contexts/auth-context.tsx`, `user-context.tsx`, `virtual-assistant-context.tsx`.
- Drop `tenant_id` from `lib/types/emma.ts`, `lib/types.ts`.
- Delete forms for managing local roles (`/admin/roles/*` pages) — KeyCloak admin UI handles this.
- Delete document sharing forms and components.
- **Add** a multi-select roles widget to the document upload form.
- **Add** a multi-select roles widget to the connector creation/edit form (admin-only).
- **Add** role badges in document cards (e.g. `[SALES]`, `[LEGAL]`).

### F. Quantitative impact estimate

| Metric | Estimated value |
|---|---|
| Tables dropped | 12 |
| Tables modified (drop tenant_id) | 25-30 |
| Alembic migrations after refactor | 1 (initial schema, all "create table" statements) |
| Backend LoC removed | ~500-800 |
| Backend LoC added | ~150 |
| Microservice LoC removed | ~200-300 |
| Microservice LoC added | ~50 |
| Frontend LoC removed | ~300-400 |
| Frontend LoC added | ~100 |
| Endpoints removed | 15-20 |
| Endpoints modified | 40-50 |

---

## Section 3 — Implementation Sequence, Validation, Rollback

### A. Implementation sequence (8 commits on `refactor/remove-multi-tenancy`)

The sequence is ordered by **dependency**, not priority. Each commit unblocks the next.

**Commit 1 — `chore: rename DB to nouxcube + introduce ACL helpers (no behavior change)`**
- Update `.env`, `docker-compose*.yml`, microservice configs to `nouxcube`.
- Create `backend/app/config/role_mapping.yaml` with the canonical role mappings.
- Create `backend/app/core/auth/acl.py` with `filter_visible_to_user` and `require_role` helpers.
- No model changes yet. The system still works with the old schema.

**Commit 2 — `feat(db): drop tenant model + tables, add roles[] for ACL`**
- Delete model classes from `backend/app/db/models.py`: `Tenant`, `TenantAuthConfig`, `Role`, `Permission`, `RoleAssignment`, `RoleAssignmentAudit`, `PermissionAssignmentAudit`, `DocumentShare`, `DocumentShareRecipient`, `DocumentShareAccessLog`, `TeamInvitation`, `TagAudit`.
- Drop `tenant_id` columns and FKs from all surviving models.
- Add `roles ARRAY(String)` to `Document` and `IndexedDocument`.
- Add `default_document_roles ARRAY(String)` to `Connector`.
- Update `emma_memory_models.py`, `emma_reactive_models.py`, `agent_models.py`.

**Commit 3 — `feat(alembic): single initial migration for nouxcube schema`**
- Move all existing migrations from `backend/alembic/versions/` to `backend/alembic/versions/_archived/` for historical reference.
- Generate one new migration: `alembic revision --autogenerate -m "initial nouxcube schema"`.
- Verify the generated SQL contains only `CREATE TABLE` statements, no `ALTER` or `DROP`.

**Commit 4 — `refactor(api): replace tenant filter with role-based ACL`**
- Delete tenant middlewares, dependencies, services.
- Delete tenant/role/permission/share endpoints.
- Replace `filter(Model.tenant_id == ...)` with `filter_visible_to_user(query, user)` across all services.
- Update Pydantic schemas with `roles` and `default_document_roles` fields.
- Apply `require_role("ADMIN")` to connector endpoints.

**Commit 5 — `refactor(microservices): drop tenant_id from all clients and schemas`**
- All microservices updated in lockstep (they're independent of each other but all depend on Commit 4):
  - `emma-agent-service`: state, namespaces, headers, prompts.
  - `knowledge-tree-service`: `triple_store.py`, `graph_assembler.py`, `reindex_trustgraph.py` use `role` instead of `user`/`tenant_id`.
  - `weaviate-service`: `WeaviateClient.hybrid_search()` filters by `roles`. Schemas updated.
  - `intelligence-docs-service`, `document-forge-service`, MCP servers: drop tenant from configs.
  - `background-worker`, `emma-reactive-worker`: drop tenant from tasks and consumers.

**Commit 6 — `refactor(frontend): drop tenant context, add role selectors`**
- Delete `tenant.service.ts`, contexts, types.
- Delete role/share management pages.
- Add roles multi-select to upload form and connector form.
- Add role badges in document cards.

**Commit 7 — `test: update fixtures and ACL assertions for nouxcube schema`**
- Update `backend/tests/conftest.py` to drop tenant setup.
- Update integration tests to use the new ACL model.
- **Update `emma-agent-service/app/api/diagnostics.py`**: rewrite the 11+ sanity check functions (`_check_hybrid_search`, `_check_graph_query`, `_check_memorag`, `_check_smart_search`, `_check_smart_search_temporal`, `_check_smart_search_person`, `_check_smart_search_legislation`, `_check_graph_entity_query`, `_check_react_pipeline`, `_check_user_memory`, etc.) to take `user_roles: List[str]` instead of `tenant_id: str`. Remove the hardcoded `_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"` constant. The diagnostics endpoints (`/diagnostics/run-all`, `/diagnostics/integration`) are updated to read roles from the JWT.
- Run `./run_tests.sh` and confirm all green.

**Commit 8 — `docs: reflect single-tenant + claims-based RBAC`**
- Update `CLAUDE.md`: replace the multi-tenancy section with single-tenant + KeyCloak RBAC documentation.
- Update `README.md`: DB name, ACL model.
- Update `docs/on-premise/ONBOARDING.md`: KeyCloak group creation steps and `role_mapping.yaml` configuration.
- Update `docs/architecture/` if any diagram references tenants.

### B. Drop & rebuild commands

After all 8 commits are merged to `refactor/remove-multi-tenancy` and the branch is ready, the drop & rebuild is executed against the running stack:

```bash
cd backend/docker

# 1. Stop application services (NOT the db service, NOT keycloak if it lives there)
docker compose stop \
  backend emma-agent-service knowledge-tree-service \
  weaviate-service intelligence-docs-service elasticsearch-service \
  background-worker emma-reactive-worker frontend

# 2. Drop the application database (PRESERVE langfuse)
docker compose exec db psql -U nexus_user -d postgres <<'EOF'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname = 'nexus_db' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS nexus_db;
CREATE DATABASE nouxcube
  WITH OWNER = nexus_user
       ENCODING = 'UTF8'
       LC_COLLATE = 'C'
       LC_CTYPE = 'C'
       TEMPLATE = template0;
GRANT ALL PRIVILEGES ON DATABASE nouxcube TO nexus_user;
EOF

# 3. Drop derived stores (these volumes can be safely removed)
docker compose stop weaviate falkordb elasticsearch
docker volume rm \
  docker_weaviate_data \
  docker_falkordb_data \
  docker_elasticsearch_data

# 4. Restart everything with the new code
docker compose up -d --build

# 5. Apply schema and seed
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.init_db

# 6. Re-seed Langfuse prompts (only if any new prompts were added)
docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py

# 7. Re-ingest content
./onboarding.sh boe              # ~10 min
./onboarding.sh sync-all         # depends on connector volume
./onboarding.sh status           # monitor progress
```

### C. Validation — smoke tests

After the rebuild completes, the following 12 smoke tests must pass before declaring success. Any failure triggers rollback.

| # | Test | Command / action | Success criterion |
|---|---|---|---|
| 1 | Postgres healthy | `docker compose exec db psql -U nexus_user -d nouxcube -c "\dt"` | Lists new schema tables, no error |
| 2 | Langfuse intact | `docker compose exec db psql -U nexus_user -d langfuse -c "SELECT count(*) FROM prompts"` | Returns the original prompt count, not zero |
| 3 | Backend up | `curl http://localhost:8000/health` | `200 OK` |
| 4 | Microservices up | `curl http://localhost:{8009,8011,8007,8012,8008}/health` | All `200 OK` |
| 5 | KeyCloak login | Manual login with a user assigned to a KeyCloak group mapped to `LEGAL` | JWT contains `realm_access.roles: ["LEGAL"]` after `map_groups_to_roles` |
| 6 | Upload with role | `POST /documents` with a PDF and `roles: ["LEGAL"]` | Response `200`, `document.roles == ["LEGAL"]` |
| 7 | Role filtering | Login as a `SALES` user, `GET /documents` | The doc from step 6 is NOT in the list |
| 8 | EVERYONE wildcard | Upload with `roles: ["EVERYONE"]`, query as any user | Doc appears in the list for all users |
| 9 | Connector default role | Create connector with `default_document_roles: ["SALES"]`, run sync | Ingested docs have `roles: ["SALES"]` |
| 10 | Emma query filtering | Login as `LEGAL`, ask Emma "show me the contracts" | Only retrieves docs accessible to `LEGAL` |
| 11 | TrustGraph filtering | Issue a `graph_rag` query from Emma | Only expands subgraph nodes with `role` matching user's roles or `EVERYONE` |
| 12 | BOE re-indexed | `./onboarding.sh status` | All laws marked as `indexed` |

A 13th test runs the diagnostics endpoint:

```bash
curl -X POST "http://localhost:8009/diagnostics/run-all" \
  -H "Authorization: Bearer $JWT"
```

This invokes the refactored sanity checks (`_check_hybrid_search`, `_check_graph_query`, `_check_memorag`, `_check_smart_search` ×4 variants, `_check_graph_entity_query`, `_check_react_pipeline`, `_check_user_memory`). All must return `status: "ok"`.

### D. Rollback procedure

Because no customer data exists in this testing environment and primary sources (GCS, KeyCloak) are preserved, rollback is mechanical:

```bash
# 1. Switch back
git checkout development
git pull origin development

# 2. Restore the original DB
docker compose exec db psql -U nexus_user -d postgres <<'EOF'
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
  WHERE datname = 'nouxcube' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS nouxcube;
CREATE DATABASE nexus_db
  WITH OWNER = nexus_user
       ENCODING = 'UTF8'
       LC_COLLATE = 'C'
       LC_CTYPE = 'C'
       TEMPLATE = template0;
GRANT ALL PRIVILEGES ON DATABASE nexus_db TO nexus_user;
EOF

# 3. Restore derived stores
docker compose down
docker volume rm \
  docker_weaviate_data \
  docker_falkordb_data \
  docker_elasticsearch_data
docker compose up -d --build

# 4. Re-run the old onboarding
docker compose exec backend alembic upgrade head
docker compose exec backend python -m scripts.init_db
./onboarding.sh boe
./onboarding.sh sync-all
```

Rollback time: ~30 minutes mechanical work plus the same TrustGraph re-extraction time as the forward rebuild.

### E. Coordination notes and risks

1. **KeyCloak setup must precede smoke test #5.** The KeyCloak realm must have the groups defined (`/Comercial`, `/Departamento Legal`, `/Recursos Humanos`, etc.) and at least one test user assigned to each. The `role_mapping.yaml` must be in place before the backend starts. Otherwise login will succeed but the user will have an empty `roles` list and see only `EVERYONE` content.

2. **`role_mapping.yaml` is a critical artifact.** If missing, all users effectively have empty roles and see only `EVERYONE` content. The `init_db.py` script validates its existence and refuses to start otherwise.

3. **TrustGraph re-extraction is the bottleneck.** With 47 BOE laws plus indexed test documents, expect 2-4 hours of LLM extraction work via 4 parallel extractors per chunk. Run with `nohup` or in a tmux session. Monitor via `docker compose logs -f knowledge-tree-service`.

4. **Frontend and backend deploy in lockstep.** A backend running the new schema with an old frontend will accept legacy headers as no-ops, but uploads will default all docs to `["EVERYONE"]`. Both must be deployed together.

5. **Test database isolation.** `nouxcube_test` lives in the same Postgres instance but is a separate logical database. Destructive integration tests cannot affect `nouxcube` or `langfuse`.

6. **Redis Streams consumer reset.** Emma Reactive uses Redis Streams keys that include `tenant_id` in the namespace. After the rebuild, those keys are obsolete and the consumer groups must be recreated. The simplest fix is `docker compose exec redis redis-cli FLUSHDB` (Redis is ephemeral by design).

7. **Diagnostics module is NOT optional**. Smoke test #13 (the diagnostics endpoint) is the most thorough validation. If the diagnostics rewrite in Commit 7 is incomplete, the smoke test fails and the rebuild is considered failed.

8. **Migration archive preservation.** The old Alembic migrations in `versions/_archived/` are kept for historical reference but never executed. They serve as documentation of the schema evolution.

---

## Open questions

None at the time of writing. All decisions are explicitly captured above.

## Acceptance criteria

The refactor is considered complete when:

1. All 8 commits are merged to `development`.
2. The 12 smoke tests + the diagnostics check pass on a freshly rebuilt stack.
3. `CLAUDE.md` accurately reflects the new architecture.
4. `feat/trustgraph-phase2` style cleanup: the branch `refactor/remove-multi-tenancy` is deleted from local and remote.
5. The next session starting from `development` can read `CLAUDE.md` and have a complete picture of the post-refactor architecture without needing to consult this spec.

## References

- `backend/app/db/models.py` — current schema with all tenant_id columns
- `backend/app/core/auth/providers/oidc.py:261` — existing role extraction from JWT
- `backend/app/core/auth/base.py:219` — existing `map_groups_to_roles` function
- `backend/microservices/emma-agent-service/app/api/diagnostics.py` — sanity checks to refactor
- `backend/microservices/knowledge-tree-service/app/services/triple_store.py` — graph store with `user` parameter
- `backend/microservices/weaviate-service/app/services/weaviate_service.py` — vector store with tenant filters
- `docs/on-premise/ONBOARDING.md` — current onboarding flow that this refactor changes
