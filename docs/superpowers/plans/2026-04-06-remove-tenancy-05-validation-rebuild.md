# Remove Multi-Tenancy — Plan 5: Diagnostics, Tests, Drop & Rebuild, Docs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the multi-tenancy removal refactor: rewrite `emma-agent-service/app/api/diagnostics.py` (the last file with `tenant_id`), update all remaining tests in `backend/tests/` and `backend/microservices/*/tests/`, execute the drop & rebuild against the running stack, run the 12 smoke tests + the diagnostics check, and update `CLAUDE.md`, `README.md`, and the `docs/` tree to reflect the new architecture. After this plan, the refactor is complete and the branch is ready to merge.

**Architecture:** This plan ties together everything from Plans 1-4. Diagnostics rewrite is pure code (Commit 7 part A). Test updates are pure code (Commit 7 part B). The rebuild is operational work (executed against the local Docker stack). The doc updates are pure markdown (Commit 8). The plan is split into clearly-marked code phases and operational phases so an agent can pause between them.

**Tech Stack:** Python 3.9+ / FastAPI / pytest / Docker Compose / Postgres 15 / Weaviate / FalkorDB / Elasticsearch / Redis. No new dependencies.

**Spec reference:** `docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md` (Section 3 "Implementation Sequence, Validation, Rollback")
**Previous plan:** `docs/superpowers/plans/2026-04-06-remove-tenancy-04-frontend.md`

**Plan boundaries:**
- ✅ Covers Commits 7 and 8 of Section 3.A of the spec.
- ✅ Outputs: a diagnostics module with no `tenant_id`, all tests green, the running database renamed to `nouxcube` with the new schema, all derived stores rebuilt and re-indexed, the BOE corpus re-downloaded, the 12 smoke tests passing, and CLAUDE.md/README.md/docs updated.
- ❌ Does NOT touch microservice business logic (Plan 3) or frontend components (Plan 4) — those are done.
- ❌ Does NOT introduce new features. The refactor is functional parity with the previous system.

---

## Volume estimate

- 1 file rewritten (`diagnostics.py`, ~1100 lines, 70 occurrences of `tenant_id`)
- ~12-15 backend test files modified
- 5 backend test files DELETED (pure tenant artifacts: `test_tenants.py`, `test_document_shares.py`, `test_document_insights.py`, `test_teams.py`, `test_role_assignments.py` if present)
- 1 `conftest.py` rewritten
- ~8 doc files modified (CLAUDE.md, README.md, AUTHENTICATION.md, ONBOARDING.md, ACL_SYSTEM.md, EMMA_REACTIVE.md, MODULAR_ARCHITECTURE.md, RAG_PIPELINE.md)
- ~30 minutes of build + ~2-4 hours of TrustGraph re-extraction

---

## Phase map

This plan has **three phases**, executed in order. Each phase ends with a commit. Do not skip phases.

| Phase | Description | Code or Operation | Commit |
|---|---|---|---|
| **A** | Rewrite `diagnostics.py`, update all tests, get the test suite green | Code | Commit 7 |
| **B** | Drop & rebuild the running stack, re-seed, run the 12 smoke tests + diagnostics | Operation | (no commit, runs on clean code) |
| **C** | Update CLAUDE.md, README.md, and docs | Code | Commit 8 |

---

## Phase A — Diagnostics rewrite, tests, Commit 7

### Task A1: Verify Plans 1-4 are in place

**Files:** none (verification only)

- [ ] **Step 1: Confirm branch and previous commits**

```bash
git status
git log --oneline -10
```

Expected: branch `refactor/remove-multi-tenancy`. The four previous plan commits are present:
- `feat(foundation): rename DB to nouxcube + introduce role-based ACL helpers`
- `refactor(api): replace tenant filter with role-based ACL`
- `refactor(microservices): drop tenant_id from all clients and schemas`
- `refactor(frontend): drop tenant context, add role selectors`

- [ ] **Step 2: Confirm only `diagnostics.py` still has `tenant_id` in microservices**

```bash
grep -rln "tenant_id\|X-Tenant-ID" backend/microservices 2>/dev/null \
  | grep -v "__pycache__"
```

Expected: a single match — `backend/microservices/emma-agent-service/app/api/diagnostics.py`. If there are other matches, finish the relevant prior plan first.

- [ ] **Step 3: Confirm frontend is clean**

```bash
grep -rln "tenant_id\|tenantId" frontend/src 2>/dev/null
```

Expected: zero matches.

---

### Task A2: Read and understand the current `diagnostics.py`

**Files:**
- Read: `backend/microservices/emma-agent-service/app/api/diagnostics.py`

- [ ] **Step 1: Read the full file**

It is ~1100 lines. Pay special attention to:

