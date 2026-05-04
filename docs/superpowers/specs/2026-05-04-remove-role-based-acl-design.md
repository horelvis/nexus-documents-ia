---
title: Remove role-based ACL across the stack
date: 2026-05-04
status: ready-for-implementation
owner: H Castillo
related-commits:
  - 973f0797 (multi-tenancy removal merge, 2026-04-21)
  - dba67f29 (delete JSONBACLProvider + core/acl tree, 2026-04-23)
  - fca4461e (drop is_tenant_public/shared_with_* columns, 2026-04-23)
  - d5e6f7a8b9c0 (Alembic migration for fca4461e)
  - 1416b401 (HEAD at design time, 2026-04-27)
supersedes-task: priority-stack item #3 (TrustGraph role isolation) — pivoted from "fix" to "remove"
---

# Remove role-based ACL across the stack

## TL;DR

NouxCubeIA is single-tenant on-premise; today every document, indexed object, and graph triple is tagged with `roles=['EVERYONE']`, and no production deployment uses role-restriction. The role-based ACL machinery (15 SQL filter call sites, 12+ Weaviate filter applications, 8 duplicated `auth_headers.py` modules, 1 frontend service file, 1 KTS Cypher property) is theatrical complexity. This spec removes it atomically in a single PR (6 commits), drops the `roles` columns + Weaviate property + KTS `user` property, and consolidates authorization onto `User.is_superuser` for admin gating. KeyCloak authentication stays untouched; JWT `realm_access.roles` continues to be issued but no longer consumed for data scoping.

## Background

This is the next logical step in a 2-week trajectory of ACL simplification:

| Date | Commit | Removed |
|---|---|---|
| 2026-04-21 | `973f0797` | Multi-tenancy (`tenant_id` columns, propagation, isolation logic) |
| 2026-04-23 | `dba67f29` | `JSONBACLProvider`, `backend/core/acl/` tree, `ACLProviderFactory` |
| 2026-04-23 | `fca4461e` | `is_tenant_public`, `shared_with_users`, `shared_with_groups` columns |
| 2026-05-04 | THIS SPEC | `roles` columns, Weaviate `roles` property, KTS `user` Cypher property, `EVERYONE` sentinel |

Each step removed a layer that no production deployment was consuming meaningfully. The current PR closes the arc.

The decision was reached after exploring three alternatives:
- **A. Propagate roles end-to-end**: complete the role-based ACL implementation. ~2-4h work.
- **B. Remove ACL entirely**: this spec. ~3-5h work, mostly deletion.
- **C. Simplify but keep column**: hybrid — keep column as informational, remove enforcement. Rejected as "system half-built".

Driver: "ACL is a consequence of removing tenantId; if all info is provided for a determined group of users, maybe time to remove it" (user, 2026-05-04). For single-tenant on-premise customers where every authenticated user belongs to the same organization, role-departmental partitioning is not a load-bearing requirement. If a future customer requires it, reintroducing a clean ACL is cheaper than maintaining the current half-built one indefinitely.

## Decisions log

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | What's the granularity of role tags in the graph? (Node/Literal/Rel array vs Rel-only) | **Superseded** by Q3 | Initially Rel-only (B), then redesigned to remove entirely |
| 2 | MERGE semantics multi-source (Union vs Provenance-based) | **Superseded** by Q3 | Initially Union (A), then redesigned to remove entirely |
| 3 | Fix role isolation vs remove ACL entirely | **Remove entirely** | "ACL is a consequence of tenancy removal; default sano sería B" |
| 4 | What survives of the auth model? | `is_superuser` boolean for admin gating; KeyCloak auth untouched | "Solo uno o varios usuarios son is_superuser, que permite acceder a secciones de config o administracion" |
| 5 | Rollout strategy (atomic vs phased) | **Approach A — atomic single PR** | System already at terminal state; phasing introduces transitional half-built code |
| 6 | API breaking change handling (strict drop vs lenient/deprecated) | **Strict drop (422 on `roles` input)** | Coherent with project trajectory ("delete, don't deprecate"); same pattern as Plan 5 irreversible migration |

## Scope

### What dies (data-scoping ACL)

#### SQL columns (`backend/app/db/models.py`)
- `Document.roles` ARRAY(String) (line 178) + `idx_documents_roles` GIN index (line 184)
- `IndexedDocument.roles` ARRAY(String) (line 1696) + `idx_indexed_documents_roles` GIN index (line 1703)
- New Alembic migration drops both. Downgrade marked irreversible (precedent: `d5e6f7a8b9c0`).

