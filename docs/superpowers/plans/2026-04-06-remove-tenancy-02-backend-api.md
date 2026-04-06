# Remove Multi-Tenancy — Plan 2: Backend API Refactor

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor every backend API endpoint and service to use the role-based ACL helpers from Plan 1. Delete endpoints, services, and middlewares that are pure multi-tenant artifacts (`tenants.py`, `document_shares.py`, `sharing_insights.py`, `teams.py`, `document_acl.py`). Add `roles` and `default_document_roles` fields to Pydantic schemas. Apply `require_role("ADMIN")` to admin-only endpoints (notably connectors).

**Architecture:** This plan operates at the FastAPI layer. It depends on Plan 1's outputs (`acl.py`, the model changes, the new schema). After this plan, the backend imports cleanly and all queries filter by roles, but the application is **still not runnable end-to-end** because the microservices (Plan 3) and frontend (Plan 4) still expect tenant headers.

**Tech Stack:** Python 3.9+ / FastAPI / SQLAlchemy 2.x / Pydantic v2 / pytest. No new dependencies introduced.

**Spec reference:** `docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md` (Section 2.E "Backend (`backend/app/`)")
**Previous plan:** `docs/superpowers/plans/2026-04-06-remove-tenancy-01-foundation.md`

**Plan boundaries:**
- ✅ Covers Commit 4 of Section 3.A of the spec.
- ✅ Outputs: every `backend/app/api/v1/*.py` and `backend/app/services/*.py` either deleted or refactored to use `filter_visible_to_user`. Pydantic schemas updated with `roles` field.
- ❌ Does NOT touch microservices in `backend/microservices/` (Plan 3).
- ❌ Does NOT touch frontend (Plan 4).
- ❌ Does NOT run the actual database rebuild (Plan 5).

---

## Volume estimate (from grep against current codebase)

- 43 endpoint files contain `tenant_id` (1013 occurrences)
- 50 service files contain `tenant_id` (719 occurrences)
- ~5 endpoint files are pure tenant artifacts (deleted entirely)
- ~3 service files are pure tenant artifacts (deleted entirely)
- ~85 files net modified

---

## File map (locked decisions)

**Endpoint files DELETED entirely:**
- `backend/app/api/v1/tenants.py`
- `backend/app/api/v1/document_shares.py`
- `backend/app/api/v1/sharing_insights.py`
- `backend/app/api/v1/teams.py`
- `backend/app/api/v1/document_acl.py` (the per-document ACL JSONB endpoints — replaced by `roles[]` column managed via the document update endpoint)

**Service files DELETED entirely:**
- `backend/app/services/document_share_service.py`
- `backend/app/services/document_acl_service.py`
- `backend/app/services/sharing_insights_service.py`
- Any `tenant_service.py` if present
- Any `role_service.py` / `permission_service.py` if present

**Endpoint files MODIFIED (high tenant_id density, ≥30 occurrences each):**
- `backend/app/api/v1/weaviate.py` (74)
- `backend/app/api/v1/connectors.py` (72) — also gains `require_role("ADMIN")`
- `backend/app/api/v1/emma.py` (68)
- `backend/app/api/v1/data_learning.py` (68)
- `backend/app/api/v1/documents.py` (64)
- `backend/app/api/v1/prompts.py` (38)
- `backend/app/api/v1/search.py` (38)
- `backend/app/api/v1/dashboard.py` (37)
- `backend/app/api/v1/admin.py` (36)
- `backend/app/api/v1/channels.py` (35)
- `backend/app/api/v1/agents.py` (32)

**Endpoint files MODIFIED (lower density, <30 occurrences each):** all remaining files in `backend/app/api/v1/` that contain `tenant_id`. The full list is generated dynamically in Task 12 below.

**Service files MODIFIED (high density, ≥30 occurrences each):**
- `backend/app/services/weaviate_client.py` (77)
- `backend/app/services/async_document_service.py` (59)
- `backend/app/services/async_signature_service.py` (54)
- `backend/app/services/document_service.py` (35)
- `backend/app/services/site_guest_service.py` (36)
- `backend/app/services/folder_service.py` (22 — borderline but included for completeness)

**Service files MODIFIED (lower density):** all remaining files in `backend/app/services/` that contain `tenant_id`.

**Pydantic schemas updated:**
- `backend/app/schemas/document.py` — add `roles: List[str]` to create/update/response
- `backend/app/schemas/connector.py` — add `default_document_roles: List[str]` to create/update/response
- `backend/app/schemas/unified_document.py` — add roles
- Any other schema that exposes documents to the frontend

**Routers updated:**
- `backend/app/api/v1/__init__.py` — remove imports and registrations of deleted routers

**Auth dependencies:**
- `backend/app/api/dependencies.py` — remove `get_current_tenant`, `require_tenant`, any other tenant-related dependency
- `backend/app/api/async_dependencies.py` — same
- `backend/app/core/auth/` — delete any tenant middleware files

---

## The canonical refactor pattern

Every `tenant_id`-dependent query in the codebase follows roughly the same shape:

