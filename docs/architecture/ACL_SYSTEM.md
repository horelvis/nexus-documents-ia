# ACL System — Role-Based Access Control

**Architecture doc for NouxCubeIA (single-tenant, on-premise)**
Last updated: 2026-04-22 (post-tenancy refactor, domain field removed)

---

## 1. Overview

NouxCubeIA uses a **claims-based, role-based access control** model. Every document in the system carries a `roles: ARRAY(String)` column. A user can see a document if and only if their role set intersects the document's role set — or the document is tagged with the reserved sentinel `EVERYONE`, which grants visibility to any authenticated user regardless of their roles.

There is no tenant isolation layer. Multi-tenancy was fully removed on 2026-04-21 (commit 973f0797). There is no `document_acls` join table, no per-user ACL rows, no `DocumentACLService`, and no per-request tenant resolution. The entire permission check collapses to one SQLAlchemy clause: `Document.roles @> ['EVERYONE'] OR Document.roles && user_roles`. The same semantics are replicated in Weaviate via a `roles` TEXT_ARRAY property and a `contains_any` filter, and in the TrustGraph (FalkorDB) via a `user` property on every `:Node`, `:Literal`, and `:Rel` (currently collapsed to the `EVERYONE` sentinel, pending the full per-role graph query wave).

Roles are sourced from KeyCloak. They flow through the JWT as group memberships, are translated to canonical uppercase identifiers by `AuthProvider.map_groups_to_roles()` using `backend/app/config/role_mapping.yaml`, and are attached to every request as `UserProfile.roles`. When the main API calls a downstream microservice, it forwards the resolved roles as the `X-User-Roles` HTTP header.

---

## 2. Data Model

### 2.1 `Document` (table: `documents`)

```python
roles = Column(ARRAY(String), nullable=False, server_default="{EVERYONE}")
```

- Default: `["EVERYONE"]` — newly created documents are readable by all authenticated users until explicitly restricted.
- A GIN index is maintained: `idx_documents_roles` (`roles`, `postgresql_using='gin'`).
- No `tenant_id` column. No separate ACL join table.

### 2.2 `IndexedDocument` (table: `indexed_documents`)

```python
roles = Column(ARRAY(String), nullable=False, server_default="{EVERYONE}")
```

Documents ingested from external connectors (Alfresco, SharePoint, OneDrive, Google Drive). Same semantics as `Document.roles`. A GIN index: `idx_indexed_documents_roles`.

The table still carries legacy columns from the pre-refactor multi-tenant model (`is_tenant_public`, `shared_with_users`, `shared_with_groups`). These are dead columns — no code path reads or writes them. They will be dropped by a follow-up migration. The authoritative ACL is `roles`.

### 2.3 `Connector` (table: `connectors`)

```python
default_document_roles = Column(ARRAY(String), nullable=False, server_default="{EVERYONE}")
```

When a connector sync job indexes a new document, `default_document_roles` is copied to `IndexedDocument.roles`. This allows admins to configure per-connector baseline visibility (e.g., a SharePoint connector for the Legal department defaults to `["LEGAL", "ADMIN"]` rather than `["EVERYONE"]`).

### 2.4 `DocumentACL` and `DocumentACLAudit` (tables: `document_acls`, `document_acl_audits`)

These tables exist in the database schema from a pre-refactor era but are not used by any active code path. No service reads from or writes to them. They represent a granular per-document ACL design that was superseded by the simpler `roles` array model. They will be dropped by a future migration.

### 2.5 Weaviate: `Nouxcube_documents`, `Nouxcube_knowledge`, `Nouxcube_visual`

Each Weaviate object has a `roles` property of type `TEXT_ARRAY`:

```
Property: roles
Type: TEXT_ARRAY
Description: KeyCloak roles allowed to view (plus EVERYONE sentinel)
```

The Weaviate schema does **not** use `acl_user_ids`, `acl_role_ids`, or `acl_everyone` as separate properties. The `DocumentCreate` Pydantic schema (`weaviate-service/app/schemas/weaviate.py`) defines `acl_user_ids`, `acl_role_ids`, and `acl_everyone` as input fields for backwards compatibility with old callers, but the `add_document` method in `WeaviateService` extracts `document.roles` (falling back to `[EVERYONE_ROLE]`) and stores only the unified `roles` array as a Weaviate property. The `acl_*` input fields are therefore inert at the Weaviate layer.