#### Backend code (`backend/app/`)
- `core/auth/acl.py` — entire module: `EVERYONE_ROLE` constant, `build_role_filter_clause()`, `filter_visible_to_user()`. The `require_role()` function is renamed and simplified (see "What stays").
- `services/document_service.py` — `EVERYONE_ROLE` constant, `user_roles` extraction, `can_access_document()`, default role assignment (lines 13, 37, 63, 127).
- `services/async_document_service.py` — 11+ filter clauses (lines 461-466, 976, 1212-1217, 1260-1265, 1662-1668), `IndexedDocument.roles.contains()` and `.overlap()` calls.
- `services/search_service.py:37` — `self.role_ids` extraction.
- `services/elasticsearch_client.py:130-131` — role member init.
- 15 call sites of `filter_visible_to_user()` across:
  - `api/v1/documents.py:53, 93, 267, 964`
  - `api/v1/document_categorization.py:73, 400, 438`
  - `api/v1/analysis_queue.py:53, 135, 460`
  - `api/v1/classification.py:303`
  - `api/v1/document_insights.py:36`
  - `api/v1/entities.py:42, 177`
  - `api/v1/notebooks.py:679`

#### Microservice code (`backend/microservices/`)
8 microservices each have a duplicated `auth_headers.py` containing `EVERYONE_ROLE` + `allowed_roles()`:
- `weaviate-service/app/core/auth_headers.py:21,57,99`
- `knowledge-tree-service/app/core/auth_headers.py:21,57`
- `emma-agent-service/app/core/auth_headers.py:21,57,73,76`
- `intelligence-docs-service/app/core/auth_headers.py:21,57`
- `background-worker/worker_app/core/auth_headers.py:21,57`
- `storage-service/app/core/auth_headers.py:21,57`
- `document-forge-service/app/core/auth_headers.py:21,57`
- MCP servers (Alfresco, Google Drive, OneDrive) — each with its own copy

Service-specific consumers:

**weaviate-service**
- `services/weaviate_service.py:79-87` — `_roles_filter()` function.
- 12+ filter applications (lines 453, 506, 680, 724, 1223, 1599, 1857, 1946, 2001, 2332, 2384, 2439).
- `services/rag/indexing_pipeline.py:1028-1042` and indexing call sites — role writes during ingestion.
- Weaviate schema: `roles` TEXT_ARRAY property on every collection (`Nouxcube_documents`, `Nouxcube_documents_summaries`, `Nouxcube_knowledge`, `Nouxcube_visual`, `TrustGraphEntities`, `OntologyTerms`).
- `core/execution_context.py:59,163` — `EVERYONE_ROLE` in execution context.

**knowledge-tree-service**
- `api/triples.py:50-59` — `_graph_scope()` function (returns hardcoded `EVERYONE_ROLE`).
- `api/extract.py:43,67,82,102,108` — hardcoded `user=EVERYONE_ROLE` in 5 endpoints.
- `api/reports.py:45` — same.
- `services/triple_store.py` — `merge_node`, `merge_literal`, `create_rel`, `batch_store_triples` Cypher with `{user: $user, collection: $collection}` properties.
- `services/triple_query.py` — `_col_where()` keeps `collection` filter; the `user` filter (`{user: $user}` on Node/Literal) is removed entirely.
- `scripts/dedup_entities.py:26,133` and `scripts/reindex_trustgraph.py:46,280` — `user=EVERYONE_ROLE` in batch ops.
- The `user` Cypher property on `:Node`, `:Literal`, `:Rel` is **dropped entirely**, not renamed to `role`.
- `clear_tenant()` method in `triples.py:282` renamed `clear_scope()` (bonus cleanup of bug-of-intent).
- `services/triple_query.py:7` docstring "All methods are async and enforce multi-tenant isolation via `user`..." rewritten.

**emma-agent-service / background-worker / storage-service / document-forge-service / MCP**
- Only the `auth_headers.py` constant + helper to remove. No downstream consumption.

#### Frontend (`frontend/src/`)
- `lib/services/document-acl.service.ts` (259 LOC) — entire file deleted: `getMyPermissions`, `grantPermission`, `revokePermission`, `grantPermissionsBatch`, `bulkUpdateACLs`, `makePublicInTenant`, etc.
- `contexts/auth-context.tsx`, `contexts/auth/types.ts`, `lib/services/auth.service.ts` — audit and remove role-based feature gates; preserve `is_superuser` checks.
- `components/auth/admin-guard.tsx` — verify uses `is_superuser` only (probably already correct).