```python
# BEFORE
@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_async_db),
):
    doc = await db.execute(
        select(Document).where(
            Document.id == doc_id,
            Document.tenant_id == tenant.id,
        )
    )
    return doc.scalar_one_or_none()
```

```python
# AFTER
from app.core.auth.acl import filter_visible_to_user

@router.get("/documents/{doc_id}")
async def get_document(
    doc_id: UUID,
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    query = select(Document).where(Document.id == doc_id)
    query = filter_visible_to_user(query, user)
    result = await db.execute(query)
    return result.scalar_one_or_none()
```

Key transformations:

| Before | After |
|---|---|
| `tenant: Tenant = Depends(get_current_tenant)` | `user: UserProfile = Depends(get_current_user)` |
| `Model.tenant_id == tenant.id` | `filter_visible_to_user(query, user)` |
| `Model.tenant_id == current_tenant_id` | `filter_visible_to_user(query, user)` |
| `tenant_id=tenant.id` (passed to a service) | `user=user` (and the service uses the helper internally) |
| `request.headers["X-Tenant-ID"]` | Removed; users are identified by their JWT |
| `Tenant.query.filter(Tenant.id == ...)` | Removed; the table no longer exists |

For **admin-only endpoints** (connector CRUD, prompt management, etc.), the dependency changes to:

```python
from app.core.auth.acl import require_role

@router.post("/connectors")
async def create_connector(
    payload: ConnectorCreate,
    user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db),
):
    ...
```

For **service functions**, the canonical refactor is:

```python
# BEFORE
async def list_documents_for_tenant(tenant_id: UUID, db: AsyncSession):
    return (await db.execute(
        select(Document).where(Document.tenant_id == tenant_id)
    )).scalars().all()

# AFTER
async def list_documents_for_user(user: UserProfile, db: AsyncSession):
    query = filter_visible_to_user(select(Document), user)
    return (await db.execute(query)).scalars().all()
```

The service function takes `user: UserProfile` instead of `tenant_id: UUID`.

---

## Task 1: Verify Plan 1 is in place

**Files:** none (verification only)

- [ ] **Step 1: Confirm branch and Plan 1 commit**

```bash
git status
git log --oneline -3
```

Expected: branch `refactor/remove-multi-tenancy`, recent commits include "feat(foundation): rename DB to nouxcube + introduce role-based ACL helpers".

- [ ] **Step 2: Confirm Plan 1 outputs exist**

```bash
test -f backend/app/core/auth/acl.py && echo "acl.py ok"
test -f backend/app/config/role_mapping.yaml && echo "yaml ok"
python -c "from app.core.auth.acl import filter_visible_to_user, require_role, EVERYONE_ROLE; print('imports ok')"
```

Expected: all three lines print `ok`.

- [ ] **Step 3: Confirm Plan 1 model changes are in place**

```bash
python -c "
from app.db.models import Document, Connector
assert hasattr(Document, 'roles'), 'Document.roles missing'
assert hasattr(Connector, 'default_document_roles'), 'Connector.default_document_roles missing'
assert not hasattr(Document, 'tenant_id'), 'Document.tenant_id still present'
print('schema ok')
"
```

Expected: prints `schema ok`. If any assertion fails, Plan 1 is incomplete — go back and finish it.

---

## Task 2: Delete the `tenants` endpoint and its router registration

**Files:**
- Delete: `backend/app/api/v1/tenants.py`
- Modify: `backend/app/api/v1/__init__.py` (remove import and registration)

- [ ] **Step 1: Read the router registration**

```bash
grep -n "tenants" backend/app/api/v1/__init__.py
```

Expected: at least one import line and one `include_router` line for tenants.

- [ ] **Step 2: Remove the tenants import**

In `backend/app/api/v1/__init__.py`, find:

```python
from app.api.v1 import tenants
```

Delete that line.

- [ ] **Step 3: Remove the tenants router registration**

In the same file, find:

```python
router.include_router(tenants.router, ...)
```

Delete that line.

- [ ] **Step 4: Delete the file**

```bash
git rm backend/app/api/v1/tenants.py
```

- [ ] **Step 5: Verify**

```bash
grep -n "tenants" backend/app/api/v1/__init__.py
test ! -f backend/app/api/v1/tenants.py && echo "deleted ok"
```

Expected: zero matches in `__init__.py` (or only matches that are unrelated, like the word "tenants" inside a comment), and the file is deleted.

---

## Task 3: Delete the `document_shares` endpoint and router registration

**Files:**
- Delete: `backend/app/api/v1/document_shares.py`
- Modify: `backend/app/api/v1/__init__.py`

- [ ] **Step 1: Remove import and registration**

In `backend/app/api/v1/__init__.py`, find and delete:
```python
from app.api.v1 import document_shares
```
and:
```python
router.include_router(document_shares.router, ...)
```

- [ ] **Step 2: Delete the file**

```bash
git rm backend/app/api/v1/document_shares.py
```

- [ ] **Step 3: Verify**