At query time, the `SearchRequest` schema carries `user_roles: List[str]` and `is_admin: bool`. These feed the `_roles_filter()` function.

### 2.6 TrustGraph (FalkorDB): `:Node`, `:Literal`, `:Rel`

Every node in the knowledge graph carries a `user` property and a `collection` property used as scope qualifiers:

```cypher
MERGE (n:Node {uri: $uri, user: $user, collection: $collection})
MERGE (:Literal {value: $value, user: $user, collection: $collection})
MERGE (s)-[r:Rel {uri: $p_uri, user: $user, collection: $collection}]->(o)
```

Currently, the `_graph_scope()` helper in `knowledge-tree-service/app/api/triples.py` collapses all role inputs to the `EVERYONE` sentinel unconditionally:

```python
def _graph_scope(user_roles: List[str]) -> str:
    return EVERYONE_ROLE
```

This means all graph triples are written under `user=EVERYONE` and are visible to all authenticated users. A future wave will rename the property to `role`, expand the query layer to accept `role IN $allowed_roles`, and enforce per-role graph isolation.

---

## 3. The Core Filter

### 3.1 `filter_visible_to_user(query, user)`

**File**: `backend/app/core/auth/acl.py`

```python
EVERYONE_ROLE = "EVERYONE"

def build_role_filter_clause(user: UserProfile) -> BooleanClauseList:
    from app.db.models import Document
    clauses = [Document.roles.contains([EVERYONE_ROLE])]
    if user.roles:
        clauses.append(Document.roles.overlap(list(user.roles)))
    return or_(*clauses)

def filter_visible_to_user(query, user: UserProfile):
    return query.filter(build_role_filter_clause(user))
```

The SQL emitted is equivalent to:

```sql
WHERE (documents.roles @> ARRAY['EVERYONE'])
   OR (documents.roles && ARRAY['LEGAL', 'SALES'])   -- when user has roles
```

The `@>` operator (PostgreSQL array contains) matches documents tagged `EVERYONE`. The `&&` operator (array overlap) matches documents whose role set intersects the user's role set. Only one of these branches needs to be true.

If `user.roles` is empty (e.g., a new user not yet assigned to any KeyCloak group), the second clause is omitted and only `EVERYONE` documents are visible.

### 3.2 Call sites

`filter_visible_to_user` is called unconditionally before returning results. Key call sites:

| File | Context |
|------|---------|
| `backend/app/api/v1/documents.py` | Document list and search endpoints |
| `backend/app/services/async_document_service.py` | Folder listing, document count, bulk queries |
| `backend/app/services/document_service.py` | Sync document queries |
| `backend/app/services/unified_document_query.py` | Cross-service unified search |
| `backend/app/services/search_service.py` | Full-text search pre-filter |
| `backend/app/services/query_optimizer.py` | Query optimization paths |
| `backend/app/api/v1/entities.py` | Entity queries scoped to visible docs |
| `backend/app/api/v1/notebooks.py` | Notebook document access |
| `backend/app/api/v1/document_categorization.py` | Classification queries |
| `backend/app/api/v1/analysis_queue.py` | Analysis job visibility |
| `backend/app/api/v1/document_insights.py` | Insight queries |
| `backend/app/api/v1/classification.py` | Classification visibility |

There is no code path that queries `Document` or `IndexedDocument` for business results without going through `filter_visible_to_user`. Document fetch by ID goes through the same filter before returning a row (returning 404 rather than 403 to avoid leaking existence information).

---

## 4. Role Sources: KeyCloak to UserProfile

### 4.1 Flow

```
Browser / Client
    │
    │  Bearer JWT (KeyCloak-signed)
    ▼
Main API (port 8000)
    │
    │  get_current_user_async()
    │    1. Validate JWT via AuthProviderFactory (OIDC/SAML/LDAP)
    │    2. Extract identity.groups from token claims
    │    3. provider.map_groups_to_roles(identity.groups)
    │    4. Look up User row by sso_external_id
    │    5. Build UserProfile(sub, email, name, roles)
    ▼
UserProfile.roles  ←  canonical uppercase identifiers, e.g. ["LEGAL", "ADMIN"]
```

