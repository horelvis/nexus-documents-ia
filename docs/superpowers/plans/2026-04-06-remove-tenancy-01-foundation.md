# Remove Multi-Tenancy — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lay the groundwork for the multi-tenancy removal: rename the database to `nouxcube`, introduce role-based ACL helpers, drop tenant model classes from SQLAlchemy, add `roles[]` columns, and produce a single fresh Alembic migration. This plan ends with a code state that compiles and lints clean but is **not yet wired into the API or microservices** — those come in Plans 2 and 3.

**Architecture:** Single atomic refactor on branch `refactor/remove-multi-tenancy`. Database is recreated from scratch, no incremental migration. ACL is per-document via a `roles ARRAY(String)` column with the wildcard `EVERYONE`. KeyCloak JWT is the source of truth for user roles via the existing `map_groups_to_roles()` indirection.

**Tech Stack:** Python 3.9+ / FastAPI / SQLAlchemy 2.x / Alembic / PostgreSQL 15 / KeyCloak (OIDC). Tests with pytest.

**Spec reference:** `docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md`

**Plan boundaries:**
- ✅ This plan covers Commits 1-3 of Section 3.A of the spec.
- ✅ Outputs: `nouxcube` rename in configs, `acl.py` helpers, `role_mapping.yaml`, models without tenant, single new Alembic migration.
- ❌ Does NOT touch API endpoints, services, microservices, frontend, or run the rebuild. Those are Plans 2-5.
- ❌ Does NOT execute the drop & rebuild commands. The schema lives in code; the database stays as-is until Plan 5.

---

## File map (locked decisions)

**Files created in this plan:**
- `backend/app/config/role_mapping.yaml` — KeyCloak group → application role mapping
- `backend/app/core/auth/acl.py` — `filter_visible_to_user()` and `require_role()` helpers

**File modified for the new dataclass (added 2026-04-08, see Task 8b):**
- `backend/app/core/auth/base.py` — append a `UserProfile` frozen dataclass that `acl.py` and `test_acl.py` import. The legacy `UserProfile` ORM class was deleted in a previous refactor (see comment in `backend/app/db/models.py` near "UserProfile eliminado"); this new one is a request-scoped DTO carrying `sub`, `email`, `name`, `roles: List[str]`. It is **dormant in Plan 1**: no caller wires it up. Plan 2 refactors `get_current_user` to return it.
- `backend/tests/test_acl.py` — tests for the ACL helpers
- `backend/docker/init-scripts/02-init-nouxcube.sql` — Postgres init script for `nouxcube` database
- `backend/alembic/versions/_archived/.gitkeep` — placeholder so the archive folder exists
- A single new Alembic migration file (auto-generated, name varies)

**Files modified in this plan:**
- `backend/docker/.env` — DB rename
- `backend/docker/docker-compose.yml` — DB rename
- `backend/docker/docker-compose.onpremise.yml` — DB rename
- `backend/docker/docker-compose.test.yml` — test DB rename
- `backend/docker/docker-compose.prod.yml` — DB rename (if applicable)
- `backend/docker/docker-compose.onboarding.yml` — DB rename (if applicable)
- `backend/app/core/config.py` — DATABASE_URL fallback
- `backend/microservices/emma-agent-service/app/core/config.py` — DB references
- `backend/microservices/knowledge-tree-service/app/core/config.py` — DB references
- `backend/microservices/weaviate-service/app/core/config.py` — DB references
- `backend/microservices/intelligence-docs-service/app/core/config.py` — DB references
- `backend/microservices/document-forge-service/app/core/config.py` — DB references
- `backend/scripts/init_db.py` — DB name reference + `role_mapping.yaml` validation
- `backend/tests/conftest.py` — test DB reference
- `backend/app/db/models.py` — drop 12 tenant-related classes, drop `tenant_id` columns from **~32 surviving classes** (re-measured 2026-04-08: 44 classes total currently touch `tenant_id`, minus the 12 to delete = 32 to modify), add `roles` column to `Document`, add `default_document_roles` column to `Connector`
- `backend/app/db/emma_memory_models.py` — drop tenant_id
- `backend/app/db/emma_reactive_models.py` — drop tenant_id
- `backend/app/db/agent_models.py` — drop tenant_id
- `backend/app/db/edit_session_models.py` — drop tenant_id
- `backend/docker/onboarding.sh` — DB name references
- `README.md` — DB name reference
- `CLAUDE.md` — DB name reference

**Files moved (not deleted):**
- All `backend/alembic/versions/*.py` → `backend/alembic/versions/_archived/`

**Files NOT touched in this plan (deferred to later plans):**
- API endpoints (Plan 2)
- Services in `backend/app/services/` (Plan 2)
- Microservice business logic outside config (Plan 3)
- Frontend (Plan 4)
- Diagnostics, tests beyond ACL helper unit tests (Plan 5)

---

## Task 1: Verify clean working tree on the right branch

**Files:** none (verification only)

- [ ] **Step 1: Confirm branch and clean state**

```bash
git status
git branch --show-current
```

Expected: `On branch refactor/remove-multi-tenancy` and `nothing to commit, working tree clean`. If the branch is wrong, run `git checkout refactor/remove-multi-tenancy`. If there are uncommitted changes, stash or commit them before proceeding.

- [ ] **Step 2: Verify the spec file exists**

```bash
ls docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
```

Expected: file exists. This plan references it.

---

## Task 2: Update environment file with `nouxcube` database name

**Files:**
- Modify: `backend/docker/.env` (the `POSTGRES_DB` and `DATABASE_URL` lines)

- [ ] **Step 1: Open the file**