```bash
test ! -f backend/app/api/v1/document_shares.py && echo "deleted ok"
grep -n "document_shares" backend/app/api/v1/__init__.py
```

Expected: file deleted, no remaining references in `__init__.py`.

---

## Task 4: Delete the `sharing_insights` endpoint and router registration

**Files:**
- Delete: `backend/app/api/v1/sharing_insights.py`
- Modify: `backend/app/api/v1/__init__.py`

- [ ] **Step 1: Remove import and registration**

In `backend/app/api/v1/__init__.py`, find and delete:
```python
from app.api.v1 import sharing_insights
```
and:
```python
router.include_router(sharing_insights.router, ...)
```

- [ ] **Step 2: Delete the file**

```bash
git rm backend/app/api/v1/sharing_insights.py
```

- [ ] **Step 3: Verify**

```bash
test ! -f backend/app/api/v1/sharing_insights.py && echo "deleted ok"
```

---

## Task 5: Delete the `teams` endpoint and router registration

**Files:**
- Delete: `backend/app/api/v1/teams.py`
- Modify: `backend/app/api/v1/__init__.py`

- [ ] **Step 1: Remove import and registration**

Same pattern as Tasks 2-4.

- [ ] **Step 2: Delete the file**

```bash
git rm backend/app/api/v1/teams.py
```

- [ ] **Step 3: Verify**

```bash
test ! -f backend/app/api/v1/teams.py && echo "deleted ok"
```

---

## Task 6: Delete the `document_acl` endpoint and router registration

The legacy `document_acl.py` exposed CRUD over a JSONB ACL column on `IndexedDocument`. With the new model (per-document `roles` array), this functionality is replaced by extending the existing document update endpoint to accept `roles` in its payload (handled in Task 13).

**Files:**
- Delete: `backend/app/api/v1/document_acl.py`
- Modify: `backend/app/api/v1/__init__.py`

- [ ] **Step 1: Remove import and registration**

Same pattern.

- [ ] **Step 2: Delete the file**

```bash
git rm backend/app/api/v1/document_acl.py
```

- [ ] **Step 3: Verify**

```bash
test ! -f backend/app/api/v1/document_acl.py && echo "deleted ok"
```

---

## Task 7: Delete tenant-coupled service files

**Files:**
- Delete: `backend/app/services/document_share_service.py`
- Delete: `backend/app/services/document_acl_service.py`
- Delete: `backend/app/services/sharing_insights_service.py`
- Possibly delete: `backend/app/services/tenant_service.py` (if present)
- Possibly delete: `backend/app/services/role_service.py` (if present)
- Possibly delete: `backend/app/services/permission_service.py` (if present)

- [ ] **Step 1: Delete the known-obsolete services**

```bash
git rm backend/app/services/document_share_service.py
git rm backend/app/services/document_acl_service.py
git rm backend/app/services/sharing_insights_service.py
```

- [ ] **Step 2: Check for additional tenant services**

```bash
ls backend/app/services/ | grep -E "tenant|role_service|permission_service"
```

For each match, delete it:

```bash
git rm backend/app/services/<filename>
```

- [ ] **Step 3: Verify**

```bash
ls backend/app/services/ | grep -E "tenant|share_service|acl_service|sharing|role_service|permission_service"
```

Expected: zero matches.

---

## Task 8: Delete tenant middleware and tenant-related auth dependencies

**Files:**
- Delete: any file under `backend/app/core/auth/` whose name contains `tenant`
- Modify: `backend/app/api/dependencies.py` (remove `get_current_tenant`, `require_tenant`)
- Modify: `backend/app/api/async_dependencies.py` (same)
- Modify: `backend/app/core/auth/base.py` (drop `tenant_id` from `UserProfile` if present)

- [ ] **Step 1: Locate tenant middleware files**

```bash
ls backend/app/core/auth/ | grep -i tenant
find backend/app/core -type f -name "*.py" | xargs grep -l "class.*Middleware.*Tenant\|tenant_middleware\|TenantMiddleware" 2>/dev/null
```

For each match, `git rm` it.

- [ ] **Step 2: Remove `get_current_tenant` and `require_tenant`**

In `backend/app/api/dependencies.py`, find any function definitions named `get_current_tenant`, `require_tenant`, `get_tenant_id`, or anything with `tenant` in the name. Delete those functions entirely.

Repeat for `backend/app/api/async_dependencies.py`.

- [ ] **Step 3: Remove `tenant_id` from `UserProfile`**

```bash
grep -n "tenant_id" backend/app/core/auth/base.py
```

If `UserProfile` has a `tenant_id` field, delete it:

```python
# BEFORE
@dataclass
class UserProfile:
    sub: str
    email: str
    name: str
    tenant_id: Optional[str] = None  # ← delete this line
    roles: List[str] = field(default_factory=list)
```

```python
# AFTER
@dataclass
class UserProfile:
    sub: str
    email: str
    name: str
    roles: List[str] = field(default_factory=list)
```

Also remove `tenant_id` from `UserProfile.to_dict()` and `UserProfile.from_dict()` if those methods exist.