- Line 46: `_DEFAULT_TENANT = "00000000-0000-0000-0000-000000000001"` — to be deleted
- Lines 247-707: the 11 `_check_*` functions — each takes `tenant_id: str` and must take `user_roles: List[str]` instead
- Lines 1050-1058: the dispatcher list mapping check names to coroutines
- Lines 1097-1113: the FastAPI route handlers that read `tenant_id` from a query param

- [ ] **Step 2: List the functions to refactor**

```bash
grep -n "^async def _check_" backend/microservices/emma-agent-service/app/api/diagnostics.py
```

Expected: 11+ functions. The canonical list (from the spec):

| Function | Purpose |
|---|---|
| `_check_hybrid_search` | Weaviate hybrid retrieval |
| `_check_graph_query` | FalkorDB Cypher direct |
| `_check_memorag` | RLM processor |
| `_check_smart_search` | SmartSearch tool, default scope |
| `_check_smart_search_temporal` | SmartSearch with temporal filter |
| `_check_smart_search_person` | SmartSearch with person filter |
| `_check_smart_search_legislation` | SmartSearch on PublicKnowledge |
| `_check_graph_entity_query` | TrustGraph entity lookup |
| `_check_react_pipeline` | Full LangGraph ReAct loop |
| `_check_user_memory` | UserFactsService Store backend |
| (any others detected by the grep) | ... |

---

### Task A3: Rewrite the `_check_*` functions

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/diagnostics.py`

- [ ] **Step 1: Delete the `_DEFAULT_TENANT` constant**

Locate it with `grep -n "_DEFAULT_TENANT" backend/microservices/emma-agent-service/app/api/diagnostics.py` and remove the assignment line entirely.

- [ ] **Step 2: For each `_check_*` function, change the signature**

```python
# BEFORE
async def _check_hybrid_search(tenant_id: str) -> Dict[str, Any]:
    client = WeaviateClient()
    result = await client.hybrid_search(query="test", tenant_id=tenant_id)
    return {"status": "ok", "hits": len(result)}
```

```python
# AFTER
async def _check_hybrid_search(user_roles: List[str], user_id: str) -> Dict[str, Any]:
    client = WeaviateClient()
    result = await client.hybrid_search(
        query="test",
        user_roles=user_roles,
        user_id=user_id,
    )
    return {"status": "ok", "hits": len(result)}
```

- [ ] **Step 3: Update the contexts passed to LangGraph**

Find every `context={"tenant_id": _DEFAULT_TENANT}` (locate with `grep -n '_DEFAULT_TENANT' backend/microservices/emma-agent-service/app/api/diagnostics.py`). Replace with `context={"user_roles": user_roles, "user_id": user_id}`.

- [ ] **Step 4: Update the dispatcher list**

Find the dispatcher with `grep -n '_check_smart_search\b' backend/microservices/emma-agent-service/app/api/diagnostics.py | tail -3` — it's the block where check names are mapped to coroutines (the `checks = [...]` list, near the end of the file). Pass `user_roles` and `user_id` to each:

```python
# BEFORE
checks = [
    ("smart_search", _check_smart_search(tenant_id)),
    ...
]
```

```python
# AFTER
checks = [
    ("smart_search", _check_smart_search(user_roles, user_id)),
    ...
]
```

- [ ] **Step 5: Update the route handlers**

The endpoints (`/diagnostics/run-all`, `/diagnostics/integration`, etc.) currently take `tenant_id: str = Query(default=_DEFAULT_TENANT)`. Change to:

```python
from fastapi import Header