### 4.2 `role_mapping.yaml`

**File**: `backend/app/config/role_mapping.yaml`

```yaml
group_to_role:
  "/Administradores": ADMIN
  "/Comercial": SALES
  "/Departamento Legal": LEGAL
  "/Recursos Humanos": HR
  "/Finanzas": FINANCE
  "/Médicos": MEDICAL
```

This is the only file in the codebase where Spanish group names appear. Adding a new role requires:
1. Create the group in KeyCloak admin UI.
2. Add one line to this YAML.
3. Restart the backend service (no code change required).

### 4.3 `map_groups_to_roles()`

Implemented on `AuthProvider` base class (`backend/app/core/auth/base.py`):

```python
def map_groups_to_roles(self, groups: List[str]) -> List[str]:
    mapping = self.config.get("group_role_mapping", {})
    roles = []
    for group in groups:
        if group in mapping:
            mapped = mapping[group]
            if isinstance(mapped, list):
                roles.extend(mapped)
            else:
                roles.append(mapped)
    return list(set(roles))  # deduplicated
```

Groups not listed in the YAML are silently dropped — they do not become roles. This is intentional: only explicitly mapped groups grant application roles.

### 4.4 `UserProfile`

**File**: `backend/app/core/auth/base.py`

```python
@dataclass(frozen=True)
class UserProfile:
    sub: str          # user UUID (matches User.id)
    email: str
    name: Optional[str] = None
    roles: List[str] = field(default_factory=list)
```

`UserProfile` is immutable and request-scoped. The `EVERYONE` sentinel is never assigned to a user's role list — `_build_profile()` in `async_dependencies.py` defensively strips it:

```python
roles = [r for r in sso_roles if r != "EVERYONE"]
```

Superusers (`User.is_superuser = True`) always receive `ADMIN` in their role list, even if the KeyCloak group mapping does not include it.

---

## 5. Inter-Service Propagation

### 5.1 Header protocol

Microservices do not validate JWTs. The main API is the JWT trust boundary. After resolving `UserProfile`, it forwards the user context to downstream services as:

| Header | Format | Example |
|--------|--------|---------|
| `X-User-Id` | UUID string | `a060f046-9992-4d1a-87c4-fa5c6f8c066c` |
| `X-User-Roles` | Comma-separated roles | `LEGAL,ADMIN` |
| `X-API-Key` | Service API key | `<from MICROSERVICES_API_KEY env var>` |

### 5.2 Injection points in the main API

**`BaseServiceClient._build_headers()`** (`backend/app/clients/base.py`):
```python
if user_id:
    headers["X-User-ID"] = str(user_id)
if user_roles:
    headers["X-User-Roles"] = ",".join(user_roles)
```
All service clients in `backend/app/clients/` inherit from this base. Any call to a microservice that passes `user_roles` gets the `X-User-Roles` header automatically.

**Manual proxy calls** (e.g., `backend/app/api/v1/threads.py`):
```python
def _proxy_headers(current_user: UserProfile) -> dict:
    return {
        "X-API-Key": settings.MICROSERVICES_API_KEY or "",
        "X-User-ID": current_user.sub,
        "X-User-Roles": ",".join(current_user.roles or []),
    }
```

**Weaviate search calls** (`backend/app/services/async_document_service.py`):
```python
headers = {
    "X-API-Key": settings.MICROSERVICES_API_KEY,
    "X-User-Roles": ",".join(self.user_roles),
}
```

### 5.3 Consumption in microservices

Every microservice has an `app/core/auth_headers.py` file (replicated, not shared, because there is no cross-service Python package). It provides:

```python
async def extract_user_roles(
    x_user_roles: Optional[str] = Header(default=None, alias="X-User-Roles"),
) -> List[str]:
    if not x_user_roles:
        return []
    return [r.strip() for r in x_user_roles.split(",") if r.strip()]

async def extract_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
) -> Optional[str]:
    return x_user_id

def allowed_roles(user_roles: List[str]) -> List[str]:
    return list({*user_roles, EVERYONE_ROLE})
```

The `allowed_roles()` helper is the key function: it adds the `EVERYONE` sentinel to the caller's role list so that a single `contains_any` Weaviate filter covers both public and role-restricted documents. Microservices use `extract_user_roles` as a FastAPI dependency on their endpoints.