- [ ] **Step 4: Verify**

```bash
grep -rn "get_current_tenant\|require_tenant\|tenant_middleware" backend/app/
grep -n "tenant_id" backend/app/core/auth/base.py
```

Expected: zero matches in both grep commands.

---

## Task 9: Refactor the high-density endpoint files

This task applies the canonical refactor pattern (shown at the top of this plan) to the 11 high-density endpoint files. Each file gets the same treatment: replace `Depends(get_current_tenant)` with `Depends(get_current_user)`, replace `Model.tenant_id == X` with `filter_visible_to_user(query, user)`, drop `tenant_id` parameters from function signatures.

**Files to modify (in this order):**
1. `backend/app/api/v1/documents.py` (64 refs)
2. `backend/app/api/v1/connectors.py` (72 refs) — also add `require_role("ADMIN")` to all CRUD endpoints
3. `backend/app/api/v1/emma.py` (68 refs)
4. `backend/app/api/v1/weaviate.py` (74 refs)
5. `backend/app/api/v1/data_learning.py` (68 refs)
6. `backend/app/api/v1/prompts.py` (38 refs) — also add `require_role("ADMIN")`
7. `backend/app/api/v1/search.py` (38 refs)
8. `backend/app/api/v1/dashboard.py` (37 refs)
9. `backend/app/api/v1/admin.py` (36 refs) — also add `require_role("ADMIN")`
10. `backend/app/api/v1/channels.py` (35 refs)
11. `backend/app/api/v1/agents.py` (32 refs)

- [ ] **Step 1: Process `documents.py`**

Open the file. For every occurrence of `tenant_id`:
- If it's in a function signature (`tenant_id: UUID`, `tenant: Tenant = Depends(...)`), replace with `user: UserProfile = Depends(get_current_user)`.
- If it's in a query (`Document.tenant_id == X`, `.filter(tenant_id=...)`), apply the canonical pattern: build the query without the tenant filter, then call `filter_visible_to_user(query, user)`.
- If it's in a Pydantic model field, delete the field.
- If it's passed to a service call, replace with the user object.

Add `roles: List[str]` parameter to the document upload endpoint:

```python
@router.post("/documents")
async def upload_document(
    file: UploadFile,
    roles: List[str] = Form(default=["EVERYONE"]),  # NEW
    user: UserProfile = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    # ... existing logic ...
    new_doc.roles = roles  # NEW: persist the roles on the document
    ...
```

The document update endpoint accepts `roles` in its payload (handled via the Pydantic schema update in Task 11).

Add the import at the top of the file:

```python
from app.core.auth.acl import filter_visible_to_user
from app.api.dependencies import get_current_user
from app.core.auth.base import UserProfile
```

After editing, verify:

```bash
grep -c "tenant_id" backend/app/api/v1/documents.py
```

Expected: `0`

- [ ] **Step 2: Process `connectors.py`**

Same canonical refactor as Step 1, plus add `require_role("ADMIN")` to all write endpoints:

```python
from app.core.auth.acl import require_role

@router.post("/connectors")
async def create_connector(
    payload: ConnectorCreate,
    user: UserProfile = Depends(require_role("ADMIN")),
    db: AsyncSession = Depends(get_async_db),
):
    new_connector = Connector(
        connector_type=payload.connector_type,
        name=payload.name,
        config=payload.config,
        default_document_roles=payload.default_document_roles or ["EVERYONE"],  # NEW
        created_by=user.sub,
    )
    ...
```

The list and read endpoints (GET) can use plain `get_current_user` if any authenticated user is allowed to see the connector list. Check the spec — Section 1 says connectors are admin-managed, but it doesn't explicitly say only admins can VIEW them. Decision: only admins see and manage connectors. Apply `require_role("ADMIN")` to GET endpoints too.

Verify:

```bash
grep -c "tenant_id" backend/app/api/v1/connectors.py
grep -c "require_role" backend/app/api/v1/connectors.py
```

Expected: `0` for tenant_id, `>= 1` for require_role.

- [ ] **Step 3: Process `emma.py`**

Standard canonical refactor. Emma has no admin-only endpoints (every authenticated user can query Emma), so only `get_current_user` is needed.

Verify:

```bash
grep -c "tenant_id" backend/app/api/v1/emma.py
```

Expected: `0`.

- [ ] **Step 4: Process `weaviate.py`**

Standard refactor. The weaviate endpoint proxies queries to the weaviate-service microservice, which currently receives `tenant_id` in its payload. Replace that with the `user.roles` list. For example:

```python
# BEFORE
@router.post("/search")
async def search(payload: SearchRequest, tenant: Tenant = Depends(get_current_tenant)):
    response = await weaviate_client.hybrid_search(
        query=payload.query,
        tenant_id=tenant.id,
    )

# AFTER
@router.post("/search")
async def search(payload: SearchRequest, user: UserProfile = Depends(get_current_user)):
    response = await weaviate_client.hybrid_search(
        query=payload.query,
        user_roles=user.roles,
    )
```

