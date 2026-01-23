# Modular Architecture - SaaS/On-Premise Separation

## Overview

This document describes the modular architecture implemented to cleanly separate SaaS and On-Premise deployment modes. The architecture allows the same codebase to support different deployment scenarios with different features, authentication providers, and ACL mechanisms.

## Problem Statement

The original codebase mixed SaaS and on-premise concerns:

| Issue | SaaS | On-Premise |
|-------|------|------------|
| Document tables | `documents` | `indexed_documents` |
| ACL mechanism | `DocumentACL` table | JSONB fields in IndexedDocument |
| Authentication | Clerk | OIDC/SAML |
| Billing | Stripe integration | None |
| Features | Signatures, Site Portal | Connectors (Alfresco, SharePoint) |

This mixing caused:
- Maintenance difficulty (changes to one mode could break the other)
- Unnecessary dependencies loaded
- Complex conditional logic throughout the codebase

## Solution: Modular Architecture

The solution separates concerns into independent **modules** that connect to a **shared core**.

```
backend/
├── core/                    # Shared core (always loaded)
│   └── acl/                 # ACL abstraction layer
│       ├── base.py          # ACLProvider ABC, Permission, PermissionSet
│       └── factory.py       # ACLProviderFactory
│
├── modules/
│   ├── on_premise/          # On-Premise module
│   │   ├── module.py        # OnPremiseModule registration
│   │   ├── acl/             # JSONB ACL provider
│   │   └── api/             # On-premise-specific APIs
│   │
│   └── saas/                # SaaS module
│       ├── module.py        # SaaSModule registration
│       ├── acl/             # Table ACL provider
│       └── api/             # SaaS-specific APIs
│
└── app/main.py              # Loads module based on DEPLOYMENT_MODE
```

## Core Components

### 1. ACLProvider Abstract Base Class

Location: `backend/core/acl/base.py`

```python
class ACLProvider(ABC):
    """Abstract base class for ACL providers."""

    def __init__(self, tenant_id: str, user_id: str, config: Optional[Dict] = None):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.config = config or {}

    @abstractmethod
    async def check_permission(self, db, document_id, permission, user_id=None) -> bool:
        """Check if user has a specific permission on a document."""
        pass

    @abstractmethod
    async def get_effective_permissions(self, db, document_id, user_id=None) -> PermissionSet:
        """Get all effective permissions for a user on a document."""
        pass

    @abstractmethod
    async def get_accessible_document_ids(self, db, permission, limit=None, offset=0) -> List[UUID]:
        """Get list of document IDs the user can access."""
        pass

    @abstractmethod
    async def filter_accessible_documents(self, db, document_ids, permission) -> List[UUID]:
        """Filter a list of document IDs to only those the user can access."""
        pass

    @abstractmethod
    async def sync_to_vector_db(self, db, document_id) -> None:
        """Sync ACL changes to the vector database (Weaviate)."""
        pass
```

### 2. ACLProviderFactory

Location: `backend/core/acl/factory.py`

```python
class ACLProviderFactory:
    """Factory for creating and managing ACL providers."""

    _providers: Dict[ACLProviderType, Type[ACLProvider]] = {}
    _instances: Dict[str, ACLProvider] = {}
    _default_type: Optional[ACLProviderType] = None

    @classmethod
    def register(cls, provider_type: ACLProviderType, provider_class: Type[ACLProvider]):
        """Register a provider implementation."""
        cls._providers[provider_type] = provider_class

    @classmethod
    def set_default(cls, provider_type: ACLProviderType):
        """Set the default provider type."""
        cls._default_type = provider_type

    @classmethod
    async def get_provider(cls, tenant_id, user_id, db, provider_type=None) -> ACLProvider:
        """Get an ACL provider for the given tenant and user."""
        # Uses caching for efficiency
        pass
```

### 3. Permission and PermissionSet

```python
class Permission(str, Enum):
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"
    SHARE = "share"

@dataclass
class PermissionSet:
    can_view: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_share: bool = False
    is_owner: bool = False
    is_admin: bool = False
    # Source tracking
    from_user_acl: bool = False
    from_role_acl: bool = False
    from_group_acl: bool = False
    from_everyone_acl: bool = False
```