Read `backend/docker/.env`.

- [ ] **Step 2: Replace POSTGRES_DB and DATABASE_URL**

Find:
```
POSTGRES_DB=nexus_db
DATABASE_URL=postgresql://nexus_user:nexus_password@db:5432/nexus_db
```

Replace with:
```
POSTGRES_DB=nouxcube
DATABASE_URL=postgresql://nexus_user:nexus_password@db:5432/nouxcube
```

Note: `POSTGRES_USER` (`nexus_user`) and `POSTGRES_PASSWORD` (`nexus_password`) **stay the same**. Only the database name changes.

- [ ] **Step 3: Verify with grep**

Run:
```bash
grep -n "nexus_db\|nouxcube" backend/docker/.env
```

Expected: two lines, both containing `nouxcube`. Zero matches for `nexus_db`.

---

## Task 3: Update Docker Compose files with `nouxcube` database name

**Files:**
- Modify: `backend/docker/docker-compose.yml`
- Modify: `backend/docker/docker-compose.onpremise.yml`
- Modify: `backend/docker/docker-compose.test.yml`
- Modify: `backend/docker/docker-compose.prod.yml` (if it has POSTGRES_DB)
- Modify: `backend/docker/docker-compose.onboarding.yml` (if it has POSTGRES_DB)

- [ ] **Step 1: Find every compose file with POSTGRES_DB**

```bash
grep -ln "POSTGRES_DB\|nexus_db" backend/docker/docker-compose*.yml
```

Expected: list of compose files that need editing.

- [ ] **Step 2: Update each compose file**

For each file in the list, find any of these patterns and replace `nexus_db` with `nouxcube`:
- `POSTGRES_DB: nexus_db`
- `POSTGRES_DB: ${POSTGRES_DB:-nexus_db}`
- `POSTGRES_DB=nexus_db`
- Any `DATABASE_URL=...nexus_db` hardcoded fallback
- Any volume name reference (do NOT rename volume names — only DB names inside env vars)

For `docker-compose.test.yml`, the test database becomes `nouxcube_test`, not `nouxcube`. Look for `nexus_test_db` or similar and replace with `nouxcube_test`.

- [ ] **Step 3: Verify**

```bash
grep -n "nexus_db\|nexus_test_db" backend/docker/docker-compose*.yml
```

Expected: zero matches.

```bash
grep -n "nouxcube" backend/docker/docker-compose*.yml
```

Expected: at least one match in each file that previously had `nexus_db`.

---