Note: the `weaviate_client.hybrid_search()` method itself is updated in Plan 3 (microservices). For now, we only update the call site. The microservice will accept both signatures for one commit cycle (no, actually it won't — the deploys are atomic in Plan 5). Just update the call site here and trust that Plan 3 will update the receiver.

Verify:

```bash
grep -c "tenant_id" backend/app/api/v1/weaviate.py
```

Expected: `0`.

- [ ] **Step 5: Process the remaining 7 files**

Apply the canonical refactor to:
- `data_learning.py`
- `prompts.py` (add `require_role("ADMIN")` to write endpoints)
- `search.py`
- `dashboard.py`
- `admin.py` (add `require_role("ADMIN")` to ALL endpoints — it's admin.py)
- `channels.py`
- `agents.py`

For each file, follow the pattern. After editing, verify:

```bash
for f in data_learning prompts search dashboard admin channels agents; do
  count=$(grep -c "tenant_id" backend/app/api/v1/${f}.py)
  echo "${f}.py: tenant_id count = $count"
done
```

Expected: every file shows `count = 0`.

---

## Task 10: Refactor the lower-density endpoint files

The remaining endpoint files have fewer than 30 `tenant_id` occurrences each but still need cleanup. The canonical refactor applies to all of them.

- [ ] **Step 1: Generate the work list**

```bash
grep -lc "tenant_id" backend/app/api/v1/*.py | grep -v ":0$"
```

This lists every endpoint file that still has `tenant_id`. After Task 9, the high-density files should be gone from this list. The remaining files are the work list for this task.

- [ ] **Step 2: Apply the canonical refactor to each file in the list**

For each file, follow the same pattern as Task 9 Step 1:
- Replace `tenant: Tenant = Depends(get_current_tenant)` with `user: UserProfile = Depends(get_current_user)`
- Replace `Model.tenant_id == X` with `filter_visible_to_user(query, user)` for Document queries
- For non-Document models that previously filtered by tenant_id, drop the filter entirely (single-tenant means there's only one set of records)
- Drop `tenant_id` from function signatures and Pydantic models

Specific decisions per file:

| File | Notes |
|---|---|
| `notebooks.py` | Notebooks belong to the org. Drop tenant_id, keep `created_by` for ownership. |
| `signatures.py`, `signature_ai.py`, `signature_contacts.py` | Drop tenant_id; signatures are tied to their `created_by` user. |
| `entities.py` | Entity catalog is now global. Drop tenant_id. |
| `folders.py` | Folders are visual organization, not ACL. Drop tenant_id. |
| `auth_sso.py`, `auth.py` | Drop any tenant_id propagation in token issuance — JWT carries roles, not tenant. |
| `lgpd.py` | Drop tenant_id. The LGPD deletion is per-user. |
| `storage.py` | Drop tenant_id. Storage paths no longer namespaced by tenant. |
| `webhooks.py` | Drop tenant_id from webhook routing. Webhooks fire on org events, not tenant events. |
| `forge.py` | Drop tenant_id. |
| `analysis_queue.py` | Drop tenant_id. The queue is global. |
| `classification.py` | Drop tenant_id. |
| `document_categorization.py` | Drop tenant_id. |
| `document_insights.py` | Drop tenant_id. |
| `gemini_voice.py` | Drop tenant_id. |
| `internal_*` files | These are internal-only endpoints; drop tenant_id but verify they still work (they may be called by background jobs or microservices). |
| `site_guests.py`, `site_portal.py` | Site guest portal was a multi-tenant concept (each tenant had a guest portal). Either delete entirely OR keep as global guest access. Decision: KEEP as global (no `tenant_id`), only ADMIN can create guest links. Add `require_role("ADMIN")` to the create endpoint. |
| `features.py` | Feature flags are now global. Drop tenant_id. |
| `heartbeat_stats.py` | Drop tenant_id. |
| `user_sync.py` | Drop tenant_id. User sync now creates users without tenant binding. |
| `users.py` | Drop tenant_id. User listing is global; admin-only via `require_role("ADMIN")`. |
| `threads.py` | Drop tenant_id. |

- [ ] **Step 3: Verify**

```bash
grep -lc "tenant_id" backend/app/api/v1/*.py | grep -v ":0$" | grep -v "^$"
```

Expected: empty output. Every endpoint file has zero `tenant_id` references.

```bash
grep -rln "tenant_id" backend/app/api/v1/
```

Expected: zero matches across the whole `api/v1/` directory.

---

## Task 11: Update Pydantic schemas to expose `roles` and `default_document_roles`

**Files:**
- Modify: `backend/app/schemas/document.py`
- Modify: `backend/app/schemas/connector.py`
- Modify: `backend/app/schemas/unified_document.py`
- Modify: any other schema in `backend/app/schemas/` that exposes documents or connectors
- Delete: `backend/app/schemas/document_share.py`
- Delete: `backend/app/schemas/document_acl.py` (if it exists)

- [ ] **Step 1: Add `roles` to document schemas**

Open `backend/app/schemas/document.py`. For `DocumentBase`, `DocumentCreate`, `DocumentUpdate`, and `DocumentResponse`, add the field:

```python
from typing import List
from pydantic import BaseModel, Field

class DocumentBase(BaseModel):
    title: str
    file_type: str
    # ... existing fields ...
    roles: List[str] = Field(
        default=["EVERYONE"],
        description="KeyCloak role names that can see this document. "
                    "Use ['EVERYONE'] for organization-wide visibility."
    )
```

Drop any existing `tenant_id` field from the same classes.

- [ ] **Step 2: Add `default_document_roles` to connector schemas**

Open `backend/app/schemas/connector.py`. For `ConnectorCreate`, `ConnectorUpdate`, and `ConnectorResponse`, add:

```python
from typing import List
from pydantic import Field

class ConnectorCreate(ConnectorBase):
    """Schema for creating a connector (admin only)."""
    connector_type: ConnectorType
    auth_type: ConnectorAuthType = Field(default=ConnectorAuthType.DELEGATED)
    default_document_roles: List[str] = Field(
        default=["EVERYONE"],
        description="Roles applied to documents ingested through this connector. "
                    "Use ['EVERYONE'] for organization-wide visibility, or "
                    "specify roles like ['SALES'] to restrict to a department."
    )
```

Same for `ConnectorUpdate` (optional in update) and `ConnectorResponse`.

Drop any existing `tenant_id` field.

- [ ] **Step 3: Update `unified_document.py` and others**

```bash
grep -rln "tenant_id" backend/app/schemas/
```

For each file in the list, drop `tenant_id` fields. If the schema exposes documents, add `roles` like in Step 1.

- [ ] **Step 4: Delete obsolete schema files**

```bash
git rm backend/app/schemas/document_share.py
test -f backend/app/schemas/document_acl.py && git rm backend/app/schemas/document_acl.py || true
```

Also remove the imports of these schemas from any other module that referenced them:

```bash
grep -rn "document_share\|document_acl" backend/app/
```

For each match, remove the import and any usage.

- [ ] **Step 5: Verify**

```bash
grep -rn "tenant_id" backend/app/schemas/
test ! -f backend/app/schemas/document_share.py && echo "share schema deleted ok"
```

Expected: zero matches in schemas, share schema gone.

---

## Task 12: Refactor service files

This task applies the canonical refactor to the service layer. Same pattern as the endpoint refactor, but services typically receive `user: UserProfile` instead of having a `Depends(...)` annotation.

**Files to modify (high density first):**
1. `backend/app/services/weaviate_client.py` (77)
2. `backend/app/services/async_document_service.py` (59)
3. `backend/app/services/async_signature_service.py` (54)
4. `backend/app/services/site_guest_service.py` (36)
5. `backend/app/services/document_service.py` (35)

Then the lower-density files (under 30 each).

- [ ] **Step 1: Process `weaviate_client.py`**

The weaviate client is a thin wrapper that calls the weaviate-service microservice. Update its method signatures:

```python
# BEFORE
class WeaviateClient:
    async def hybrid_search(
        self,
        query: str,
        tenant_id: UUID,
        top_k: int = 10,
    ):
        response = await self._http.post(
            "/search",
            json={
                "query": query,
                "tenant_id": str(tenant_id),
                "top_k": top_k,
            }
        )
        ...

# AFTER
class WeaviateClient:
    async def hybrid_search(
        self,
        query: str,
        user_roles: list[str],
        top_k: int = 10,
    ):
        response = await self._http.post(
            "/search",
            json={
                "query": query,
                "user_roles": user_roles,
                "top_k": top_k,
            }
        )
        ...
```

Apply the same pattern to every method that takes `tenant_id`.

Verify:

```bash
grep -c "tenant_id" backend/app/services/weaviate_client.py
```

Expected: `0`.

- [ ] **Step 2: Process `async_document_service.py`**

This service has many methods that filter documents. Standard canonical refactor:

```python
# BEFORE
async def list_documents(self, tenant_id: UUID, ...):
    return (await self.db.execute(
        select(Document).where(Document.tenant_id == tenant_id)
    )).scalars().all()

# AFTER
async def list_documents(self, user: UserProfile, ...):
    query = filter_visible_to_user(select(Document), user)
    return (await self.db.execute(query)).scalars().all()
```

For methods that create documents, accept `roles` as a parameter and persist it:

```python
async def create_document(
    self,
    user: UserProfile,
    title: str,
    content: bytes,
    roles: list[str] | None = None,
    ...
):
    new_doc = Document(
        title=title,
        roles=roles or ["EVERYONE"],
        created_by=user.sub,
        ...
    )
    ...
```

Verify:

```bash
grep -c "tenant_id" backend/app/services/async_document_service.py
```

Expected: `0`.

- [ ] **Step 3: Process `async_signature_service.py`, `site_guest_service.py`, `document_service.py`**

Same canonical refactor for each.

```bash
for f in async_signature_service site_guest_service document_service; do
  count=$(grep -c "tenant_id" backend/app/services/${f}.py)
  echo "${f}.py: $count"
done
```

Expected: every file shows `0`.

- [ ] **Step 4: Process all remaining service files**

```bash
grep -lc "tenant_id" backend/app/services/**/*.py | grep -v ":0$"
```

For every file in the list, apply the canonical refactor. The patterns are:

1. **Service that queries documents**: use `filter_visible_to_user`.
2. **Service that queries non-document tables that had tenant_id**: drop the filter — single tenant means all rows are accessible.
3. **Service that calls a microservice and passed tenant_id**: replace with `user_roles` (the microservice update is in Plan 3).
4. **Service that takes `tenant_id: UUID` as parameter**: change signature to `user: UserProfile`.

Also handle subdirectories:

```bash
grep -rln "tenant_id" backend/app/services/
```

This includes `data_learning/`, `channels/`, etc. Process every file in the list.

- [ ] **Step 5: Verify all services are clean**

```bash
grep -rln "tenant_id" backend/app/services/
```

Expected: empty output.

---

## Task 13: Update `backend/app/api/v1/__init__.py` aggregator

After all the deletions in Tasks 2-6, the router aggregator needs to be checked for any stale references that the individual deletion tasks might have missed.

**Files:**
- Modify: `backend/app/api/v1/__init__.py`

- [ ] **Step 1: Verify no stale imports**

```bash
grep -n "tenants\|document_shares\|sharing_insights\|teams\|document_acl" backend/app/api/v1/__init__.py
```

Expected: zero matches. If any remain, delete them.

- [ ] **Step 2: Verify the file imports cleanly**

```bash
python -c "from app.api.v1 import router; print('router ok, routes:', len(router.routes))"
```

Expected: prints `router ok, routes: <some number>`. If it raises ImportError, find the offending import and fix it.

---

## Task 14: Update other places that reference deleted services or tables

Many modules outside `api/v1/` and `services/` may import from `document_share_service`, `document_acl_service`, etc. They need cleanup.

**Files:** discovered dynamically.

- [ ] **Step 1: Find stale imports**

```bash
grep -rn "from app.services.document_share_service\|from app.services.document_acl_service\|from app.services.sharing_insights_service" backend/
grep -rn "from app.db.models import.*Tenant\|from app.db.models import.*Role\|from app.db.models import.*Permission\|from app.db.models import.*DocumentShare\|from app.db.models import.*TeamInvitation" backend/
```

Expected: a list of files. Each one needs the offending import removed and any usage of the imported names cleaned up.

- [ ] **Step 2: Process each file**

For each file in the list:
- Open the file
- Remove the offending import line
- Find every usage of the deleted symbol and either replace it (if functionality moves to acl helpers) or delete it (if obsolete)
- Save

- [ ] **Step 3: Verify**

```bash
grep -rn "from app.services.document_share_service\|from app.services.document_acl_service\|from app.services.sharing_insights_service" backend/
grep -rn "from app.db.models import.*Tenant\|from app.db.models import.*Role\|from app.db.models import.*Permission\|from app.db.models import.*DocumentShare\|from app.db.models import.*TeamInvitation" backend/
```

Expected: zero matches.

---

## Task 15: Run import smoke test on the whole backend

**Files:** none (verification only)

- [ ] **Step 1: Check that the backend imports cleanly**

```bash
cd backend && python -c "
import importlib
import pkgutil
import app

failed = []
for finder, modname, ispkg in pkgutil.walk_packages(app.__path__, prefix='app.'):
    try:
        importlib.import_module(modname)
    except Exception as e:
        failed.append((modname, str(e)))

if failed:
    print('FAILED IMPORTS:')
    for modname, err in failed:
        print(f'  {modname}: {err}')
    exit(1)
else:
    print(f'All modules imported successfully')
"
```

Expected: prints `All modules imported successfully`. If any module fails, fix the offending import (typically a leftover reference to a deleted class) and re-run.

- [ ] **Step 2: Check that the FastAPI app starts**

```bash
cd backend && python -c "
from app.main import app
routes = [r.path for r in app.routes]
print(f'FastAPI app loaded with {len(routes)} routes')
assert '/api/v1/documents' in routes or any('/documents' in r for r in routes), 'documents route missing'
assert not any('tenants' in r for r in routes), 'tenants route still present'
assert not any('document-shares' in r for r in routes), 'document-shares route still present'
print('routes ok')
"
```

Expected: prints route count and `routes ok`.

---

## Task 16: Run the ACL unit tests

**Files:** none

- [ ] **Step 1: Run tests**

```bash
cd backend && python -m pytest tests/test_acl.py -v
```

Expected: 7 tests pass. (These were created in Plan 1 and should still pass since the helpers haven't changed.)

- [ ] **Step 2: Quick smoke against any existing tests that might catch regressions**

```bash
cd backend && python -m pytest tests/ --collect-only 2>&1 | tail -5
```

Expected: pytest can collect the test suite without errors. We don't run the full suite here — that's Plan 5. We just check that test collection works.

---

## Task 17: Final verification and commit

**Files:** none (verification + commit)

- [ ] **Step 1: Confirm zero `tenant_id` references in `backend/app/`**

```bash
grep -rln "tenant_id" backend/app/ \
  --include="*.py" \
  | grep -v "alembic/versions/_archived"
```

Expected: empty output. Any remaining match must be cleaned up before committing.

- [ ] **Step 2: Confirm zero references to deleted classes**

```bash
grep -rn "Tenant\b\|RoleAssignment\b\|DocumentShare\b\|TeamInvitation\b" backend/app/ \
  --include="*.py" \
  | grep -v "alembic/versions/_archived" \
  | grep -v "# tenant" \
  | grep -v "no_tenant"
```

Expected: zero matches. Any remaining matches are stale references and must be removed.

- [ ] **Step 3: Stage all changes**

```bash
git add backend/app/api/v1/
git add backend/app/api/dependencies.py backend/app/api/async_dependencies.py
git add backend/app/services/
git add backend/app/schemas/
git add backend/app/core/auth/
```

- [ ] **Step 4: Verify staged files**

```bash
git status --short
```

Expected: many M (modified) and several D (deleted) entries. No untracked files of significance.

- [ ] **Step 5: Commit**

```bash
git commit -m "$(cat <<'EOF'
refactor(api): replace tenant filter with role-based ACL across backend

Implements Plan 2 of the multi-tenancy removal refactor.

Endpoint files DELETED entirely:
  - api/v1/tenants.py
  - api/v1/document_shares.py
  - api/v1/sharing_insights.py
  - api/v1/teams.py
  - api/v1/document_acl.py

Service files DELETED entirely:
  - services/document_share_service.py
  - services/document_acl_service.py
  - services/sharing_insights_service.py
  - any tenant_service.py / role_service.py / permission_service.py

Endpoint files REFACTORED (canonical pattern: get_current_tenant →
get_current_user, Model.tenant_id == X → filter_visible_to_user):
  - documents.py, connectors.py (+ require_role ADMIN), emma.py,
    weaviate.py, data_learning.py, prompts.py, search.py, dashboard.py,
    admin.py, channels.py, agents.py
  - all remaining endpoint files in api/v1/ (~25 more)

Service files REFACTORED:
  - weaviate_client.py, async_document_service.py,
    async_signature_service.py, document_service.py, site_guest_service.py
  - all remaining service files in services/ and subdirectories

Pydantic schemas:
  - document.py, unified_document.py: add roles[] field
  - connector.py: add default_document_roles[] field
  - drop document_share.py, document_acl.py schemas

Auth dependencies:
  - dependencies.py / async_dependencies.py: drop get_current_tenant
    and require_tenant
  - core/auth/base.py: drop tenant_id from UserProfile

After this commit the backend imports cleanly and the FastAPI app boots,
but the application is still not runnable end-to-end because the
microservices (Plan 3) still expect tenant_id in their payloads.

Spec: docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
Plan: docs/superpowers/plans/2026-04-06-remove-tenancy-02-backend-api.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Verify the commit**

```bash
git log -1 --stat
git log --oneline -5
```

Expected: shows the new commit and its parents, including Plan 1 and the spec.

---

## Task 18: Self-check before handing off to Plan 3

**Files:** none

- [ ] **Step 1: Smoke test imports**

```bash
cd backend && python -c "
from app.main import app
from app.api.v1 import router
from app.core.auth.acl import filter_visible_to_user, require_role, EVERYONE_ROLE
from app.db.models import Document, Connector, User
from app.schemas.document import DocumentCreate, DocumentResponse
from app.schemas.connector import ConnectorCreate
print('all imports ok')
print('Document.roles:', Document.roles.type)
print('Connector.default_document_roles:', Connector.default_document_roles.type)
print('routes count:', len(app.routes))
"
```

Expected: prints `all imports ok` and the type info.

- [ ] **Step 2: Confirm no residual tenant references in backend/app/**

```bash
grep -rln "tenant_id\|TenantAuthConfig\|RoleAssignment" backend/app/ \
  --include="*.py" \
  | grep -v "alembic/versions/_archived"
```

Expected: empty.

- [ ] **Step 3: Confirm backend/microservices/ STILL has tenant_id**

```bash
grep -rln "tenant_id" backend/microservices/ --include="*.py" | head -5
```

Expected: NON-empty. The microservices are NOT touched in Plan 2 — they get refactored in Plan 3. If this check returns empty, something is wrong.

- [ ] **Step 4: Mark Plan 2 complete**

Plan 2 is done. The backend API and service layers are refactored. The next plan handles microservices.

**The application backend imports and starts**, but it cannot serve real requests yet because:
- Microservices (Plan 3) still expect `tenant_id` in their payloads, so calls to KTS, Emma, Weaviate, etc. will fail.
- Frontend (Plan 4) still sends `X-Tenant-ID` headers and expects tenant fields in responses.

This intermediate state is intentional. The atomic deploy in Plan 5 brings everything online together.

**Next plan:** `docs/superpowers/plans/2026-04-06-remove-tenancy-03-microservices.md`