#### Pydantic schemas (`backend/app/schemas/`)
- `document.py:13-22,128-146` — `roles` field removed from `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentDetail`.
- `connector.py` — `default_document_roles` removed from `ConnectorCreate`, `ConnectorUpdate`.
- `unified_document.py:107` — `roles` field on `UnifiedDocument` dataclass removed.

#### Tests
- `backend/tests/test_acl.py` (entire file, 8 tests including `test_filter_visible_to_user_includes_everyone`, `test_filter_visible_to_user_includes_user_roles`, `test_require_role_*`).
- Fixtures setting up multi-role scenarios across integration tests.

#### Connector adapters
- Alfresco / Google Drive / SharePoint sync code that sets `roles=["EVERYONE"]` on `UnifiedDocument`. Specifically `mcp-google-drive-server/app/services/sync_service.py:71,109,141,202-305` (`default_document_roles`, `default_roles`).

### What stays (auth + admin gating)

- **KeyCloak realm and group claim mapper** — untouched. JWT `realm_access.roles` continues to be issued; consumed for `UserProfile.roles` (informational only after this PR).
- **`User.is_superuser` boolean** (`models.py:69`) — sole authz dimension. Set only via PATCH `/users/{id}/role` (`api/v1/users.py:196-200`); this endpoint stays.
- **`require_role()` → `require_superuser()`** rename (`core/auth/acl.py:68-102`): the dependency is preserved but simplified to check `user.is_superuser=True`. All callers using `require_role("ADMIN")` migrate to `require_superuser()`.
- **`User.roles` propagation from JWT to `UserProfile.roles`** (`schemas/user.py:97-100`) — kept as informational metadata, returned in `/auth/me`. No filter consumes it after this PR.
- **Document ownership model** (`Document.owner_id` FK) — sole discriminator alongside `is_superuser`.

### Out of scope

- KeyCloak realm reconfiguration (the `Administradores` group, group claim mapper) — stays as-is, becomes inert.
- Audit logs / Prometheus metrics — even if logs include user roles from JWT, they remain valid identity metadata.
- Frontend role-display widgets that render `UserProfile.roles` (if any) — stay as informational, don't gate behavior.
- `User.roles` propagation pipeline from JWT — stays. The cleanup target is data scoping (document filtering), not user identity.

## Implementation: 6 commits in 1 PR

Each commit leaves the system functional. Order is **consumers before producers, producers before schemas**.

### Commit 1 — `chore(frontend): remove role-based ACL surface`

**Files:**
- DELETE `frontend/src/lib/services/document-acl.service.ts`
- EDIT `frontend/src/contexts/auth-context.tsx` — remove role-based feature gates
- EDIT `frontend/src/contexts/auth/types.ts` — drop role fields if used for gating
- EDIT `frontend/src/lib/services/auth.service.ts` — remove role-based JWT consumption beyond informational `UserProfile.roles`
- VERIFY `frontend/src/components/auth/admin-guard.tsx` uses `is_superuser` only

**Why safe:** Frontend reads from backend; backend still serves `roles` (now ignored client-side).

**Tests:** Frontend unit tests adjusted (likely empty area).

### Commit 2 — `refactor(backend): drop role-based document filtering`

**Files:**
- DELETE `backend/app/core/auth/acl.py` (after moving `require_role` → `require_superuser` to a new `core/auth/superuser.py` or inline into `dependencies.py`)
- EDIT `backend/app/services/document_service.py` — gut `can_access_document()`, replace with owner check
- EDIT `backend/app/services/async_document_service.py` — remove 11+ filter clauses; preserve owner-based filters
- EDIT `backend/app/services/search_service.py` — drop `role_ids` initialization
- EDIT `backend/app/services/elasticsearch_client.py` — drop role member init
- EDIT 15 API endpoint files — remove `filter_visible_to_user()` calls; replace with owner/superuser logic where appropriate
  - `api/v1/documents.py`, `api/v1/document_categorization.py`, `api/v1/analysis_queue.py`, `api/v1/classification.py`, `api/v1/document_insights.py`, `api/v1/entities.py`, `api/v1/notebooks.py`