Services with `auth_headers.py`:
- `weaviate-service`
- `knowledge-tree-service`
- `document-forge-service`
- `mcp-google-drive-server`
- `mcp-onedrive-server`
- `mcp-alfresco-server`

### 5.4 API key authentication

All inter-service calls also carry `X-API-Key`. Microservice endpoints validate this key via `verify_api_key` before processing any request — including before reading the role headers. A missing or invalid API key returns 401 regardless of role headers. This prevents unauthenticated callers from constructing arbitrary `X-User-Roles` headers.

---

## 6. TrustGraph ACL (FalkorDB)

The TrustGraph stores knowledge graph triples. Every `:Node`, `:Literal`, and `:Rel` is scoped by `(user, collection)` properties. The `user` property conceptually maps to an access scope.

**Current state**: `_graph_scope()` in `knowledge-tree-service/app/api/triples.py` returns `EVERYONE_ROLE` unconditionally for all callers. All writes use `user=EVERYONE`; all reads query `user=EVERYONE`. The graph is effectively public to all authenticated users.

**Planned state**: When the per-role graph isolation wave lands, `_graph_scope()` will be replaced with a Cypher filter pattern: `WHERE n.role IN $allowed_roles` where `$allowed_roles = allowed_roles(user_roles)`. The property will be renamed from `user` to `role` on `:Node` and `:Literal`. `:Rel` edges will inherit scope from their endpoint nodes, so no property rename is needed there.

**Impact on graph_rag**: The `graph_rag` tool and `smart_search` tool call `knowledge-tree-service` via `POST /triples/query`, passing `user_roles` in the request body. When per-role isolation activates, documents with restricted roles will produce graph triples only visible to authorized callers, maintaining ACL consistency between the vector store and the graph store.

---

## 7. Weaviate ACL

### 7.1 `_roles_filter()` function

**File**: `backend/microservices/weaviate-service/app/services/weaviate_service.py`

```python
def _roles_filter(user_roles: List[str]):
    """Build the single-clause roles ACL filter."""
    return weaviate.classes.query.Filter.by_property("roles").contains_any(
        allowed_roles(user_roles or [])
    )
```

`allowed_roles(user_roles)` returns `user_roles ∪ {EVERYONE}`. The `contains_any` filter returns any object whose `roles` array contains at least one value from the input list. This is the Weaviate equivalent of the PostgreSQL `&&` (overlap) operator with the `EVERYONE` sentinel included.

### 7.2 Filter application in search

```python
if is_admin:
    combined_filters = None          # admin bypass: no ACL filter
else:
    combined_filters = _roles_filter(request_roles)
```

Additional filters (folder path, semantic type, person, date range) are AND-composed into `combined_filters`. The ACL filter is always the first component, so every search result set is guaranteed to be ACL-filtered before enrichment filters narrow it further.

### 7.3 Document indexing

`add_document()` extracts `roles` from the `DocumentCreate` input:

```python
doc_roles = getattr(document, 'roles', None) or [EVERYONE_ROLE]
base_properties = {
    ...
    "roles": doc_roles,
    ...
}
```

If the caller does not set `roles` (e.g., an older integration), the default is `[EVERYONE_ROLE]`. The `acl_user_ids`, `acl_role_ids`, and `acl_everyone` fields on `DocumentCreate` are not stored in Weaviate. They are input-only fields retained for schema compatibility.

### 7.4 ACL update after indexing

`update_document_acl(document_id, collection_name, roles)` updates only the `roles` property on all Weaviate objects matching a `document_id`. This is called when an admin changes a document's role list after initial indexing.

### 7.5 Admin bypass

The `is_admin` flag in `SearchRequest` causes the entire ACL filter to be skipped (`combined_filters = None`). This flag is set by the main API only when the calling `UserProfile` has the `ADMIN` role. It is not user-settable from client requests.

---

## 8. `EVERYONE` Wildcard

`EVERYONE` is a reserved sentinel string with a single, precise meaning:

> A document tagged with `EVERYONE` in its `roles` array is visible to every authenticated user, regardless of what roles they carry in their JWT.

Properties of `EVERYONE`:

- **Document-side only**: `EVERYONE` appears in `Document.roles`, `IndexedDocument.roles`, and Weaviate `roles` properties. It is never assigned to a `UserProfile`.
- **Default value**: Both `Document.roles` and `IndexedDocument.roles` default to `{EVERYONE}` at the database level (`server_default="{EVERYONE}"`). Newly uploaded or indexed documents are public until explicitly restricted.
- **Not an endpoint gate**: `require_role()` raises `ValueError` if called with `EVERYONE` as an argument. Endpoints open to all authenticated users use `Depends(get_current_user)` directly.
- **Weaviate equivalent**: The `allowed_roles()` helper always appends `EVERYONE` to the user's role list before calling `contains_any`. This means one filter covers both `EVERYONE` documents and role-specific documents.

---

## 9. Connector Defaults

When an admin creates a connector, they may specify `default_document_roles`:

```python
# backend/app/api/v1/connectors.py
connector = Connector(
    ...
    default_document_roles=connector_data.default_document_roles or ["EVERYONE"],
)
```

Default if not specified: `["EVERYONE"]`.

When the connector sync job runs and creates an `IndexedDocument`, the connector's `default_document_roles` is copied to `IndexedDocument.roles`. This allows:

- A Legal department SharePoint connector to default to `["LEGAL", "ADMIN"]` — documents visible only to Legal and Admin users.
- A public knowledge base connector to use `["EVERYONE"]` — documents visible to all authenticated users.
- A Medical connector to default to `["MEDICAL", "ADMIN"]`.

After indexing, an admin can override individual document roles by calling the Weaviate `update_document_acl` endpoint (which updates both the PostgreSQL `roles` column and the Weaviate `roles` property).

---

## 10. Admin Bypass and `require_role()`

### 10.1 `require_role()` dependency

**File**: `backend/app/core/auth/acl.py`

```python
def require_role(*allowed_roles: str):
    def _dependency(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(status_code=403, detail="forbidden: missing required role")
        return user
    return _dependency
```

Usage:

```python
# Gate an endpoint to ADMIN users only:
@router.delete("/admin/user/{id}")
async def delete_user(user: UserProfile = Depends(require_role("ADMIN"))):
    ...

# Gate to either LEGAL or ADMIN:
@router.get("/legal/contracts")
async def list_contracts(user: UserProfile = Depends(require_role("LEGAL", "ADMIN"))):
    ...
```

Endpoints in `backend/app/api/v1/admin.py` and `backend/app/api/v1/prompts.py` use `require_role("ADMIN")` to restrict system administration operations. Site guest management uses `require_role("ADMIN")`.

### 10.2 Weaviate `is_admin` bypass

When the main API builds a `SearchRequest` to forward to the weaviate-service, it sets `is_admin=True` if the resolved `UserProfile` has the `ADMIN` role. The weaviate-service then skips the `_roles_filter()` entirely and returns results from all documents regardless of their `roles` array.

### 10.3 `is_superuser` flag

`User.is_superuser` in the database is an additional mechanism. When `_build_profile()` in `async_dependencies.py` resolves a superuser, it unconditionally appends `ADMIN` to their role list even if the KeyCloak group mapping does not include it. This provides a break-glass admin access path independent of KeyCloak group assignments.

---

## 11. Debugging Cheatsheet

### 11.1 Inspect a user's effective roles

```sql
-- Check a user's SSO groups (raw from KeyCloak):
SELECT id, email, sso_external_id, sso_groups, is_superuser
FROM users
WHERE email = 'user@example.com';

-- sso_groups is a JSONB array of raw KeyCloak group paths.
-- The backend maps these to canonical roles via role_mapping.yaml.
-- Superusers get ADMIN unconditionally.
```

At runtime, use the `/api/v1/auth/me` endpoint (authenticated) to see the resolved `UserProfile` including roles.

### 11.2 Inspect a document's roles

```sql
-- For uploaded documents:
SELECT id, title, roles FROM documents WHERE id = '<uuid>';

-- For connector-indexed documents:
SELECT id, title, roles, connector_id FROM indexed_documents WHERE id = '<uuid>';
```

In Weaviate:
```python
# Via weaviate-service API (internal, port 8007):
GET /documents/{document_id}
# Returns document metadata including roles property.
```

### 11.3 Understand why a document is not visible

Run the equivalent of `filter_visible_to_user` manually:

```sql
-- Does the document have EVERYONE?
SELECT roles @> ARRAY['EVERYONE'] AS is_public
FROM documents WHERE id = '<doc_uuid>';

-- Does it overlap with the user's roles?
SELECT roles && ARRAY['LEGAL', 'ADMIN'] AS user_can_see
FROM documents WHERE id = '<doc_uuid>';
```

If both are false, the document is not visible to a user with those roles.

### 11.4 Audit `default_document_roles` for a connector

```sql
SELECT id, name, connector_type, default_document_roles
FROM connectors
ORDER BY created_at DESC;
```

### 11.5 Check Weaviate ACL for a document chunk

```bash
# Query via weaviate-service (microservice port 8007, API key required):
curl -X GET "http://localhost:8007/documents/search" \
  -H "X-API-Key: $MICROSERVICES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "title of the document",
    "user_roles": ["LEGAL"],
    "is_admin": false,
    "limit": 5
  }'
```

Admin bypass (returns all documents regardless of roles):
```bash
curl -X GET "http://localhost:8007/documents/search" \
  -H "X-API-Key: $MICROSERVICES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "title of the document",
    "user_roles": [],
    "is_admin": true,
    "limit": 5
  }'
```

---

## 12. Key Files

| File | Purpose |
|------|---------|
| `backend/app/core/auth/acl.py` | `filter_visible_to_user()`, `build_role_filter_clause()`, `require_role()`, `EVERYONE_ROLE` constant |
| `backend/app/core/auth/base.py` | `UserProfile` dataclass, `AuthProvider.map_groups_to_roles()` |
| `backend/app/api/async_dependencies.py` | `get_current_user_async()` — JWT validation, SSO group resolution, `UserProfile` construction |
| `backend/app/api/dependencies.py` | Legacy sync `get_current_user()` — Clerk SaaS path (deprecated) |
| `backend/app/config/role_mapping.yaml` | KeyCloak group path → canonical role name mapping |
| `backend/app/db/models.py` | `Document.roles`, `IndexedDocument.roles`, `Connector.default_document_roles` |
| `backend/app/clients/base.py` | `_build_headers()` — injects `X-User-Roles` into inter-service calls |
| `backend/microservices/weaviate-service/app/services/weaviate_service.py` | `_roles_filter()`, `add_document()`, `update_document_acl()`, `hybrid_search()` |
| `backend/microservices/weaviate-service/app/core/auth_headers.py` | `extract_user_roles()`, `allowed_roles()`, `EVERYONE_ROLE` (weaviate-service copy) |
| `backend/microservices/weaviate-service/app/schemas/weaviate.py` | `DocumentCreate` (with `acl_*` fields — inert at Weaviate layer), `SearchRequest` |
| `backend/microservices/knowledge-tree-service/app/api/triples.py` | `_graph_scope()` — currently collapses all roles to `EVERYONE` |
| `backend/microservices/knowledge-tree-service/app/services/triple_store.py` | `:Node`, `:Literal`, `:Rel` MERGE with `user` property |
| `backend/microservices/knowledge-tree-service/app/core/auth_headers.py` | `extract_user_roles()`, `allowed_roles()` (knowledge-tree copy) |
| `backend/app/api/v1/admin.py` | Admin-only endpoints using `require_role("ADMIN")` |
| `backend/app/api/v1/connectors.py` | Connector creation with `default_document_roles` |

---

## 13. Common Patterns — Code Snippets

### 13.1 Get documents visible to the current user

```python
from sqlalchemy import select
from app.core.auth.acl import filter_visible_to_user
from app.db.models import Document

async def list_my_documents(db: AsyncSession, user: UserProfile) -> list[Document]:
    stmt = select(Document).order_by(Document.created_at.desc())
    stmt = filter_visible_to_user(stmt, user)
    result = await db.execute(stmt)
    return result.scalars().all()
```

### 13.2 Gate an endpoint to a specific role

```python
from fastapi import APIRouter, Depends
from app.core.auth.acl import require_role
from app.core.auth.base import UserProfile

router = APIRouter()

@router.get("/legal/contracts")
async def list_contracts(
    db: AsyncSession = Depends(get_async_db),
    user: UserProfile = Depends(require_role("LEGAL", "ADMIN")),
):
    stmt = select(Document).where(Document.category == "contract")
    stmt = filter_visible_to_user(stmt, user)
    ...
```