## Task 4: Update microservice configs with `nouxcube` database name

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/core/config.py`
- Modify: `backend/microservices/knowledge-tree-service/app/core/config.py`
- Modify: `backend/microservices/weaviate-service/app/core/config.py`
- Modify: `backend/microservices/intelligence-docs-service/app/core/config.py`
- Modify: `backend/microservices/document-forge-service/app/core/config.py`
- Modify: any other `*/app/core/config.py` that hardcodes `nexus_db`

- [ ] **Step 1: Find all hardcoded references**

```bash
grep -rn "nexus_db" backend/microservices/*/app/core/config.py
```

Expected: list of files with hardcoded fallback strings (e.g. `DATABASE_URL: str = "postgresql://nexus_user:nexus_password@db:5432/nexus_db"`).

- [ ] **Step 2: Update each file**

For every match, replace `nexus_db` with `nouxcube` in the string. Do not change the user, password, or host.

- [ ] **Step 3: Verify**

```bash
grep -rn "nexus_db" backend/microservices/
```

Expected: zero matches.

---

## Task 5: Update backend main config and init script

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/scripts/init_db.py`
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Find references**

```bash
grep -rn "nexus_db\|nexus_test_db" backend/app/core/config.py backend/scripts/init_db.py backend/tests/conftest.py
```

- [ ] **Step 2: Update**

For `backend/app/core/config.py`: any hardcoded fallback `DATABASE_URL` or `POSTGRES_DB` becomes `nouxcube`.

For `backend/scripts/init_db.py`: any DB name string becomes `nouxcube`.

For `backend/tests/conftest.py`: test DB string becomes `nouxcube_test`.

- [ ] **Step 3: Verify**

```bash
grep -rn "nexus_db\|nexus_test_db" backend/app/core/config.py backend/scripts/init_db.py backend/tests/conftest.py
```

Expected: zero matches.

---

## Task 6: Update onboarding script and documentation

**Files:**
- Modify: `backend/docker/onboarding.sh`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Find references in scripts**

```bash
grep -n "nexus_db" backend/docker/onboarding.sh
```

Replace any matches with `nouxcube`.

- [ ] **Step 2: Find references in docs**

```bash
grep -n "nexus_db" README.md CLAUDE.md
```

Replace any matches with `nouxcube`.

- [ ] **Step 3: Verify entire repo (excluding _archived)**

```bash
grep -rn "nexus_db" --include="*.py" --include="*.yml" --include="*.sh" --include="*.md" --include="*.env" \
  backend/ frontend/ docs/ README.md CLAUDE.md 2>/dev/null \
  | grep -v "alembic/versions/_archived"
```

Expected: zero matches. If any match remains, fix it before continuing.

---

## Task 7: Create the `02-init-nouxcube.sql` Postgres init script

**Files:**
- Create: `backend/docker/init-scripts/02-init-nouxcube.sql`

- [ ] **Step 1: Verify the existing langfuse init script**

```bash
cat backend/docker/init-scripts/01-init-langfuse.sql
```

Expected: shows the SQL that creates the `langfuse` database. We follow the same pattern.

- [ ] **Step 2: Create the new script**

Write file `backend/docker/init-scripts/02-init-nouxcube.sql` with this content:

```sql
-- Create nouxcube database (main application database, single-tenant on-premise)
-- Executed on container first start (docker-entrypoint-initdb.d)
-- This script is idempotent: it will not fail if the database already exists

SELECT 'CREATE DATABASE nouxcube
    WITH OWNER = nexus_user
    ENCODING = ''UTF8''
    LC_COLLATE = ''C''
    LC_CTYPE = ''C''
    TEMPLATE = template0'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nouxcube')\gexec

GRANT ALL PRIVILEGES ON DATABASE nouxcube TO nexus_user;

\c nouxcube

ALTER DEFAULT PRIVILEGES FOR ROLE nexus_user GRANT ALL ON TABLES TO nexus_user;
ALTER DEFAULT PRIVILEGES FOR ROLE nexus_user GRANT ALL ON SEQUENCES TO nexus_user;
```

- [ ] **Step 3: Verify**

```bash
ls backend/docker/init-scripts/
cat backend/docker/init-scripts/02-init-nouxcube.sql | head -5
```

Expected: file exists, content starts with the comment line.

---

## Task 8: Create the role mapping YAML file

**Files:**
- Create: `backend/app/config/role_mapping.yaml`

- [ ] **Step 1: Ensure the directory exists**

```bash
ls backend/app/config/ 2>/dev/null || mkdir -p backend/app/config
```

- [ ] **Step 2: Create the file**

Write `backend/app/config/role_mapping.yaml` with this content:

```yaml
# Role mapping configuration
#
# Maps KeyCloak group names (left side) to canonical application role
# identifiers (right side, English uppercase). The application uses only
# the right-side identifiers internally — the YAML is the only place
# where Spanish or organization-specific names are mentioned.
#
# Reserved value 'EVERYONE' is a wildcard meaning "any authenticated user".
# It is NEVER assigned to a user as a regular role. Documents with
# roles=['EVERYONE'] are visible to all authenticated users regardless
# of the roles they carry in their JWT.
#
# To add a new role for this deployment:
#   1. Create the group in KeyCloak admin UI.
#   2. Add a line below mapping the group path to a canonical identifier.
#   3. Restart the backend service.
# No code change required.

group_to_role:
  "/Administradores": ADMIN
  "/Comercial": SALES
  "/Departamento Legal": LEGAL
  "/Recursos Humanos": HR
  "/Finanzas": FINANCE
  "/Médicos": MEDICAL
```

- [ ] **Step 3: Verify**

```bash
cat backend/app/config/role_mapping.yaml | head -10
```

Expected: shows the file content starting with `# Role mapping configuration`.

- [ ] **Step 4: Verify it's valid YAML**

```bash
python -c "import yaml; print(yaml.safe_load(open('backend/app/config/role_mapping.yaml')))"
```

Expected: prints a dict like `{'group_to_role': {'/Administradores': 'ADMIN', ...}}`.

---

## Task 8b: Define the `UserProfile` dataclass

**Files:**
- Modify: `backend/app/core/auth/base.py` (append a new dataclass)

**Context:** The original Plan 1 assumed `UserProfile` already existed in `app.core.auth.base`, but a previous refactor deleted it (the only remaining reference is the comment `# UserProfile eliminado` in `backend/app/db/models.py`). The new `acl.py` and `test_acl.py` files in Tasks 9-10 import `UserProfile` from `app.core.auth.base`, so we need to (re)create it before those tasks. The dataclass is **dormant** during Plan 1: nothing constructs it at runtime. Plan 2 refactors `get_current_user` to return it.

- [ ] **Step 1: Read the existing file**

```bash
head -30 backend/app/core/auth/base.py
```

Confirm it already imports `dataclass`, `field`, and `List` (from `typing`). If not, add the imports in Step 2.

- [ ] **Step 2: Append the dataclass at the bottom of the file**

Append this block to `backend/app/core/auth/base.py`:

```python


@dataclass(frozen=True)
class UserProfile:
    """Request-scoped immutable view of an authenticated user.

    Built once per request from the JWT (in Plan 2 — currently dormant).
    Carries the canonical role identifiers from `map_groups_to_roles()`,
    not raw KeyCloak group names.

    The `roles` field is a list of strings (e.g. ['LEGAL', 'SALES']).
    The reserved value 'EVERYONE' is NEVER present here — it is a wildcard
    used only on the document side. See `app.core.auth.acl` for usage.
    """

    sub: str
    email: str
    name: Optional[str] = None
    roles: List[str] = field(default_factory=list)
```

`Optional`, `List`, `field`, and `dataclass` are already imported at the top of the file. If any is missing, add it to the existing import lines.

- [ ] **Step 3: Verify the import works**

```bash
cd backend && python -c "from app.core.auth.base import UserProfile; u = UserProfile(sub='x', email='y@z'); print(u, u.roles)"
```

Expected: prints something like `UserProfile(sub='x', email='y@z', name=None, roles=[]) []`. No ImportError, no TypeError.

- [ ] **Step 4: Defensive check for the EVERYONE wildcard**

The spec Section 1 ("Wildcard semantics") says `EVERYONE` should never appear in `UserProfile.roles`. We don't enforce this at the dataclass level (it's a defensive check, not a hard invariant — invalid input could still construct one). The enforcement lives in Plan 2's refactored `get_current_user`, which will assert it after running `map_groups_to_roles`.

For Plan 1 just leave a comment in the docstring (already done above).

---

## Task 9: Write tests for the ACL helpers (TDD)

**Files:**
- Create: `backend/tests/test_acl.py`

The helpers don't exist yet — these tests will fail. That's the point.

- [ ] **Step 1: Create the test file**

Write `backend/tests/test_acl.py` with this content:

```python
"""Tests for the role-based ACL helpers in app.core.auth.acl."""
import pytest
from sqlalchemy import create_engine, Column, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.core.auth.acl import filter_visible_to_user, require_role
from app.core.auth.base import UserProfile

Base = declarative_base()


class FakeDoc(Base):
    __tablename__ = "fake_docs_for_acl_test"
    id = Column(String, primary_key=True)
    roles = Column(ARRAY(String), nullable=False)


@pytest.fixture
def db_session():
    # In-memory SQLite for tests; ARRAY is only Postgres, so we use a
    # session-level mock instead. The query construction is what we test —
    # not the SQL execution against a real DB. Plan 5 covers integration
    # tests against real Postgres.
    engine = create_engine("sqlite://")
    Session = sessionmaker(bind=engine)
    return Session()


def make_user(roles):
    """Helper: create a UserProfile with the given role list."""
    return UserProfile(
        sub="test-user-id",
        email="test@example.com",
        name="Test User",
        roles=roles,
    )


def test_filter_visible_to_user_includes_everyone():
    """A user with no relevant roles still sees EVERYONE-tagged docs."""
    user = make_user(roles=[])
    query = "SELECT * FROM fake_docs_for_acl_test"  # placeholder; the helper builds the WHERE
    # We test the query string, not actual execution
    from app.core.auth.acl import build_role_filter_clause
    clause = build_role_filter_clause(user)
    assert "EVERYONE" in str(clause)


def test_filter_visible_to_user_includes_user_roles():
    """A user with role SALES sees docs tagged SALES."""
    user = make_user(roles=["SALES"])
    from app.core.auth.acl import build_role_filter_clause
    clause = build_role_filter_clause(user)
    clause_str = str(clause).upper()
    assert "EVERYONE" in clause_str
    assert "OVERLAP" in clause_str or "&&" in clause_str


def test_require_role_passes_when_user_has_role():
    """require_role(*roles) returns the user when at least one role matches."""
    user = make_user(roles=["LEGAL", "SALES"])
    dep = require_role("LEGAL")
    result = dep(user=user)
    assert result is user


def test_require_role_passes_when_user_has_any_of_multiple():
    """require_role passes if the user has ANY of the listed roles."""
    user = make_user(roles=["SALES"])
    dep = require_role("LEGAL", "SALES", "HR")
    result = dep(user=user)
    assert result is user


def test_require_role_raises_when_user_lacks_role():
    """require_role raises 403 if the user has none of the listed roles."""
    user = make_user(roles=["HR"])
    dep = require_role("LEGAL", "ADMIN")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=user)
    assert exc_info.value.status_code == 403
    assert "forbidden" in exc_info.value.detail.lower()


def test_require_role_raises_when_user_has_no_roles():
    """A user with empty roles list cannot pass any require_role check."""
    user = make_user(roles=[])
    dep = require_role("LEGAL")
    with pytest.raises(HTTPException) as exc_info:
        dep(user=user)
    assert exc_info.value.status_code == 403


def test_require_role_admin_bypass_not_implicit():
    """ADMIN role does NOT implicitly grant other roles. Each check is explicit."""
    user = make_user(roles=["ADMIN"])
    dep = require_role("LEGAL")
    with pytest.raises(HTTPException):
        dep(user=user)
    # If you want admin to bypass, the endpoint must list ADMIN in require_role.
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
cd backend && python -m pytest tests/test_acl.py -v
```

Expected: All tests FAIL with `ImportError: cannot import name 'filter_visible_to_user' from 'app.core.auth.acl'` (because `acl.py` doesn't exist yet). This is correct — TDD red phase.

---

## Task 10: Implement the ACL helpers

**Files:**
- Create: `backend/app/core/auth/acl.py`

- [ ] **Step 1: Create the file**

Write `backend/app/core/auth/acl.py` with this content:

```python
"""Role-based ACL helpers for single-tenant claims-based authorization.

This module replaces the multi-tenant filtering of the previous architecture.
After the multi-tenancy removal refactor, document access is governed by
KeyCloak roles carried in the JWT (via UserProfile.roles) checked against
the per-document `roles` array column.

Two public surfaces:

1. `filter_visible_to_user(query, user)` — apply WHERE clause to a Document
   query so it only returns rows the user is authorized to see.

2. `require_role(*allowed_roles)` — FastAPI dependency that returns the
   current user if they hold any of the listed roles, else 403.

The wildcard role `EVERYONE` is reserved: any document with this role in
its roles[] is visible to every authenticated user regardless of their
individual role list.
"""
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.sql.elements import BooleanClauseList

from app.core.auth.base import UserProfile
from app.api.dependencies import get_current_user

EVERYONE_ROLE = "EVERYONE"


def build_role_filter_clause(user: UserProfile) -> BooleanClauseList:
    """Build the SQLAlchemy filter clause for role-based document visibility.

    Returns a clause equivalent to:
        documents.roles @> ARRAY['EVERYONE'] OR documents.roles && user_roles

    where the second branch is omitted if the user has no roles.

    This is exposed separately from filter_visible_to_user so unit tests
    can inspect the generated clause without needing a Document model.
    """
    # Late import to avoid circular dependency with app.db.models
    from app.db.models import Document

    clauses = [Document.roles.contains([EVERYONE_ROLE])]
    if user.roles:
        clauses.append(Document.roles.overlap(list(user.roles)))
    return or_(*clauses)


def filter_visible_to_user(query, user: UserProfile):
    """Apply role-based ACL filter to a Document query.

    Replaces every legacy `filter(Document.tenant_id == ...)` call.

    Args:
        query: A SQLAlchemy query object selecting from Document.
        user: The current authenticated user profile.

    Returns:
        The query with an additional WHERE clause restricting results
        to documents accessible to the user's roles.
    """
    return query.filter(build_role_filter_clause(user))


def require_role(*allowed_roles: str):
    """FastAPI dependency factory that gates endpoints by KeyCloak role.

    Usage:
        @router.get("/admin/things", dependencies=[Depends(require_role("ADMIN"))])
        def list_things(): ...

        # or to receive the user inside the handler:
        @router.get("/legal/contracts")
        def list_contracts(user: UserProfile = Depends(require_role("LEGAL", "ADMIN"))):
            ...

    The wildcard `EVERYONE` is NOT a valid argument here — it is meaningful
    only for documents, not for endpoint authorization. Endpoints that
    should be accessible to any authenticated user should use
    `Depends(get_current_user)` directly without `require_role`.

    Raises:
        HTTPException 403 if the user has none of the listed roles.
    """
    if EVERYONE_ROLE in allowed_roles:
        raise ValueError(
            f"{EVERYONE_ROLE} is not a valid argument to require_role. "
            "Use Depends(get_current_user) for endpoints open to any authenticated user."
        )

    def _dependency(user: UserProfile = Depends(get_current_user)) -> UserProfile:
        if not any(role in user.roles for role in allowed_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="forbidden: missing required role",
            )
        return user

    return _dependency
```

- [ ] **Step 2: Run the tests again**

```bash
cd backend && python -m pytest tests/test_acl.py -v
```

Expected: All 7 tests PASS. If any fail, read the error and fix the implementation. Do NOT modify the tests to pass — the test is the contract.

- [ ] **Step 3: Verify import works from any backend module**

```bash
cd backend && python -c "from app.core.auth.acl import filter_visible_to_user, require_role, EVERYONE_ROLE; print('ok')"
```

Expected: prints `ok`. If it prints an ImportError, check the dependency chain.

---

## Task 11: Drop tenant model classes from `models.py`

**Files:**
- Modify: `backend/app/db/models.py`

The classes to delete (12 total):
- `Tenant`
- `TenantAuthConfig`
- `Role`
- `Permission`
- `RoleAssignment`
- `RoleAssignmentAudit`
- `PermissionAssignmentAudit`
- `DocumentTagAudit` (the tenant-scoped audit)
- `DocumentShare`
- `DocumentShareRecipient`
- `DocumentShareAccessLog`
- `TeamInvitation`

Some classes may reference each other via `relationship()`. Deleting them in dependency order avoids stale relationships during the edit.

- [ ] **Step 1: Make a backup of the current file**

```bash
cp backend/app/db/models.py backend/app/db/models.py.backup
```

This is a safety net while editing. It will be deleted at the end of the task.

- [ ] **Step 2: Find every class definition and its line range**

```bash
grep -n "^class " backend/app/db/models.py
```

Note the line numbers of the 12 classes listed above.

- [ ] **Step 3: Delete each class**

For each of the 12 classes, delete the entire class body (from `class X(Base):` line through the last attribute or `__table_args__` line, including any blank line that follows the class). Use the Edit tool with the exact `old_string` for each class block.

Suggested deletion order (reverse-dependency, so referenced classes are deleted last):
1. `TeamInvitation` (references Tenant)
2. `DocumentShareAccessLog` (references DocumentShare)
3. `DocumentShareRecipient` (references DocumentShare)
4. `DocumentShare` (references Tenant + Document)
5. `DocumentTagAudit` (references Tenant)
6. `RoleAssignmentAudit` (references Tenant + Role + User)
7. `PermissionAssignmentAudit` (references Tenant + User + Permission)
8. `RoleAssignment` (references Role + User)
9. `Permission` (independent or referenced by RoleAssignment — already gone)
10. `Role` (references Tenant)
11. `TenantAuthConfig` (references Tenant + Role)
12. `Tenant` (referenced by all above — last)

- [ ] **Step 4: Verify the classes are gone**

```bash
grep -E "^class (Tenant|TenantAuthConfig|Role|Permission|RoleAssignment|RoleAssignmentAudit|PermissionAssignmentAudit|DocumentTagAudit|DocumentShare|DocumentShareRecipient|DocumentShareAccessLog|TeamInvitation)\b" backend/app/db/models.py
```

Expected: no matches.

- [ ] **Step 5: Verify the file still parses as Python**

```bash
python -c "import ast; ast.parse(open('backend/app/db/models.py').read()); print('ok')"
```

Expected: prints `ok`. Note: this checks syntax, not import errors. Imports are tested in Task 13.

---

## Task 12: Drop `tenant_id` columns and back_populates from surviving models

**Files:**
- Modify: `backend/app/db/models.py`
- Modify: `backend/app/db/emma_memory_models.py`
- Modify: `backend/app/db/emma_reactive_models.py`
- Modify: `backend/app/db/agent_models.py`
- Modify: `backend/app/db/edit_session_models.py`

Surviving models that need `tenant_id` removed (from the spec Section 2.C):
- `User`
- `Document`
- `FolderMarker`
- `DocumentView`
- `DocumentMetrics`
- `Tag`
- `SignatureProvider`
- `SignatureRequest`
- `GoogleDriveToken`
- `Connector`
- Plus any models in `emma_memory_models.py`, `emma_reactive_models.py`, `agent_models.py`, `edit_session_models.py` that have `tenant_id`

- [ ] **Step 1: Locate all `tenant_id` declarations across the db package**

```bash
grep -rn "tenant_id" backend/app/db/ --include="*.py"
```

Expected: a list of every line containing `tenant_id`. This is the work list.

- [ ] **Step 2: For each model, remove four things**

For each class that has `tenant_id`, delete:

1. The column definition line, e.g.:
```python
tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True)
```

2. Any composite indexes in `__table_args__` that include `tenant_id`, e.g.:
```python
Index('idx_documents_tenant_created', 'tenant_id', 'created_at'),
Index('idx_documents_type_tenant', 'file_type', 'tenant_id'),
Index('idx_documents_category_tenant', 'category', 'tenant_id'),
Index('idx_documents_folder_path', 'tenant_id', 'folder_path'),
```
Replace with single-column or non-tenant-prefixed equivalents where the index is still useful, e.g.:
```python
Index('idx_documents_created', 'created_at'),
Index('idx_documents_type', 'file_type'),
Index('idx_documents_category', 'category'),
Index('idx_documents_folder_path', 'folder_path'),
```

3. Any unique constraint scoped by tenant, e.g.:
```python
UniqueConstraint('name', 'tenant_id', name='uq_role_name_tenant'),
UniqueConstraint('tenant_id', 'folder_path', name='uq_folder_marker_tenant_path'),
```
Replace with the global form (no `tenant_id`):
```python
UniqueConstraint('name', name='uq_tag_name'),
UniqueConstraint('folder_path', name='uq_folder_marker_path'),
```

4. Any `relationship("Tenant", ...)` lines and any references to `tenant` in `back_populates` from the OTHER side (we already deleted `Tenant`, but the reverse references may still linger).

- [ ] **Step 3: Verify**

```bash
grep -rn "tenant_id\|tenants.id\|Tenant\b" backend/app/db/ --include="*.py"
```

Expected: zero matches. Any remaining match must be removed before continuing.

- [ ] **Step 4: Verify the files still parse**

```bash
for f in backend/app/db/models.py backend/app/db/emma_memory_models.py \
         backend/app/db/emma_reactive_models.py backend/app/db/agent_models.py \
         backend/app/db/edit_session_models.py; do
  python -c "import ast; ast.parse(open('$f').read()); print('$f ok')"
done
```

Expected: every file prints `ok`.

---

## Task 13: Add `roles` column to Document and `default_document_roles` to Connector

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Locate the Document class**

```bash
grep -n "^class Document\b" backend/app/db/models.py
```

- [ ] **Step 2: Add the roles column**

In the `Document` class, after the existing columns (and before any `__table_args__` block), add:

```python
    roles = Column(
        ARRAY(String),
        nullable=False,
        server_default="{EVERYONE}",
    )
```

Make sure `ARRAY` is imported at the top of the file. If `from sqlalchemy.dialects.postgresql import ARRAY` is not already there, add it.

In the `__table_args__` of the same class, add a GIN index entry:

```python
        Index('idx_documents_roles', 'roles', postgresql_using='gin'),
```

- [ ] **Step 3: Locate the Connector class**

The `Connector` model lives in `backend/app/db/models.py` (search confirmed during exploration). If it lives in another file (e.g. `agent_models.py`), edit there instead.

```bash
grep -n "^class Connector\b" backend/app/db/models.py backend/app/db/agent_models.py
```

- [ ] **Step 4: Add the default_document_roles column to Connector**

After the existing columns of `Connector`, add:

```python
    default_document_roles = Column(
        ARRAY(String),
        nullable=False,
        server_default="{EVERYONE}",
    )
```

Note: `EVERYONE` as the default ensures backwards compatibility — if an admin creates a connector without specifying roles, the ingested documents will be visible to all authenticated users. Admins can override this in the create form (Plan 4) or via API (Plan 2).

- [ ] **Step 5: Verify**

```bash
python -c "
from app.db.models import Document, Connector
print('Document.roles:', Document.roles.type)
print('Connector.default_document_roles:', Connector.default_document_roles.type)
"
```

Expected: prints `Document.roles: ARRAY(VARCHAR)` and similar for Connector. If it raises ImportError, check that all references to deleted classes have been removed (Task 11) and that no surviving class still references `tenant_id` (Task 12).

---

## Task 14: Archive existing Alembic migrations

**Files:**
- Move: `backend/alembic/versions/*.py` → `backend/alembic/versions/_archived/`
- Create: `backend/alembic/versions/_archived/.gitkeep`

- [ ] **Step 1: Create the archive directory**

```bash
mkdir -p backend/alembic/versions/_archived
touch backend/alembic/versions/_archived/.gitkeep
```

- [ ] **Step 2: Move every existing migration file**

```bash
git mv backend/alembic/versions/*.py backend/alembic/versions/_archived/
```

Expected: all 37 migration files moved into `_archived/`. The `versions/` directory should now be empty except for `_archived/`.

- [ ] **Step 3: Verify**

```bash
ls backend/alembic/versions/
ls backend/alembic/versions/_archived/ | wc -l
```

Expected: `versions/` shows only `_archived/`. The count of files in `_archived/` is the original migration count (37).

- [ ] **Step 4: Update Alembic config to ignore the archive**

Read `backend/alembic/env.py`. If it uses the default `script_location`, no change is needed — Alembic only scans the top-level `versions/` folder, not subdirectories. But verify by checking the file:

```bash
grep -n "version_locations\|version_path_separator\|script_location" backend/alembic.ini backend/alembic/env.py
```

If `version_locations` is set to anything other than the default, ensure `_archived` is NOT in the path list. Otherwise no action.

- [ ] **Step 5: Confirm Alembic sees zero migrations**

```bash
cd backend && alembic history
```

Expected: empty output or a message like "no migrations". If it shows old migrations, the archive directory is being scanned — fix the config from Step 4.

---

## Task 15: Generate the new initial Alembic migration

**Files:**
- Create: a new `backend/alembic/versions/<hash>_initial_nouxcube_schema.py` (auto-generated)

- [ ] **Step 1: Make sure the database is reachable**

The autogeneration step needs to compare the current ORM models against an empty database. Spin up the `db` service if it's not running:

```bash
cd backend/docker && docker compose up -d db
```

Wait ~5 seconds for Postgres to be ready.

- [ ] **Step 2: Create an empty `nouxcube` database for autogeneration**

```bash
docker compose exec db psql -U nexus_user -d postgres -c "CREATE DATABASE nouxcube_autogen;"
```

This is a temporary scratch DB used only for the autogen step. It will be dropped at the end.

- [ ] **Step 3: Point Alembic at the scratch DB**

```bash
cd backend
DATABASE_URL=postgresql://nexus_user:nexus_password@localhost:5432/nouxcube_autogen \
  alembic revision --autogenerate -m "initial nouxcube schema"
```

Expected: a new file appears in `backend/alembic/versions/` with a name like `<hash>_initial_nouxcube_schema.py`. The output should mention "Detected added table: <table_name>" for each model in the schema.

- [ ] **Step 4: Inspect the generated migration**

```bash
ls backend/alembic/versions/*.py | grep -v _archived
cat backend/alembic/versions/<hash>_initial_nouxcube_schema.py
```

Verify:
1. The file contains only `op.create_table(...)` and `op.create_index(...)` statements.
2. NO `op.alter_column`, `op.drop_table`, `op.drop_column` statements.
3. NO references to `tenant_id`, `tenants`, `roles_table` (the old table), `permissions_table`, `role_assignments`, `document_shares`, `tenant_auth_configs`, `team_invitations`.
4. The `documents` table has a `roles` column with type `ARRAY(VARCHAR)`.
5. The `connectors` table has a `default_document_roles` column.
6. There is an index `idx_documents_roles` using `postgresql_using='gin'`.

If any of these are violated, the model files still have residual tenant code — go back to Task 11/12/13 and clean it up, then re-run autogen.

- [ ] **Step 5: Drop the scratch database**

```bash
docker compose exec db psql -U nexus_user -d postgres -c "DROP DATABASE nouxcube_autogen;"
```

- [ ] **Step 6: Verify the new migration file is the only one in versions/**

```bash
ls backend/alembic/versions/ | grep -v _archived
```

Expected: exactly one Python file (the one just generated).

---

## Task 16: Wire `init_db.py` to validate the role mapping YAML

**Files:**
- Modify: `backend/scripts/init_db.py`

- [ ] **Step 1: Read the current init_db.py**

```bash
cat backend/scripts/init_db.py
```

- [ ] **Step 2: Add role mapping validation**

After the existing imports and before the main DB creation logic, add:

```python
import os
import sys
import yaml
from pathlib import Path

ROLE_MAPPING_PATH = Path(__file__).parent.parent / "app" / "config" / "role_mapping.yaml"


def validate_role_mapping():
    """Ensure role_mapping.yaml exists and is valid before init runs.

    The application cannot function without this file because it is the
    only source of translation between KeyCloak group names and the
    canonical application role identifiers used throughout the codebase.
    """
    if not ROLE_MAPPING_PATH.exists():
        print(
            f"FATAL: role_mapping.yaml not found at {ROLE_MAPPING_PATH}",
            file=sys.stderr,
        )
        print(
            "Create it before running init_db. See "
            "docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md",
            file=sys.stderr,
        )
        sys.exit(1)

    with open(ROLE_MAPPING_PATH) as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict) or "group_to_role" not in config:
        print(
            f"FATAL: role_mapping.yaml is missing the 'group_to_role' key",
            file=sys.stderr,
        )
        sys.exit(1)

    mapping = config["group_to_role"]
    if not isinstance(mapping, dict) or len(mapping) == 0:
        print(
            f"FATAL: role_mapping.yaml has empty group_to_role mapping",
            file=sys.stderr,
        )
        sys.exit(1)

    # EVERYONE must NOT appear as a mapping target
    if "EVERYONE" in mapping.values():
        print(
            f"FATAL: 'EVERYONE' is reserved and must not be assigned to a group",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"role_mapping.yaml validated: {len(mapping)} groups configured")
```

Then call `validate_role_mapping()` at the very top of the `main()` (or whatever the entry function is).

- [ ] **Step 3: Verify**

```bash
cd backend && python -m scripts.init_db --dry-run 2>&1 | head -20
```

Expected: prints `role_mapping.yaml validated: 6 groups configured` (or similar). If `--dry-run` is not supported, comment out the actual DB calls temporarily to test the validation in isolation, then revert.

---

## Task 17: Run the ACL tests one more time and commit Plan 1

**Files:** none (verification + commit)

- [ ] **Step 1: Run the ACL tests**

```bash
cd backend && python -m pytest tests/test_acl.py -v
```

Expected: 7 tests pass.

- [ ] **Step 2: Run a syntax check across the whole db package**

```bash
python -c "
import importlib
for mod in ['app.db.models', 'app.db.emma_memory_models',
            'app.db.emma_reactive_models', 'app.db.agent_models',
            'app.db.edit_session_models', 'app.core.auth.acl']:
    importlib.import_module(mod)
    print(f'{mod} ok')
"
```

Expected: every module prints `ok`. If any raises ImportError, fix the residual references before committing.

- [ ] **Step 3: Verify the working tree**

```bash
git status
```

Expected: many modified files, several new files, several moved migration files in `_archived/`. No deleted files outside `versions/`.

- [ ] **Step 4: Stage Plan 1 changes**

```bash
git add backend/docker/.env backend/docker/docker-compose*.yml
git add backend/docker/init-scripts/02-init-nouxcube.sql
git add backend/docker/onboarding.sh
git add backend/app/config/role_mapping.yaml
git add backend/app/core/auth/acl.py
git add backend/app/core/auth/base.py
git add backend/app/core/config.py
git add backend/microservices/*/app/core/config.py
git add backend/scripts/init_db.py
git add backend/tests/conftest.py
git add backend/tests/test_acl.py
git add backend/app/db/models.py
git add backend/app/db/emma_memory_models.py
git add backend/app/db/emma_reactive_models.py
git add backend/app/db/agent_models.py
git add backend/app/db/edit_session_models.py
git add backend/alembic/versions/
git add README.md CLAUDE.md
```

- [ ] **Step 5: Delete the backup file**

```bash
rm -f backend/app/db/models.py.backup
```

- [ ] **Step 6: Verify staged files**

```bash
git status --short
```

Expected: every file from the file map at the top of this plan should be staged (M, A, R, or D). Nothing else.

- [ ] **Step 7: Commit**

```bash
git commit -m "$(cat <<'EOF'
feat(foundation): rename DB to nouxcube + introduce role-based ACL helpers

