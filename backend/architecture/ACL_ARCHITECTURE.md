# ACL (Access Control List) Architecture - NexusDocs360

## Overview

NexusDocs360 implements document-level Access Control Lists (ACL) across all services to ensure that users can only access documents they have permission to view. This document describes the ACL architecture, data flow, and implementation details.

## Table of Contents

1. [Permission Model](#permission-model)
2. [Permission Flow Diagram](#permission-flow-diagram)
3. [Data Sources](#data-sources)
4. [Service Integration](#service-integration)
5. [Security Considerations](#security-considerations)

---

## Permission Model

### Grantee Types

Documents can be shared with three types of grantees:

| Type | Description | Example |
|------|-------------|---------|
| `user` | Specific user ID | Share with "john@company.com" |
| `role` | Role-based access | Share with "Legal Department" role |
| `everyone` | All tenant users | Make document visible to entire organization |

### Permission Hierarchy

Access is evaluated in the following order (first match wins):

```
1. OWNER         → Document creator always has full access
2. ADMIN         → Tenant admins bypass ACL checks
3. USER ACL      → Explicit user permission (user_id in acl_user_ids)
4. ROLE ACL      → Role-based permission (any role_id in acl_role_ids)
5. EVERYONE      → Document marked as accessible to all (acl_everyone=true)
6. LEGACY        → Documents without ACL (created_by is empty) - backwards compatibility
7. DENY          → No access if none of the above match
```

### Permission Levels

Each ACL entry can grant different permission levels:

| Permission | Description |
|------------|-------------|
| `can_view` | Read document content and metadata |
| `can_edit` | Modify document content |
| `can_delete` | Delete the document |
| `can_share` | Share document with other users/roles |

---

## Permission Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER REQUEST FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────┐     ┌──────────────┐     ┌─────────────────────────────────┐│
│   │  User    │────▶│   Frontend   │────▶│       Backend API               ││
│   │ (Browser)│     │  (Next.js)   │     │       (FastAPI)                 ││
│   └──────────┘     └──────────────┘     └───────────────┬─────────────────┘│
│                                                         │                   │
│                                         ┌───────────────▼───────────────┐  │
│                                         │     Authentication Layer      │  │
│                                         │  ┌─────────────────────────┐  │  │
│                                         │  │ • user_id (from Clerk)  │  │  │
│                                         │  │ • tenant_id             │  │  │
│                                         │  │ • user_role_ids (DB)    │  │  │
│                                         │  │ • is_admin flag         │  │  │
│                                         │  └─────────────────────────┘  │  │
│                                         └───────────────┬───────────────┘  │
│                                                         │                   │
│  ┌──────────────────────────────────────────────────────┼──────────────────┐│
│  │                    SERVICE LAYER                     │                  ││
│  │                                                      ▼                  ││
│  │  ┌─────────────────────────────────────────────────────────────────┐   ││
│  │  │                    SearchUserContext                            │   ││
│  │  │  {                                                              │   ││
│  │  │    user_id: "user-123",                                        │   ││
│  │  │    role_ids: ["role-legal", "role-analysts"],                  │   ││
│  │  │    is_admin: false                                             │   ││
│  │  │  }                                                              │   ││
│  │  └──────────────────────────┬──────────────────────────────────────┘   ││
│  │                             │                                          ││
│  │     ┌───────────────────────┼───────────────────────┐                  ││
│  │     │                       │                       │                  ││
│  │     ▼                       ▼                       ▼                  ││
│  │  ┌──────────┐        ┌──────────────┐        ┌──────────────┐         ││
│  │  │Weaviate  │        │Elasticsearch │        │  RAG/Emma    │         ││
│  │  │ Service  │        │   Service    │        │   Pipeline   │         ││
│  │  └────┬─────┘        └──────┬───────┘        └──────┬───────┘         ││
│  │       │                     │                       │                  ││
│  │       ▼                     ▼                       ▼                  ││
│  │  ┌──────────────────────────────────────────────────────────────────┐ ││
│  │  │                      ACL FILTER APPLIED                          │ ││
│  │  │                                                                  │ ││
│  │  │   WHERE (                                                        │ ││
│  │  │     owner_user_id = "user-123"          -- Owner                 │ ││
│  │  │     OR "user-123" IN acl_user_ids       -- Explicit user ACL     │ ││
│  │  │     OR "role-legal" IN acl_role_ids     -- Role-based ACL        │ ││
│  │  │     OR "role-analysts" IN acl_role_ids  -- Role-based ACL        │ ││
│  │  │     OR acl_everyone = true              -- Public within tenant  │ ││
│  │  │   )                                                              │ ││
│  │  │   AND tenant_id = "tenant-xyz"          -- Tenant isolation      │ ││
│  │  │                                                                  │ ││
│  │  └──────────────────────────────────────────────────────────────────┘ ││
│  │                                                                        ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                      FILTERED RESULTS                                │  │
│   │                                                                     │  │
│   │   Only documents matching ACL filter are returned to the user       │  │
│   │                                                                     │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Sources

### PostgreSQL (Source of Truth)

```sql
-- Document ACL Table
CREATE TABLE document_acls (
    id UUID PRIMARY KEY,
    document_id UUID REFERENCES documents(id),
    grantee_type VARCHAR(20),  -- 'user', 'role', 'everyone'
    grantee_id UUID,           -- user_id or role_id (NULL for 'everyone')
    can_view BOOLEAN DEFAULT TRUE,
    can_edit BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    can_share BOOLEAN DEFAULT FALSE,
    granted_by UUID REFERENCES users(id),
    granted_at TIMESTAMP,
    expires_at TIMESTAMP       -- Optional expiration
);

-- Document ACL Audit Table
CREATE TABLE document_acl_audit (
    id UUID PRIMARY KEY,
    document_id UUID,
    action VARCHAR(20),        -- 'grant', 'revoke', 'modify'
    grantee_type VARCHAR(20),
    grantee_id UUID,
    actor_id UUID,
    permissions JSONB,
    timestamp TIMESTAMP
);
```

### Weaviate (Vector Database)

```python
# Document properties in Weaviate collection
document_properties = [
    Property(name="owner_user_id", data_type=DataType.TEXT),
    Property(name="acl_user_ids", data_type=DataType.TEXT_ARRAY),
    Property(name="acl_role_ids", data_type=DataType.TEXT_ARRAY),
    Property(name="acl_everyone", data_type=DataType.BOOL),
]
```

### Elasticsearch

```json
{
  "mappings": {
    "properties": {
      "created_by": { "type": "keyword" },
      "acl_user_ids": { "type": "keyword" },
      "acl_role_ids": { "type": "keyword" },
      "acl_everyone": { "type": "boolean" }
    }
  }
}
```

---

## Service Integration

### 1. Backend API (FastAPI)

**File:** `backend/app/services/document_acl_service.py`

```python
class DocumentACLService:
    async def check_permission(
        self,
        document_id: str,
        user_id: str,
        permission: str,
        user_role_ids: List[str] = None
    ) -> bool:
        """
        Check if user has specific permission on document.

        Permission hierarchy:
        1. Owner always has all permissions
        2. Admin bypasses ACL
        3. Check user ACL entries
        4. Check role ACL entries
        5. Check 'everyone' flag
        """

    async def grant_permission(self, document_id, grantee_type, grantee_id, ...):
        """Grant permission and sync to Weaviate/Elasticsearch"""

    async def _sync_document_acl_to_weaviate(self, document_id):
        """Sync ACL changes to Weaviate"""

    async def _sync_acl_to_elasticsearch(self, document_id):
        """Sync ACL changes to Elasticsearch"""
```

### 2. Weaviate Service

**File:** `backend/microservices/weaviate-service/app/services/weaviate_service.py`

```python
def _build_document_access_filter(
    self,
    user_id: str,
    user_role_ids: List[str] = None,
    is_admin: bool = False
) -> Filter:
    """
    Build Weaviate filter for document-level ACL.

    Returns filter that matches documents where:
    - User is the owner (owner_user_id = user_id)
    - User has explicit ACL (user_id in acl_user_ids)
    - User's role has ACL (any role_id in acl_role_ids)
    - Document is shared with everyone (acl_everyone = true)
    """
    if is_admin:
        return None  # Admins see all

    return Filter.any_of([
        Filter.by_property("owner_user_id").equal(user_id),
        Filter.by_property("acl_user_ids").contains_any([user_id]),
        Filter.by_property("acl_role_ids").contains_any(user_role_ids or []),
        Filter.by_property("acl_everyone").equal(True),
    ])
```

### 3. Elasticsearch Service

**File:** `backend/microservices/elasticsearch-service/app/services/elasticsearch_service.py`

```python
def _build_acl_filter(
    self,
    user_id: str,
    role_ids: List[str] = None,
    is_admin: bool = False
) -> Dict:
    """
    Build Elasticsearch filter clause for ACL.
    """
    if is_admin:
        return None  # Admins see all

    should_clauses = [
        {"term": {"created_by": user_id}},
        {"term": {"acl_user_ids": user_id}},
        {"term": {"acl_everyone": True}},
    ]

    if role_ids:
        for role_id in role_ids:
            should_clauses.append({"term": {"acl_role_ids": role_id}})

    return {"bool": {"should": should_clauses, "minimum_should_match": 1}}
```

### 4. RAG Pipeline

**File:** `backend/microservices/weaviate-service/app/services/rag/rag_pipeline.py`

```python
async def process_query(
    self,
    query: str,
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[List[str]] = None,
    is_admin: bool = False,
    ...
) -> RAGResponse:
    """
    Process RAG query with ACL filtering.

    SECURITY: user_id and user_role_ids are used for:
    1. ACL filtering in document retrieval
    2. User-isolated semantic caching
    """
    # Retrieval with ACL
    retrieved_docs = await self.retriever.retrieve(
        query_analysis=query_analysis,
        tenant_id=tenant_id,
        user_id=user_id,
        user_role_ids=user_role_ids,
        is_admin=is_admin,
        ...
    )
```

### 5. Agent Tools (ExecutionContext)

**File:** `backend/microservices/weaviate-service/app/core/execution_context.py`

```python
# Context variables for thread-safe ACL propagation
_user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
_user_role_ids_var: ContextVar[Optional[list]] = ContextVar('user_role_ids', default=None)
_is_admin_var: ContextVar[bool] = ContextVar('is_admin', default=False)

def set_execution_context(
    tenant_id: str,
    user_id: Optional[str] = None,
    user_role_ids: Optional[list] = None,
    is_admin: bool = False,
    ...
):
    """Set execution context for all @ai_function tools"""

# Usage in @ai_function tools
@ai_function
async def semantic_search(query: str, tenant_id: str, ...) -> str:
    user_id = get_user_id()
    user_role_ids = get_user_role_ids()
    is_admin = get_is_admin()

    # Search with ACL filtering
    results = await service.search_with_acl(
        query=query,
        user_id=user_id,
        user_role_ids=user_role_ids,
        is_admin=is_admin
    )
```

### 6. Semantic Cache (User Isolation)

**File:** `backend/microservices/weaviate-service/app/services/rag/semantic_cache.py`

```python
def _cache_key(self, tenant_id: str, user_id: str, scope: str, query_hash: str) -> str:
    """
    Generate cache key with user isolation.

    SECURITY: user_id is included to prevent cross-user cache pollution.
    Each user has their own cache namespace.
    """
    return f"rag:cache:{tenant_id}:{user_id}:{scope}:{query_hash}"
```

---

## Security Considerations

### 1. Multi-Tenant Isolation

All queries MUST include `tenant_id` filtering. This is the first line of defense:

```python
# Every search includes tenant filter
filter_clauses = [{"term": {"tenant_id": self.tenant_id}}]
```

### 2. ACL Synchronization

When document permissions change in PostgreSQL:

```
PostgreSQL (Source of Truth)
    │
    ├──▶ Weaviate (sync via _sync_document_acl_to_weaviate)
    │
    └──▶ Elasticsearch (sync via _sync_acl_to_elasticsearch)
```

### 3. Cache Security

The semantic cache includes `user_id` in the cache key to prevent:
- Cross-user data exposure
- Cached responses leaking between users with different permissions

### 4. Admin Bypass

Admin users (`is_admin=True`) bypass ACL checks but still respect tenant isolation:

```python
if is_admin:
    return None  # No ACL filter, but tenant filter still applies
```

### 5. Audit Trail

All ACL changes are logged in `document_acl_audit` table:

```python
await self._log_acl_audit(
    document_id=document_id,
    action="grant",
    grantee_type=grantee_type,
    grantee_id=grantee_id,
    actor_id=current_user.id,
    permissions={"can_view": True, "can_edit": False, ...}
)
```

---

## Implementation Checklist

### Completed Fixes (January 2026)

- [x] **ExecutionContext**: Added `user_role_ids` and `is_admin` context variables
- [x] **Semantic Cache**: Added `user_id` to cache key for user isolation
- [x] **RAG Pipeline**: Propagates `user_role_ids` and `is_admin` to retriever
- [x] **Multi-Stage Retriever**: Passes ACL context to vector/BM25 searches
- [x] **Agent Tools**: Uses ExecutionContext for ACL in search functions
- [x] **SearchRequest Schema**: Added `is_admin` field
- [x] **Elasticsearch Facets/Analytics**: Added `user_context` parameter for ACL filtering
- [x] **EmmaQuery Schema**: Added `user_role_ids` and `is_admin` fields
- [x] **Emma API Endpoints**: Extract ACL from authenticated user (`/emma/query`, `/emma/query/stream`)
- [x] **EmmaCoordinator**: Propagates `user_role_ids` and `is_admin` to `set_execution_context()`
- [x] **EmmaService**: Passes ACL context to coordinator for both sync and streaming queries

### Pending Improvements

- [ ] **Direct Document Lookup**: Add ACL check to `get_document_by_id_across_collections`
- [ ] **Document Update Hooks**: Auto-invalidate cache when document ACL changes

---

## Related Files

| Component | File Path |
|-----------|-----------|
| ACL Service | `backend/app/services/document_acl_service.py` |
| Database Models | `backend/app/db/models.py` (DocumentACL, DocumentACLAudit) |
| Weaviate Service | `backend/microservices/weaviate-service/app/services/weaviate_service.py` |
| Elasticsearch Service | `backend/microservices/elasticsearch-service/app/services/elasticsearch_service.py` |
| RAG Pipeline | `backend/microservices/weaviate-service/app/services/rag/rag_pipeline.py` |
| Multi-Stage Retriever | `backend/microservices/weaviate-service/app/services/rag/multi_stage_retriever.py` |
| Semantic Cache | `backend/microservices/weaviate-service/app/services/rag/semantic_cache.py` |
| Execution Context | `backend/microservices/weaviate-service/app/core/execution_context.py` |
| Agent Search Tools | `backend/microservices/weaviate-service/app/agents/tools/search_tools.py` |
| Search Request Schema | `backend/microservices/weaviate-service/app/schemas/weaviate.py` |
| **Emma API Gateway** | `backend/app/api/v1/weaviate.py` (extracts ACL from user) |
| **Emma Query Schema** | `backend/microservices/weaviate-service/app/schemas/emma.py` |
| **Emma Coordinator** | `backend/microservices/weaviate-service/app/agents/emma_coordinator.py` |
| **Emma Service** | `backend/microservices/weaviate-service/app/services/emma_service.py` |