### 13.3 Check if a specific document is visible to a user

```python
from sqlalchemy import select, exists
from app.core.auth.acl import build_role_filter_clause
from app.db.models import Document

async def can_user_see_document(
    db: AsyncSession,
    user: UserProfile,
    document_id: uuid.UUID,
) -> bool:
    clause = build_role_filter_clause(user)
    stmt = select(exists().where(
        Document.id == document_id,
        clause,
    ))
    result = await db.execute(stmt)
    return result.scalar()
```

### 13.4 Set document roles at creation time

```python
# Public document (default):
doc = Document(title="Annual Report", ..., roles=["EVERYONE"])

# Restricted to Legal and Admin:
doc = Document(title="Legal Brief", ..., roles=["LEGAL", "ADMIN"])

# Restricted to HR only:
doc = Document(title="Employee File", ..., roles=["HR"])
```

### 13.5 Build a Weaviate search request with roles

```python
from app.schemas.weaviate import SearchRequest

# Inside a service that knows the user's roles:
search_req = SearchRequest(
    query="contrato de trabajo",
    user_roles=["LEGAL", "ADMIN"],  # from UserProfile.roles
    is_admin=("ADMIN" in user.roles),
    limit=10,
    search_type="hybrid",
)

# The weaviate-service will apply:
# Filter.by_property("roles").contains_any(["LEGAL", "ADMIN", "EVERYONE"])
```

### 13.6 Forward roles to a microservice from the main API

```python
headers = {
    "X-API-Key": settings.MICROSERVICES_API_KEY,
    "X-User-Id": user.sub,
    "X-User-Roles": ",".join(user.roles),  # e.g. "LEGAL,ADMIN"
}
async with httpx.AsyncClient() as client:
    response = await client.post(
        f"{settings.WEAVIATE_SERVICE_URL}/documents/search",
        json=search_payload,
        headers=headers,
    )
```

### 13.7 Consume roles in a microservice endpoint

```python
from fastapi import APIRouter, Depends
from app.core.auth_headers import extract_user_roles, extract_user_id, allowed_roles

router = APIRouter()

@router.post("/query")
async def query_something(
    user_roles: list[str] = Depends(extract_user_roles),
    user_id: str | None = Depends(extract_user_id),
):
    # allowed_roles(user_roles) = user_roles ∪ {"EVERYONE"}
    visible_roles = allowed_roles(user_roles)
    # Use visible_roles to filter results...
```

---

## 14. Architectural Notes and Known Gaps

**`DocumentACL` table**: The `document_acls` and `document_acl_audits` tables exist in the database but are unused. No migration has dropped them yet. They do not affect runtime behavior — no code reads from them.

**TrustGraph role isolation**: The `user` property on `:Node` and `:Literal` currently stores `EVERYONE` for all triples. This means the graph does not enforce per-role access today. The planned fix (property rename `user` → `role`, query expansion) is tracked as a future wave. Until then, all authenticated users see all graph triples through `graph_rag` and `smart_search`.

**Weaviate `acl_*` fields**: `DocumentCreate.acl_user_ids`, `acl_role_ids`, and `acl_everyone` are inert. They are parsed by the Pydantic model but not stored in Weaviate. The authoritative ACL property is `roles`. The `acl_*` fields should be removed from `DocumentCreate` in a future cleanup.

**`X-Tenant-Id` header**: The CORS middleware still lists `X-Tenant-Id` in `allow_headers`. This is a CORS configuration artifact from the multi-tenant era. It does not affect backend behavior — no endpoint reads this header. It will be removed in a future cleanup commit.

**Legacy SharePoint/OneDrive connector configs**: Some `source_metadata` JSONB payloads in `IndexedDocument` may contain a `tenant_id` key originating from Microsoft Graph API metadata (SharePoint site identifier, not NouxCubeIA tenancy). This is Microsoft's terminology for their tenant concept and is unrelated to the removed NouxCubeIA multi-tenancy model.

**Role identifiers are case-sensitive uppercase strings**: `LEGAL` and `legal` are different values. All canonical role identifiers in `role_mapping.yaml` are uppercase. Document `roles` arrays should always use uppercase. Lowercase role values in `Document.roles` will not match against `UserProfile.roles` and will effectively make those documents invisible to all non-admin users.