Implements Plan 1 of the multi-tenancy removal refactor.

- Rename main application database nexus_db → nouxcube across env,
  compose files, microservice configs, scripts, and docs. Postgres user
  (nexus_user) is unchanged. Langfuse database is preserved.
- Create role_mapping.yaml: KeyCloak group → canonical role identifier
  indirection. EVERYONE reserved as wildcard.
- Create app/core/auth/acl.py with filter_visible_to_user (the universal
  role-based query filter) and require_role (FastAPI dependency factory).
  Full TDD coverage in tests/test_acl.py.
- Drop 12 tenant model classes from app/db/models.py: Tenant,
  TenantAuthConfig, Role, Permission, RoleAssignment, the audit tables,
  DocumentShare and friends, TeamInvitation.
- Drop tenant_id columns and FKs from all surviving models across
  app/db/{models,emma_memory_models,emma_reactive_models,agent_models,
  edit_session_models}.py. Replace tenant-scoped composite indexes and
  unique constraints with their global equivalents.
- Add roles ARRAY(String) column to Document with GIN index.
- Add default_document_roles ARRAY(String) column to Connector.
- Archive 37 existing Alembic migrations into versions/_archived/.
  Generate a single new initial migration matching the new schema.
- Wire init_db.py to validate role_mapping.yaml at startup.

