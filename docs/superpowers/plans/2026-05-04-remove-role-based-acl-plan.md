# Remove role-based ACL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomically remove role-based document ACL across the entire stack (PostgreSQL columns, Weaviate property, KTS Cypher property, EVERYONE sentinel, 8 duplicated `auth_headers.py` modules, frontend ACL service, role-overlap filters at every layer) in a single PR with 6 sequential commits, consolidating authorization onto `User.is_superuser` for admin gating while keeping KeyCloak authentication and informational `UserProfile.roles` propagation untouched.

**Architecture:** Six sequential commits in one PR, ordered consumers-before-producers, producers-before-schemas: (1) frontend cleanup, (2) backend service layer, (3) microservices, (4) Pydantic schema breaking change with `extra='forbid'`, (5) Alembic + Weaviate blue/green + FalkorDB cleanup scripts (irreversible migrations), (6) docs. Each phase leaves the system functional. Pre-flight checks gate the merge; post-merge ops runbook handles the customer-deployment migration window.

**Tech Stack:** Python 3.9+ FastAPI backend, SQLAlchemy + Alembic, Pydantic v2, PostgreSQL 15, Weaviate v4 client, FalkorDB (Cypher), Next.js 15 + TypeScript frontend, KeyCloak (OIDC/SAML), pytest.

**Spec reference:** `docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md` (commit `6def310a`).

**Branch strategy:** Implement on a feature branch named `refactor/remove-role-based-acl` off `development`. Open PR against `development`. Each phase below = one commit on the branch.

---

## File Structure

This plan modifies files in 5 layers; each layer maps to a phase below.

| Layer | Files modified | Files deleted | Files created |
|---|---|---|---|
| Frontend | `frontend/src/contexts/auth-context.tsx`, `auth/types.ts`, `lib/services/auth.service.ts`, `components/auth/admin-guard.tsx` (verify only) | `frontend/src/lib/services/document-acl.service.ts` | — |
| Backend service/api | 7 API endpoint files in `app/api/v1/`, `services/document_service.py`, `services/async_document_service.py`, `services/search_service.py`, `services/elasticsearch_client.py`, `app/api/dependencies.py`, `app/api/async_dependencies.py` | `app/core/auth/acl.py`, `backend/tests/test_acl.py` | `app/core/auth/superuser.py` (extracted dependency) |
| Microservices | `weaviate_service.py`, `rag/indexing_pipeline.py`, `core/execution_context.py`, KTS `api/triples.py`, `api/extract.py`, `api/reports.py`, `services/triple_store.py`, `services/triple_query.py`, KTS scripts, MCP `sync_service.py` | 8 copies of `auth_headers.py` (or stripped to empty) | — |
| Pydantic schemas | `app/schemas/document.py`, `app/schemas/connector.py`, `app/schemas/unified_document.py` | — | — |
| DB migrations | `app/db/models.py` (column removal) | — | `backend/alembic/versions/<rev>_drop_role_acl_columns.py`, `backend/scripts/weaviate_drop_roles_property.py`, `backend/scripts/kts_remove_user_property.py` |
| Docs | `CLAUDE.md`, `app/db/models.py` (docstrings only), `triple_query.py:7`, `weaviate_service.py:4-7`, `docs/on-premise/ONBOARDING.md` | — | — |

---

## Phase 0: Pre-flight verification (NO commit)

**Goal:** Confirm no production deployment uses role-restriction. If any check returns >0, halt and consult user before proceeding.

### Task 0.1: SQL pre-flight check

**Files:**
- Run against the deployment's PostgreSQL.

- [ ] **Step 1: Run the count query**

```bash
docker compose -f backend/docker/docker-compose.yml exec db psql -U nexus_user -d nexus_db -c "SELECT 'documents' AS tbl, COUNT(*) AS role_restricted_docs FROM documents WHERE NOT 'EVERYONE' = ANY(roles) UNION ALL SELECT 'indexed_documents', COUNT(*) FROM indexed_documents WHERE NOT 'EVERYONE' = ANY(roles);"
```

Expected: both counts = 0. If either > 0, **HALT** and consult user.

### Task 0.2: FalkorDB Cypher pre-flight check

**Files:**
- Run against the deployment's FalkorDB.

- [ ] **Step 1: Run the count query**

```bash
redis-cli -p 6380 GRAPH.QUERY knowledge_graph "MATCH (n) WHERE n.user IS NOT NULL AND n.user <> 'EVERYONE' RETURN count(n) AS non_everyone_nodes"
redis-cli -p 6380 GRAPH.QUERY knowledge_graph "MATCH ()-[r]-() WHERE r.user IS NOT NULL AND r.user <> 'EVERYONE' RETURN count(r) AS non_everyone_rels"
```

Expected: both counts = 0. If either > 0, **HALT** and consult user.

### Task 0.3: Weaviate pre-flight check

**Files:**
- Create temporary script: `backend/scripts/preflight_weaviate_roles_check.py`

- [ ] **Step 1: Write the check script**

```python
# backend/scripts/preflight_weaviate_roles_check.py
import os
import weaviate

COLLECTIONS = ["Nouxcube_documents", "Nouxcube_documents_summaries",
               "Nouxcube_knowledge", "Nouxcube_visual",
               "TrustGraphEntities", "OntologyTerms"]

client = weaviate.connect_to_local(
    host=os.environ.get("WEAVIATE_HOST", "localhost"),
    port=int(os.environ.get("WEAVIATE_PORT", "8080")),
)
try:
    for col_name in COLLECTIONS:
        col = client.collections.get(col_name)
        role_restricted = sum(
            1 for obj in col.iterator(return_properties=["roles"])
            if "EVERYONE" not in (obj.properties.get("roles") or [])
        )
        print(f"{col_name}: {role_restricted} role-restricted objects")
finally:
    client.close()
```

- [ ] **Step 2: Run the check**

```bash
python backend/scripts/preflight_weaviate_roles_check.py
```

Expected: every collection prints `0 role-restricted objects`. If any > 0, **HALT** and consult user.

- [ ] **Step 3: Delete the temporary script** (it lives only for pre-flight; the production migration script comes later)

```bash
rm backend/scripts/preflight_weaviate_roles_check.py
```

---

## Phase 1: Frontend cleanup → Commit 1

**Goal:** Remove the frontend role-ACL surface. Backend still serves `roles` (now ignored client-side).

**Branch setup:**

- [ ] **Pre-task: Create feature branch**

```bash
git checkout -b refactor/remove-role-based-acl
```

### Task 1.1: Verify no callers of document-acl.service

- [ ] **Step 1: List all callers**

```bash
grep -rn "from '@/lib/services/document-acl" frontend/src/ || echo "no callers"
grep -rn "DocumentACLService\|documentAclService" frontend/src/ || echo "no usages"
```

Expected: zero callers. If callers exist, fix them in Tasks 1.3-1.5 below.

### Task 1.2: Delete `document-acl.service.ts`

- [ ] **Step 1: Delete the file**

```bash
rm frontend/src/lib/services/document-acl.service.ts
```

- [ ] **Step 2: Run TypeScript compiler to surface broken imports**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. If errors mention missing `document-acl` imports, fix the importing files in Tasks 1.3-1.5.

### Task 1.3: Audit and clean `auth-context.tsx`

- [ ] **Step 1: Find role-based gates**

```bash
grep -n "roles\|hasRole\|userRoles\|EVERYONE" frontend/src/contexts/auth-context.tsx
```

- [ ] **Step 2: For each match, decide**
  - Feature gate based on KeyCloak roles → remove the gate (allow all authenticated users); route admin paths through `is_superuser`.
  - Setting `userProfile.roles` from JWT claims for display → KEEP. Stays as informational metadata per spec.

- [ ] **Step 3: Apply edits inline** (exact code depends on findings)

- [ ] **Step 4: Verify TypeScript compilation**

```bash
cd frontend && npx tsc --noEmit
```

### Task 1.4: Audit and clean `auth/types.ts`

- [ ] **Step 1: Find role types used for gating**

```bash
grep -n "roles\|Role\|EVERYONE\|hasPermission\|canAccess" frontend/src/contexts/auth/types.ts
```

- [ ] **Step 2: For each match, decide**
  - TypeScript type for `User.roles` (informational) → KEEP.
  - Function signature or union type that gates behavior on roles → DELETE.

- [ ] **Step 3: Apply edits inline**

- [ ] **Step 4: Verify TypeScript compilation**

```bash
cd frontend && npx tsc --noEmit
```

### Task 1.5: Audit and clean `auth.service.ts`

- [ ] **Step 1: Find role-based JWT consumption**

```bash
grep -n "roles\|hasRole\|extractRoles\|EVERYONE" frontend/src/lib/services/auth.service.ts
```

- [ ] **Step 2: For each match, decide**
  - JWT `realm_access.roles` extracted into `userProfile.roles` for display → KEEP.
  - `roles` consumed for client-side request filtering or feature gating → DELETE.

- [ ] **Step 3: Apply edits inline**

- [ ] **Step 4: Verify TypeScript compilation**

```bash
cd frontend && npx tsc --noEmit
```

### Task 1.6: Verify `admin-guard.tsx` uses `is_superuser` only

- [ ] **Step 1: Inspect the gate**