@router.post("/run-all")
async def run_all(
    x_user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    user_roles = (x_user_roles or "").split(",") if x_user_roles else []
    user_id = x_user_id or "diagnostics-anonymous"
    # ... call the dispatcher with user_roles, user_id ...
```

For local manual diagnostics where no headers are provided, default to `user_roles=["EVERYONE"]` so the checks still hit the `EVERYONE`-tagged seed data.

- [ ] **Step 6: Verify the file**

```bash
grep -n "tenant_id\|_DEFAULT_TENANT" backend/microservices/emma-agent-service/app/api/diagnostics.py
```

Expected: zero matches.

```bash
cd backend/microservices/emma-agent-service && python -c "from app.api.diagnostics import router; print('ok')"
```

Expected: prints `ok`.

---

### Task A4: Delete obsolete backend test files

**Files to delete (pure tenant artifacts):**
- `backend/tests/test_api/test_tenants.py`
- `backend/tests/test_api/test_document_shares.py`
- `backend/tests/test_api/test_document_insights.py` (verify it's the sharing-insights one, not a generic insights test)
- `backend/tests/test_api/test_teams.py` (if present)
- `backend/tests/test_api/test_role_assignments.py` (if present)

- [ ] **Step 1: Verify each candidate file is purely tenant-related**

```bash
for f in test_tenants test_document_shares test_document_insights test_teams test_role_assignments; do
  if [ -f "backend/tests/test_api/$f.py" ]; then
    echo "=== $f.py ==="
    head -5 "backend/tests/test_api/$f.py"
  fi
done
```

Read each file. If it tests **only** the deleted endpoints, delete it. If it tests something orthogonal, refactor instead.

- [ ] **Step 2: Delete the confirmed pure-tenant test files**

```bash
git rm backend/tests/test_api/test_tenants.py
git rm backend/tests/test_api/test_document_shares.py
# repeat for the others if confirmed
```

---

### Task A5: Refactor the surviving backend tests

**Files:**
- `backend/tests/conftest.py`
- `backend/tests/test_acl_security.py`
- `backend/tests/test_api/test_admin.py`
- `backend/tests/test_api/test_search.py`
- `backend/tests/test_api/test_auth.py`
- `backend/tests/test_services/test_storage_service.py`
- `backend/tests/test_services/test_embedding_service.py`
- All remaining files under `backend/tests/` containing `tenant`

- [ ] **Step 1: Generate the working list**

```bash
grep -rln "tenant" backend/tests 2>/dev/null > /tmp/test_remaining.txt
wc -l /tmp/test_remaining.txt
```

- [ ] **Step 2: Rewrite `conftest.py`**

Replace tenant fixtures with role fixtures:

```python
# BEFORE
@pytest.fixture
async def test_tenant(db):
    tenant = Tenant(name="test", ...)
    db.add(tenant)
    await db.commit()
    return tenant

@pytest.fixture
async def test_user(db, test_tenant):
    user = User(email="t@example.com", tenant_id=test_tenant.id, ...)
    ...
```

```python
# AFTER
@pytest.fixture
def test_user_profile():
    """A UserProfile equivalent that fixtures can pass into endpoint dependencies."""
    from app.core.auth.base import UserProfile
    return UserProfile(
        user_id="test-user-1",
        email="t@example.com",
        roles=["LEGAL", "EVERYONE"],
    )

@pytest.fixture
async def test_user(db):
    user = User(email="t@example.com", ...)  # NO tenant_id
    db.add(user)
    await db.commit()
    return user
```

- [ ] **Step 3: Rewrite `test_acl_security.py`**

This is the test file that exercises the ACL behavior. After the refactor, it must test:

1. A user with `LEGAL` role sees documents tagged `["LEGAL"]` and `["EVERYONE"]` but NOT documents tagged `["SALES"]`.
2. A user with no roles sees only documents tagged `["EVERYONE"]`.
3. The `EVERYONE` wildcard never appears in `UserProfile.roles` (defensive check).
4. `require_role("ADMIN")` returns 403 for non-admin users.

This file is the canonical test for the new ACL model — invest the effort to make it thorough.

- [ ] **Step 4: Refactor the remaining test files mechanically**

For each file in the working list:
- Replace `test_tenant` fixture usage with `test_user_profile`.
- Replace `headers={"X-Tenant-ID": ...}` with `headers={"X-User-Roles": "LEGAL,EVERYONE", "X-User-Id": "test-user-1"}`.
- Replace assertions on `tenant_id` with assertions on `roles`.

- [ ] **Step 5: Run the backend test suite**

```bash
cd backend/tests && ./run_tests.sh 2>&1 | tail -40
```

Expected: all tests green. If any test fails, fix it before proceeding. Failing tests are not acceptable in Phase B.

---

### Task A6: Refactor the microservice tests left over from Plan 3

**Files:**
- `backend/microservices/*/tests/**/*.py` containing `tenant`

- [ ] **Step 1: Generate the working list**

```bash
grep -rln "tenant" backend/microservices/*/tests 2>/dev/null > /tmp/microservice_tests_remaining.txt
wc -l /tmp/microservice_tests_remaining.txt
```

- [ ] **Step 2: Refactor each file**

Same patterns as Task A5 Step 4. The most likely hot spots are emma-agent-service tests that exercised the diagnostics endpoints — these now need the new headers.

- [ ] **Step 3: Run microservice tests**

```bash
for srv in emma-agent-service weaviate-service knowledge-tree-service intelligence-docs-service; do
  echo "=== $srv ==="
  cd backend/microservices/$srv && python -m pytest tests/ -x --no-header 2>&1 | tail -10
  cd - >/dev/null
done
```

Expected: all green.

---

### Task A7: Verify zero `tenant_id` references in the entire repo (excluding archived migrations)

**Files:** none (verification only)

- [ ] **Step 1: Scan everything**

```bash
grep -rln "tenant_id\|X-Tenant-ID\|_DEFAULT_TENANT" backend/ frontend/src 2>/dev/null \
  | grep -v "alembic/versions/_archived" \
  | grep -v "__pycache__" \
  | grep -v ".next" \
  | grep -v "node_modules"
```

Expected: zero matches. If any match remains, fix it before committing.

---

### Task A8: Commit Phase A (Commit 7)

**Files:** none (git operation)

- [ ] **Step 1: Stage all changes**

```bash
git add backend/microservices/emma-agent-service/app/api/diagnostics.py
git add backend/tests
git add backend/microservices/*/tests
```

- [ ] **Step 2: Verify the diff**

```bash
git status --short
git diff --stat HEAD | tail -10
```

- [ ] **Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
test: update fixtures and ACL assertions for nouxcube schema

Implements Commit 7 of the multi-tenancy removal refactor (Plan 5
Phase A).

- Rewrite emma-agent-service/app/api/diagnostics.py: drop the
  _DEFAULT_TENANT constant and refactor all 11 _check_* functions
  (_check_hybrid_search, _check_graph_query, _check_memorag,
  _check_smart_search ×4 variants, _check_graph_entity_query,
  _check_react_pipeline, _check_user_memory) to take user_roles and
  user_id instead of tenant_id. Endpoints read X-User-Roles and
  X-User-Id headers, defaulting to ['EVERYONE'] for local manual runs.
- Delete backend tests that exercise removed endpoints
  (test_tenants.py, test_document_shares.py, test_document_insights.py,
  test_teams.py, test_role_assignments.py if present).
- Rewrite backend/tests/conftest.py: drop tenant fixtures, add a
  test_user_profile fixture with roles=['LEGAL','EVERYONE'].
- Rewrite backend/tests/test_acl_security.py to test the role-based
  ACL model end-to-end (LEGAL sees LEGAL+EVERYONE, no roles sees only
  EVERYONE, EVERYONE never assigned to user, require_role 403).
- Update remaining backend tests and microservice tests to send
  X-User-Roles/X-User-Id headers and assert on roles instead of
  tenant_id.

The codebase now imports cleanly, all unit tests pass, and zero
references to tenant_id remain outside backend/alembic/versions/_archived/.
The actual database rebuild and the 12 smoke tests are deferred to
Phase B of this plan; doc updates are deferred to Phase C.

Spec: docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
Plan: docs/superpowers/plans/2026-04-06-remove-tenancy-05-validation-rebuild.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 4: Verify the commit**

```bash
git log -1 --stat | tail -20
```

---

## Phase B — Drop & Rebuild + Smoke Tests

> **WARNING:** Phase B executes destructive operations on the local Docker stack. The application database (`nexus_db`), Weaviate collections, FalkorDB graph, and Elasticsearch indices are dropped and rebuilt. Confirm with the user before proceeding. The Langfuse database is preserved.

### Task B1: Pre-rebuild snapshot

**Files:** none (operational)

- [ ] **Step 1: Confirm the user wants to proceed**

This is a destructive operation. Pause and confirm explicitly before continuing.

- [ ] **Step 2: Snapshot the current Langfuse prompt count**

```bash
cd backend/docker
docker compose exec db psql -U nexus_user -d langfuse -c "SELECT count(*) FROM prompts" 2>&1
```

Save the number. After rebuild, smoke test #2 verifies the same number is present.

- [ ] **Step 3: Snapshot the connector list (if any user-defined connectors exist)**

```bash
docker compose exec db psql -U nexus_user -d nexus_db -c \
  "SELECT id, name, type FROM connectors" 2>&1
```

Save to `/tmp/pre_rebuild_connectors.txt`. After rebuild, the user must recreate any custom connectors.

- [ ] **Step 4: Stop application services (NOT db, NOT keycloak, NOT langfuse)**

```bash
docker compose stop \
  api emma-agent-service knowledge-tree-service \
  weaviate-service intelligence-docs-service elasticsearch-service \
  background-worker emma-reactive-worker frontend
```

Expected: each container stops cleanly.

---

### Task B2: Drop the application database, create `nouxcube`

**Files:** none (operational)

- [ ] **Step 1: Drop nexus_db, create nouxcube**

```bash
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
```

Expected: no error. The `nouxcube` database now exists, empty, owned by `nexus_user`.

- [ ] **Step 2: Verify Langfuse is intact**

```bash
docker compose exec db psql -U nexus_user -d langfuse -c "SELECT count(*) FROM prompts"
```

Expected: same number as the pre-rebuild snapshot. If different, **stop and investigate** before proceeding.

---

### Task B3: Drop derived store volumes

**Files:** none (operational)

- [ ] **Step 1: Stop the derived stores**

```bash
docker compose stop weaviate falkordb elasticsearch redis
```

- [ ] **Step 2: Remove the volumes**

```bash
docker volume rm \
  docker_weaviate_data \
  docker_falkordb_data \
  docker_elasticsearch_data
```

If a volume name is different (check with `docker volume ls | grep docker_`), use the actual name.

Note: do NOT remove `docker_postgres_data` (that's the volume backing both `nouxcube` and `langfuse`). Do NOT remove the keycloak volume.

- [ ] **Step 3: Optional Redis flush**

Redis is ephemeral by design and Plan 3 changed the stream namespaces, so old keys are obsolete:

```bash
docker compose start redis
docker compose exec redis redis-cli FLUSHDB
```

---

### Task B4: Restart everything with the new code

**Files:** none (operational)

- [ ] **Step 1: Build and start**

```bash
docker compose up -d --build
```

This rebuilds every image that needs it and starts every service. Expect 5-15 minutes depending on cache state.

- [ ] **Step 2: Wait for the db to be healthy**

```bash
docker compose ps db
```

Expected: `Up (healthy)`. If not, `docker compose logs db | tail -30`.

- [ ] **Step 3: Apply the new schema**

```bash
docker compose exec api alembic upgrade head
```

Expected: a single migration is applied (the initial nouxcube schema from Plan 1). No errors.

- [ ] **Step 4: Run the seed script**

```bash
docker compose exec api python -m scripts.init_db
```

Expected: succeeds. The script validates that `role_mapping.yaml` exists (Plan 1 added that check).

---

### Task B5: Re-seed Langfuse prompts (if any new ones were added during the refactor)

**Files:** none (operational)

- [ ] **Step 1: Run the safe-by-default seed**

```bash
docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py
```

This only creates missing prompts (per CLAUDE.md). Existing prompts are untouched.

- [ ] **Step 2: Show the diff to confirm**

```bash
docker compose exec emma-agent-service python scripts/seed_langfuse_prompts.py --diff
```

Expected: zero or a small set of new prompts.

---

### Task B6: Re-ingest content (BOE + connectors)

**Files:** none (operational, long-running)

- [ ] **Step 1: Re-download the BOE corpus**

```bash
cd backend/docker && ./onboarding.sh boe
```

Expected: ~10 minutes. Downloads ~47 Spanish laws across 13 presets and indexes them into the new `PublicKnowledge` Weaviate collection (with `roles: ["EVERYONE"]`) and the legal graph.

- [ ] **Step 2: Re-create user-defined connectors**

For each connector in `/tmp/pre_rebuild_connectors.txt`, recreate it via the frontend or via curl. Each new connector must include `default_document_roles` (empty list defaults to `["EVERYONE"]`).

- [ ] **Step 3: Sync connectors**

```bash
./onboarding.sh sync-all
./onboarding.sh status
```

Expected: each connector reports `synced` after some time. The TrustGraph extraction runs in the background and may take 2-4 hours for a full corpus.

---

### Task B7: Run the 12 smoke tests

**Files:** none (operational, validation)

The spec defines 12 smoke tests in Section 3.C. Execute each one and record pass/fail.

- [ ] **Test 1: Postgres healthy**

```bash
docker compose exec db psql -U nexus_user -d nouxcube -c "\dt"
```

Pass: lists the new schema tables, no error.

- [ ] **Test 2: Langfuse intact**

```bash
docker compose exec db psql -U nexus_user -d langfuse -c "SELECT count(*) FROM prompts"
```

Pass: returns the same number as the pre-rebuild snapshot.

- [ ] **Test 3: Backend up**

```bash
curl -fsS http://localhost:8000/health
```

Pass: HTTP 200.

- [ ] **Test 4: Microservices up**

```bash
for port in 8009 8011 8007 8012 8008; do
  echo -n "port $port: "
  curl -fsS http://localhost:$port/health && echo
done
```

Pass: all return HTTP 200.

- [ ] **Test 5: KeyCloak login + JWT roles**

Manual: log in via the frontend with a user assigned to a KeyCloak group mapped to `LEGAL`. Open browser devtools, copy the JWT, and decode it (or use `jwt.io`). Pass: `realm_access.roles` contains the expected role names; the application's `UserProfile.roles` (visible in network tab as `X-User-Roles` on subsequent requests) is `["LEGAL", ...]`.

- [ ] **Test 6: Upload with role**

```bash
JWT=...  # paste your JWT from test 5
curl -fsS -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $JWT" \
  -F "file=@/tmp/sample.pdf" \
  -F 'roles=["LEGAL"]'
```

Pass: HTTP 200, response body contains `roles: ["LEGAL"]`.

- [ ] **Test 7: Role filtering**

Log in as a `SALES` user, list documents:

```bash
SALES_JWT=...
curl -fsS http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $SALES_JWT" | jq '.[] | {id, roles}'
```

Pass: the doc from test 6 (`roles: ["LEGAL"]`) is NOT in the list.

- [ ] **Test 8: EVERYONE wildcard**

Upload a doc with `roles: ["EVERYONE"]`. Query as any user. Pass: appears in every user's list.

- [ ] **Test 9: Connector default role**

Create a connector with `default_document_roles: ["SALES"]`, run sync. Pass: ingested docs in the database have `roles: ["SALES"]`.

```bash
docker compose exec db psql -U nexus_user -d nouxcube -c \
  "SELECT id, title, roles FROM documents ORDER BY created_at DESC LIMIT 5"
```

- [ ] **Test 10: Emma query filtering**

Log in as `LEGAL`, ask Emma "show me the contracts" via the frontend. Pass: the response only references docs accessible to `LEGAL` (no `SALES`-only docs leak in).

- [ ] **Test 11: TrustGraph filtering**

Issue a `graph_rag` query. Pass: the expanded subgraph only contains nodes whose `role` matches the user's roles or `EVERYONE`. Verify in the FalkorDB browser:

```bash
docker compose exec falkordb redis-cli GRAPH.QUERY knowledge_graph \
  "MATCH (n:Node) WHERE n.role IN ['LEGAL','EVERYONE'] RETURN count(n)"
```

- [ ] **Test 12: BOE re-indexed**

```bash
./onboarding.sh status
```

Pass: every law is `indexed`.

---

### Task B8: Run the diagnostics check (Test 13)

**Files:** none (operational, validation)

- [ ] **Step 1: Get a JWT for any user**

Log in via the frontend, copy the JWT.

- [ ] **Step 2: Call the diagnostics endpoint**

```bash
JWT=...
curl -fsS -X POST http://localhost:8009/diagnostics/run-all \
  -H "Authorization: Bearer $JWT" \
  -H "X-User-Roles: LEGAL,EVERYONE" \
  -H "X-User-Id: test-diagnostics" | jq '.'
```

- [ ] **Step 3: Verify every check returns `status: "ok"`**

Expected output shape:

```json
{
  "checks": {
    "hybrid_search": {"status": "ok", "hits": 12},
    "graph_query": {"status": "ok", ...},
    "memorag": {"status": "ok", ...},
    "smart_search": {"status": "ok", ...},
    "smart_search_temporal": {"status": "ok", ...},
    "smart_search_person": {"status": "ok", ...},
    "smart_search_legislation": {"status": "ok", ...},
    "graph_entity_query": {"status": "ok", ...},
    "react_pipeline": {"status": "ok", ...},
    "user_memory": {"status": "ok", ...}
  }
}
```

If ANY check returns a non-`ok` status, the rebuild is **considered failed**. Investigate the failing check, fix the underlying issue, and re-run from Task B7. Do not proceed to Phase C with failing diagnostics.

---

### Task B9: Mark Phase B complete

**Files:** none (verification only)

- [ ] **Step 1: Confirm all 13 tests passed**

Write down the result of each test. If any failed, do not proceed; investigate first.

- [ ] **Step 2: Confirm the system is operationally healthy**

```bash
docker compose ps
```

Expected: every service is `Up (healthy)` (or `Up` for services without a healthcheck).

- [ ] **Step 3: Note that no commit happens in Phase B**

Phase B is operational; the code already matches the running state from Commit 7.

---

## Phase C — Documentation, Commit 8

### Task C1: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

`CLAUDE.md` is the document that the next session reads to understand the architecture (per acceptance criterion #5 of the spec). It must accurately reflect the post-refactor state.

- [ ] **Step 1: Find the multi-tenancy section**

```bash
grep -n -i "tenant\|multi-tenan" CLAUDE.md
```

- [ ] **Step 2: Replace the multi-tenancy description with the role-based ACL description**

Add a new section "Single-Tenant + Claims-Based RBAC" that documents:

- One deployment = one organization. No tenant table, no `tenant_id`.
- Authentication: KeyCloak OIDC. The JWT carries `realm_access.roles` (a list of KeyCloak role names).
- The `map_groups_to_roles()` function in `backend/app/core/auth/base.py` translates KeyCloak group names to canonical English role identifiers (`SALES`, `LEGAL`, etc.) via `backend/app/config/role_mapping.yaml`.
- Documents have a `roles: ARRAY(String)` column. The wildcard `EVERYONE` means "any authenticated user".
- Connectors have a `default_document_roles: ARRAY(String)` column. When the connector ingests a document, those roles are copied to the document's `roles` field.
- The universal query filter is `app/core/auth/acl.py::filter_visible_to_user(query, user)`, which expands to `WHERE roles && user_roles OR roles && ['EVERYONE']`.
- Inter-service HTTP calls propagate `X-User-Id` and `X-User-Roles` headers.
- TrustGraph nodes carry a `role` property (renamed from `user`). Multi-role queries dedupe at the application layer.

- [ ] **Step 3: Update the database name everywhere**

```bash
grep -n "nexus_db" CLAUDE.md
```

Replace every match with `nouxcube`.

- [ ] **Step 4: Update the troubleshooting / development commands sections**

If any example uses `tenant_id` or `X-Tenant-ID`, replace with the role-based equivalents.

- [ ] **Step 5: Verify the file is internally consistent**

Read the whole file once. Confirm there are no leftover references to deleted concepts (tenants, role assignments tables, document shares, team invitations, sharing insights, local roles table).

---

### Task C2: Update `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Find tenant references**

```bash
grep -n -i "tenant\|nexus_db" README.md
```

- [ ] **Step 2: Update the database name**

Replace `nexus_db` with `nouxcube`.

- [ ] **Step 3: Update the architecture diagram / overview**

If the README has an architecture section that mentions multi-tenancy, replace it with a single-tenant + role-based ACL summary (one paragraph is enough — the full documentation lives in CLAUDE.md and the spec).

---

### Task C3: Update on-premise docs

**Files:**
- `docs/on-premise/AUTHENTICATION.md`
- `docs/on-premise/ONBOARDING.md`
- `docs/on-premise/CONNECTORS.md`

- [ ] **Step 1: Update `AUTHENTICATION.md`**

```bash
grep -n "tenant" docs/on-premise/AUTHENTICATION.md
```

Add a section explaining how to:
1. Create KeyCloak groups (`/Comercial`, `/Departamento Legal`, `/Recursos Humanos`, etc.).
2. Edit `backend/app/config/role_mapping.yaml` to map each group to a canonical role (`SALES`, `LEGAL`, `HR`, ...).
3. Assign users to groups in the KeyCloak admin UI.
4. Verify the JWT contains the expected role list after login.

Remove references to the deleted local roles table and per-tenant auth configs.

- [ ] **Step 2: Update `ONBOARDING.md`**

Remove the "create tenant" steps. Add the "configure role_mapping.yaml" step. Update any database name references.

- [ ] **Step 3: Update `CONNECTORS.md`**

Add documentation for the `default_document_roles` field in connector creation. Explain that it defaults to `["EVERYONE"]` if omitted.

---

### Task C4: Update architecture docs

**Files:**
- `docs/architecture/ACL_SYSTEM.md` (if exists, update; otherwise create)
- `docs/architecture/EMMA_REACTIVE.md`
- `docs/architecture/MODULAR_ARCHITECTURE.md`
- `docs/architecture/RAG_PIPELINE.md`
- `docs/architecture/PROMPT_MANAGEMENT.md` (if it mentions tenant scoping)
- `docs/architecture/PUBLIC_KNOWLEDGE.md` (PublicKnowledge always uses `EVERYONE`)

- [ ] **Step 1: For each file, find and remove tenant references**

```bash
for f in docs/architecture/*.md; do
  echo "=== $f ==="
  grep -n -i "tenant" "$f" | head
done
```

- [ ] **Step 2: Update each file**

Replace tenant scoping descriptions with role-based ACL descriptions. Diagrams that show `tenant_id` flowing through the pipeline should now show `user_roles`.

- [ ] **Step 3: For `ACL_SYSTEM.md`, write the canonical reference doc**

This document is the long-form companion to the spec. It should cover:
- The data model (`Document.roles`, `Connector.default_document_roles`, KeyCloak source-of-truth)
- The query helper (`filter_visible_to_user`)
- The role propagation across microservices (`X-User-Id`, `X-User-Roles`)
- The TrustGraph `role` property and multi-role dedup
- The Weaviate filter
- The wildcards and reserved literals
- A debugging cheatsheet (how to inspect a user's effective roles, how to check what a document's roles are, etc.)

If `ACL_SYSTEM.md` doesn't exist, create it.

---

### Task C5: Final repo-wide doc verification

**Files:** none (verification only)

- [ ] **Step 1: Confirm zero stale references in docs**

```bash
grep -rln -i "tenant_id\|nexus_db\|multi-tenan" docs/ CLAUDE.md README.md 2>/dev/null \
  | grep -v "docs/superpowers/specs/2026-04-06-remove-multi-tenancy" \
  | grep -v "docs/superpowers/plans/2026-04-06-remove-tenancy"
```

The spec and plan files themselves are allowed to mention these (they're the historical record). Everything else should be clean.

---

### Task C6: Commit Phase C (Commit 8)

**Files:** none (git operation)

- [ ] **Step 1: Stage doc changes**

```bash
git add CLAUDE.md README.md docs/
```

- [ ] **Step 2: Commit**

```bash
git commit -m "$(cat <<'EOF'
docs: reflect single-tenant + claims-based RBAC

Implements Commit 8 of the multi-tenancy removal refactor (Plan 5
Phase C).

- Rewrite the multi-tenancy section of CLAUDE.md as a Single-Tenant +
  Claims-Based RBAC section. Documents the role-based ACL model, the
  KeyCloak indirection via role_mapping.yaml, the universal query
  filter, the TrustGraph role property rename, and the inter-service
  X-User-Id / X-User-Roles header propagation.
- Update README.md: nouxcube database name, brief architecture summary
  reflecting single-tenant deployment.
- Update docs/on-premise/AUTHENTICATION.md with KeyCloak group creation
  and role mapping instructions. Remove the deleted local roles table
  references.
- Update docs/on-premise/ONBOARDING.md: remove tenant creation steps,
  add role_mapping.yaml configuration step.
- Update docs/on-premise/CONNECTORS.md with the default_document_roles
  field documentation.
- Update docs/architecture/{EMMA_REACTIVE,MODULAR_ARCHITECTURE,
  RAG_PIPELINE,PROMPT_MANAGEMENT,PUBLIC_KNOWLEDGE}.md to reflect the
  new ACL flow.
- Create (or rewrite) docs/architecture/ACL_SYSTEM.md as the canonical
  long-form reference for the role-based ACL: data model, query helper,
  role propagation, TrustGraph schema, wildcards, debugging cheatsheet.

This commit completes the multi-tenancy removal refactor. The branch
refactor/remove-multi-tenancy is ready to merge into development.

Spec: docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
Plan: docs/superpowers/plans/2026-04-06-remove-tenancy-05-validation-rebuild.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 3: Verify the commit**

```bash
git log -1 --stat | tail -20
```

---

## Task Final: Self-check before merge

**Files:** none (verification only)

- [ ] **Step 1: Confirm the 8 commits are present**

```bash
git log --oneline development..HEAD
```

Expected: 8 (or 9 if you needed an extra fix-up) commits matching the 8 from the spec — the 4 plan commits, the docs commits at the end, plus any spec/plan documentation commits that came earlier.

- [ ] **Step 2: Confirm zero residual `tenant_id` outside archived migrations**

```bash
grep -rln "tenant_id\|X-Tenant-ID\|_DEFAULT_TENANT" backend/ frontend/src docs/ CLAUDE.md README.md 2>/dev/null \
  | grep -v "alembic/versions/_archived" \
  | grep -v "__pycache__" \
  | grep -v ".next" \
  | grep -v "node_modules" \
  | grep -v "docs/superpowers/specs/2026-04-06-remove-multi-tenancy" \
  | grep -v "docs/superpowers/plans/2026-04-06-remove-tenancy"
```

Expected: zero matches.

- [ ] **Step 3: Confirm 13 smoke tests are documented as passed**

Refer to the result table from Tasks B7 + B8. Every entry must be `PASS`.

- [ ] **Step 4: Confirm `CLAUDE.md` is internally consistent**

Read the file once start-to-finish. The next agent that opens this repo should be able to understand the architecture from CLAUDE.md alone, without needing to consult this plan or the spec.

- [ ] **Step 5: Acceptance criteria from the spec**

| Criterion | Status |
|---|---|
| All 8 commits merged to `development` (or ready to merge) | ☐ |
| The 12 smoke tests + the diagnostics check pass on a fresh stack | ☐ |
| `CLAUDE.md` accurately reflects the new architecture | ☐ |
| The branch `refactor/remove-multi-tenancy` is deleted (after merge) | ☐ |
| The next session starting from `development` can read `CLAUDE.md` and have a complete picture without consulting this spec | ☐ |

Tick each box only when the criterion is genuinely met. If anything is unticked, do not declare the refactor complete.

- [ ] **Step 6: Hand off**

The refactor is complete. The branch is ready to be merged into `development` via PR. The PR description should reference the spec and the 5 plans.

Suggested PR title:

```
refactor: remove multi-tenancy + claims-based RBAC
```

Suggested PR body (skeleton):

```
Implements docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
across 5 plans (8 commits).

## Summary
- Drops 12 tenant-related tables and the entire multi-tenant abstraction layer.
- Replaces tenant scoping with role-based ACL backed by KeyCloak JWT roles.
- Renames database nexus_db → nouxcube (langfuse preserved).
- Adds Document.roles[] and Connector.default_document_roles[] columns with GIN index.
- Renames FalkorDB :Node/:Literal/:Rel `user` property → `role`.
- Updates all microservices, frontend, tests, and docs.

## Validation
All 12 smoke tests + the diagnostics check passed on a freshly rebuilt
stack (see Plan 5 Phase B Tasks B7-B8).

## Plans
- Plan 1: Foundation (DB rename + ACL helpers + schema) — commit XXXX
- Plan 2: Backend API refactor — commit YYYY
- Plan 3: Microservices refactor — commit ZZZZ
- Plan 4: Frontend refactor — commit AAAA
- Plan 5 Phase A: Diagnostics + tests — commit BBBB
- Plan 5 Phase C: Docs — commit CCCC
```