This commit changes the schema definition only. API endpoints, services,
microservices, frontend, and the actual database rebuild come in
subsequent plans (2-5). The current running database is not touched.

Spec: docs/superpowers/specs/2026-04-06-remove-multi-tenancy-design.md
Plan: docs/superpowers/plans/2026-04-06-remove-tenancy-01-foundation.md

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: Verify the commit**

```bash
git log -1 --stat
```

Expected: shows the commit summary and the list of files changed. The file count should be ~50 files (the configs, the models, the 37 archived migrations, the new migration, the new files).

---

## Task 18: Self-check before handing off to Plan 2

**Files:** none (verification only)

- [ ] **Step 1: Confirm Plan 1 outputs are in place**

```bash
test -f backend/app/config/role_mapping.yaml && echo "yaml ok"
test -f backend/app/core/auth/acl.py && echo "acl ok"
test -f backend/docker/init-scripts/02-init-nouxcube.sql && echo "init script ok"
python -c "from app.core.auth.base import UserProfile; UserProfile(sub='x', email='y')" && echo "UserProfile ok"
ls backend/alembic/versions/ | grep -v _archived | wc -l   # expected: 1
ls backend/alembic/versions/_archived/ | grep ".py$" | wc -l  # expected: 37
```

Expected: all four checks succeed.