- EDIT `backend/app/api/dependencies.py:45` and `api/async_dependencies.py:59-62` — remove the `["ADMIN"] if is_superuser` synthesis
- DELETE `backend/tests/test_acl.py`
- AUDIT all imports of `app.core.auth.acl` across `backend/` and `backend/tests/` — any test that imports `EVERYONE_ROLE`, `filter_visible_to_user`, or `build_role_filter_clause` breaks at import time after the module is deleted. Either remove the imports (if the test no longer applies) or migrate to `require_superuser` / direct ownership checks. Run `grep -r "from app.core.auth.acl" backend/` before deletion to enumerate.

**Why safe:** Data in PostgreSQL still has `roles` populated; we stop reading them. `is_superuser` continues to gate admin paths.

**Tests:** `test_acl.py` fully removed. Integration tests asserting role-filtered behavior re-baselined or deleted.

### Commit 3 — `refactor(microservices): drop role plumbing across 8 services`

**Files:**
- EDIT 8× `auth_headers.py` (paths above) — remove `EVERYONE_ROLE` constant and `allowed_roles()` helper. Optionally: remove the entire file if no other content remains.
- EDIT `weaviate-service/app/services/weaviate_service.py` — DELETE `_roles_filter()` (lines 79-87) and 12+ call sites (453, 506, 680, 724, 1223, 1599, 1857, 1946, 2001, 2332, 2384, 2439).
- EDIT `weaviate-service/app/services/rag/indexing_pipeline.py:1028-1042` — drop `roles` from indexing payload.
- EDIT `weaviate-service/app/core/execution_context.py:59,163` — drop `EVERYONE_ROLE` references.
- EDIT `knowledge-tree-service/app/api/triples.py` — DELETE `_graph_scope()` (lines 50-59) and remove all 8 call sites; drop `user_roles` parameter from endpoint signatures (header still parsed by FastAPI but unused; the dependency declaration is removed).
- EDIT `knowledge-tree-service/app/api/extract.py` — drop `user=EVERYONE_ROLE` at lines 43, 67, 82, 102, 108. Remove `user` parameter from `coordinator.extract_document()` and downstream `triple_store` methods.
- EDIT `knowledge-tree-service/app/api/reports.py:45` — same.
- EDIT `knowledge-tree-service/app/services/triple_store.py` — drop `user` parameter from `merge_node`, `merge_literal`, `create_rel`, `batch_store_triples`, `batch_store_provenance`, `store_document_node`, `merge_chunk_node`. Cypher property `user` is removed from MERGE/MATCH patterns.
- EDIT `knowledge-tree-service/app/services/triple_query.py` — drop `user` from MATCH patterns (Node, Literal, Rel). Keep `collection` filter intact (it's namespace, not ACL).
- EDIT `knowledge-tree-service/scripts/dedup_entities.py:26,133` and `scripts/reindex_trustgraph.py:46,280` — drop `user` parameter.
- RENAME `clear_tenant()` → `clear_scope()` in `triples.py:282`.
- EDIT `mcp-google-drive-server/app/services/sync_service.py` — drop `default_document_roles`, `default_roles`, role propagation (lines 71, 109, 141, 202-305).

**Why safe:** Data in FalkorDB and Weaviate still has `user`/`roles` properties populated; we stop reading and stop writing them. Existing data becomes vestigial; cleanup happens in Commit 5.

**Tests:** Microservice tests adjusted. KTS test of `_graph_scope` removed.

### Commit 4 — `feat(api)!: remove roles field from Document/Connector schemas` ⚠️ breaking

**Files:**
- EDIT `backend/app/schemas/document.py:13-22,128-146` — drop `roles` from `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentDetail`.
- EDIT `backend/app/schemas/connector.py` — drop `default_document_roles` from `ConnectorCreate`, `ConnectorUpdate`.
- EDIT `backend/app/schemas/unified_document.py:107` — drop `roles` field.
- EDIT all places that construct these schemas to stop passing `roles`.

**Critical Pydantic config:** to ensure the 422 behavior (strict drop), the affected schemas MUST use `model_config = ConfigDict(extra='forbid')`. Pydantic's default is `extra='ignore'`, which would silently drop the `roles` field instead of rejecting the request — that would be lenient drop, contradicting Decision 6. Verify each affected model's config explicitly in this commit.

**Why this is the breaking-change moment:** clients sending `POST /documents` with `roles` in body get **422 Unprocessable Entity** from Pydantic with `extra='forbid'`.

**Tests:** Schema validation tests adjusted; `test_*_schema_accepts_roles` deleted. Add a positive test asserting `extra='forbid'` behavior: `POST /documents` with extra `roles` field → 422.

### Commit 5 — `feat(db)!: drop roles columns + Weaviate property + KTS user property` ⚠️ breaking, irreversible

**Files:**
- NEW `backend/alembic/versions/<rev>_drop_role_acl_columns.py`:
  ```python
  def upgrade():
      op.drop_index('idx_documents_roles', table_name='documents')
      op.drop_column('documents', 'roles')
      op.drop_index('idx_indexed_documents_roles', table_name='indexed_documents')
      op.drop_column('indexed_documents', 'roles')

  def downgrade():
      raise NotImplementedError(
          "Irreversible: roles column dropped permanently. Restore from pg_dump backup."
      )
  ```
- NEW `backend/scripts/weaviate_drop_roles_property.py` — blue/green per-collection migration. Vectors are preserved during copy (no re-embed); operational window is dominated by object copy time, not embedding time. Outline:
  ```python
  COLLECTIONS = ["Nouxcube_documents", "Nouxcube_documents_summaries",
                 "Nouxcube_knowledge", "Nouxcube_visual",
                 "TrustGraphEntities", "OntologyTerms"]
  for col_name in COLLECTIONS:
      old = client.collections.get(col_name)
      new_props = [p for p in old.config.get().properties if p.name != "roles"]
      client.collections.create(name=f"{col_name}_v2", properties=new_props, vector_config=...)
      target = client.collections.get(f"{col_name}_v2")
      with target.batch.dynamic() as batch:
          for obj in old.iterator(include_vector=True):
              props = {k: v for k, v in obj.properties.items() if k != "roles"}
              batch.add_object(properties=props, vector=obj.vector["default"], uuid=obj.uuid)
      client.collections.delete(col_name)
      client.collections.update_name(f"{col_name}_v2", col_name)
  ```
- NEW `backend/scripts/kts_remove_user_property.py`:
  ```python
  # Run via FalkorDB Python client
  await client.query(graph_name, "MATCH (n) WHERE n.user IS NOT NULL REMOVE n.user")
  await client.query(graph_name, "MATCH ()-[r]-() WHERE r.user IS NOT NULL REMOVE r.user")
  ```

**Why this is the operational hot path:** the Weaviate blue/green is the only step with significant elapsed time. Pre-flight backups are mandatory.

**Tests:** Migration tested via `alembic upgrade head` then `alembic downgrade base` in sandbox (downgrade should fail loudly with `NotImplementedError`).

### Commit 6 — `docs: rewrite ACL model from role-based to ownership`

**Files:**
- EDIT `CLAUDE.md` lines 45, 82, 502 — replace role-based ACL description with ownership + `is_superuser` model.
- EDIT `backend/app/db/models.py:1600-1617` — IndexedDocument class docstring rewritten.
- EDIT `backend/microservices/knowledge-tree-service/app/services/triple_query.py:7` — drop "multi-tenant isolation" language.
- EDIT `backend/microservices/weaviate-service/app/services/weaviate_service.py:4-7` — clean up "single-org refactor" / "multi-tenant" mixed language.
- EDIT `docs/on-premise/ONBOARDING.md` and any architecture docs that describe role-based ACL.

**Why safe:** Docs only; no runtime impact.

## Operations runbook

### Pre-flight checks (mandatory before merge)

```sql
-- Run on production PostgreSQL of each customer deployment
SELECT 'documents' AS tbl, COUNT(*) AS role_restricted_docs
  FROM documents WHERE NOT 'EVERYONE' = ANY(roles)
UNION ALL
SELECT 'indexed_documents', COUNT(*)
  FROM indexed_documents WHERE NOT 'EVERYONE' = ANY(roles);
```

```cypher
-- Run on FalkorDB (knowledge_graph) of each customer deployment
MATCH (n) WHERE n.user IS NOT NULL AND n.user <> 'EVERYONE' RETURN count(n) AS non_everyone_nodes;
MATCH ()-[r]-() WHERE r.user IS NOT NULL AND r.user <> 'EVERYONE' RETURN count(r) AS non_everyone_rels;
```

```python
# Weaviate per collection — intent: count objects whose `roles` array
# does NOT contain "EVERYONE". Weaviate v4 array-filter semantics vary;
# the implementer should pick the right primitive (probably an iterator
# + client-side check is safest). Below is illustrative pseudocode:
for col in ["Nouxcube_documents", "Nouxcube_documents_summaries",
            "Nouxcube_knowledge", "Nouxcube_visual",
            "TrustGraphEntities", "OntologyTerms"]:
    role_restricted = sum(
        1 for obj in client.collections.get(col).iterator()
        if "EVERYONE" not in (obj.properties.get("roles") or [])
    )
    print(f"{col}: {role_restricted} role-restricted objects")
```

**Decision rule**: if any check returns >0, the deployment HAS active role-restriction usage. Upgrade is **NOT** automatic; customer must be consulted before proceeding. Document the count in the customer release note.

### Backups (mandatory)

| System | Command | Why |
|---|---|---|
| PostgreSQL | `pg_dump -Fc -U nexus_user nexus_db > pre-acl-removal.dump` | Sole rollback path for column drop (Alembic downgrade is `NotImplementedError`) |
| Weaviate | `client.backup.create(backup_id="pre-acl-removal", backend="filesystem", wait_for_completion=True)` | Restore point if blue/green fails |
| FalkorDB | `redis-cli -p 6380 BGSAVE` then copy dump.rdb | Cheap insurance; vestigial property cannot lose business data |

### Migration sequence (maintenance window)

```
T+0:     docker compose stop frontend emma-agent-service
T+1:     pg_dump (~1-5 min depending on corpus size)
T+2:     Weaviate snapshot (~5-15 min)
T+3:     git pull + alembic upgrade head    # Drops roles columns
T+4:     python backend/scripts/weaviate_drop_roles_property.py    # Blue/green per collection
T+5:     python backend/scripts/kts_remove_user_property.py        # MATCH (n) REMOVE n.user
T+6:     docker compose up -d
T+7:     Smoke tests (5 min)
T+8:     Exit maintenance mode
```

Estimated total: **30-90 min** depending on corpus size. Hot path is Weaviate blue/green.

### Smoke tests (post-migration)

1. Admin login (KeyCloak) → `GET /auth/me` returns `is_superuser=true` for known admin user.
2. `POST /documents` without `roles` field → **200 OK**.
3. `POST /documents` WITH `roles` field → **422 Unprocessable Entity** (strict drop confirmed).
4. `GET /documents/{id}` response → no `roles` field present (schema drift confirmed).
5. Emma query "buscar contratos de 2024" → response with sources (smart_search functional).
6. Emma graph_rag query "qué empleados tiene Acme" → entities + provenance returned (KTS reads work without `user` filter).
7. Knowledge report "facturas Q1" → DOCX generated (report path works without role scoping).
8. Connector sync (Alfresco / Google Drive) → docs ingested without `roles` (write path works).

If **any** smoke test fails: rollback per next section.

### Rollback plan

| Failure | Action |
|---|---|
| Alembic migration error or post-upgrade SQL errors | `git revert PR` + `pg_restore -d nexus_db pre-acl-removal.dump` + redeploy old image |
| Weaviate blue/green failure (e.g., `_v2` collection not created or copy errored) | Delete any partial `_v2` collections; original collections intact; restart services with old image; investigate copy script |
| KTS cleanup script error | Original data unchanged (script removes `user` property idempotently); `git revert PR` and redeploy |
| Runtime regression in production traffic | `git revert PR`; redeploy services in reverse-deploy order (frontend last); root-cause from logs |

**Zero data loss path:** the data eliminated by this PR (`user` property in KTS, `roles` arrays in SQL/Weaviate) is functionally vestigial — no business information lives in it. Backups exist solely to restore schema, not content.

### Customer release note (CHANGELOG.md draft)

```markdown
## [vN+1.0.0] — BREAKING

### Removed
- **Role-based document ACL eliminated**. All documents are now visible to all
  authenticated users in the deployment. Admin/config sections remain restricted
  to users with `is_superuser=true`.
- `roles` field removed from the following endpoints:
  - `POST /documents`, `PATCH /documents/{id}`, `GET /documents` (response)
  - `POST /connectors`, `PATCH /connectors/{id}` (field `default_document_roles`)
  Requests sending `roles` or `default_document_roles` will return **422**.

### Migration window required
- Mandatory backup (PostgreSQL + Weaviate) — see `scripts/pre-flight-check.sh`.
- Estimated window: 30-90 min depending on corpus size.
- Migration **irreversible**: `documents.roles` and `indexed_documents.roles` columns
  are dropped permanently. Restore requires backup.

### Justification
KeyCloak roles continue to be issued in JWTs but are no longer consumed for data
scoping in single-tenant on-premise deployments. If your deployment requires
departmental partitioning, contact us before upgrading.
```

## References

### Primary inventory citations (file:line)
- `backend/app/db/models.py:69` — `User.is_superuser` (KEEP)
- `backend/app/db/models.py:178,184` — `Document.roles` column + index (DROP)
- `backend/app/db/models.py:1696,1703` — `IndexedDocument.roles` column + index (DROP)
- `backend/app/core/auth/acl.py:29` — `EVERYONE_ROLE` constant (DROP)
- `backend/app/core/auth/acl.py:32-49` — `build_role_filter_clause()` (DROP)
- `backend/app/core/auth/acl.py:52-65` — `filter_visible_to_user()` (DROP)
- `backend/app/core/auth/acl.py:68-102` — `require_role()` (RENAME → `require_superuser()`, simplify)
- `backend/app/api/v1/users.py:196-200` — `is_superuser` manual promotion (KEEP)
- `backend/app/services/async_document_service.py:461-466` — primary role-overlap clause (DROP)
- `backend/app/schemas/document.py:13-22,128-146` — `DocumentBase.roles` (DROP)
- `backend/app/schemas/connector.py` — `default_document_roles` (DROP)
- `backend/app/schemas/user.py:97-100` — `UserProfile.roles` from JWT (KEEP, informational)
- `backend/microservices/knowledge-tree-service/app/api/triples.py:50-59` — `_graph_scope()` (DROP)
- `backend/microservices/knowledge-tree-service/app/api/triples.py:282` — `clear_tenant()` (RENAME)
- `backend/microservices/knowledge-tree-service/app/api/extract.py:43,67,82,102,108` — `user=EVERYONE_ROLE` (DROP)
- `backend/microservices/knowledge-tree-service/app/api/reports.py:45` — `user=EVERYONE_ROLE` (DROP)
- `backend/microservices/knowledge-tree-service/app/services/triple_store.py:34,52,89,111,263,341,393` — Cypher write methods with `user` (REWRITE without `user`)
- `backend/microservices/knowledge-tree-service/app/services/triple_query.py:7,84-90,103,112-114,601-602` — Cypher read methods with `user` (REWRITE without `user`)
- `backend/microservices/weaviate-service/app/services/weaviate_service.py:79-87` — `_roles_filter()` (DROP)
- `frontend/src/lib/services/document-acl.service.ts` (entire file, 259 LOC) — DELETE

### Related work
- 2026-04-21 `973f0797` — Multi-tenancy removal merge.
- 2026-04-23 `dba67f29` — `JSONBACLProvider` + `core/acl/` tree deletion.
- 2026-04-23 `fca4461e` — `is_tenant_public` + `shared_with_*` columns dropped.
- 2026-04-23 `d5e6f7a8b9c0` — Alembic migration for the above.

### Memory references
- `project_acl_architectural_debt.md` (10 days old at design time) — original Finding 2 about `_graph_scope`.
- `project_session_2026-04-23_acl_cleanup.md` — Plan 5 closure.
- `project_remove_tenancy_in_progress.md` — multi-tenancy removal context.

## Open questions / followups (none blocking)

None blocking. Two future considerations recorded for posterity:

1. **KeyCloak `Administradores` group claim mapper** — currently inert after this PR. If a future spec wants to remove KeyCloak roles from the JWT entirely (currently kept as informational), a separate spec would address realm reconfiguration per customer.
2. **`UserProfile.roles` informational propagation** — kept after this PR. If a future spec finds it adds no UI value, it can be removed in a follow-up cleanup that touches `schemas/user.py:97-100` and the JWT decoder logic.

## Acceptance criteria

- All 6 commits land in a single PR; each commit individually green on CI.
- Pre-flight checks documented and runnable as `scripts/pre-flight-check.sh` (or equivalent).
- Smoke tests 1-8 all pass on a clean staging deployment.
- `CLAUDE.md` no longer references role-based ACL; mentions ownership + `is_superuser`.
- `pg_dump`-based rollback verified end-to-end in staging once before production.
- Customer release note included in CHANGELOG.md and shipped with the version bump.