```bash
grep -n "is_superuser\|isSuperuser\|isAdmin\|roles\|hasRole" frontend/src/components/auth/admin-guard.tsx
cat frontend/src/components/auth/admin-guard.tsx
```

- [ ] **Step 2: Confirm the gate uses `is_superuser` only**
  - If it does: no edits needed.
  - If it derives admin status from `roles` (e.g., `user.roles.includes('ADMIN')`): rewrite to `user.is_superuser === true`.

### Task 1.7: Run frontend lint + type-check + build

- [ ] **Step 1: Lint**

```bash
cd frontend && npm run lint
```

Expected: clean.

- [ ] **Step 2: TypeScript check (no emit)**

```bash
cd frontend && npx tsc --noEmit
```

Expected: zero errors.

- [ ] **Step 3: Production build**

```bash
cd frontend && npm run build
```

Expected: build succeeds.

### Task 1.8: Commit Phase 1

- [ ] **Step 1: Stage frontend changes**

```bash
git add frontend/src/lib/services/document-acl.service.ts frontend/src/contexts/auth-context.tsx frontend/src/contexts/auth/types.ts frontend/src/lib/services/auth.service.ts frontend/src/components/auth/admin-guard.tsx
```

- [ ] **Step 2: Verify diff is what you expect**

```bash
git diff --cached --stat
```

- [ ] **Step 3: Create commit**

```bash
git commit -m "$(cat <<'EOF'
chore(frontend): remove role-based ACL surface

Delete document-acl.service.ts (259 LOC of permission grant/revoke
machinery never wired to live ACL backend). Audit auth-context,
auth/types, auth.service and remove role-based feature gates;
preserve UserProfile.roles propagation as informational metadata
(displayed in /auth/me but not consumed for filtering). Verify
admin-guard uses is_superuser only.

Backend still serves the roles field at this commit; later phases
remove it. Frontend tolerates extra response fields, so this commit
is forward-compatible with the remaining phases.

Refs: docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2: Backend service layer → Commit 2

**Goal:** Stop reading `roles` from PostgreSQL across all API endpoints and services. Data still has the column populated; we simply ignore it.

### Task 2.1: Audit imports of `app.core.auth.acl`

- [ ] **Step 1: List all importers**

```bash
grep -rn "from app.core.auth.acl\|from \.acl\|import acl" backend/ | grep -v __pycache__ > /tmp/acl_importers.txt
cat /tmp/acl_importers.txt
```

This list drives Tasks 2.4-2.16 (which files need their imports cleaned up).

### Task 2.2: Create `app/core/auth/superuser.py` with the simplified dependency

- [ ] **Step 1: Verify import path for `get_current_user`**

```bash
grep -rn "def get_current_user" backend/app/core/auth/
```

- [ ] **Step 2: Write the new module** (adjust the import line to match)

```python
# backend/app/core/auth/superuser.py
"""Authorization dependency for admin-gated endpoints.

The single surviving authz dimension after the role-based ACL removal.
Set User.is_superuser=True via the manual PATCH /users/{id}/role flow.
"""
from fastapi import Depends, HTTPException, status

from app.core.auth.dependencies import get_current_user
from app.db.models import User