- [ ] **Step 2: Confirm zero residual tenant_id references in db package**

```bash
grep -rn "tenant_id\|tenants.id\|TenantAuthConfig\|RoleAssignment\|DocumentShare" backend/app/db/ --include="*.py"
```

Expected: zero matches.

- [ ] **Step 3: Confirm zero `nexus_db` references outside archived migrations**

```bash
grep -rn "nexus_db" backend/ frontend/ docs/ README.md CLAUDE.md 2>/dev/null \
  | grep -v "alembic/versions/_archived" \
  | grep -v "docs/superpowers/plans/_2026"
```

Expected: zero matches. Any match must be cleaned before Plan 2.

- [ ] **Step 4: Mark Plan 1 complete**

Plan 1 is done. The codebase now has:
- The new schema in models (no tenant tables, `roles[]` on documents, `default_document_roles` on connectors).
- A single Alembic migration matching that schema.
- The ACL helpers, fully tested.
- The role_mapping.yaml config and its validation.
- All `nexus_db` references replaced with `nouxcube`.

**The application backend will not start cleanly yet** because the API layer still references the deleted `tenant_id`, `Tenant`, `Role`, etc. classes. That is intentional — Plan 2 will fix the API, Plan 3 the microservices, Plan 4 the frontend, and Plan 5 will run the rebuild.

**Next plan:** `docs/superpowers/plans/2026-04-06-remove-tenancy-02-backend-api.md`