## Module Implementations

### On-Premise Module

Location: `backend/modules/on_premise/`

**ACL Provider: JSONBACLProvider**

Uses JSONB fields in `IndexedDocument` for simple, efficient ACL:
- `owner_id` - Document owner (full access)
- `is_tenant_public` - All tenant users can view
- `shared_with_users` - List of user IDs with view access
- `shared_with_groups` - List of SSO groups with view access

```python
class JSONBACLProvider(ACLProvider):
    """ACL provider using JSONB fields in IndexedDocument."""

    @property
    def provider_type(self) -> ACLProviderType:
        return ACLProviderType.JSONB

    async def check_permission(self, db, document_id, permission, user_id=None) -> bool:
        # 1. Owner has full access
        # 2. Admin has full access
        # 3. Non-owners only get VIEW permission via:
        #    - is_tenant_public = True
        #    - user_id in shared_with_users
        #    - user's groups in shared_with_groups
        pass
```

**Module Registration:**

```python
class OnPremiseModule:
    @classmethod
    def register(cls, app: FastAPI) -> None:
        # Register JSONB ACL provider
        ACLProviderFactory.register(ACLProviderType.JSONB, JSONBACLProvider)
        ACLProviderFactory.set_default(ACLProviderType.JSONB)

        # Include on-premise-specific routers
        # (connectors, user_sync currently in main api.py)
```

### SaaS Module

Location: `backend/modules/saas/`

**ACL Provider: TableACLProvider**

Wraps existing `DocumentACLService` for fine-grained permissions:
- Uses dedicated `DocumentACL` table
- Supports user, role, and 'everyone' grantees
- Full audit trail
- Expiration support

```python
class TableACLProvider(ACLProvider):
    """ACL provider using dedicated DocumentACL table."""

    @property
    def provider_type(self) -> ACLProviderType:
        return ACLProviderType.TABLE

    def _get_acl_service(self):
        """Lazy-load the DocumentACLService."""
        if self._acl_service is None:
            from app.services.document_acl_service import DocumentACLService
            self._acl_service = DocumentACLService(self.tenant_id, self.user_id)
        return self._acl_service
```

## Application Loader

Location: `backend/app/main.py`

```python
def _load_deployment_module(app):
    """Load the appropriate module based on deployment mode."""
    mode = FeatureFlags.get_deployment_mode()

    if is_on_premise_mode():
        from modules.on_premise import OnPremiseModule
        OnPremiseModule.register(app)
    elif is_saas_mode():
        from modules.saas import SaaSModule
        SaaSModule.register(app)

# Called during app initialization
app = create_application()
_load_deployment_module(app)
```

## Configuration

### Environment Variable

```bash
# Set deployment mode
DEPLOYMENT_MODE=on_premise  # Options: saas, on_premise, custom
```

### Docker Volume Mounts

Added to `docker-compose.yml`:

```yaml
volumes:
  - ../core:/app/core:ro
  - ../modules:/app/modules:ro
```

## Usage Examples

### Getting an ACL Provider

```python
from core.acl import ACLProviderFactory, Permission

async def check_document_access(db, tenant_id, user_id, document_id):
    # Get provider (uses default based on deployment mode)
    provider = await ACLProviderFactory.get_provider(tenant_id, user_id, db)

    # Check specific permission
    can_view = await provider.check_permission(db, document_id, Permission.VIEW)

    # Get all permissions
    permissions = await provider.get_effective_permissions(db, document_id)

    return permissions
```

### Filtering Search Results

```python
async def search_with_acl(db, tenant_id, user_id, query):
    provider = await ACLProviderFactory.get_provider(tenant_id, user_id, db)

    # Get all documents from search
    all_results = await vector_search(query)

    # Filter to only accessible documents
    accessible_ids = await provider.filter_accessible_documents(
        db,
        [r.id for r in all_results],
        Permission.VIEW
    )

    return [r for r in all_results if r.id in accessible_ids]
```