def require_superuser(user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency that 403s non-superuser callers."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return user
```

### Task 2.3: Update all callers of `require_role` → `require_superuser`

- [ ] **Step 1: List callers**

```bash
grep -rn "require_role\b" backend/ | grep -v __pycache__ | grep -v "core/auth/acl.py"
```

- [ ] **Step 2: For each match, replace**

Pattern to replace:
```python
from app.core.auth.acl import require_role
# ...
@router.get("/admin/foo", dependencies=[Depends(require_role("ADMIN"))])
```

With:
```python
from app.core.auth.superuser import require_superuser
# ...
@router.get("/admin/foo", dependencies=[Depends(require_superuser)])
```

Note: `require_superuser` is referenced **without** parentheses (plain dependency, no factory).

- [ ] **Step 3: Verify no `require_role(` references remain (except in the soon-to-be-deleted `acl.py`)**

```bash
grep -rn "require_role(" backend/ | grep -v __pycache__ | grep -v "core/auth/acl.py"
```

Expected: zero output.

### Task 2.4: Remove `filter_visible_to_user()` calls in `documents.py`

**Files:**
- Modify: `backend/app/api/v1/documents.py:53,93,267,964`

- [ ] **Step 1: Inspect**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE\|build_role_filter_clause" backend/app/api/v1/documents.py
```

- [ ] **Step 2: For each call, remove the filter**

Pattern to find:
```python
from app.core.auth.acl import filter_visible_to_user
# ...
query = select(Document).where(...)
query = filter_visible_to_user(query, user)  # ← remove this line
result = await db.execute(query)
```

Replace with:
```python
query = select(Document).where(...)
result = await db.execute(query)
```

If the surrounding endpoint had ownership semantics, replace `filter_visible_to_user(query, user)` with `query.where(Document.owner_id == user.id)` UNLESS the endpoint should be visible to all authenticated users (the new default).

- [ ] **Step 3: Remove the import**

```python
from app.core.auth.acl import filter_visible_to_user  # ← delete
```

- [ ] **Step 4: Run the documents endpoint tests**

```bash
cd backend/tests && pytest -k documents -v
```

Expected: pass (or fail for tests that asserted role-filter behavior — those tests are addressed in Task 2.16).

### Task 2.5: Remove `filter_visible_to_user()` calls in `document_categorization.py`

**Files:**
- Modify: `backend/app/api/v1/document_categorization.py:73,400,438`

- [ ] **Step 1: Apply the same pattern as Task 2.4**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE" backend/app/api/v1/document_categorization.py
```

For each call site:
- Remove `filter_visible_to_user(query, user)` line
- Remove the import if no longer used
- If ownership-restricted, substitute `query.where(Document.owner_id == user.id)`

- [ ] **Step 2: Run categorization tests**

```bash
cd backend/tests && pytest -k categorization -v
```

### Task 2.6: Remove `filter_visible_to_user()` calls in `analysis_queue.py`

**Files:**
- Modify: `backend/app/api/v1/analysis_queue.py:53,135,460`

- [ ] **Step 1: Apply the Task 2.4 pattern**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE" backend/app/api/v1/analysis_queue.py
```

Remove `filter_visible_to_user(query, user)` lines + imports.

- [ ] **Step 2: Run analysis queue tests**

```bash
cd backend/tests && pytest -k analysis -v
```

### Task 2.7: Remove `filter_visible_to_user()` calls in `classification.py`

**Files:**
- Modify: `backend/app/api/v1/classification.py:303`

- [ ] **Step 1: Apply the Task 2.4 pattern**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE" backend/app/api/v1/classification.py
```

Remove + clean imports.

- [ ] **Step 2: Run classification tests**

```bash
cd backend/tests && pytest -k classification -v
```

### Task 2.8: Remove `filter_visible_to_user()` calls in `document_insights.py`

**Files:**
- Modify: `backend/app/api/v1/document_insights.py:36`

- [ ] **Step 1: Apply the Task 2.4 pattern**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE" backend/app/api/v1/document_insights.py
```

Remove + clean imports.

- [ ] **Step 2: Run insights tests**

```bash
cd backend/tests && pytest -k insights -v
```

### Task 2.9: Remove `filter_visible_to_user()` calls in `entities.py`

**Files:**
- Modify: `backend/app/api/v1/entities.py:42,177`

- [ ] **Step 1: Apply the Task 2.4 pattern**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE" backend/app/api/v1/entities.py
```

Remove + clean imports.

- [ ] **Step 2: Run entities tests**

```bash
cd backend/tests && pytest -k entities -v
```

### Task 2.10: Remove `filter_visible_to_user()` calls in `notebooks.py`

**Files:**
- Modify: `backend/app/api/v1/notebooks.py:679`

- [ ] **Step 1: Apply the Task 2.4 pattern**

```bash
grep -n "filter_visible_to_user\|EVERYONE_ROLE" backend/app/api/v1/notebooks.py
```

Remove + clean imports.

- [ ] **Step 2: Run notebooks tests**

```bash
cd backend/tests && pytest -k notebooks -v
```

### Task 2.11: Gut `can_access_document()` in `document_service.py`

**Files:**
- Modify: `backend/app/services/document_service.py:13,37,63,127`

- [ ] **Step 1: Inspect**

```bash
grep -n "can_access_document\|EVERYONE_ROLE\|user_roles" backend/app/services/document_service.py
```

- [ ] **Step 2: Replace `can_access_document` body**

Find:
```python
def can_access_document(doc: Document, user: User) -> bool:
    if EVERYONE_ROLE in doc.roles:
        return True
    if any(role in user.roles for role in doc.roles):
        return True
    return False
```

Replace with:
```python
def can_access_document(doc: Document, user: User) -> bool:
    """Authorization check post role-based ACL removal.

    Single-tenant on-premise: every authenticated user can access every document.
    Returns True unconditionally; preserved as a hook for future ownership checks.
    """
    return True
```

Or, if the codebase prefers, delete the function entirely and remove all callers (verify with `grep -rn can_access_document backend/`).

- [ ] **Step 3: Remove the `EVERYONE_ROLE` import + `user_roles` extraction**

Remove lines that import `EVERYONE_ROLE` from `core.auth.acl` and any line that extracts `user_roles = list(user.roles)` for use in the role check.

- [ ] **Step 4: Remove default role assignment**

Find any line setting `roles=[EVERYONE_ROLE]` on Document creation. Drop it (the column itself is dropped in Phase 5).

- [ ] **Step 5: Run service tests**

```bash
cd backend/tests && pytest -k document_service -v
```

### Task 2.12: Remove role filter clauses in `async_document_service.py`

**Files:**
- Modify: `backend/app/services/async_document_service.py:461-466,976,1212-1217,1260-1265,1662-1668`

- [ ] **Step 1: Inspect**

```bash
grep -n "IndexedDocument.roles\|EVERYONE_ROLE\|allowed_roles\|roles.contains\|roles.overlap" backend/app/services/async_document_service.py
```

- [ ] **Step 2: Apply the same pattern at each filter clause**

Find:
```python
indexed_base_filters = [IndexedDocument.roles.contains([EVERYONE_ROLE])]
if self.user_roles:
    indexed_base_filters = [
        or_(
            IndexedDocument.roles.contains([EVERYONE_ROLE]),
            IndexedDocument.roles.overlap(list(self.user_roles)),
        )
    ]
```

Replace with empty (drop the filter):
```python
indexed_base_filters = []
```

Then either remove `indexed_base_filters` entirely (if no callers use it) or leave the empty list as a no-op for downstream `query.where(*indexed_base_filters)` callers.

- [ ] **Step 3: Drop `self.user_roles` member if no longer used**

```bash
grep -n "self.user_roles\|user_roles=" backend/app/services/async_document_service.py
```

Remove the `user_roles` parameter from `__init__` and any usage if zero remaining references.

- [ ] **Step 4: Drop the `EVERYONE_ROLE` import**

- [ ] **Step 5: Run async document service tests**

```bash
cd backend/tests && pytest -k async_document -v
```

### Task 2.13: Drop `role_ids` in `search_service.py` and `elasticsearch_client.py`

**Files:**
- Modify: `backend/app/services/search_service.py:37`
- Modify: `backend/app/services/elasticsearch_client.py:130-131`

- [ ] **Step 1: search_service.py**

```bash
grep -n "role_ids\|user.roles" backend/app/services/search_service.py
```

Find:
```python
self.role_ids = role_ids or (list(user.roles) if user else [])
```

Delete the line. Remove `role_ids` parameter from `__init__` and any usage.

- [ ] **Step 2: elasticsearch_client.py**

```bash
grep -n "self.roles\|role" backend/app/services/elasticsearch_client.py
```

Find lines 130-131 (role member init). Delete.

- [ ] **Step 3: Run search tests**

```bash
cd backend/tests && pytest -k search -v
```

### Task 2.14: Drop `["ADMIN"] if is_superuser` synthesis in dependencies

**Files:**
- Modify: `backend/app/api/dependencies.py:45`
- Modify: `backend/app/api/async_dependencies.py:59-62`

- [ ] **Step 1: Inspect**

```bash
grep -n "ADMIN\|is_superuser\|roles =" backend/app/api/dependencies.py backend/app/api/async_dependencies.py
```

- [ ] **Step 2: Find the synthesis**

```python
# Pattern, e.g.:
roles = ["ADMIN"] if user.is_superuser else []
```

This synthesizes a role list from `is_superuser` for downstream code that expected a roles list. Now redundant.

- [ ] **Step 3: Delete the synthesis line**

If downstream code consumed `roles`, replace with explicit `is_superuser` checks at those call sites.

- [ ] **Step 4: Run dependency tests**

```bash
cd backend/tests && pytest -k dependencies -v
```

### Task 2.15: Delete `app/core/auth/acl.py`

- [ ] **Step 1: Confirm no remaining importers (other than test_acl.py and superuser.py)**

```bash
grep -rn "from app.core.auth.acl\|from \.acl" backend/ | grep -v __pycache__
```

Expected: only `backend/tests/test_acl.py` (which dies in Task 2.16). `superuser.py` does NOT import from `acl.py`.

- [ ] **Step 2: Delete the file**

```bash
rm backend/app/core/auth/acl.py
```

- [ ] **Step 3: Run import smoke**

```bash
cd backend && python -c "from app.main import app; print('imports OK')"
```

Expected: `imports OK`. If `ImportError`, an importer was missed in earlier tasks.

### Task 2.16: Delete `backend/tests/test_acl.py`

- [ ] **Step 1: Delete the file**

```bash
rm backend/tests/test_acl.py
```

- [ ] **Step 2: Run full backend test suite**

```bash
cd backend/tests && ./run_tests.sh
```

Expected: all tests pass. If any test fails because it imports symbols from `app.core.auth.acl` (e.g., `EVERYONE_ROLE`, `filter_visible_to_user`), edit that test to remove the import and any role-filter assertions. Fixtures that set `user.roles` for ACL behavior should be simplified to just authenticate the user.

### Task 2.17: Commit Phase 2

- [ ] **Step 1: Stage backend changes**

```bash
git add backend/app/api/v1/documents.py backend/app/api/v1/document_categorization.py backend/app/api/v1/analysis_queue.py backend/app/api/v1/classification.py backend/app/api/v1/document_insights.py backend/app/api/v1/entities.py backend/app/api/v1/notebooks.py backend/app/services/document_service.py backend/app/services/async_document_service.py backend/app/services/search_service.py backend/app/services/elasticsearch_client.py backend/app/api/dependencies.py backend/app/api/async_dependencies.py backend/app/core/auth/superuser.py backend/app/core/auth/acl.py backend/tests/test_acl.py
```

- [ ] **Step 2: Verify diff stat**

```bash
git diff --cached --stat
```

- [ ] **Step 3: Create commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(backend): drop role-based document filtering

Remove the 15 filter_visible_to_user() call sites across api/v1/
endpoints (documents, document_categorization, analysis_queue,
classification, document_insights, entities, notebooks). Gut
can_access_document() in document_service. Drop 11+ role-overlap
filter clauses in async_document_service. Drop role_ids from
search_service and elasticsearch_client. Drop the ["ADMIN"] if
is_superuser synthesis in dependencies.

Extract require_role -> require_superuser to a new
app/core/auth/superuser.py module (simplified to is_superuser=True
check, no role list). Delete app/core/auth/acl.py entirely
(EVERYONE_ROLE, build_role_filter_clause, filter_visible_to_user
all gone). Delete backend/tests/test_acl.py (8 tests).

System still has roles columns in PostgreSQL with EVERYONE values;
they are no longer read. Schemas and column drops follow in later
phases.

Refs: docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3: Microservices → Commit 3

**Goal:** Drop role plumbing across all 8 microservices: 8 copies of `auth_headers.py`, weaviate-service `_roles_filter`, KTS Cypher `user` property, MCP role propagation. Existing data in FalkorDB and Weaviate retains the property; we simply stop reading and writing it.

### Task 3.1: Strip `auth_headers.py` in 8 microservices

**Files:**
- Modify all 8 copies. Locate them:

- [ ] **Step 1: Locate every copy**

```bash
find backend/microservices -name "auth_headers.py" -not -path "*/__pycache__/*"
```

- [ ] **Step 2: For each copy, strip the role machinery**

Each file currently contains roughly:
```python
EVERYONE_ROLE = "EVERYONE"

def extract_user_roles(...) -> List[str]: ...

def allowed_roles(user_roles: List[str]) -> List[str]:
    return list({*user_roles, EVERYONE_ROLE})
```

Apply:
- DELETE `EVERYONE_ROLE` constant.
- DELETE `allowed_roles()` function.
- KEEP `extract_user_roles()` if it parses `X-User-Roles` header (informational metadata still flows through; not consumed downstream after this PR). Alternatively, if no caller remains in the service, delete it too.

- [ ] **Step 3: Verify no remaining `EVERYONE_ROLE` references in the service**

For each microservice:
```bash
grep -rn "EVERYONE_ROLE\|allowed_roles" backend/microservices/<service>/ | grep -v __pycache__
```

Expected: zero references after the cleanup propagates through Tasks 3.2-3.11.

### Task 3.2: weaviate-service — drop `_roles_filter()` and 12 callers

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py:79-87,453,506,680,724,1223,1599,1857,1946,2001,2332,2384,2439`

- [ ] **Step 1: Inspect**

```bash
grep -n "_roles_filter\|allowed_roles\|EVERYONE_ROLE" backend/microservices/weaviate-service/app/services/weaviate_service.py
```

- [ ] **Step 2: Delete `_roles_filter()` (lines 79-87)**

Find:
```python
def _roles_filter(user_roles: List[str]):
    """Build the single-clause roles ACL filter."""
    return weaviate.classes.query.Filter.by_property("roles").contains_any(
        allowed_roles(user_roles or [])
    )
```

Delete the function entirely.

- [ ] **Step 3: At each of the 12 call sites, drop the filter usage**

Find:
```python
filters = _roles_filter(user_roles)
results = collection.query.hybrid(query=q, filters=filters, ...)
```

Replace with:
```python
results = collection.query.hybrid(query=q, ...)
```

If the filter was combined with other filters via `Filter.all_of([...])`, drop the `_roles_filter(...)` element from the list.

- [ ] **Step 4: Drop the import**

```python
from .auth_headers import allowed_roles, EVERYONE_ROLE  # ← remove
```

- [ ] **Step 5: Run weaviate-service tests**

```bash
cd backend/microservices/weaviate-service && python -m pytest -v
```

### Task 3.3: weaviate-service — drop `roles` from indexing pipeline

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py:1028-1042`

- [ ] **Step 1: Inspect**

```bash
grep -n "roles\|EVERYONE_ROLE" backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py
```

- [ ] **Step 2: At every indexing call, drop the `roles` field**

Find:
```python
data_object = {
    "doc_id": doc_id,
    "text": chunk_text,
    "roles": roles or [EVERYONE_ROLE],  # ← drop this line
    ...
}
```

Replace by removing the `roles` line.

- [ ] **Step 3: Drop the `roles` parameter from any internal methods that accept it**

```bash
grep -n "def .*roles" backend/microservices/weaviate-service/app/services/rag/indexing_pipeline.py
```

Where roles are passed as parameter, drop the parameter and update callers accordingly.

### Task 3.4: weaviate-service — drop `EVERYONE_ROLE` in execution_context

**Files:**
- Modify: `backend/microservices/weaviate-service/app/core/execution_context.py:59,163`

- [ ] **Step 1: Inspect**

```bash
grep -n "EVERYONE_ROLE" backend/microservices/weaviate-service/app/core/execution_context.py
```

- [ ] **Step 2: For each match, drop the reference**

Either remove the line entirely or replace `EVERYONE_ROLE` with a sensible default (likely just delete the line).

- [ ] **Step 3: Drop the import**

### Task 3.5: KTS — drop `_graph_scope()` in `triples.py`

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/api/triples.py:50-59,66,135,168,191,201,221,271,282,299`

- [ ] **Step 1: Inspect**

```bash
grep -n "_graph_scope\|EVERYONE_ROLE\|user_roles" backend/microservices/knowledge-tree-service/app/api/triples.py
```

- [ ] **Step 2: Delete `_graph_scope()` function (lines 50-59)**

- [ ] **Step 3: At each of the 8+ call sites, drop the `user=_graph_scope(user_roles)` argument**

Find:
```python
result = await ts.query_triples(
    user=_graph_scope(user_roles),
    collection=request.collection,
    ...
)
```

Replace with:
```python
result = await ts.query_triples(
    collection=request.collection,
    ...
)
```

- [ ] **Step 4: Drop `user_roles: List[str] = Depends(extract_user_roles)` parameter from endpoint signatures**

Endpoint signatures currently look like:
```python
@router.post("/query")
async def query_triples_endpoint(
    request: TripleQueryRequest,
    user_roles: List[str] = Depends(extract_user_roles),  # ← drop
):
```

Drop the parameter (FastAPI still parses the X-User-Roles header but no one consumes it in KTS post-removal).

- [ ] **Step 5: Rename `clear_tenant()` → `clear_scope()` (line 282)**

```python
@router.post("/clear-tenant")  # ← rename to /clear-scope
async def clear_tenant(...):    # ← rename to clear_scope
```

Update the route path AND function name. Verify no callers expect `/clear-tenant`:

```bash
grep -rn "clear-tenant\|clear_tenant" backend/
```

If callers exist, update them.

- [ ] **Step 6: Drop the `EVERYONE_ROLE` import**

### Task 3.6: KTS — drop `user=EVERYONE_ROLE` in `extract.py`

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/api/extract.py:43,67,82,102,108`

- [ ] **Step 1: Inspect**

```bash
grep -n "EVERYONE_ROLE\|user=\|user_roles" backend/microservices/knowledge-tree-service/app/api/extract.py
```

- [ ] **Step 2: At each `user=EVERYONE_ROLE` call, drop the argument**

Find (line 43):
```python
result = await coordinator.extract_document(
    chunks=request.chunks,
    document_id=request.document_id,
    user=EVERYONE_ROLE,  # ← drop
    collection=request.collection,
    ...
)
```

Replace with:
```python
result = await coordinator.extract_document(
    chunks=request.chunks,
    document_id=request.document_id,
    collection=request.collection,
    ...
)
```

Apply the same pattern at lines 67, 82, 102, 108.

- [ ] **Step 3: Drop the `EVERYONE_ROLE` import**

### Task 3.7: KTS — drop `user=EVERYONE_ROLE` in `reports.py`

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/api/reports.py:45`

- [ ] **Step 1: Inspect**

```bash
grep -n "EVERYONE_ROLE\|user=" backend/microservices/knowledge-tree-service/app/api/reports.py
```

- [ ] **Step 2: At line 45, drop the argument**

Find:
```python
result = await assembler.assemble(
    entity_uri=request.entity_uri,
    report_type=request.report_type,
    user=EVERYONE_ROLE,  # ← drop
    collection=request.collection,
)
```

Replace with:
```python
result = await assembler.assemble(
    entity_uri=request.entity_uri,
    report_type=request.report_type,
    collection=request.collection,
)
```

- [ ] **Step 3: Drop the `EVERYONE_ROLE` import**

### Task 3.8: KTS — rewrite `triple_store.py` (drop `user` parameter)

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/services/triple_store.py:34,52,89,111,263,341,393`

- [ ] **Step 1: Inspect every method signature**

```bash
grep -n "user:\|user=\|{user:" backend/microservices/knowledge-tree-service/app/services/triple_store.py
```

- [ ] **Step 2: At each method signature, drop the `user` parameter**

Methods to update:
- `merge_node(uri, user, collection)` → `merge_node(uri, collection)`
- `merge_chunk_node(chunk_uri, document_uri, chunk_offset, user, collection)` → drop `user`
- `merge_literal(value, user, collection)` → `merge_literal(value, collection)`
- `create_rel(subject_uri, predicate_uri, object_value, user, collection, object_is_node, extraction_method, source_chunk, valid_from, valid_until)` → drop `user`
- `batch_store_triples(triples, user, collection)` → `batch_store_triples(triples, collection)`
- `batch_store_provenance(records, user, collection)` → `batch_store_provenance(records, collection)`
- `store_document_node(document_id, user, collection, title, file_path, semantic_type)` → drop `user`

- [ ] **Step 3: Rewrite Cypher patterns to drop `user` property**

For `create_rel` (around line 145-147), find:
```python
"""
MATCH (s:Node {uri: $s_uri, user: $user, collection: $collection})
MATCH (o:Node {uri: $o_uri, user: $user, collection: $collection})
MERGE (s)-[r:Rel {uri: $p_uri, user: $user, collection: $collection}]->(o)
"""
```

Replace with:
```python
"""
MATCH (s:Node {uri: $s_uri, collection: $collection})
MATCH (o:Node {uri: $o_uri, collection: $collection})
MERGE (s)-[r:Rel {uri: $p_uri, collection: $collection}]->(o)
"""
```

For `batch_store_triples` (around lines 299-305), find:
```cypher
UNWIND $triples AS t
MERGE (s:Node {uri: t.s_uri, user: $user, collection: $col})
ON CREATE SET s.created_at = timestamp()
MERGE (o:Node {uri: t.o_uri, user: $user, collection: $col})
ON CREATE SET o.created_at = timestamp()
MERGE (s)-[r:Rel {uri: t.p_uri, user: $user, collection: $col}]->(o)
ON CREATE SET r.extraction_method = t.method, ...
```

Replace by stripping `user: $user` from every MERGE/MATCH key:
```cypher
UNWIND $triples AS t
MERGE (s:Node {uri: t.s_uri, collection: $col})
ON CREATE SET s.created_at = timestamp()
MERGE (o:Node {uri: t.o_uri, collection: $col})
ON CREATE SET o.created_at = timestamp()
MERGE (s)-[r:Rel {uri: t.p_uri, collection: $col}]->(o)
ON CREATE SET r.extraction_method = t.method, ...
```

Drop `"user": user` from every Cypher params dictionary.

- [ ] **Step 4: Drop the `EVERYONE_ROLE` import if present**

### Task 3.9: KTS — rewrite `triple_query.py` (drop `user` filter from MATCH)

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/services/triple_query.py:7,84-90,103,112-114,601-602`

- [ ] **Step 1: Inspect every MATCH pattern**

```bash
grep -n "user:\|user=\|{user:" backend/microservices/knowledge-tree-service/app/services/triple_query.py
```

- [ ] **Step 2: Drop `user: $user` from every MATCH key**

Examples:
```cypher
MATCH (s:Node {uri: $subject_uri, user: $user})-[r:Rel]->(o)  -- before
MATCH (s:Node {uri: $subject_uri})-[r:Rel]->(o)              -- after
```

```cypher
MATCH (s:Node {user: $user})-[r:Rel {uri: $predicate_uri}]->(o)  -- before
MATCH (s:Node)-[r:Rel {uri: $predicate_uri}]->(o)                -- after
```

```cypher
MATCH (s:Node {user: $user})-[r:Rel {uri: $type_pred}]->(o:Literal {user: $user})  -- before
MATCH (s:Node)-[r:Rel {uri: $type_pred}]->(o:Literal)                              -- after
```

- [ ] **Step 3: Drop `user` from method signatures**

```bash
grep -n "def .*user" backend/microservices/knowledge-tree-service/app/services/triple_query.py
```

Drop `user: str` parameter from every public method (`build_context`, `by_subject`, `by_predicate`, `by_spo`, `top_entities`, `batch_neighbors`, `trace_sources`, `get_stats`, etc.).

- [ ] **Step 4: Drop `"user": user` from Cypher params dicts**

- [ ] **Step 5: Verify `_col_where()` is unchanged**

```bash
grep -n "_col_where" backend/microservices/knowledge-tree-service/app/services/triple_query.py
```

The `collection` filter STAYS (it's namespace, not ACL).

### Task 3.10: KTS — clean `dedup_entities.py` and `reindex_trustgraph.py`

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/scripts/dedup_entities.py:26,133`
- Modify: `backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py:46,280`

- [ ] **Step 1: Inspect**

```bash
grep -n "EVERYONE_ROLE\|user=" backend/microservices/knowledge-tree-service/scripts/dedup_entities.py backend/microservices/knowledge-tree-service/scripts/reindex_trustgraph.py
```

- [ ] **Step 2: Drop `user=EVERYONE_ROLE` arguments at each match**

Apply the same pattern as Tasks 3.6-3.7 (drop the `user=...` keyword argument).

- [ ] **Step 3: Drop `EVERYONE_ROLE` imports**

- [ ] **Step 4: Smoke test the scripts**

```bash
cd backend/microservices/knowledge-tree-service && python -c "import scripts.dedup_entities; import scripts.reindex_trustgraph; print('imports OK')"
```

### Task 3.11: MCP servers — drop role propagation

**Files:**
- Modify: `backend/microservices/mcp-google-drive-server/app/services/sync_service.py:71,109,141,202-305`
- Modify: equivalent files in Alfresco and OneDrive MCP servers

- [ ] **Step 1: Inspect (google-drive)**

```bash
grep -n "default_document_roles\|default_roles\|roles=" backend/microservices/mcp-google-drive-server/app/services/sync_service.py
```

- [ ] **Step 2: At each call site that sets `roles=` on `UnifiedDocument`, drop the field**

Find:
```python
unified_doc = UnifiedDocument(
    document_id=doc_id,
    title=title,
    content=content,
    roles=connector_settings.default_document_roles or [EVERYONE_ROLE],  # ← drop
    ...
)
```

Replace by removing the `roles=...` line.

- [ ] **Step 3: Drop `default_document_roles` and `default_roles` member references**

```bash
grep -n "default_document_roles\|default_roles" backend/microservices/mcp-google-drive-server/app/services/sync_service.py
```

Drop every reference. The Pydantic schema removal in Phase 4 handles the input side.

- [ ] **Step 4: Apply the same pattern to Alfresco and OneDrive MCP servers**

```bash
grep -rn "default_document_roles\|default_roles" backend/microservices/ | grep -v __pycache__
```

For each match, drop similarly.

### Task 3.12: Run microservice tests

- [ ] **Step 1: Run weaviate-service tests**

```bash
cd backend/microservices/weaviate-service && python -m pytest -v
```

- [ ] **Step 2: Run knowledge-tree-service tests**

```bash
cd backend/microservices/knowledge-tree-service && python -m pytest -v
```

- [ ] **Step 3: Run other microservice tests as available**

```bash
for svc in emma-agent-service intelligence-docs-service background-worker storage-service document-forge-service; do
    echo "=== $svc ==="
    (cd backend/microservices/$svc && python -m pytest -v) || echo "FAIL: $svc"
done
```

Expected: all green or skipped (some services may have minimal test surface). Fix any failures from import errors of removed `EVERYONE_ROLE` / `allowed_roles`.

### Task 3.13: Commit Phase 3

- [ ] **Step 1: Stage all microservice changes**

```bash
git add backend/microservices/
```

- [ ] **Step 2: Verify diff stat**

```bash
git diff --cached --stat
```

- [ ] **Step 3: Create commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(microservices): drop role plumbing across 8 services

Strip EVERYONE_ROLE constant + allowed_roles() helper from the 8
duplicated auth_headers.py copies (weaviate, knowledge-tree, emma,
intelligence-docs, background-worker, storage, document-forge,
3x MCP servers). Drop _roles_filter() and 12 call sites in
weaviate_service.py. Drop roles from indexing_pipeline payloads.

Knowledge-tree-service: delete _graph_scope() (returned hardcoded
EVERYONE_ROLE), drop user parameter from triple_store and
triple_query Cypher patterns and method signatures, drop
user=EVERYONE_ROLE from extract.py (5 sites) and reports.py.
Rename clear_tenant() to clear_scope() as a bonus cleanup of
tenancy-era language. Strip role propagation from MCP google-drive,
alfresco, and onedrive sync_service.

Existing FalkorDB nodes/rels still carry the user property and
existing Weaviate objects still carry the roles property; both
become vestigial after this commit and are physically removed in
Commit 5 (Alembic + blue/green Weaviate + KTS cleanup script).

Refs: docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4: Pydantic schema breaking change → Commit 4

**Goal:** Drop `roles` from API surface and enforce strict 422 on incoming `roles`. This is the externally visible breaking change.

### Task 4.1: Drop `roles` from `DocumentBase` and descendants + add `extra='forbid'`

**Files:**
- Modify: `backend/app/schemas/document.py:13-22,128-146`

- [ ] **Step 1: Inspect**

```bash
grep -n "roles\|EVERYONE\|model_config\|extra=" backend/app/schemas/document.py
```

- [ ] **Step 2: Find DocumentBase**

Find:
```python
class DocumentBase(BaseModel):
    title: str
    ...
    roles: List[str] = Field(
        default=["EVERYONE"],
        description="KeyCloak role names that can see this document."
    )
```

Drop the `roles` field (and any related `EVERYONE_ROLE` import).

- [ ] **Step 3: Find DocumentUpdate, DocumentDetail, and any other model with `roles`**

```python
class DocumentUpdate(BaseModel):
    roles: Optional[List[str]] = Field(...)
```

Drop the `roles` field.

- [ ] **Step 4: Add `model_config = ConfigDict(extra='forbid')` to all Document models**

For each Pydantic model in `document.py` (`DocumentBase`, `DocumentCreate`, `DocumentUpdate`, `DocumentDetail`):

```python
from pydantic import BaseModel, ConfigDict, Field

class DocumentBase(BaseModel):
    model_config = ConfigDict(extra='forbid')

    title: str
    ...
```

Without `extra='forbid'`, Pydantic silently ignores unknown fields (lenient drop). With it, unknown fields cause `422 Unprocessable Entity` (strict drop, matching Decision 6).

### Task 4.2: Drop `default_document_roles` from Connector schemas + add `extra='forbid'`

**Files:**
- Modify: `backend/app/schemas/connector.py`

- [ ] **Step 1: Inspect**

```bash
grep -n "roles\|EVERYONE\|default_document_roles\|model_config\|extra=" backend/app/schemas/connector.py
```

- [ ] **Step 2: Find ConnectorCreate / ConnectorUpdate**

Find:
```python
class ConnectorCreate(BaseModel):
    ...
    default_document_roles: List[str] = Field(
        default_factory=lambda: ["EVERYONE"],
        description="Roles applied to documents ingested through this connector."
    )
```

Drop the field.

- [ ] **Step 3: Add `model_config = ConfigDict(extra='forbid')` to both `ConnectorCreate` and `ConnectorUpdate`**

### Task 4.3: Drop `roles` from `UnifiedDocument` dataclass

**Files:**
- Modify: `backend/app/schemas/unified_document.py:107`

- [ ] **Step 1: Inspect**

```bash
grep -n "roles\|EVERYONE" backend/app/schemas/unified_document.py
```

- [ ] **Step 2: Find UnifiedDocument**

Find:
```python
@dataclass
class UnifiedDocument:
    ...
    roles: List[str] = field(default_factory=lambda: ["EVERYONE"])
```

Drop the field.

`@dataclass` does not have an `extra='forbid'` equivalent (dataclasses are not Pydantic models); skip that part for this file.

### Task 4.4: Update all schema constructors

- [ ] **Step 1: Find constructors passing `roles`**

```bash
grep -rn "DocumentCreate(\|DocumentUpdate(\|UnifiedDocument(\|ConnectorCreate(\|ConnectorUpdate(" backend/ | grep -v __pycache__ | grep "roles="
```

- [ ] **Step 2: Drop the `roles=` argument at each call site**

Apply the pattern: remove `roles=...` keyword argument from each constructor call.

### Task 4.5: Add positive test for 422 on POST /documents with roles

**Files:**
- Modify: `backend/tests/api/v1/test_documents.py` (or create new test if needed)

- [ ] **Step 1: Inspect existing test patterns**

```bash
ls backend/tests/api/v1/
head -50 backend/tests/api/v1/test_documents.py 2>/dev/null || head -50 backend/tests/test_documents*.py
```

Note the authenticated client fixture name used in the codebase.

- [ ] **Step 2: Write the test**

```python
# backend/tests/api/v1/test_documents.py (append, adapt fixture name)
import pytest

@pytest.mark.asyncio
async def test_post_documents_with_roles_returns_422(authenticated_client):
    """Strict drop: extra `roles` field in body must trigger 422 (Pydantic extra='forbid')."""
    response = await authenticated_client.post(
        "/api/v1/documents",
        json={
            "title": "Test doc",
            "roles": ["LEGAL"],  # this field no longer exists in schema
        },
    )
    assert response.status_code == 422, response.text
    assert "extra" in response.text.lower() or "forbidden" in response.text.lower()
```

- [ ] **Step 3: Run the test, expect PASS**

```bash
cd backend/tests && pytest -k test_post_documents_with_roles_returns_422 -v
```

Expected: PASS (the schema change in Task 4.1 already enforces this; the test is a regression guard).

If FAIL: confirm `model_config = ConfigDict(extra='forbid')` was applied in Task 4.1.

### Task 4.6: Run schema test suite

- [ ] **Step 1: Run schema and API tests**

```bash
cd backend/tests && pytest -k "schema or document or connector" -v
```

Expected: all green. Fix any failures by updating tests to drop `roles` from fixtures.

### Task 4.7: Commit Phase 4

- [ ] **Step 1: Stage schema changes**

```bash
git add backend/app/schemas/document.py backend/app/schemas/connector.py backend/app/schemas/unified_document.py backend/tests/
```

(Plus any callers updated in Task 4.4.)

- [ ] **Step 2: Verify diff stat**

```bash
git diff --cached --stat
```

- [ ] **Step 3: Create commit**

```bash
git commit -m "$(cat <<'EOF'
feat(api)!: remove roles field from Document/Connector schemas

BREAKING CHANGE: drop the roles field from DocumentBase, DocumentCreate,
DocumentUpdate, DocumentDetail, ConnectorCreate, ConnectorUpdate, and
UnifiedDocument. Add model_config = ConfigDict(extra='forbid') to all
Pydantic Document and Connector models so requests with extra fields
return 422 Unprocessable Entity (strict drop semantics).

Without extra='forbid', Pydantic default extra='ignore' would silently
accept and discard the field, producing lenient drop semantics that
contradict Decision 6 of the spec. Strict drop forces clients to
notice the breaking change immediately rather than discovering it
later via missing functionality.

Add a positive regression test asserting POST /documents with roles
returns 422.

Refs: docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5: DB migrations + Weaviate blue/green + KTS cleanup → Commit 5

**Goal:** Drop the `roles` columns from PostgreSQL, drop the `roles` property from every Weaviate collection (without re-embedding), and remove the vestigial `user` property from FalkorDB nodes/rels. This is the irreversible-on-disk part.

### Task 5.1: Generate Alembic migration scaffold

- [ ] **Step 1: Generate revision**

```bash
cd backend && python scripts/create_migration.py -m "drop role-acl columns"
```

This creates a new file at `backend/alembic/versions/<auto-generated-rev>_drop_role_acl_columns.py`.

- [ ] **Step 2: Inspect the scaffold**

```bash
ls -t backend/alembic/versions/ | head -1
cat backend/alembic/versions/<the-new-file>
```

### Task 5.2: Implement upgrade() and irreversible downgrade()

**Files:**
- Modify: `backend/alembic/versions/<rev>_drop_role_acl_columns.py`

- [ ] **Step 1: Replace the migration body**

```python
"""drop role-acl columns

Revision ID: <auto-generated>
Revises: <previous head>
Create Date: 2026-05-04 ...

"""
from alembic import op
import sqlalchemy as sa


revision = "<auto-generated>"
down_revision = "<previous head>"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("idx_documents_roles", table_name="documents")
    op.drop_column("documents", "roles")

    op.drop_index("idx_indexed_documents_roles", table_name="indexed_documents")
    op.drop_column("indexed_documents", "roles")


def downgrade():
    raise NotImplementedError(
        "Irreversible: roles column dropped permanently. "
        "Restore from pg_dump backup."
    )
```

(Match the actual revision ID and `down_revision` to whatever Alembic generated.)

### Task 5.3: Test alembic upgrade head in sandbox

- [ ] **Step 1: Stand up sandbox database**

```bash
cd backend/docker && docker compose -f docker-compose.test.yml up -d db
```

- [ ] **Step 2: Run upgrade**

```bash
cd backend && DATABASE_URL=postgresql+asyncpg://test_user:test_password@localhost:5433/test_db alembic upgrade head
```

Expected: success, the migration runs cleanly.

- [ ] **Step 3: Verify columns dropped**

```bash
docker compose -f backend/docker/docker-compose.test.yml exec db psql -U test_user -d test_db -c "\d documents" | grep roles
docker compose -f backend/docker/docker-compose.test.yml exec db psql -U test_user -d test_db -c "\d indexed_documents" | grep roles
```

Expected: no `roles` column listed.

### Task 5.4: Test alembic downgrade base raises NotImplementedError

- [ ] **Step 1: Try downgrade**

```bash
cd backend && DATABASE_URL=postgresql+asyncpg://test_user:test_password@localhost:5433/test_db alembic downgrade -1
```

Expected: `NotImplementedError: Irreversible: roles column dropped permanently. Restore from pg_dump backup.`

If the command succeeds (no error), `downgrade()` is wrong — go back to Task 5.2 and ensure it raises.

- [ ] **Step 2: Tear down sandbox**

```bash
cd backend/docker && docker compose -f docker-compose.test.yml down -v
```

### Task 5.5: Drop `roles` columns from SQLAlchemy models

**Files:**
- Modify: `backend/app/db/models.py:178,184,1696,1703`

- [ ] **Step 1: Inspect**

```bash
grep -n "roles = Column\|idx_documents_roles\|idx_indexed_documents_roles" backend/app/db/models.py
```

- [ ] **Step 2: Drop the column from `Document` (line 178)**

Find:
```python
class Document(Base):
    ...
    roles = Column(ARRAY(String), nullable=False, server_default="{EVERYONE}")
```

Drop the `roles = Column(...)` line.

- [ ] **Step 3: Drop the index from `Document.__table_args__` (line 184)**

Find:
```python
__table_args__ = (
    ...
    Index('idx_documents_roles', 'roles', postgresql_using='gin'),
    ...
)
```

Drop the `Index('idx_documents_roles', ...)` line.

- [ ] **Step 4: Apply the same pattern to `IndexedDocument` (lines 1696, 1703)**

- [ ] **Step 5: Verify model imports OK**

```bash
cd backend && python -c "from app.db.models import Document, IndexedDocument; print('imports OK')"
```

### Task 5.6: Create Weaviate blue/green migration script

**Files:**
- Create: `backend/scripts/weaviate_drop_roles_property.py`

- [ ] **Step 1: Write the script**

```python
"""Blue/green migration: drop the `roles` property from every Weaviate collection.

Vectors are preserved during copy (no re-embedding). The hot path is bounded
by object copy time, not embedding time.
"""
import logging
import os

import weaviate

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

COLLECTIONS = [
    "Nouxcube_documents",
    "Nouxcube_documents_summaries",
    "Nouxcube_knowledge",
    "Nouxcube_visual",
    "TrustGraphEntities",
    "OntologyTerms",
]


def migrate_collection(client: weaviate.WeaviateClient, col_name: str) -> int:
    old = client.collections.get(col_name)
    old_config = old.config.get()

    new_props = [p for p in old_config.properties if p.name != "roles"]

    new_name = f"{col_name}_v2"
    if client.collections.exists(new_name):
        logger.warning("Stale %s exists; deleting before retry", new_name)
        client.collections.delete(new_name)

    client.collections.create(
        name=new_name,
        properties=new_props,
        vectorizer_config=old_config.vectorizer_config,
        vector_index_config=old_config.vector_index_config,
        inverted_index_config=old_config.inverted_index_config,
        replication_config=old_config.replication_config,
    )
    target = client.collections.get(new_name)

    copied = 0
    with target.batch.dynamic() as batch:
        for obj in old.iterator(include_vector=True):
            props = {k: v for k, v in obj.properties.items() if k != "roles"}
            vector = obj.vector.get("default") if isinstance(obj.vector, dict) else obj.vector
            batch.add_object(properties=props, vector=vector, uuid=obj.uuid)
            copied += 1

    if target.batch.failed_objects:
        raise RuntimeError(
            f"{col_name}: {len(target.batch.failed_objects)} failed during copy; aborting"
        )

    logger.info("%s: copied %d objects to %s", col_name, copied, new_name)

    client.collections.delete(col_name)
    client.collections.update_name(new_name, col_name)
    logger.info("%s: swap complete", col_name)

    return copied


def main():
    host = os.environ.get("WEAVIATE_HOST", "localhost")
    port = int(os.environ.get("WEAVIATE_PORT", "8080"))
    grpc_port = int(os.environ.get("WEAVIATE_GRPC_PORT", "50051"))

    client = weaviate.connect_to_local(host=host, port=port, grpc_port=grpc_port)
    try:
        for col_name in COLLECTIONS:
            if not client.collections.exists(col_name):
                logger.warning("%s does not exist; skipping", col_name)
                continue
            migrate_collection(client, col_name)
    finally:
        client.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Lint check**

```bash
cd backend && python -m py_compile scripts/weaviate_drop_roles_property.py
```

Expected: no syntax errors.

### Task 5.7: Test the Weaviate script against staging

- [ ] **Step 1: Create a sandbox collection with `roles` property**

```python
# Quick sanity script (do not commit)
import weaviate
from weaviate.classes.config import Configure, Property, DataType

client = weaviate.connect_to_local(host="localhost", port=8080)
try:
    if client.collections.exists("SandboxColl"):
        client.collections.delete("SandboxColl")
    client.collections.create(
        name="SandboxColl",
        properties=[
            Property(name="text", data_type=DataType.TEXT),
            Property(name="roles", data_type=DataType.TEXT_ARRAY),
        ],
        vectorizer_config=Configure.Vectorizer.none(),
    )
    coll = client.collections.get("SandboxColl")
    coll.data.insert(properties={"text": "hello", "roles": ["EVERYONE"]}, vector=[0.1] * 8)
finally:
    client.close()
```

- [ ] **Step 2: Run the migration script against the sandbox collection**

Edit `COLLECTIONS = ["SandboxColl"]` temporarily and run:

```bash
python backend/scripts/weaviate_drop_roles_property.py
```

Expected: `SandboxColl: copied 1 objects to SandboxColl_v2`, then `SandboxColl: swap complete`.

- [ ] **Step 3: Verify the resulting collection has no `roles` property**

```python
import weaviate
client = weaviate.connect_to_local(host="localhost", port=8080)
try:
    coll = client.collections.get("SandboxColl")
    print([p.name for p in coll.config.get().properties])
    obj = next(coll.iterator(include_vector=True))
    print(obj.properties, obj.vector)
finally:
    client.close()
```

Expected: properties list does NOT include `roles`; the original object is preserved with its vector.

- [ ] **Step 4: Cleanup sandbox**

```python
import weaviate
client = weaviate.connect_to_local(host="localhost", port=8080)
try:
    if client.collections.exists("SandboxColl"):
        client.collections.delete("SandboxColl")
finally:
    client.close()
```

- [ ] **Step 5: Restore `COLLECTIONS` in the script to the production list**

(If you edited the constant in Step 2, restore it now.)

### Task 5.8: Create FalkorDB cleanup script

**Files:**
- Create: `backend/scripts/kts_remove_user_property.py`

- [ ] **Step 1: Write the script**

```python
"""Remove vestigial `user` property from FalkorDB nodes and relationships.

Post role-based ACL removal, every node and rel still carries `user='EVERYONE'`.
This script removes the property entirely. Idempotent.
"""
import asyncio
import logging
import os

from redis import asyncio as aioredis

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def main():
    falkor_host = os.environ.get("FALKOR_HOST", "localhost")
    falkor_port = int(os.environ.get("FALKOR_PORT", "6380"))
    graph_name = os.environ.get("FALKOR_GRAPH", "knowledge_graph")

    r = aioredis.from_url(f"redis://{falkor_host}:{falkor_port}", decode_responses=True)
    try:
        node_result = await r.execute_command(
            "GRAPH.QUERY", graph_name,
            "MATCH (n) WHERE n.user IS NOT NULL REMOVE n.user RETURN count(n) AS modified"
        )
        logger.info("Nodes cleaned: %s", node_result)

        rel_result = await r.execute_command(
            "GRAPH.QUERY", graph_name,
            "MATCH ()-[r]-() WHERE r.user IS NOT NULL REMOVE r.user RETURN count(r) AS modified"
        )
        logger.info("Rels cleaned: %s", rel_result)
    finally:
        await r.close()


if __name__ == "__main__":
    asyncio.run(main())
```

(The exact `r.execute_command` invocation may need adjustment depending on the redis-py / falkor client API in the project. Confirm by inspecting how `knowledge-tree-service` connects to FalkorDB — `services/falkor_client.py` or similar.)

- [ ] **Step 2: Lint check**

```bash
cd backend && python -m py_compile scripts/kts_remove_user_property.py
```

### Task 5.9: Test the FalkorDB script against staging

- [ ] **Step 1: Seed a test graph with `user` property**

```bash
redis-cli -p 6380 GRAPH.QUERY test_graph "CREATE (n:Node {uri: 'test://1', user: 'EVERYONE'}) RETURN n"
redis-cli -p 6380 GRAPH.QUERY test_graph "CREATE (a:Node {uri: 'test://2', user: 'EVERYONE'}), (b:Node {uri: 'test://3', user: 'EVERYONE'}), (a)-[:Rel {user: 'EVERYONE'}]->(b) RETURN a, b"
```

- [ ] **Step 2: Run the script with `FALKOR_GRAPH=test_graph`**

```bash
FALKOR_GRAPH=test_graph python backend/scripts/kts_remove_user_property.py
```

Expected log: nodes cleaned, rels cleaned.

- [ ] **Step 3: Verify**

```bash
redis-cli -p 6380 GRAPH.QUERY test_graph "MATCH (n) WHERE n.user IS NOT NULL RETURN count(n)"
```

Expected: 0.

- [ ] **Step 4: Tear down test graph**

```bash
redis-cli -p 6380 GRAPH.DELETE test_graph
```

### Task 5.10: Commit Phase 5

- [ ] **Step 1: Stage migration + scripts + model changes**

```bash
git add backend/alembic/versions/ backend/scripts/weaviate_drop_roles_property.py backend/scripts/kts_remove_user_property.py backend/app/db/models.py
```

- [ ] **Step 2: Verify diff stat**

```bash
git diff --cached --stat
```

- [ ] **Step 3: Create commit**

```bash
git commit -m "$(cat <<'EOF'
feat(db)!: drop roles columns + Weaviate property + KTS user property

BREAKING CHANGE: irreversible Alembic migration drops
documents.roles and indexed_documents.roles columns plus their
GIN indexes. Downgrade raises NotImplementedError; restore
requires pg_dump backup taken in pre-flight.

New backend/scripts/weaviate_drop_roles_property.py performs a
blue/green migration per collection: creates Nouxcube_*_v2
without the roles property, copies objects with vectors preserved
(no re-embedding), atomic-renames into place. Operational window
bounded by object copy time, not embedding time.

New backend/scripts/kts_remove_user_property.py runs Cypher
REMOVE n.user / REMOVE r.user across knowledge_graph, eliminating
the vestigial property from FalkorDB.

SQLAlchemy models updated to drop the column definitions, keeping
schema in sync with the migration.

Refs: docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6: Documentation → Commit 6

**Goal:** Update CLAUDE.md, docstrings, and on-premise docs to reflect the new auth model. Pure documentation; no runtime impact.

### Task 6.1: Rewrite CLAUDE.md role-based ACL mentions

**Files:**
- Modify: `CLAUDE.md` lines 45, 82, 502 (and any others uncovered by grep)

- [ ] **Step 1: Inspect**

```bash
grep -n "role-based\|roles:\|EVERYONE\|filter_visible_to_user\|Document.roles" CLAUDE.md
```

- [ ] **Step 2: At each match, rewrite**

Replace narrative like:
> "single-tenant intelligent document management system with microservices architecture and role-based access control (KeyCloak OIDC/SAML + `roles: ARRAY(String)` on documents, `EVERYONE` wildcard)"

With:
> "single-tenant intelligent document management system with microservices architecture. Authentication via KeyCloak OIDC/SAML; authorization is consolidated onto `User.is_superuser` for admin/config sections. All authenticated users can access all documents in the deployment."

Replace narrative like:
> "ACL | `roles: ARRAY(String)` on IndexedDocument, `EVERYONE` wildcard for public docs"

With:
> "ACL | `User.is_superuser` boolean for admin gating; documents are visible to all authenticated users."

Replace narrative like:
> "Use role-based access: `filter(Document.roles.overlap(user.roles))` (no tenant_id — single-tenant)"

With:
> "All authenticated users can access all documents (no role-based or tenant-based scoping). Admin endpoints use `Depends(require_superuser)` from `app.core.auth.superuser`."

### Task 6.2: Rewrite IndexedDocument docstring in models.py

**Files:**
- Modify: `backend/app/db/models.py:1600-1617`

- [ ] **Step 1: Inspect**

```bash
sed -n '1600,1625p' backend/app/db/models.py
```

- [ ] **Step 2: Rewrite the docstring to drop role-based ACL language**

Replace with:

```python
class IndexedDocument(Base):
    """Indexed document record (post role-based ACL removal).

    Authorization model:
    - All authenticated users can read every IndexedDocument in the deployment.
    - Admin/config endpoints use User.is_superuser for gating.
    - The roles column was dropped in migration <rev> (2026-05-04); restore
      from pg_dump backup taken pre-migration if a future spec reintroduces
      role-based scoping.

    See docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md
    for the full rationale.
    """
```

### Task 6.3: Fix triple_query.py docstring

**Files:**
- Modify: `backend/microservices/knowledge-tree-service/app/services/triple_query.py:7`

- [ ] **Step 1: Inspect**

```bash
head -15 backend/microservices/knowledge-tree-service/app/services/triple_query.py
```

- [ ] **Step 2: Rewrite the line "All methods are async and enforce multi-tenant isolation via `user`..."**

Replace with:
```python
"""Knowledge graph query primitives for FalkorDB.

All methods are async. Triples are scoped by `collection` (the Weaviate
collection namespace, e.g., `Nouxcube_documents`). There is no per-user
isolation; the post-2026-05-04 single-tenant on-premise model exposes
all triples to every authenticated user.

See docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md
for the full rationale.
"""
```

### Task 6.4: Fix weaviate_service.py module docstring

**Files:**
- Modify: `backend/microservices/weaviate-service/app/services/weaviate_service.py:4-7`

- [ ] **Step 1: Inspect**

```bash
head -15 backend/microservices/weaviate-service/app/services/weaviate_service.py
```

- [ ] **Step 2: Replace the mixed "single-org refactor" / "multi-tenant legacy" language**

With clean single-tenant + ownership wording matching the new model.

### Task 6.5: Update docs/on-premise/ONBOARDING.md

**Files:**
- Modify: `docs/on-premise/ONBOARDING.md`

- [ ] **Step 1: Inspect for ACL mentions**

```bash
grep -n "roles\|ACL\|EVERYONE\|role-based" docs/on-premise/ONBOARDING.md
```

- [ ] **Step 2: At each match, rewrite or delete**

Onboarding docs likely mention role assignment during indexing — update to reflect that no role assignment is needed; admin promotion is via `PATCH /users/{id}/role` setting `is_superuser=true`.

### Task 6.6: Search for other ACL doc mentions

- [ ] **Step 1: Grep all of `docs/`**

```bash
grep -rn "EVERYONE\|filter_visible_to_user\|roles: ARRAY\|role-based ACL" docs/
```

- [ ] **Step 2: For each match outside this PR's spec/plan, update or delete the mention**

(The spec at `docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md` and this plan are exempt — they are historical record.)

### Task 6.7: Commit Phase 6

- [ ] **Step 1: Stage doc changes**

```bash
git add CLAUDE.md backend/app/db/models.py backend/microservices/knowledge-tree-service/app/services/triple_query.py backend/microservices/weaviate-service/app/services/weaviate_service.py docs/
```

- [ ] **Step 2: Verify diff stat**

```bash
git diff --cached --stat
```

- [ ] **Step 3: Create commit**

```bash
git commit -m "$(cat <<'EOF'
docs: rewrite ACL model from role-based to ownership

Replace 3 references in CLAUDE.md (lines 45, 82, 502) describing
role-based ACL with the new model: KeyCloak auth, all
authenticated users access all documents, is_superuser gates
admin/config sections only.

Rewrite the IndexedDocument class docstring in models.py to
document the post-2026-05-04 access model and reference the
spec for rationale. Fix the multi-tenant-isolation language in
triple_query.py module docstring and the mixed
single-org / multi-tenant phrasing in weaviate_service.py.

Update docs/on-premise/ONBOARDING.md and any other docs that
reference role-based ACL.

Refs: docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 7: PR creation

### Task 7.1: Push branch

- [ ] **Step 1: Push the feature branch**

```bash
git push -u origin refactor/remove-role-based-acl
```

### Task 7.2: Open PR

- [ ] **Step 1: Create PR via gh CLI**

```bash
gh pr create --base development --head refactor/remove-role-based-acl --title "refactor!: remove role-based ACL across the stack" --body "$(cat <<'EOF'
## Summary

- Atomically removes role-based document ACL per spec `docs/superpowers/specs/2026-05-04-remove-role-based-acl-design.md`.
- Drops `Document.roles` and `IndexedDocument.roles` columns + indexes.
- Drops `roles` property from all 6 Weaviate collections (blue/green, no re-embed).
- Drops vestigial `user` property from FalkorDB nodes/rels.
- Drops `EVERYONE_ROLE` sentinel and `allowed_roles()` helper from all 8 microservice `auth_headers.py` copies.
- Drops 15 `filter_visible_to_user()` call sites in backend API endpoints.
- Drops `_roles_filter()` and 12 callers in weaviate-service.
- Drops `_graph_scope()` + `user` Cypher property in knowledge-tree-service.
- Drops frontend `document-acl.service.ts` (259 LOC).
- Drops `roles` field from Document/Connector/UnifiedDocument schemas; enforces `extra='forbid'` (422 on POST with roles).

## Architectural rationale

ACL was a consequence of removing tenant_id (commit `973f0797`). For single-tenant on-premise customers, role-based departmental partition is not a load-bearing requirement; no production deployment uses role-restriction today. Reintroducing a clean ACL is cheaper than maintaining the current half-built one indefinitely.

Authorization consolidates onto `User.is_superuser` for admin gating. KeyCloak authentication and informational `UserProfile.roles` propagation are unchanged.

## Migration window required

This is a breaking change requiring a customer-deployment migration window:

- pg_dump backup MANDATORY (Alembic downgrade is `NotImplementedError`).
- Weaviate snapshot recommended.
- Estimated window: 30-90 min depending on corpus size; hot path is Weaviate blue/green object copy (vectors preserved, no re-embedding).

See spec section "Migration sequence (maintenance window)" for the runbook.

## Test plan

- [ ] All 6 commits individually green on CI.
- [ ] Pre-flight checks pass on staging (no role-restricted docs).
- [ ] Alembic upgrade runs cleanly on sandbox; downgrade raises `NotImplementedError`.
- [ ] Weaviate blue/green script tested on sandbox collection; vectors preserved.
- [ ] FalkorDB cleanup script tested on sandbox graph; properties removed.
- [ ] Smoke tests 1-8 from spec pass on staging post-migration.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

### Task 7.3: Confirm CI green on all 6 commits

- [ ] **Step 1: Watch CI**

```bash
gh pr checks <pr-number> --watch
```

Expected: all checks green for the 6 commits.

If any commit fails CI, address the failure with a fixup commit and squash before merge.

---

## Post-merge ops runbook (per customer deployment)

This is operational, not part of the PR. Each customer deployment runs through this runbook on upgrade.

### Pre-flight (mandatory)

Run Tasks 0.1, 0.2, 0.3 against the customer's production data. Halt and consult if any returns >0.

### Backups (mandatory)

```bash
# PostgreSQL
pg_dump -Fc -U nexus_user nexus_db > pre-acl-removal-$(date +%Y%m%d).dump

# Weaviate
python -c "
import weaviate
c = weaviate.connect_to_local(host='localhost', port=8080)
try:
    c.backup.create(backup_id='pre-acl-removal', backend='filesystem', wait_for_completion=True)
finally:
    c.close()
"

# FalkorDB
redis-cli -p 6380 BGSAVE
sleep 5
cp /var/lib/redis/dump.rdb /var/backups/falkor-pre-acl-removal-$(date +%Y%m%d).rdb
```

### Migration sequence

```
T+0:  docker compose stop frontend emma-agent-service
T+1:  pg_dump (1-5 min)
T+2:  Weaviate snapshot (5-15 min)
T+3:  git pull && cd backend && alembic upgrade head
T+4:  python backend/scripts/weaviate_drop_roles_property.py
T+5:  python backend/scripts/kts_remove_user_property.py
T+6:  docker compose up -d
T+7:  Run smoke tests (5 min)
T+8:  Exit maintenance mode
```

### Smoke tests post-migration (8 items)

1. Admin login (KeyCloak) → `GET /auth/me` returns `is_superuser=true` for known admin user.
2. `POST /documents` without `roles` field → 200 OK.
3. `POST /documents` WITH `roles` field → 422.
4. `GET /documents/{id}` response → no `roles` field.
5. Emma query "buscar contratos de 2024" → response with sources.
6. Emma graph_rag query "qué empleados tiene Acme" → entities + provenance.
7. Knowledge report "facturas Q1" → DOCX generated.
8. Connector sync (Alfresco / Google Drive) → docs ingested without `roles`.

### Rollback

| Failure | Action |
|---|---|
| Alembic error or post-upgrade SQL errors | `git revert PR` + `pg_restore -d nexus_db pre-acl-removal-YYYYMMDD.dump` + redeploy |
| Weaviate blue/green failure | Delete partial `_v2` collections; original collections intact; restart with old image; investigate copy script |
| KTS cleanup script error | Original data unchanged (idempotent REMOVE); `git revert PR` and redeploy |
| Runtime regression | `git revert PR`; redeploy services in reverse-deploy order; root-cause from logs |

Zero data loss path: data eliminated by this PR was vestigial; backups restore schema, not content.

---

## Self-review (filled out by plan author)

- **Spec coverage:** every section of the spec maps to at least one task.
  - "What dies (data-scoping ACL)" SQL columns → Task 5.5.
  - Backend code → Tasks 2.1-2.16.
  - Microservice code → Tasks 3.1-3.13.
  - Frontend → Tasks 1.1-1.8.
  - Pydantic schemas → Tasks 4.1-4.4.
  - Tests → Tasks 2.16, 4.5.
  - Connector adapters → Task 3.11.
  - "What stays" preserved by Tasks 1.6 (admin-guard), 2.2-2.3 (require_superuser).
  - "Out of scope" items are not introduced.
  - Operations runbook → Tasks 0.1-0.3 (pre-flight) + Phase 7 + Post-merge runbook.
  - Customer release note → covered by PR body in Task 7.2.

- **Placeholder scan:** the migration revision filename uses `<rev>` and `<previous head>` as Alembic generates these dynamically; this is intentional and resolved at Task 5.1 (revision generation) before Task 5.2 (body fill). No other "TBD" / "TODO" / unspecified-error-handling placeholders.

- **Type consistency:** `require_superuser` referenced consistently throughout (no `requireSuperuser` / `require_admin` drift). `EVERYONE_ROLE` always quoted as the constant being deleted. `roles` field consistently treated as the deletion target. Method names match the spec's file:line citations (`merge_node`, `merge_chunk_node`, `create_rel`, `batch_store_triples`, `_roles_filter`, `_graph_scope`, `clear_tenant` → `clear_scope`, `filter_visible_to_user`, `build_role_filter_clause`).