### Getting User's Accessible Documents

```python
async def get_user_documents(db, tenant_id, user_id, page=1, per_page=20):
    provider = await ACLProviderFactory.get_provider(tenant_id, user_id, db)

    # Get document IDs user can access
    doc_ids = await provider.get_accessible_document_ids(
        db,
        Permission.VIEW,
        limit=per_page,
        offset=(page - 1) * per_page
    )

    return doc_ids
```

## Future Module-Aware Migrations

The `alembic/env.py` has been prepared for module-specific migrations:

```
alembic/versions/
├── core/               # Always applied (future)
├── saas/               # Only in SaaS mode (future)
└── on_premise/         # Only in on-premise mode (future)
```

Currently, all migrations remain in `alembic/versions/`. This structure will be implemented when we have module-specific database schema changes.

## Extending the Architecture

### Adding a New ACL Provider

1. Create provider class implementing `ACLProvider`:

```python
# backend/modules/my_module/acl/provider.py
from core.acl.base import ACLProvider, ACLProviderType

class MyACLProvider(ACLProvider):
    @property
    def provider_type(self) -> ACLProviderType:
        return ACLProviderType.MY_TYPE  # Add to enum first

    async def initialize(self, db):
        # Load user context
        pass

    async def check_permission(self, db, document_id, permission, user_id=None):
        # Implement permission check
        pass

    # ... implement other abstract methods
```

2. Register in module:

```python
# backend/modules/my_module/module.py
from core.acl.factory import ACLProviderFactory
from core.acl.base import ACLProviderType

class MyModule:
    @classmethod
    def register(cls, app):
        ACLProviderFactory.register(ACLProviderType.MY_TYPE, MyACLProvider)
        ACLProviderFactory.set_default(ACLProviderType.MY_TYPE)
```

### Adding Module-Specific Routes

1. Create router in module:

```python
# backend/modules/my_module/api/my_routes.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/my-endpoint")
async def my_endpoint():
    return {"module": "my_module"}
```

2. Include in module registration:

```python
class MyModule:
    @classmethod
    def register(cls, app):
        from modules.my_module.api import my_routes
        app.include_router(my_routes.router, prefix="/api/v1/my-module")
```

## Verification

### Check Module Loading

```bash
# View logs for module registration
docker compose logs api | grep -i module

# Expected output:
# Loading deployment module for mode: on_premise
# Registered ACL provider: jsonb
# Set default ACL provider: jsonb
# On-Premise module registered successfully
```

### Test ACL Provider

```bash
docker compose exec api python3 -c "
from core.acl.factory import ACLProviderFactory
print('Providers:', ACLProviderFactory.get_registered_providers())
print('Default:', ACLProviderFactory.get_default_type())
"
```

### Isolation Test

```bash
DEPLOYMENT_MODE=on_premise python -c "
from app.main import app
routes = [r.path for r in app.routes]
# Should NOT include /stripe, /signatures
print([r for r in routes if 'stripe' in r or 'signature' in r])
"
```

## Files Reference

| File | Purpose |
|------|---------|
| `core/acl/base.py` | ACLProvider ABC, Permission enum, PermissionSet |
| `core/acl/factory.py` | ACLProviderFactory with registration and caching |
| `modules/on_premise/module.py` | On-premise module registration |
| `modules/on_premise/acl/provider.py` | JSONBACLProvider implementation |
| `modules/saas/module.py` | SaaS module registration |
| `modules/saas/acl/provider.py` | TableACLProvider implementation |
| `app/main.py` | Module-aware application loader |
| `alembic/env.py` | Prepared for module-aware migrations |
| `docker/docker-compose.yml` | Volume mounts for core/ and modules/ |

## Benefits

1. **Clean separation** - SaaS code never loaded in on-premise mode
2. **Easy maintenance** - Changes isolated to specific module
3. **Flexible deployment** - Same codebase, different configurations
4. **Clear dependencies** - Each module declares its own requirements
5. **Testability** - Modules can be tested independently
6. **Extensibility** - New modules can be added without modifying core
