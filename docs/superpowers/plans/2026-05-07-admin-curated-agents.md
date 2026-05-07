# Admin-Curated Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir los 10 dominios hardcoded de Emma (`analyze_domain`) en un catálogo de agentes administrado vía CRUD admin-only, invocables por usuarios autenticados desde el chat de Emma con `@<slug>`, sobre el stack existente LangGraph + LangChain + Langfuse.

**Architecture:** Tabla `agents` en PostgreSQL (slug único, persona JSONB, scope JSONB) + endpoints REST `GET/POST/PUT/DELETE /api/v1/agents` (admin gating con `require_superuser`). El microservicio `emma-agent-service` reemplaza el tool `analyze_domain` por `invoke_agent(agent_slug, question, context)`, que carga el agente vía `AgentLoader` (DB row + Langfuse prompt `agent_<slug>_persona`) y ejecuta una llamada LLM con la persona + scope filters. Frontend: páginas `/agents` (gallery todos) y `/admin/agents/*` (CRUD admin), extensión del menú `@`-mention con sección "Asistentes", y badge `🤖 <agent_name>` en el bubble de respuesta.

**Tech Stack:** FastAPI + SQLAlchemy 2.x async + Alembic + Pydantic v2 (backend); LangGraph 1.x + LangChain + Langfuse SDK + psycopg3 + Redis (emma microservice); Next.js 15 App Router + React 19 + Tailwind + shadcn/ui (frontend); pytest-asyncio (tests).

**Branch:** `feature/admin-curated-agents` desde `development`.

**Spec source:** `docs/superpowers/specs/2026-05-06-admin-curated-agents-design.md` (commit `ee3dcad1`).

---

## File Structure

### New backend files

| Path | Responsibility |
|---|---|
| `backend/app/core/auth/superuser.py` | `require_superuser` FastAPI dependency reusable. |
| `backend/app/db/agent_models.py` | (rewritten) `Agent` SQLAlchemy model — orphan deleted in Phase 0. |
| `backend/app/schemas/agent.py` | Pydantic schemas: `AgentBase`, `AgentCreate`, `AgentUpdate`, `AgentResponse`, `Persona`, `Scope`. |
| `backend/app/services/agent_service.py` | `AgentService` con CRUD operations + Langfuse push hook. |
| `backend/app/api/v1/agents.py` | (rewritten) 6 endpoints REST (list/get/create/update/delete/duplicate). |
| `backend/alembic/versions/<rev>_add_agents_table.py` | Migración aditiva (downgrade reversible). |
| `backend/scripts/seed_default_agents.py` | One-shot: inserta `emma_general` (seed) + 3 starters inactivos. |
| `backend/scripts/sync_agents_to_langfuse.py` | One-shot recovery: re-push de cada agente activo a Langfuse. |
| `backend/tests/test_agents_service.py` | Unit tests del service. |
| `backend/tests/test_agents_api.py` | Integration tests de los 6 endpoints. |
| `backend/tests/test_require_superuser.py` | Tests de la dependency. |

### Modified backend files

| Path | Change |
|---|---|
| `backend/app/api/v1/__init__.py` | Re-incluir `agents` router (sigue ahí, solo verificar). |
| `backend/app/api/v1/emma.py` | Aceptar `agent_slug?: str` en el body de `/emma/query/stream`. |

### New emma-agent-service files

| Path | Responsibility |
|---|---|
| `backend/microservices/emma-agent-service/app/services/agent_loader.py` | `AgentLoader.load_by_slug(slug)` → `LoadedAgent` con persona + scope + runtime params. |
| `backend/microservices/emma-agent-service/app/agents/langgraph/tools/invoke_agent.py` | (renombrado de `specialists.py`) Tool `invoke_agent`. |
| `backend/microservices/emma-agent-service/scripts/migrate_admin_curated_agents_prompt.py` | Push `emma_react_system` v12 con `<available_agents>` block. |
| `backend/microservices/emma-agent-service/scripts/migrate_seed_agent_personas.py` | Push `agent_emma_general_persona` + 3 starter personas. |
| `backend/microservices/emma-agent-service/tests/test_agent_loader.py` | Unit tests del loader. |
| `backend/microservices/emma-agent-service/tests/test_invoke_agent_tool.py` | Unit tests del tool. |

### Modified emma-agent-service files

| Path | Change |
|---|---|
| `backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py` | Quitar `analyze_domain`, añadir `invoke_agent`. |
| `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py` | Si `state["agent_slug"]` está set, marcar para forzar `invoke_agent` en ReAct. |
| `backend/microservices/emma-agent-service/app/agents/langgraph/state.py` | Añadir `agent_slug: Optional[str]` al `EmmaState`. |
| `backend/microservices/emma-agent-service/app/api/emma.py` | Pasar `agent_slug` y emitir SSE `agent_metadata`. |

### Deleted (Phase 0)

| Path | Status |
|---|---|
| `backend/app/api/v1/agents.py` | Orphan (a recrear en Phase 1). |
| `backend/app/db/agent_models.py` | Orphan `AgentType` enum (a recrear en Phase 1). |
| `backend/app/db/models_with_agents.backup` | Backup file. |
| `backend/app/schemas/agent_management.py` | Orphan schemas. |
| `backend/scripts/seed_agents.py`, `init_agent_definitions.py`, `init_agents.py` | Orphan scripts. |
| `backend/alembic/versions/_archived/60341decaf9a_add_agent_management_tables.py` | Archived migration. |
| `frontend/src/app/agents/page.tsx` | Dashboard orphan. |
| `frontend/src/components/agents/*` (9 archivos) | Componentes orphan. |
| `frontend/src/lib/services/agent.service.ts`, `agents.service.ts` | Servicios orphan. |
| `frontend/src/lib/agent-use-cases.ts` | Orphan. |
| `frontend/src/components/layout/agents-sidebar.tsx`, `agents-main-sidebar.tsx` | Orphan layout. |
| `frontend/src/components/navigation/nav-agents.tsx` | Orphan navigation. |
| `frontend/src/components/chat/agent-message-renderer.tsx` | Orphan renderer. |

### New frontend files (cherry-picked from `feature/user-agents-mock` o reescritos)

| Path | Origin |
|---|---|
| `frontend/src/app/admin/agents/page.tsx` | Cherry-pick de `feature/user-agents-mock`. |
| `frontend/src/app/admin/agents/new/page.tsx` | Cherry-pick. |
| `frontend/src/app/admin/agents/[id]/edit/page.tsx` | Cherry-pick. |
| `frontend/src/components/agents/agent-builder-form.tsx` | Cherry-pick. |
| `frontend/src/components/agents/agent-playground.tsx` | Cherry-pick + rewire al backend real. |
| `frontend/src/lib/services/agents.service.ts` | Reescrito (real API client). |
| `frontend/src/app/agents/page.tsx` | Nuevo (gallery read-only). |

### Modified frontend files

| Path | Change |
|---|---|
| `frontend/src/components/documents/entity-search-menu.tsx` | Añadir sección "Asistentes" con fetch a `/api/v1/agents?active=true`. |
| `frontend/src/components/ui/rich-input-with-mentions.tsx` | `parseEntityTags` ya devuelve `agent`-typed tags; el chat sender extrae `agent_slug` del primer agent tag. |
| `frontend/src/lib/services/emma.service.ts` | Aceptar `agent_slug?: string` en payload, capturar SSE `agent_metadata`. |
| `frontend/src/components/emma-chat/messages/MessageBubble.tsx` | Render chip `🤖 <agent_name>` cuando metadata presente y slug ≠ `emma_general`. |
| `frontend/src/components/layout/AppSidebar.tsx` (o equivalente) | Entry "Agentes" gated en AdminGuard. |

### New docs

| Path | Content |
|---|---|
| `docs/architecture/AGENTS.md` | Architecture-level doc del sistema. |
| `CLAUDE.md` | (modify) sección "Agents Catalog" referenciando `AGENTS.md`. |

---

## Phase 0 — Cleanup orphan code + create `require_superuser` helper

**Goal:** Dejar el repo limpio de los 17+ archivos orphan que conflictarían con la implementación nueva, y centralizar la dependencia `require_superuser`.

### Task 0.1: Crear branch de feature

**Files:**
- Modify: working tree (no archivos).

- [ ] **Step 1: Crear y cambiarse a la branch desde `development`**

```bash
git checkout development
git pull origin development
git checkout -b feature/admin-curated-agents
git status
```

Expected: `On branch feature/admin-curated-agents`, working tree clean.

- [ ] **Step 2: Verificar HEAD**

```bash
git log --oneline -1
```

Expected: el último commit `ee3dcad1 docs(specs): admin-curated agents design` (o un commit posterior si `development` avanzó).

---

### Task 0.2: Test que valida `require_superuser` (TDD red)

**Files:**
- Test: `backend/tests/test_require_superuser.py`

- [ ] **Step 1: Escribir test failing — escribe el archivo completo**

```python
# backend/tests/test_require_superuser.py
"""Tests for require_superuser FastAPI dependency."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.auth.superuser import require_superuser
from app.schemas.user import UserProfile


def _make_profile(*, is_superuser: bool) -> UserProfile:
    return UserProfile(
        id="00000000-0000-0000-0000-000000000001",
        email="user@example.com",
        full_name="Test User",
        is_superuser=is_superuser,
    )


@pytest.mark.asyncio
async def test_require_superuser_passes_for_admin() -> None:
    profile = _make_profile(is_superuser=True)
    result = await require_superuser(current_user=profile)
    assert result is profile


@pytest.mark.asyncio
async def test_require_superuser_rejects_non_admin() -> None:
    profile = _make_profile(is_superuser=False)
    with pytest.raises(HTTPException) as exc:
        await require_superuser(current_user=profile)
    assert exc.value.status_code == 403
    assert "superuser" in exc.value.detail.lower()
```

- [ ] **Step 2: Run test — verifica que falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_require_superuser.py -v
```

Expected: ImportError (`No module named 'app.core.auth.superuser'`).

---

### Task 0.3: Implementar `require_superuser` (TDD green)

**Files:**
- Create: `backend/app/core/auth/superuser.py`

- [ ] **Step 1: Escribir el helper**

```python
# backend/app/core/auth/superuser.py
"""Superuser-only FastAPI dependency.

Centralizes the `is_superuser` gate used across admin endpoints
(agents catalog, weaviate inspection, prompt management). Replaces
the per-router `_require_admin` helpers introduced in commit 940a3460.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.schemas.user import UserProfile


async def require_superuser(
    current_user: UserProfile = Depends(get_current_user),
) -> UserProfile:
    """Return the current user if they are a superuser, else raise 403.

    Use as ``Depends(require_superuser)`` on every admin-only route.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This operation requires a superuser account.",
        )
    return current_user
```

- [ ] **Step 2: Crear `__init__.py` si no existe en `core/auth/`**

```bash
touch /home/nexus/git/nexus-documents-ia/backend/app/core/auth/__init__.py
```

- [ ] **Step 3: Run test — verifica que pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_require_superuser.py -v
```

Expected: 2 passed.

---

### Task 0.4: Borrar archivos orphan backend

**Files:**
- Delete: 7 archivos backend listados en spec §Phase 0.

- [ ] **Step 1: Pre-deletion grep para detectar imports activos**

```bash
cd /home/nexus/git/nexus-documents-ia
grep -rn "from app.db.agent_models\|from app.schemas.agent_management\|from app.api.v1.agents" backend/ --include="*.py" | grep -v "_archived\|test_\|.backup"
```

Expected: cero matches (o solo registro en `api/v1/__init__.py` que se regenera en Phase 1).

- [ ] **Step 2: Borrar archivos orphan**

```bash
cd /home/nexus/git/nexus-documents-ia
rm -f backend/app/api/v1/agents.py
rm -f backend/app/db/agent_models.py
rm -f backend/app/db/models_with_agents.backup
rm -f backend/app/schemas/agent_management.py
rm -f backend/scripts/seed_agents.py
rm -f backend/scripts/init_agent_definitions.py
rm -f backend/scripts/init_agents.py
rm -f backend/alembic/versions/_archived/60341decaf9a_add_agent_management_tables.py
```

- [ ] **Step 3: Limpiar referencias residuales en `api/v1/__init__.py`**

Lee el archivo, localiza `from app.api.v1 import ... agents ...` y `agents.router`, y borra esas dos líneas (router + import). Después:

```bash
cd /home/nexus/git/nexus-documents-ia/backend && python -c "from app.main import app; print('imports OK', len(app.routes), 'routes')"
```

Expected: `imports OK <N> routes` sin tracebacks.

---

### Task 0.5: Borrar archivos orphan frontend

**Files:**
- Delete: 14 archivos/directorios frontend listados en spec §Phase 0.

- [ ] **Step 1: Pre-deletion grep en frontend**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
grep -rn "from '@/components/agents\|from '@/lib/services/agent" src/ --include="*.tsx" --include="*.ts" | grep -v node_modules
```

Expected: cero matches activos (los matches dentro de archivos a borrar no cuentan).

- [ ] **Step 2: Borrar archivos**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend
rm -f src/app/agents/page.tsx
rm -rf src/components/agents
rm -f src/lib/services/agent.service.ts
rm -f src/lib/services/agents.service.ts
rm -f src/lib/agent-use-cases.ts
rm -f src/components/layout/agents-sidebar.tsx
rm -f src/components/layout/agents-main-sidebar.tsx
rm -f src/components/navigation/nav-agents.tsx
rm -f src/components/chat/agent-message-renderer.tsx
```

- [ ] **Step 3: Limpiar imports rotos detectados**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npx tsc --noEmit 2>&1 | head -60
```

Cualquier error que mencione paths borrados → editar el archivo importador para quitar la referencia (puede ser sidebar/layout). Repetir hasta que `tsc` solo muestre errores pre-existentes (compárese con la baseline en `development`).

- [ ] **Step 4: Smoke test final**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npm run lint -- --quiet 2>&1 | tail -20
```

Expected: cero nuevos warnings respecto a baseline.

---

### Task 0.6: Commit Phase 0

- [ ] **Step 1: Stage + commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add backend/app/core/auth/ backend/tests/test_require_superuser.py
git add -u backend/ frontend/
git status  # confirma 17 archivos borrados + 3 nuevos
git commit -m "$(cat <<'EOF'
chore(phase-0): cleanup orphan agent code + add require_superuser dep

Removes 17 orphan files (backend agent_models, agents API stub, frontend
dashboard + service + 9 UI components) that referenced the dead model
predating the admin-curated agents redesign. Centralizes the
is_superuser gate as require_superuser for reuse across admin routes.

Spec: docs/superpowers/specs/2026-05-06-admin-curated-agents-design.md
EOF
)"
```

Expected: clean commit, working tree clean.

---

## Phase 1 — Backend: model + migration + CRUD API

**Goal:** Modelo `Agent`, migración Alembic, schemas Pydantic, service y 6 endpoints REST con admin gating. Tests primero, código después.

### Task 1.1: Test del modelo `Agent` (TDD red)

**Files:**
- Test: `backend/tests/test_agent_model.py`

- [ ] **Step 1: Escribir test del modelo**

```python
# backend/tests/test_agent_model.py
"""Smoke tests for the Agent SQLAlchemy model."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db.agent_models import Agent
from app.db.models import ModelRole


@pytest.mark.asyncio
async def test_create_minimal_agent(async_session) -> None:
    owner_id = uuid.uuid4()
    agent = Agent(
        name="Contabilidad",
        slug="contabilidad",
        description="Análisis de facturas y pagos",
        owner_id=owner_id,
    )
    async_session.add(agent)
    await async_session.flush()

    result = await async_session.execute(select(Agent).where(Agent.slug == "contabilidad"))
    fetched = result.scalar_one()
    assert fetched.id is not None
    assert fetched.is_active is False
    assert fetched.is_seed is False
    assert fetched.persona == {}
    assert fetched.scope == {}
    assert fetched.model_role == ModelRole.CHAT
    assert fetched.temperature == 0.5
    assert fetched.usage_count == 0


@pytest.mark.asyncio
async def test_unique_slug(async_session) -> None:
    from sqlalchemy.exc import IntegrityError

    owner_id = uuid.uuid4()
    async_session.add(Agent(name="A1", slug="dup", owner_id=owner_id))
    await async_session.flush()
    async_session.add(Agent(name="A2", slug="dup", owner_id=owner_id))
    with pytest.raises(IntegrityError):
        await async_session.flush()
```

- [ ] **Step 2: Run test — falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agent_model.py -v
```

Expected: ImportError (`agent_models` no existe).

---

### Task 1.2: Implementar modelo `Agent`

**Files:**
- Create: `backend/app/db/agent_models.py`

- [ ] **Step 1: Escribir el modelo**

```python
# backend/app/db/agent_models.py
"""SQLAlchemy model for the admin-curated agents catalog."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base_class import Base
from app.db.models import ModelRole


class Agent(Base):
    """Admin-curated specialist agent invokable from the chat with @<slug>."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True, index=True)
    slug = Column(String(50), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=False, default="IconRobot")
    color = Column(String(20), nullable=False, default="blue")
    persona = Column(JSONB, nullable=False, default=dict)
    scope = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=False, index=True)
    is_seed = Column(Boolean, nullable=False, default=False)
    model_role = Column(SQLEnum(ModelRole, name="modelrole"), nullable=False, default=ModelRole.CHAT)
    temperature = Column(Float, nullable=False, default=0.5)
    usage_count = Column(BigInteger, nullable=False, default=0)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_agents_slug_active", "slug", "is_active"),
    )
```

- [ ] **Step 2: Asegurar que `ModelRole` esté importable desde `app.db.models`**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && grep -n "class ModelRole" app/db/models.py
```

Si NO existe, mover/copiar la definición desde `backend/microservices/emma-agent-service/app/agents/llm_types.py` hacia `app/db/models.py`:

```python
# Append to backend/app/db/models.py if missing
import enum

class ModelRole(str, enum.Enum):
    """LLM model role for routing (mirror of emma-agent-service llm_types.ModelRole)."""
    PLANNER = "PLANNER"
    CHAT = "CHAT"
```

- [ ] **Step 3: Importar el modelo en el aggregator para que Alembic lo descubra**

Edita `backend/app/db/__init__.py` y añade al final del archivo:

```python
from app.db.agent_models import Agent  # noqa: F401
```

- [ ] **Step 4: Run tests — pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agent_model.py -v
```

Expected: 2 passed.

---

### Task 1.3: Migración Alembic `agents` table

**Files:**
- Create: `backend/alembic/versions/<rev>_add_agents_table.py` (filename autogenerado).

- [ ] **Step 1: Generar migración**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && python scripts/create_migration.py -m "add agents table" --autogenerate
```

Confirma que el archivo creado tiene `down_revision = 'f8a9b0c1d2e3'`.

- [ ] **Step 2: Inspeccionar la migración generada**

Abre el archivo `backend/alembic/versions/<rev>_add_agents_table.py`. Verifica que `op.create_table("agents", ...)` incluye:

- `id UUID PK`
- `name String(100) UNIQUE NOT NULL`
- `slug String(50) UNIQUE NOT NULL`
- `description Text`
- `icon String(50) NOT NULL DEFAULT 'IconRobot'`
- `color String(20) NOT NULL DEFAULT 'blue'`
- `persona JSONB NOT NULL DEFAULT '{}'`
- `scope JSONB NOT NULL DEFAULT '{}'`
- `is_active Boolean NOT NULL DEFAULT FALSE`
- `is_seed Boolean NOT NULL DEFAULT FALSE`
- `model_role ENUM('PLANNER','CHAT')`
- `temperature Float`
- `usage_count BigInteger DEFAULT 0`
- `owner_id UUID NOT NULL FK users.id`
- `created_at`, `updated_at` timestamps con `server_default`

Y los índices:

- `idx_agents_slug` (UNIQUE), `idx_agents_name` (UNIQUE)
- `idx_agents_is_active`
- `idx_agents_slug_active` (composite)

Si Alembic omitió alguno (es típico con `Index()` declarativos), añádelo manualmente con `op.create_index(...)`.

- [ ] **Step 3: Asegurar `downgrade()` reversible**

Reemplaza el cuerpo de `downgrade()` por:

```python
def downgrade() -> None:
    op.drop_index("idx_agents_slug_active", table_name="agents")
    op.drop_table("agents")
    op.execute("DROP TYPE IF EXISTS modelrole")
```

- [ ] **Step 4: Run migration up + down + up**

```bash
cd /home/nexus/git/nexus-documents-ia/backend
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```

Expected: cada comando termina con `OK`. La tabla `agents` existe tras el último `upgrade`.

- [ ] **Step 5: Verificar tabla en Postgres**

```bash
docker compose -f /home/nexus/git/nexus-documents-ia/backend/docker/docker-compose.yml exec db \
  psql -U nexus_user -d nouxcube -c "\d agents"
```

Expected: tabla con todas las columnas listadas.

---

### Task 1.4: Schemas Pydantic

**Files:**
- Create: `backend/app/schemas/agent.py`
- Test: `backend/tests/test_agent_schemas.py`

- [ ] **Step 1: Escribir tests primero**

```python
# backend/tests/test_agent_schemas.py
"""Tests for Agent Pydantic schemas (validation rules from spec §Data Model)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.db.models import ModelRole
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    Persona,
    Scope,
)


class TestSlugValidation:
    @pytest.mark.parametrize("good_slug", ["contabilidad", "ventas", "legal_es", "agent_v2"])
    def test_accepts_valid_slug(self, good_slug: str) -> None:
        agent = AgentCreate(name="X", slug=good_slug)
        assert agent.slug == good_slug

    @pytest.mark.parametrize(
        "bad_slug",
        ["Contabilidad", "9start", "with-dash", "with space", "x", "@mention", "with.dot"],
    )
    def test_rejects_invalid_slug(self, bad_slug: str) -> None:
        with pytest.raises(ValidationError):
            AgentCreate(name="X", slug=bad_slug)


class TestTemperatureRange:
    def test_accepts_valid(self) -> None:
        AgentCreate(name="X", slug="x", temperature=1.5)

    @pytest.mark.parametrize("bad", [-0.1, 2.01, 5.0])
    def test_rejects_out_of_range(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            AgentCreate(name="X", slug="x", temperature=bad)


class TestExtraForbid:
    def test_create_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            AgentCreate(name="X", slug="x", unknown_field="oops")


class TestPersonaShape:
    def test_default(self) -> None:
        p = Persona()
        assert p.style == "concise"
        assert p.language == "es"
        assert p.instructions == ""

    def test_invalid_style(self) -> None:
        with pytest.raises(ValidationError):
            Persona(style="weird")


class TestScopeShape:
    def test_all_optional(self) -> None:
        s = Scope()
        assert s.folders == []
        assert s.semantic_types == []
        assert s.quality_min is None

    def test_quality_min_range(self) -> None:
        with pytest.raises(ValidationError):
            Scope(quality_min=1.5)


class TestUpdate:
    def test_all_optional(self) -> None:
        u = AgentUpdate()
        assert u.name is None
        assert u.persona is None
```

- [ ] **Step 2: Run — falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agent_schemas.py -v
```

Expected: ImportError on `app.schemas.agent`.

- [ ] **Step 3: Implementar schemas**

```python
# backend/app/schemas/agent.py
"""Pydantic schemas for the agents catalog."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import ModelRole

SLUG_REGEX = re.compile(r"^[a-z][a-z0-9_]{1,49}$")


class Persona(BaseModel):
    """Persona block — author content + runtime modifiers."""

    model_config = ConfigDict(extra="forbid")

    style: Literal["concise", "detailed", "conversational"] = "concise"
    language: Literal["es", "en", "auto"] = "es"
    instructions: str = ""


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_: Optional[date] = Field(default=None, alias="from")
    to: Optional[date] = None


class Scope(BaseModel):
    """Scope = narrowing of existing tool filters; every key optional."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    folders: list[uuid.UUID] = Field(default_factory=list)
    semantic_types: list[str] = Field(default_factory=list)
    person_filter: list[uuid.UUID] = Field(default_factory=list)
    entity_filters: list[uuid.UUID] = Field(default_factory=list)
    date_range: Optional[DateRange] = None
    quality_min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    connector_ids: list[uuid.UUID] = Field(default_factory=list)


class AgentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    icon: str = "IconRobot"
    color: str = "blue"
    persona: Persona = Field(default_factory=Persona)
    scope: Scope = Field(default_factory=Scope)
    is_active: bool = False
    model_role: ModelRole = ModelRole.CHAT
    temperature: float = Field(0.5, ge=0.0, le=2.0)

    @field_validator("slug")
    @classmethod
    def slug_pattern(cls, v: str) -> str:
        if not SLUG_REGEX.match(v):
            raise ValueError(
                "slug must match ^[a-z][a-z0-9_]{1,49}$ (lowercase, starts with letter)"
            )
        return v


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    """All fields optional for PATCH-style update."""

    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    persona: Optional[Persona] = None
    scope: Optional[Scope] = None
    is_active: Optional[bool] = None
    model_role: Optional[ModelRole] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)


class AgentResponse(AgentBase):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    is_seed: bool
    usage_count: int
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: Run — pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agent_schemas.py -v
```

Expected: todos los tests passed.

---

### Task 1.5: AgentService — tests

**Files:**
- Test: `backend/tests/test_agents_service.py`

- [ ] **Step 1: Escribir tests**

```python
# backend/tests/test_agents_service.py
"""Tests for AgentService CRUD + Langfuse push hook."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.db.agent_models import Agent
from app.schemas.agent import AgentCreate, AgentUpdate, Persona, Scope
from app.services.agent_service import AgentService


@pytest.fixture
def langfuse_mock() -> AsyncMock:
    m = AsyncMock()
    m.push_persona.return_value = None
    return m


@pytest.fixture
def service(async_session, langfuse_mock) -> AgentService:
    return AgentService(db=async_session, langfuse=langfuse_mock)


@pytest.mark.asyncio
async def test_create_pushes_to_langfuse(service, langfuse_mock) -> None:
    owner = uuid.uuid4()
    payload = AgentCreate(
        name="Contabilidad",
        slug="contabilidad",
        persona=Persona(instructions="Eres el asistente de contabilidad."),
    )
    agent = await service.create(payload, owner_id=owner)
    assert agent.slug == "contabilidad"
    assert agent.is_seed is False
    langfuse_mock.push_persona.assert_awaited_once_with(
        slug="contabilidad",
        instructions="Eres el asistente de contabilidad.",
    )


@pytest.mark.asyncio
async def test_create_rolls_back_when_langfuse_fails(service, langfuse_mock, async_session) -> None:
    langfuse_mock.push_persona.side_effect = ConnectionError("langfuse down")
    payload = AgentCreate(name="X", slug="failtest")
    with pytest.raises(HTTPException) as exc:
        await service.create(payload, owner_id=uuid.uuid4())
    assert exc.value.status_code == 503
    # Confirm rollback: no row persisted.
    from sqlalchemy import select
    res = await async_session.execute(select(Agent).where(Agent.slug == "failtest"))
    assert res.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_list_active_filter(service) -> None:
    owner = uuid.uuid4()
    await service.create(AgentCreate(name="A1", slug="a1", is_active=True), owner_id=owner)
    await service.create(AgentCreate(name="A2", slug="a2", is_active=False), owner_id=owner)
    actives = await service.list(active_only=True)
    assert {a.slug for a in actives} == {"a1"}
    assert len(await service.list(active_only=False)) == 2


@pytest.mark.asyncio
async def test_delete_seed_returns_409(service) -> None:
    owner = uuid.uuid4()
    agent = await service.create(AgentCreate(name="Seed", slug="seedy"), owner_id=owner)
    # Promote to seed via direct DB write (not allowed in API).
    agent.is_seed = True
    await service.db.flush()
    with pytest.raises(HTTPException) as exc:
        await service.delete(agent.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_seed_cannot_be_deactivated(service) -> None:
    owner = uuid.uuid4()
    agent = await service.create(AgentCreate(name="Seed", slug="seed2", is_active=True), owner_id=owner)
    agent.is_seed = True
    await service.db.flush()
    with pytest.raises(HTTPException) as exc:
        await service.update(agent.id, AgentUpdate(is_active=False))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_duplicate_creates_with_new_slug(service) -> None:
    owner = uuid.uuid4()
    src = await service.create(
        AgentCreate(name="Original", slug="orig", description="desc"),
        owner_id=owner,
    )
    dup = await service.duplicate(src.id, owner_id=owner)
    assert dup.slug == "orig_copy"
    assert dup.name == "Original (copia)"
    assert dup.is_active is False
    assert dup.is_seed is False
```

- [ ] **Step 2: Run — falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agents_service.py -v
```

Expected: ImportError.

---

### Task 1.6: Implementar `AgentService`

**Files:**
- Create: `backend/app/services/agent_service.py`

- [ ] **Step 1: Escribir el service**

```python
# backend/app/services/agent_service.py
"""CRUD service for the agents catalog with Langfuse persona push hook."""
from __future__ import annotations

import logging
import uuid
from typing import Optional, Protocol

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.agent_models import Agent
from app.schemas.agent import AgentCreate, AgentUpdate

logger = logging.getLogger(__name__)


class LangfusePersonaPusher(Protocol):
    """Adapter that pushes the persona instructions to Langfuse."""

    async def push_persona(self, *, slug: str, instructions: str) -> None: ...


class AgentService:
    """CRUD for the agents catalog. Holds a DB session + a Langfuse adapter."""

    def __init__(self, db: AsyncSession, langfuse: LangfusePersonaPusher) -> None:
        self.db = db
        self.langfuse = langfuse

    async def list(self, *, active_only: bool = False) -> list[Agent]:
        stmt = select(Agent).order_by(Agent.name)
        if active_only:
            stmt = stmt.where(Agent.is_active.is_(True))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, agent_id: uuid.UUID) -> Agent:
        result = await self.db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    async def get_by_slug(self, slug: str) -> Optional[Agent]:
        result = await self.db.execute(select(Agent).where(Agent.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, payload: AgentCreate, *, owner_id: uuid.UUID) -> Agent:
        agent = Agent(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            icon=payload.icon,
            color=payload.color,
            persona=payload.persona.model_dump(),
            scope=payload.scope.model_dump(mode="json"),
            is_active=payload.is_active,
            is_seed=False,
            model_role=payload.model_role,
            temperature=payload.temperature,
            owner_id=owner_id,
        )
        self.db.add(agent)
        await self.db.flush()

        try:
            await self.langfuse.push_persona(
                slug=agent.slug,
                instructions=payload.persona.instructions,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Langfuse push failed for slug=%s: %s", agent.slug, exc)
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Langfuse unreachable; agent not created.",
            ) from exc

        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def update(self, agent_id: uuid.UUID, payload: AgentUpdate) -> Agent:
        agent = await self.get(agent_id)

        data = payload.model_dump(exclude_unset=True)
        if agent.is_seed and data.get("is_active") is False:
            raise HTTPException(
                status_code=409,
                detail="Seed agents cannot be deactivated.",
            )

        new_instructions: Optional[str] = None
        if "persona" in data:
            agent.persona = data["persona"]
            new_instructions = agent.persona.get("instructions", "")
        for key, value in data.items():
            if key == "persona":
                continue
            if key == "scope" and value is not None:
                agent.scope = value
                continue
            setattr(agent, key, value)
        await self.db.flush()

        if new_instructions is not None:
            try:
                await self.langfuse.push_persona(
                    slug=agent.slug,
                    instructions=new_instructions,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Langfuse update push failed for slug=%s: %s", agent.slug, exc)
                await self.db.rollback()
                raise HTTPException(
                    status_code=503,
                    detail="Langfuse unreachable; agent not updated.",
                ) from exc

        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def delete(self, agent_id: uuid.UUID) -> None:
        agent = await self.get(agent_id)
        if agent.is_seed:
            raise HTTPException(status_code=409, detail="Seed agents cannot be deleted.")
        await self.db.delete(agent)
        await self.db.commit()

    async def duplicate(self, agent_id: uuid.UUID, *, owner_id: uuid.UUID) -> Agent:
        src = await self.get(agent_id)
        suffix_n = 0
        candidate = f"{src.slug}_copy"
        while await self.get_by_slug(candidate) is not None:
            suffix_n += 1
            candidate = f"{src.slug}_copy{suffix_n}"
        dup = Agent(
            name=f"{src.name} (copia)",
            slug=candidate,
            description=src.description,
            icon=src.icon,
            color=src.color,
            persona=dict(src.persona),
            scope=dict(src.scope),
            is_active=False,
            is_seed=False,
            model_role=src.model_role,
            temperature=src.temperature,
            owner_id=owner_id,
        )
        self.db.add(dup)
        await self.db.flush()

        try:
            await self.langfuse.push_persona(
                slug=dup.slug,
                instructions=dup.persona.get("instructions", ""),
            )
        except Exception as exc:  # noqa: BLE001
            await self.db.rollback()
            raise HTTPException(status_code=503, detail="Langfuse unreachable.") from exc

        await self.db.commit()
        await self.db.refresh(dup)
        return dup
```

- [ ] **Step 2: Run tests — pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agents_service.py -v
```

Expected: 6 passed.

---

### Task 1.7: Tests del API endpoints

**Files:**
- Test: `backend/tests/test_agents_api.py`

- [ ] **Step 1: Escribir tests usando `httpx.AsyncClient` + dependency overrides**

```python
# backend/tests/test_agents_api.py
"""Integration tests for /api/v1/agents endpoints."""
from __future__ import annotations

import uuid

import pytest

ADMIN_HEADER = {"x-test-superuser": "true"}  # picked up by conftest dep override
USER_HEADER = {"x-test-superuser": "false"}


@pytest.mark.asyncio
async def test_list_requires_auth(client) -> None:
    r = await client.get("/api/v1/agents/")
    assert r.status_code in {401, 403}


@pytest.mark.asyncio
async def test_list_returns_agents_for_user(client, seeded_agent) -> None:
    r = await client.get("/api/v1/agents/", headers=USER_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert any(a["slug"] == seeded_agent.slug for a in body)


@pytest.mark.asyncio
async def test_create_rejected_for_non_admin(client) -> None:
    r = await client.post(
        "/api/v1/agents/",
        json={"name": "X", "slug": "xtest"},
        headers=USER_HEADER,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_create_succeeds_for_admin(client) -> None:
    r = await client.post(
        "/api/v1/agents/",
        json={
            "name": "Contabilidad",
            "slug": "contabilidad",
            "description": "Análisis contable",
            "persona": {"instructions": "Eres el asistente de contabilidad.", "style": "concise", "language": "es"},
        },
        headers=ADMIN_HEADER,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "contabilidad"
    assert body["is_seed"] is False


@pytest.mark.asyncio
async def test_active_filter(client, seeded_agent_inactive, seeded_agent) -> None:
    r = await client.get("/api/v1/agents/?active=true", headers=USER_HEADER)
    slugs = {a["slug"] for a in r.json()}
    assert seeded_agent.slug in slugs
    assert seeded_agent_inactive.slug not in slugs


@pytest.mark.asyncio
async def test_delete_seed_returns_409(client, seeded_agent_seed) -> None:
    r = await client.delete(f"/api/v1/agents/{seeded_agent_seed.id}", headers=ADMIN_HEADER)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_duplicate(client, seeded_agent) -> None:
    r = await client.post(f"/api/v1/agents/{seeded_agent.id}/duplicate", headers=ADMIN_HEADER)
    assert r.status_code == 201
    body = r.json()
    assert body["slug"].startswith(f"{seeded_agent.slug}_copy")
    assert body["is_active"] is False
```

(El plan asume que `conftest.py` ya provee fixtures `client`, `seeded_agent`, `seeded_agent_inactive`, `seeded_agent_seed` y un dependency override de `get_current_user` que lee `x-test-superuser`. Si no existe, en este step añadir esas fixtures en `backend/tests/conftest.py` siguiendo el patrón ya usado por `test_documents_api.py`.)

- [ ] **Step 2: Run — falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agents_api.py -v
```

Expected: 404 (router no registrado).

---

### Task 1.8: Implementar API endpoints

**Files:**
- Create: `backend/app/api/v1/agents.py`
- Modify: `backend/app/api/v1/__init__.py`

- [ ] **Step 1: Escribir el router**

```python
# backend/app/api/v1/agents.py
"""REST endpoints for the admin-curated agents catalog."""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.async_dependencies import get_async_db
from app.api.dependencies import get_current_user
from app.core.auth.superuser import require_superuser
from app.schemas.agent import AgentCreate, AgentResponse, AgentUpdate
from app.schemas.user import UserProfile
from app.services.agent_service import AgentService
from app.services.langfuse.persona import LangfusePersonaAdapter

router = APIRouter(prefix="/agents", tags=["agents"])


def _service(db: AsyncSession = Depends(get_async_db)) -> AgentService:
    return AgentService(db=db, langfuse=LangfusePersonaAdapter())


@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    active: Optional[bool] = None,
    _user: UserProfile = Depends(get_current_user),
    svc: AgentService = Depends(_service),
) -> list[AgentResponse]:
    rows = await svc.list(active_only=bool(active))
    return [AgentResponse.model_validate(a) for a in rows]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    _user: UserProfile = Depends(get_current_user),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    return AgentResponse.model_validate(await svc.get(agent_id))


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: AgentCreate,
    admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    agent = await svc.create(payload, owner_id=uuid.UUID(admin.id))
    return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    _admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    return AgentResponse.model_validate(await svc.update(agent_id, payload))


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: uuid.UUID,
    _admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> None:
    await svc.delete(agent_id)


@router.post("/{agent_id}/duplicate", response_model=AgentResponse, status_code=201)
async def duplicate_agent(
    agent_id: uuid.UUID,
    admin: UserProfile = Depends(require_superuser),
    svc: AgentService = Depends(_service),
) -> AgentResponse:
    dup = await svc.duplicate(agent_id, owner_id=uuid.UUID(admin.id))
    return AgentResponse.model_validate(dup)
```

- [ ] **Step 2: Stub del adapter Langfuse para Main API**

```python
# backend/app/services/langfuse/persona.py
"""Adapter from Main API to Langfuse for pushing agent persona prompts.

Main API only writes persona prompts; the read-side runtime resolution
happens inside emma-agent-service.
"""
from __future__ import annotations

import logging

from langfuse import Langfuse

from app.core.config import settings

logger = logging.getLogger(__name__)


class LangfusePersonaAdapter:
    """Thin wrapper around langfuse.create_prompt for agent personas."""

    def __init__(self) -> None:
        self._client = Langfuse(
            host=settings.LANGFUSE_HOST,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
        )

    async def push_persona(self, *, slug: str, instructions: str) -> None:
        name = f"agent_{slug}_persona"
        # langfuse SDK is sync; we wrap with run_in_executor in production but
        # for the adapter API we keep it async for AgentService consistency.
        import asyncio

        await asyncio.to_thread(
            self._client.create_prompt,
            name=name,
            prompt=instructions,
            labels=["production"],
            type="text",
        )
        logger.info("Pushed persona prompt name=%s len=%d", name, len(instructions))
```

(Si `app/services/langfuse/` no existe aún, créalo con `__init__.py` vacío.)

- [ ] **Step 3: Wire en `__init__.py`**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && grep -n "include_router\|from app.api.v1 import" app/api/v1/__init__.py | head -20
```

Edita `backend/app/api/v1/__init__.py` y añade:

```python
from app.api.v1 import agents as agents_module  # add to imports

# inside the router include block:
api_router.include_router(agents_module.router)
```

- [ ] **Step 4: Run tests — pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/test_agents_api.py -v
```

Expected: 7 passed.

---

### Task 1.9: Smoke test E2E con curl

- [ ] **Step 1: Levantar stack**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/docker && docker compose up -d --build api db redis
docker compose logs -f api | head -30
```

Expected: `Application startup complete.`

- [ ] **Step 2: Crear agente vía curl (con token admin de KeyCloak; ver `docs/on-premise/ONBOARDING.md` para obtener `$TOKEN`)**

```bash
TOKEN="<paste KeyCloak access_token of horelvis>"
curl -s -X POST "http://localhost:8000/api/v1/agents/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Smoke Contabilidad",
    "slug": "smoke_contabilidad",
    "description": "Smoke test agent",
    "persona": {"instructions": "Eres el asistente de smoke test."}
  }' > /tmp/agent.json
python3 -c "import json; print(json.load(open('/tmp/agent.json'))['slug'])"
```

Expected: `smoke_contabilidad` printed.

- [ ] **Step 3: List**

```bash
curl -s "http://localhost:8000/api/v1/agents/?active=false" -H "Authorization: Bearer $TOKEN" > /tmp/agents.json
python3 -c "import json; print(len(json.load(open('/tmp/agents.json'))))"
```

Expected: ≥ 1.

- [ ] **Step 4: Cleanup**

```bash
AGENT_ID=$(python3 -c "import json; print(json.load(open('/tmp/agent.json'))['id'])")
curl -s -X DELETE "http://localhost:8000/api/v1/agents/$AGENT_ID" -H "Authorization: Bearer $TOKEN" -o /dev/null -w "%{http_code}\n"
```

Expected: `204`.

---

### Task 1.10: Commit Phase 1

- [ ] **Step 1: Commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add backend/app/db/agent_models.py backend/app/schemas/agent.py
git add backend/app/services/agent_service.py backend/app/services/langfuse/
git add backend/app/api/v1/agents.py backend/app/api/v1/__init__.py
git add backend/alembic/versions/*_add_agents_table.py
git add backend/tests/test_agent_model.py backend/tests/test_agent_schemas.py
git add backend/tests/test_agents_service.py backend/tests/test_agents_api.py
git commit -m "$(cat <<'EOF'
feat(phase-1): agents CRUD API + model + migration

Adds Agent SQLAlchemy model, Alembic migration, Pydantic schemas
(AgentCreate/Update/Response, Persona, Scope), AgentService with
Langfuse persona push hook (rolls back on Langfuse failure), and 6
REST endpoints under /api/v1/agents (list/get/create/update/delete/
duplicate). Admin-only writes via require_superuser; reads open to
all authenticated users. Spec §Phase 1.
EOF
)"
```

---

## Phase 2 — Tool refactor: `invoke_agent` + `AgentLoader` + Emma system prompt

**Goal:** Reemplazar `analyze_domain` por `invoke_agent`. AgentLoader consulta Main API + Langfuse. Emma's `classify` node respeta `agent_slug` cuando viene en el request.

### Task 2.1: Test del `AgentLoader`

**Files:**
- Test: `backend/microservices/emma-agent-service/tests/test_agent_loader.py`

- [ ] **Step 1: Escribir test**

```python
# backend/microservices/emma-agent-service/tests/test_agent_loader.py
"""Unit tests for AgentLoader (Main API + Langfuse + Redis cache)."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from app.services.agent_loader import AgentLoader, LoadedAgent


@pytest.fixture
def main_api_mock() -> AsyncMock:
    m = AsyncMock()
    m.get_agent_by_slug.return_value = {
        "id": "00000000-0000-0000-0000-000000000099",
        "slug": "contabilidad",
        "name": "Contabilidad",
        "is_active": True,
        "model_role": "CHAT",
        "temperature": 0.5,
        "scope": {"semantic_types": ["factura"]},
        "persona": {"style": "concise", "language": "es", "instructions": "fallback"},
    }
    return m


@pytest.fixture
def langfuse_mock() -> AsyncMock:
    m = AsyncMock()
    m.get_prompt.return_value = "Eres el asistente de contabilidad. Cita la factura origen."
    return m


@pytest.fixture
def redis_mock() -> AsyncMock:
    cache: dict[str, str] = {}
    m = AsyncMock()

    async def get(k: str) -> str | None:
        return cache.get(k)

    async def set_(k: str, v: str, ex: int = 60) -> None:
        cache[k] = v

    m.get.side_effect = get
    m.set.side_effect = set_
    return m


@pytest.mark.asyncio
async def test_load_by_slug(main_api_mock, langfuse_mock, redis_mock) -> None:
    loader = AgentLoader(main_api=main_api_mock, langfuse=langfuse_mock, redis=redis_mock)
    loaded = await loader.load_by_slug("contabilidad")
    assert isinstance(loaded, LoadedAgent)
    assert loaded.slug == "contabilidad"
    assert "factura origen" in loaded.persona_instructions
    assert loaded.scope == {"semantic_types": ["factura"]}


@pytest.mark.asyncio
async def test_load_returns_none_when_inactive(main_api_mock, langfuse_mock, redis_mock) -> None:
    main_api_mock.get_agent_by_slug.return_value["is_active"] = False
    loader = AgentLoader(main_api=main_api_mock, langfuse=langfuse_mock, redis=redis_mock)
    assert await loader.load_by_slug("contabilidad") is None


@pytest.mark.asyncio
async def test_load_raises_on_langfuse_miss(main_api_mock, redis_mock) -> None:
    from app.services.langfuse_prompt_client import PromptNotFoundError

    langfuse_err = AsyncMock()
    langfuse_err.get_prompt.side_effect = PromptNotFoundError("agent_x_persona")
    loader = AgentLoader(main_api=main_api_mock, langfuse=langfuse_err, redis=redis_mock)
    with pytest.raises(PromptNotFoundError):
        await loader.load_by_slug("contabilidad")


@pytest.mark.asyncio
async def test_cache_hit_avoids_main_api(main_api_mock, langfuse_mock, redis_mock) -> None:
    loader = AgentLoader(main_api=main_api_mock, langfuse=langfuse_mock, redis=redis_mock)
    await loader.load_by_slug("contabilidad")
    await loader.load_by_slug("contabilidad")  # second call hits cache
    main_api_mock.get_agent_by_slug.assert_awaited_once()
```

- [ ] **Step 2: Run — falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  pytest tests/test_agent_loader.py -v
```

Expected: ImportError.

---

### Task 2.2: Implementar `AgentLoader`

**Files:**
- Create: `backend/microservices/emma-agent-service/app/services/agent_loader.py`
- Create: `backend/microservices/emma-agent-service/app/services/main_api_client.py` (si no existe — verificar primero).

- [ ] **Step 1: Verificar si existe ya un cliente Main API**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  grep -rn "class.*MainAPI\|get_agent_by_slug\|MICROSERVICES_API_KEY" app/services/ | head -10
```

Si NO existe `MainAPIClient`, crearlo en el siguiente paso. Si existe, extender solo con `get_agent_by_slug`.

- [ ] **Step 2: Crear/extender `MainAPIClient`**

```python
# backend/microservices/emma-agent-service/app/services/main_api_client.py
"""HTTP client to the Main API for cross-service reads."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class MainAPIClient:
    """Async client. Authenticates with the shared MICROSERVICES_API_KEY."""

    def __init__(self) -> None:
        self._base_url = settings.MAIN_API_URL.rstrip("/")
        self._headers = {"X-API-Key": settings.MICROSERVICES_API_KEY}

    async def get_agent_by_slug(self, slug: str) -> Optional[dict]:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{self._base_url}/api/v1/agents/",
                params={"slug": slug, "active": True},
                headers=self._headers,
            )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        rows = r.json()
        for row in rows:
            if row["slug"] == slug:
                return row
        return None

    async def list_active_agents(self, *, limit: int = 50) -> list[dict]:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(
                f"{self._base_url}/api/v1/agents/",
                params={"active": True, "order_by": "usage_count", "limit": limit},
                headers=self._headers,
            )
        r.raise_for_status()
        return r.json()
```

(Nota: el `params={"slug": slug}` requiere extender `list_agents` en Main API para aceptar `slug` filter — si no, hacer fan-out: list-all-active y filter cliente. Para mantenerlo simple en Phase 2, modifica `agents.py:list_agents` para aceptar `slug` query param.)

- [ ] **Step 3: Extender `list_agents` en Main API para aceptar `slug` filter**

Edita `backend/app/api/v1/agents.py` línea de `list_agents`:

```python
@router.get("/", response_model=list[AgentResponse])
async def list_agents(
    active: Optional[bool] = None,
    slug: Optional[str] = None,
    _user: UserProfile = Depends(get_current_user),
    svc: AgentService = Depends(_service),
) -> list[AgentResponse]:
    if slug is not None:
        agent = await svc.get_by_slug(slug)
        return [AgentResponse.model_validate(agent)] if agent else []
    rows = await svc.list(active_only=bool(active))
    return [AgentResponse.model_validate(a) for a in rows]
```

- [ ] **Step 4: Implementar `AgentLoader`**

```python
# backend/microservices/emma-agent-service/app/services/agent_loader.py
"""Loads an agent's full configuration (DB row + Langfuse persona + cache)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from app.agents.llm_types import ModelRole

logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = 60


@dataclass
class LoadedAgent:
    """Resolved agent ready for invoke_agent tool execution."""

    id: str
    slug: str
    name: str
    is_active: bool
    model_role: ModelRole
    temperature: float
    scope: dict
    persona_style: str
    persona_language: str
    persona_instructions: str  # resolved from Langfuse


class _MainAPI(Protocol):
    async def get_agent_by_slug(self, slug: str) -> Optional[dict]: ...


class _Langfuse(Protocol):
    async def get_prompt(self, name: str, *, label: str = "production") -> str: ...


class _Redis(Protocol):
    async def get(self, key: str) -> Optional[str]: ...
    async def set(self, key: str, value: str, ex: int = ...) -> None: ...


class AgentLoader:
    def __init__(self, main_api: _MainAPI, langfuse: _Langfuse, redis: _Redis) -> None:
        self.main_api = main_api
        self.langfuse = langfuse
        self.redis = redis

    async def load_by_slug(self, slug: str) -> Optional[LoadedAgent]:
        cache_key = f"agent_loader:{slug}"
        cached = await self.redis.get(cache_key)
        if cached:
            data = json.loads(cached)
            return self._row_to_loaded(data, persona_instructions=data["_persona_instructions"])

        row = await self.main_api.get_agent_by_slug(slug)
        if row is None or not row.get("is_active"):
            return None

        instructions = await self.langfuse.get_prompt(f"agent_{slug}_persona", label="production")

        loaded = self._row_to_loaded(row, persona_instructions=instructions)
        # Pre-write the cache entry with the resolved persona
        cache_payload = {**row, "_persona_instructions": instructions}
        await self.redis.set(cache_key, json.dumps(cache_payload), ex=CACHE_TTL_SECONDS)
        return loaded

    def _row_to_loaded(self, row: dict, *, persona_instructions: str) -> LoadedAgent:
        persona = row.get("persona") or {}
        return LoadedAgent(
            id=str(row["id"]),
            slug=row["slug"],
            name=row["name"],
            is_active=bool(row["is_active"]),
            model_role=ModelRole(row.get("model_role", "CHAT")),
            temperature=float(row.get("temperature", 0.5)),
            scope=row.get("scope") or {},
            persona_style=persona.get("style", "concise"),
            persona_language=persona.get("language", "es"),
            persona_instructions=persona_instructions,
        )
```

- [ ] **Step 5: Run tests — pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  pytest tests/test_agent_loader.py -v
```

Expected: 4 passed.

---

### Task 2.3: Tests del tool `invoke_agent`

**Files:**
- Test: `backend/microservices/emma-agent-service/tests/test_invoke_agent_tool.py`

- [ ] **Step 1: Escribir tests**

```python
# backend/microservices/emma-agent-service/tests/test_invoke_agent_tool.py
"""Tests for the invoke_agent tool (replaces analyze_domain)."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.langgraph.tools.invoke_agent import InvokeAgentTool
from app.agents.llm_types import ModelRole
from app.services.agent_loader import LoadedAgent


def _loaded() -> LoadedAgent:
    return LoadedAgent(
        id="00000000-0000-0000-0000-000000000099",
        slug="contabilidad",
        name="Contabilidad",
        is_active=True,
        model_role=ModelRole.CHAT,
        temperature=0.5,
        scope={"semantic_types": ["factura"]},
        persona_style="concise",
        persona_language="es",
        persona_instructions="Eres el asistente de contabilidad.",
    )


@pytest.fixture
def loader_mock() -> AsyncMock:
    m = AsyncMock()
    m.load_by_slug.return_value = _loaded()
    return m


@pytest.fixture
def llm_mock() -> AsyncMock:
    m = AsyncMock()
    m.ainvoke.return_value = type("Resp", (), {"content": "Tu factura más antigua es F-001."})()
    return m


@pytest.fixture
def usage_counter_mock() -> AsyncMock:
    m = AsyncMock()
    m.increment.return_value = None
    return m


@pytest.mark.asyncio
async def test_invoke_agent_happy_path(loader_mock, llm_mock, usage_counter_mock) -> None:
    tool = InvokeAgentTool(loader=loader_mock, llm=llm_mock, usage_counter=usage_counter_mock)
    result = await tool.execute(
        arguments={"agent_slug": "contabilidad", "question": "¿Qué cliente paga peor?"},
        context={},
    )
    assert result.success is True
    assert result.data["agent_slug"] == "contabilidad"
    assert "factura" in result.data["answer"].lower()
    usage_counter_mock.increment.assert_awaited_once()


@pytest.mark.asyncio
async def test_invoke_agent_unknown_slug(loader_mock, llm_mock, usage_counter_mock) -> None:
    loader_mock.load_by_slug.return_value = None
    tool = InvokeAgentTool(loader=loader_mock, llm=llm_mock, usage_counter=usage_counter_mock)
    result = await tool.execute(
        arguments={"agent_slug": "ghost", "question": "?"},
        context={},
    )
    assert result.success is False
    assert "not found" in result.error.lower() or "ghost" in result.error
    usage_counter_mock.increment.assert_not_awaited()


@pytest.mark.asyncio
async def test_invoke_agent_uses_persona_temperature(loader_mock, llm_mock, usage_counter_mock) -> None:
    tool = InvokeAgentTool(loader=loader_mock, llm=llm_mock, usage_counter=usage_counter_mock)
    await tool.execute(arguments={"agent_slug": "contabilidad", "question": "?"}, context={})
    call_kwargs = llm_mock.ainvoke.await_args.kwargs
    # Temperature passed via bind / config
    assert call_kwargs.get("config", {}).get("configurable", {}).get("temperature") == 0.5 \
           or call_kwargs.get("temperature") == 0.5
```

- [ ] **Step 2: Run — falla**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  pytest tests/test_invoke_agent_tool.py -v
```

Expected: ImportError.

---

### Task 2.4: Implementar `invoke_agent` tool

**Files:**
- Create: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/invoke_agent.py`
- Delete: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py`

- [ ] **Step 1: Leer base class para confirmar firma de `execute`**

```bash
sed -n '50,110p' /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service/app/agents/langgraph/tools/base.py
```

Confirma que la firma es `async def execute(self, arguments: dict, context: dict) -> ToolResult`.

- [ ] **Step 2: Crear `invoke_agent.py`**

```python
# backend/microservices/emma-agent-service/app/agents/langgraph/tools/invoke_agent.py
"""invoke_agent tool — replaces analyze_domain.

Delegates a focused question to a specialist agent loaded from the
admin-curated catalog (DB + Langfuse). Wraps a single LLM call with
the persona as system prompt and the scope filters injected into the
sub-context.
"""
from __future__ import annotations

import logging
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.langgraph.tools.base import EmmaTool, ToolResult
from app.agents.llm_models import get_chat_model, get_planner_model
from app.agents.llm_types import ModelRole
from app.services.agent_loader import AgentLoader, LoadedAgent

logger = logging.getLogger(__name__)


class InvokeAgentTool(EmmaTool):
    """Calls a specialist agent's LLM with its persona + scope."""

    def __init__(self, *, loader: AgentLoader, llm=None, usage_counter=None) -> None:
        self.loader = loader
        self._llm = llm  # injected for tests; None in production
        self._usage_counter = usage_counter  # injected; None uses real impl

    @property
    def name(self) -> str:
        return "invoke_agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a focused question to a specialist agent. "
            "Use when the user references @<slug> in their query, or when a specialist persona "
            "is more appropriate than Emma's general response. See <available_agents> in the system prompt."
        )

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "agent_slug": {
                    "type": "string",
                    "description": "Slug of the agent to invoke (e.g. 'contabilidad').",
                },
                "question": {"type": "string", "description": "User's question for the agent."},
                "context": {
                    "type": "string",
                    "description": "Optional extra context to prepend to the question.",
                },
            },
            "required": ["agent_slug", "question"],
        }

    async def execute(self, arguments: dict, context: dict) -> ToolResult:
        slug = arguments.get("agent_slug", "").strip()
        question = arguments.get("question", "").strip()
        extra_context = arguments.get("context") or ""

        if not slug or not question:
            return ToolResult.error("agent_slug and question are required")

        loaded: Optional[LoadedAgent] = await self.loader.load_by_slug(slug)
        if loaded is None:
            return ToolResult.error(f"Agent '{slug}' not found or inactive")

        system_prompt = self._compose_persona(loaded)
        scoped_context = self._format_scope_hint(loaded.scope, extra_context)

        llm = self._llm or self._resolve_llm(loaded.model_role)
        try:
            response = await llm.ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"{scoped_context}\n\n{question}".strip()),
                ],
                config={"configurable": {"temperature": loaded.temperature}},
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("invoke_agent LLM call failed slug=%s", slug)
            return ToolResult.error(f"LLM call failed: {exc}")

        if self._usage_counter is not None:
            await self._usage_counter.increment(loaded.id)

        return ToolResult.ok({
            "agent_id": loaded.id,
            "agent_slug": loaded.slug,
            "agent_name": loaded.name,
            "answer": getattr(response, "content", str(response)),
        })

    @staticmethod
    def _compose_persona(loaded: LoadedAgent) -> str:
        modifier_lines = []
        if loaded.persona_style == "concise":
            modifier_lines.append("Estilo: respuestas breves (2-3 frases salvo que se pidan datos extensos).")
        elif loaded.persona_style == "detailed":
            modifier_lines.append("Estilo: respuestas detalladas con razonamiento paso a paso.")
        if loaded.persona_language and loaded.persona_language != "auto":
            modifier_lines.append(f"Idioma de respuesta: {loaded.persona_language}.")
        modifiers = "\n".join(modifier_lines)
        return f"{loaded.persona_instructions}\n\n{modifiers}".strip()

    @staticmethod
    def _format_scope_hint(scope: dict, extra: str) -> str:
        if not scope:
            return extra
        lines = ["[Scope filters applied]"]
        if scope.get("semantic_types"):
            lines.append(f"- semantic_types: {', '.join(scope['semantic_types'])}")
        if scope.get("folders"):
            lines.append(f"- folders: {len(scope['folders'])} folder(s)")
        if scope.get("date_range"):
            dr = scope["date_range"]
            lines.append(f"- date_range: {dr.get('from') or '*'} → {dr.get('to') or '*'}")
        if scope.get("quality_min") is not None:
            lines.append(f"- quality_min: {scope['quality_min']}")
        return "\n".join(lines) + ("\n\n" + extra if extra else "")

    @staticmethod
    def _resolve_llm(role: ModelRole):
        return get_planner_model() if role == ModelRole.PLANNER else get_chat_model()
```

- [ ] **Step 3: Borrar `specialists.py`**

```bash
rm /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py
```

Si algún archivo importa `from app.agents.langgraph.tools.specialists import ...`, capturarlo:

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  grep -rn "from app.agents.langgraph.tools.specialists\|import specialists" app/
```

Si hay matches, en cada archivo cambiar la import por `from app.agents.langgraph.tools.invoke_agent import InvokeAgentTool`.

- [ ] **Step 4: Run tests — pasa**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  pytest tests/test_invoke_agent_tool.py -v
```

Expected: 3 passed.

---

### Task 2.5: Update tool registry

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py`

- [ ] **Step 1: Inspeccionar y editar registry**

```bash
sed -n '1,100p' /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py
```

Localiza la registración de `AnalyzeDomainTool` (líneas ~28-93 según el inventario). Reemplázala por:

```python
# backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py

# AT TOP — replace specialists import:
from app.agents.langgraph.tools.invoke_agent import InvokeAgentTool

# IN the registry init function — replace AnalyzeDomainTool registration:
def _build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    # ... other registrations stay
    registry.register(InvokeAgentTool(loader=_default_agent_loader()))
    # ... continue
    return registry


def _default_agent_loader() -> AgentLoader:
    """Lazy production-mode loader: real Main API + Langfuse + Redis clients."""
    from app.services.agent_loader import AgentLoader
    from app.services.langfuse_prompt_client import get_langfuse_client
    from app.services.main_api_client import MainAPIClient
    from app.core.redis_client import get_redis

    return AgentLoader(
        main_api=MainAPIClient(),
        langfuse=get_langfuse_client(),
        redis=get_redis(),
    )
```

- [ ] **Step 2: Smoke run del microservicio**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  python -c "from app.agents.langgraph.tools.registry import get_default_registry; r = get_default_registry(); print('tools:', sorted(r.list_tool_names())); assert 'invoke_agent' in r.list_tool_names(); assert 'analyze_domain' not in r.list_tool_names()"
```

Expected: lista de tools con `invoke_agent` y SIN `analyze_domain`.

---

### Task 2.6: Extend EmmaState + classify node para `agent_slug`

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/state.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py`

- [ ] **Step 1: Añadir `agent_slug` a `EmmaState`**

Edita `state.py`. Localiza la TypedDict / Pydantic state y añade:

```python
# en EmmaState
agent_slug: NotRequired[Optional[str]]  # set by API when user used @<slug>
```

- [ ] **Step 2: En `classify.py` — short-circuit cuando `agent_slug` está presente**

Edita el inicio del nodo `classify_node` (después del fast-path social). Añade:

```python
async def classify_node(state: EmmaState) -> dict:
    # ... existing fast-path checks ...

    requested_slug = state.get("agent_slug")
    if requested_slug:
        # User invoked @<slug>: bypass classification.
        # The ReAct loop will be constrained via state['forced_tool'] to call invoke_agent once.
        return {
            "intent": "agent_invocation",
            "forced_tool": {"name": "invoke_agent", "arguments": {"agent_slug": requested_slug}},
            "agent_slug": requested_slug,
        }
    # ... existing classify body ...
```

(Si el grafo no tiene `forced_tool` aún, también añadirlo a `EmmaState` y consumirlo en `react_loop_node` para que en la primera iteración prefiera `invoke_agent` con esos args. Es ~5 líneas extra en `react_loop.py`.)

- [ ] **Step 3: Verificar que el grafo compila**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  python -c "from app.agents.langgraph.graph import build_emma_graph; g = build_emma_graph(); print('nodes:', list(g.nodes.keys()))"
```

Expected: lista de nodos sin tracebacks.

---

### Task 2.7: API extension — `/emma/query/stream` acepta `agent_slug`

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py`

- [ ] **Step 1: Localizar el body model**

```bash
grep -n "class.*Stream\|class.*EmmaQuery\|agent_slug" /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service/app/api/emma.py | head
```

- [ ] **Step 2: Añadir `agent_slug: Optional[str]` al request schema**

En el Pydantic model del body (probablemente `EmmaQueryRequest` o similar):

```python
class EmmaQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    thread_id: Optional[str] = None
    # ... existing fields ...
    agent_slug: Optional[str] = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,49}$")
```

- [ ] **Step 3: Pasar al state en el handler**

En el handler `emma_query_stream`, donde se construye el `initial_state` para el grafo, añadir:

```python
initial_state = {
    "messages": [HumanMessage(content=req.message)],
    "thread_id": req.thread_id,
    # ...
    "agent_slug": req.agent_slug,
}
```

- [ ] **Step 4: Replicar en Main API proxy**

`backend/app/api/v1/emma.py` también necesita aceptar `agent_slug` y propagarlo al microservicio. Edita el body model + payload forwarding.

- [ ] **Step 5: Smoke test con curl**

```bash
TOKEN="<KeyCloak>"
curl -s -X POST "http://localhost:8000/api/v1/emma/query/stream" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"hola","thread_id":"smoke-1","agent_slug":"emma_general"}' | head -50
```

Expected: SSE stream sin error 422.

---

### Task 2.8: Migration script — `emma_react_system` v12 con `<available_agents>` block

**Files:**
- Create: `backend/microservices/emma-agent-service/scripts/migrate_admin_curated_agents_prompt.py`

- [ ] **Step 1: Escribir script**

```python
# backend/microservices/emma-agent-service/scripts/migrate_admin_curated_agents_prompt.py
"""Push emma_react_system v12 with <available_agents> block.

Idempotent: re-running creates a new Langfuse version each time. Pass
--force to also re-promote to the production label.

Usage:
    docker compose exec emma-agent-service \
        python scripts/migrate_admin_curated_agents_prompt.py --force
"""
from __future__ import annotations

import argparse
import asyncio

from langfuse import Langfuse
from app.core.config import settings


PROMPT = """\
[Existing emma_react_system v11 body — preserved verbatim from PROMPT_REGISTRY canonical entry]

<available_agents>
{{ available_agents_block }}
</available_agents>

If the user message contains @<slug>, you MUST call invoke_agent(agent_slug=<slug>, ...) exactly once.
Otherwise, answer as Emma general (do NOT invoke an agent).

Tool catalog:
- invoke_agent(agent_slug, question, context?): delegate to a specialist (preferred when @<slug> used).
- smart_search, graph_rag, get_document_content, structural_query, web_search, search_jurisprudence,
  list_sources, query_connector, generate_document, forge_document, send_email, verified_generation,
  predictive_analysis, generate_knowledge_report, terminate.
"""


def main(force: bool) -> None:
    client = Langfuse(
        host=settings.LANGFUSE_HOST,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
    )
    labels = ["production"] if force else ["latest"]
    client.create_prompt(
        name="emma_react_system",
        prompt=PROMPT,
        labels=labels,
        type="text",
    )
    print(f"Pushed emma_react_system v12 with labels={labels}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="Promote to production label")
    args = parser.parse_args()
    main(args.force)
```

(El `[Existing emma_react_system v11 body — preserved verbatim from PROMPT_REGISTRY canonical entry]` lo extraerá el ejecutor con: `python -c "from app.services.langfuse_prompt_client import get_langfuse_client; import asyncio; print(asyncio.run(get_langfuse_client().get_prompt('emma_react_system', label='production')))"` ANTES de ejecutar el script, y reemplazará el placeholder en el archivo.)

- [ ] **Step 2: Pull del v11 actual**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  docker compose -f ../../docker/docker-compose.yml exec emma-agent-service \
  python -c "from app.services.langfuse_prompt_client import get_langfuse_client; import asyncio; print(asyncio.run(get_langfuse_client().get_prompt('emma_react_system', label='production')))" \
  > /tmp/emma_react_system_v11.txt
```

Expected: archivo temporal con el v11 íntegro.

- [ ] **Step 3: Sustituir placeholder**

Edita `migrate_admin_curated_agents_prompt.py` línea `PROMPT = """...`: reemplaza el placeholder `[Existing emma_react_system v11 body...]` por el contenido de `/tmp/emma_react_system_v11.txt`.

Mantén el bloque `<available_agents>{{ available_agents_block }}</available_agents>` y la clausula sobre `@<slug>`.

- [ ] **Step 4: Ejecutar migration**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/docker && \
  docker compose exec emma-agent-service python scripts/migrate_admin_curated_agents_prompt.py --force
```

Expected: `Pushed emma_react_system v12 with labels=['production']`.

- [ ] **Step 5: Verificar en Langfuse UI**

Abre `http://localhost:3002` (admin@nouxcube.com), navega a `Prompts → emma_react_system`, confirma versión nueva con label `production`.

---

### Task 2.9: Implementar template fill de `<available_agents>` en runtime

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py` (o donde se construye el system prompt).

- [ ] **Step 1: Localizar dónde se inyecta el system prompt**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && \
  grep -rn "emma_react_system\|get_prompt.*react" app/agents/langgraph/nodes/
```

- [ ] **Step 2: Inyectar lista de agentes activos**

En el lugar donde se obtiene el system prompt (probablemente en `react_loop.py` antes de cada llamada al planner LLM):

```python
from app.services.main_api_client import MainAPIClient
from app.core.redis_client import get_redis
import json

_ACTIVE_AGENTS_CACHE_KEY = "active_agents_block"


async def _build_active_agents_block(limit: int = 50) -> str:
    redis = get_redis()
    cached = await redis.get(_ACTIVE_AGENTS_CACHE_KEY)
    if cached:
        return cached
    rows = await MainAPIClient().list_active_agents(limit=limit)
    lines = [f"- {row['slug']}: {(row.get('description') or '')[:80]}" for row in rows]
    block = "\n".join(lines) if lines else "(no agents currently active)"
    await redis.set(_ACTIVE_AGENTS_CACHE_KEY, block, ex=60)
    return block


# ... in the prompt construction:
raw_prompt = await langfuse.get_prompt("emma_react_system", label="production")
agents_block = await _build_active_agents_block()
system_prompt = raw_prompt.replace("{{ available_agents_block }}", agents_block)
```

- [ ] **Step 3: Smoke test E2E**

```bash
docker compose -f /home/nexus/git/nexus-documents-ia/backend/docker/docker-compose.yml \
  logs -f emma-agent-service | grep -A3 "system_prompt\|<available_agents>" | head -50
```

Tras enviar un mensaje, confirma que el log muestra el bloque `<available_agents>` poblado.

---

### Task 2.10: Seed script + starter personas

**Files:**
- Create: `backend/scripts/seed_default_agents.py`
- Create: `backend/microservices/emma-agent-service/scripts/migrate_seed_agent_personas.py`

- [ ] **Step 1: Seed script SQL-side**

```python
# backend/scripts/seed_default_agents.py
"""Insert seed agent (emma_general) + 3 inactive starter agents.

Idempotent: re-running on existing slugs UPDATEs is_seed/is_active flags,
does NOT overwrite persona content (which the admin may have customized).

Usage:
    cd backend && python scripts/seed_default_agents.py
"""
from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.db.async_session import async_session_maker
from app.db.agent_models import Agent
from app.db.models import ModelRole, User


SEED_OWNER_EMAIL = "horelvis@nouxcube.com"  # default admin

SEEDS = [
    {
        "name": "Emma General",
        "slug": "emma_general",
        "description": "Asistente general por defecto. Sin scope, persona neutra.",
        "icon": "IconRobot",
        "color": "blue",
        "persona": {"style": "concise", "language": "es", "instructions": "Eres Emma, asistente general."},
        "scope": {},
        "is_active": True,
        "is_seed": True,
        "model_role": ModelRole.CHAT,
        "temperature": 0.5,
    },
    {
        "name": "Contabilidad",
        "slug": "contabilidad",
        "description": "Análisis de facturas, pagos, conciliaciones.",
        "icon": "IconReceipt",
        "color": "green",
        "persona": {
            "style": "concise",
            "language": "es",
            "instructions": "Eres el asistente de Contabilidad. Especialízate en facturas, pagos y conciliaciones. Cita siempre la factura origen.",
        },
        "scope": {"semantic_types": ["factura", "pago"]},
        "is_active": False,
        "is_seed": False,
    },
    {
        "name": "Ventas",
        "slug": "ventas",
        "description": "Análisis de pipeline, leads, cuentas.",
        "icon": "IconChartBar",
        "color": "orange",
        "persona": {
            "style": "concise",
            "language": "es",
            "instructions": "Eres el asistente de Ventas. Analiza pipeline, leads y oportunidades.",
        },
        "scope": {"semantic_types": ["contrato", "propuesta"]},
        "is_active": False,
    },
    {
        "name": "Legal",
        "slug": "legal",
        "description": "Contratos, cumplimiento normativo, jurisprudencia.",
        "icon": "IconScale",
        "color": "purple",
        "persona": {
            "style": "detailed",
            "language": "es",
            "instructions": "Eres el asistente Legal. Cita siempre artículos y referencias normativas.",
        },
        "scope": {"semantic_types": ["contrato", "sentencia"]},
        "is_active": False,
    },
]


async def main() -> None:
    async with async_session_maker() as db:
        owner_q = await db.execute(select(User).where(User.email == SEED_OWNER_EMAIL))
        owner = owner_q.scalar_one_or_none()
        if owner is None:
            raise SystemExit(
                f"Seed owner {SEED_OWNER_EMAIL} not found — create user first."
            )

        for seed in SEEDS:
            existing_q = await db.execute(select(Agent).where(Agent.slug == seed["slug"]))
            existing = existing_q.scalar_one_or_none()
            if existing is None:
                agent = Agent(
                    id=uuid.uuid4(),
                    name=seed["name"],
                    slug=seed["slug"],
                    description=seed["description"],
                    icon=seed["icon"],
                    color=seed["color"],
                    persona=seed["persona"],
                    scope=seed["scope"],
                    is_active=seed["is_active"],
                    is_seed=seed.get("is_seed", False),
                    model_role=seed.get("model_role", ModelRole.CHAT),
                    temperature=seed.get("temperature", 0.5),
                    owner_id=owner.id,
                )
                db.add(agent)
                print(f"  + INSERT {seed['slug']}")
            else:
                existing.is_seed = seed.get("is_seed", existing.is_seed)
                if seed.get("is_seed"):
                    existing.is_active = True  # invariant
                print(f"  ~ UPDATE flags {seed['slug']}")
        await db.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Persona-side migration**

```python
# backend/microservices/emma-agent-service/scripts/migrate_seed_agent_personas.py
"""Push the 4 seed agents' personas to Langfuse as agent_<slug>_persona."""
from __future__ import annotations

from langfuse import Langfuse
from app.core.config import settings


PERSONAS = {
    "agent_emma_general_persona": "Eres Emma, asistente general.",
    "agent_contabilidad_persona": (
        "Eres el asistente de Contabilidad. Especialízate en facturas, pagos y "
        "conciliaciones. Cita siempre la factura origen."
    ),
    "agent_ventas_persona": (
        "Eres el asistente de Ventas. Analiza pipeline, leads y oportunidades."
    ),
    "agent_legal_persona": (
        "Eres el asistente Legal. Cita siempre artículos y referencias normativas."
    ),
}


def main() -> None:
    client = Langfuse(
        host=settings.LANGFUSE_HOST,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
    )
    for name, content in PERSONAS.items():
        client.create_prompt(name=name, prompt=content, labels=["production"], type="text")
        print(f"Pushed {name}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Ejecutar ambos scripts**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && python scripts/seed_default_agents.py
cd /home/nexus/git/nexus-documents-ia/backend/docker && \
  docker compose exec emma-agent-service python scripts/migrate_seed_agent_personas.py
```

- [ ] **Step 4: Verificar via API**

```bash
curl -s "http://localhost:8000/api/v1/agents/?active=true" -H "Authorization: Bearer $TOKEN" \
  | python3 -c "import json, sys; rows = json.load(sys.stdin); print([(a['slug'], a['is_seed']) for a in rows])"
```

Expected: `[('emma_general', True)]` (los 3 starters están `is_active=False`).

---

### Task 2.11: E2E smoke — `@<slug>` invocación punctual

- [ ] **Step 1: Activar el agente `contabilidad` desde admin**

```bash
AGENT_ID=$(curl -s "http://localhost:8000/api/v1/agents/?slug=contabilidad" \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")
curl -s -X PUT "http://localhost:8000/api/v1/agents/$AGENT_ID" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"is_active": true}' > /dev/null
```

- [ ] **Step 2: Query con `agent_slug=contabilidad`**

```bash
curl -s -N -X POST "http://localhost:8000/api/v1/emma/query/stream" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"¿Qué facturas tenemos pendientes?","thread_id":"e2e-1","agent_slug":"contabilidad"}' \
  | head -50
```

Expected: SSE stream incluye un `tool_call` con `name=invoke_agent` y `arguments.agent_slug=contabilidad`.

- [ ] **Step 3: Query SIN `agent_slug`**

```bash
curl -s -N -X POST "http://localhost:8000/api/v1/emma/query/stream" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"¿Qué facturas tenemos pendientes?","thread_id":"e2e-2"}' \
  | head -30
```

Expected: stream NO contiene `invoke_agent` (default `emma_general`, comportamiento como antes).

---

### Task 2.12: Commit Phase 2

- [ ] **Step 1: Commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add backend/app/api/v1/agents.py backend/app/api/v1/emma.py
git add backend/microservices/emma-agent-service/app/services/agent_loader.py
git add backend/microservices/emma-agent-service/app/services/main_api_client.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/invoke_agent.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/state.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/react_loop.py
git add backend/microservices/emma-agent-service/app/api/emma.py
git add backend/microservices/emma-agent-service/scripts/migrate_*.py
git add backend/microservices/emma-agent-service/tests/test_agent_loader.py
git add backend/microservices/emma-agent-service/tests/test_invoke_agent_tool.py
git add backend/scripts/seed_default_agents.py
git rm backend/microservices/emma-agent-service/app/agents/langgraph/tools/specialists.py
git commit -m "$(cat <<'EOF'
feat(phase-2): replace analyze_domain with invoke_agent tool

Renames the hardcoded specialists tool (analyze_domain) to data-driven
invoke_agent. AgentLoader resolves slug → DB row + Langfuse persona
(60s Redis cache). Emma's classify node short-circuits when agent_slug
is set on the request, forcing invoke_agent for that slug exactly once.
emma_react_system Langfuse prompt v12 adds <available_agents> block
filled at request time. Seeds emma_general (is_seed=True) + 3 starter
agents (inactive). Spec §Phase 2.
EOF
)"
```

---

## Phase 3 — Frontend `/admin/agents` CRUD pages

**Goal:** Cherry-pick las 3 admin pages y el builder form de `feature/user-agents-mock`, reemplazar el mock localStorage por el real `agentsService`, y proteger todo con `<AdminGuard>`.

### Task 3.1: Cherry-pick admin pages

**Files:**
- Create: 3 admin pages + `agent-builder-form.tsx`.

- [ ] **Step 1: Inspeccionar la branch mock**

```bash
cd /home/nexus/git/nexus-documents-ia
git fetch origin feature/user-agents-mock
git log feature/user-agents-mock --oneline -- frontend/src/app/admin/agents frontend/src/components/agents/agent-builder-form.tsx | head
```

- [ ] **Step 2: Cherry-pick por checkout-path (no merge)**

```bash
git checkout feature/user-agents-mock -- \
  frontend/src/app/admin/agents/page.tsx \
  frontend/src/app/admin/agents/new/page.tsx \
  frontend/src/app/admin/agents/[id]/edit/page.tsx \
  frontend/src/components/agents/agent-builder-form.tsx \
  frontend/src/components/agents/agent-playground-mock.tsx
git status
```

Expected: 5 archivos staged como nuevos (excluyendo el mock de localStorage).

- [ ] **Step 3: Renombrar el playground mock**

```bash
mv /home/nexus/git/nexus-documents-ia/frontend/src/components/agents/agent-playground-mock.tsx \
   /home/nexus/git/nexus-documents-ia/frontend/src/components/agents/agent-playground.tsx
```

- [ ] **Step 4: Compilation check**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npx tsc --noEmit 2>&1 | grep "src/app/admin/agents\|agent-builder-form\|agent-playground" | head -30
```

Expected: errors apuntan a imports del mock layer (a reemplazar en Task 3.2).

---

### Task 3.2: Real `agentsService` + types

**Files:**
- Create: `frontend/src/lib/services/agents.service.ts`
- Create: `frontend/src/lib/types/agent.ts`

- [ ] **Step 1: Types**

```typescript
// frontend/src/lib/types/agent.ts
export type AgentScope = {
  folders?: string[]
  semantic_types?: string[]
  person_filter?: string[]
  entity_filters?: string[]
  date_range?: { from?: string | null; to?: string | null }
  quality_min?: number | null
  connector_ids?: string[]
}

export type AgentPersona = {
  style: 'concise' | 'detailed' | 'conversational'
  language: 'es' | 'en' | 'auto'
  instructions: string
}

export type Agent = {
  id: string
  name: string
  slug: string
  description: string | null
  icon: string
  color: string
  persona: AgentPersona
  scope: AgentScope
  is_active: boolean
  is_seed: boolean
  model_role: 'PLANNER' | 'CHAT'
  temperature: number
  usage_count: number
  owner_id: string
  created_at: string
  updated_at: string
}

export type AgentCreate = Omit<
  Agent,
  'id' | 'is_seed' | 'usage_count' | 'owner_id' | 'created_at' | 'updated_at'
>

export type AgentUpdate = Partial<Omit<AgentCreate, 'slug'>>
```

- [ ] **Step 2: Service**

```typescript
// frontend/src/lib/services/agents.service.ts
import type { Agent, AgentCreate, AgentUpdate } from '@/lib/types/agent'
import { apiFetch } from '@/lib/api-client'

const BASE = '/api/v1/agents'

export const agentsService = {
  async list(opts?: { active?: boolean; slug?: string }): Promise<Agent[]> {
    const qs = new URLSearchParams()
    if (opts?.active !== undefined) qs.set('active', String(opts.active))
    if (opts?.slug) qs.set('slug', opts.slug)
    const url = qs.toString() ? `${BASE}/?${qs}` : `${BASE}/`
    const res = await apiFetch(url)
    if (!res.ok) throw new Error(`list agents failed: ${res.status}`)
    return res.json()
  },

  async get(id: string): Promise<Agent> {
    const res = await apiFetch(`${BASE}/${id}`)
    if (!res.ok) throw new Error(`get agent failed: ${res.status}`)
    return res.json()
  },

  async create(payload: AgentCreate): Promise<Agent> {
    const res = await apiFetch(`${BASE}/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`create agent failed: ${res.status} ${text}`)
    }
    return res.json()
  },

  async update(id: string, payload: AgentUpdate): Promise<Agent> {
    const res = await apiFetch(`${BASE}/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(`update agent failed: ${res.status} ${text}`)
    }
    return res.json()
  },

  async delete(id: string): Promise<void> {
    const res = await apiFetch(`${BASE}/${id}`, { method: 'DELETE' })
    if (!res.ok && res.status !== 204) throw new Error(`delete agent failed: ${res.status}`)
  },

  async duplicate(id: string): Promise<Agent> {
    const res = await apiFetch(`${BASE}/${id}/duplicate`, { method: 'POST' })
    if (!res.ok) throw new Error(`duplicate agent failed: ${res.status}`)
    return res.json()
  },
}
```

(`apiFetch` debe ser el helper existente del proyecto. Si su signature difiere, ajustar.)

- [ ] **Step 3: Sustituir imports del mock**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && \
  grep -rn "from '@/lib/mocks/agents-mock\|from '@/lib/services/agents-mock" src/app/admin/agents/ src/components/agents/ 2>/dev/null
```

En cada archivo encontrado, reemplazar la línea de import por:

```typescript
import { agentsService } from '@/lib/services/agents.service'
import type { Agent, AgentCreate, AgentUpdate } from '@/lib/types/agent'
```

Y todas las llamadas `mockAgentsService.X(...)` → `agentsService.X(...)`.

- [ ] **Step 4: TypeScript check**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npx tsc --noEmit 2>&1 | grep -E "src/app/admin/agents|agent-builder-form|agent-playground|agents.service" | head -30
```

Expected: cero errores nuevos en estos paths.

---

### Task 3.3: AdminGuard wrap + sidebar entry

**Files:**
- Modify: `frontend/src/app/admin/agents/page.tsx`, `new/page.tsx`, `[id]/edit/page.tsx`
- Modify: `frontend/src/components/layout/AppSidebar.tsx` (o equivalente).

- [ ] **Step 1: Wrap cada page con AdminGuard**

En cada uno de los 3 archivos, asegurar que el JSX raíz está envuelto por `<AdminGuard>`:

```tsx
import { AdminGuard } from '@/components/auth/admin-guard'

export default function AgentsAdminPage() {
  return (
    <AdminGuard>
      {/* ... existing page body ... */}
    </AdminGuard>
  )
}
```

- [ ] **Step 2: Localizar sidebar y añadir entry**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && \
  grep -rn "AppSidebar\|admin.*sidebar" src/components/layout/ | head -5
```

En el archivo de sidebar (probablemente `AppSidebar.tsx`), localizar la sección admin y añadir:

```tsx
import { IconRobot } from '@tabler/icons-react'

// in admin items array:
{ icon: IconRobot, label: 'Agentes', href: '/admin/agents', adminOnly: true },
```

- [ ] **Step 3: Smoke test manual**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npm run dev
```

Navegar a `https://localhost:3001/admin/agents`. Verificar:

- Como admin: lista de agentes (4 seeds tras Phase 2).
- Cambia user: redirección a `/`.

Crear un agente nuevo desde la UI, verificar que aparece en lista. Editar, eliminar (no debería permitir borrar `emma_general` → 409 visible como toast).

---

### Task 3.4: Live preview panel en builder

**Files:**
- Modify: `frontend/src/components/agents/agent-playground.tsx`

- [ ] **Step 1: Reemplazar simulated SSE por llamada real**

Localizar la función que actualmente simula respuestas. Reemplazar por:

```typescript
import { emmaService } from '@/lib/services/emma.service'

async function runPreview({
  message,
  agentSlug,
  draftPersona,
}: {
  message: string
  agentSlug?: string
  draftPersona?: AgentPersona
}) {
  // If agent already exists, use its slug for full server-side resolution.
  // Otherwise (new agent draft), use emma_general and inject draftPersona client-side.
  const slugToSend = agentSlug ?? 'emma_general'
  const stream = await emmaService.queryStream({
    message,
    agent_slug: slugToSend,
    thread_id: `preview-${Date.now()}`,
  })
  return stream
}
```

(Si el form pasa una persona en draft, el preview SOLO funciona con el agent ya guardado. Mensaje al usuario: "Guarda primero para previsualizar con la persona personalizada.")

- [ ] **Step 2: Smoke test manual**

Levantar dev server (Phase 3 Task 3.3 step 3) y desde el builder, escribir un mensaje en el panel de preview con un agente activo. Verificar que la respuesta es streaming real (no mockeada).

---

### Task 3.5: Commit Phase 3

- [ ] **Step 1: Commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add frontend/src/app/admin/agents/ frontend/src/components/agents/
git add frontend/src/lib/services/agents.service.ts frontend/src/lib/types/agent.ts
git add frontend/src/components/layout/AppSidebar.tsx
git commit -m "$(cat <<'EOF'
feat(phase-3): admin /admin/agents CRUD pages + real backend client

Cherry-picks the 3 admin pages and builder form from feature/user-agents-mock,
replaces the localStorage mock with the real agentsService HTTP client,
wraps each page in AdminGuard, and adds the "Agentes" entry to the admin
sidebar. Live preview panel calls /emma/query/stream against the real
backend. Spec §Phase 3.
EOF
)"
```

---

## Phase 4 — Frontend `/agents` gallery + `@`-mention extension

**Goal:** Página `/agents` accesible para todos, y extensión del menú `@`-mention con sección "Asistentes" que devuelve `agent_slug` al chat sender.

### Task 4.1: Gallery page

**Files:**
- Create: `frontend/src/app/agents/page.tsx`
- Create: `frontend/src/components/agents/agents-gallery.tsx`

- [ ] **Step 1: Page entrypoint**

```tsx
// frontend/src/app/agents/page.tsx
import { AgentsGallery } from '@/components/agents/agents-gallery'

export default function AgentsGalleryPage() {
  return (
    <div className="container mx-auto p-6">
      <h1 className="text-2xl font-semibold mb-4">Asistentes disponibles</h1>
      <AgentsGallery />
    </div>
  )
}
```

- [ ] **Step 2: Gallery component**

```tsx
// frontend/src/components/agents/agents-gallery.tsx
'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'
import { IconRobot } from '@tabler/icons-react'

export function AgentsGallery() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const router = useRouter()

  useEffect(() => {
    void (async () => {
      setIsLoading(true)
      setError(null)
      try {
        setAgents(await agentsService.list({ active: true }))
      } catch (err) {
        setError((err as Error).message)
      } finally {
        setIsLoading(false)
      }
    })()
  }, [])

  if (isLoading) return <p>Cargando…</p>
  if (error) return <p className="text-red-600">{error}</p>
  if (agents.length === 0) return <p>No hay agentes activos en este momento.</p>

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {agents.map((agent) => (
        <article key={agent.id} className="border rounded-lg p-4 hover:shadow-md transition-shadow">
          <div className="flex items-center gap-2 mb-2">
            <IconRobot size={20} className={`text-${agent.color}-500`} />
            <h2 className="font-semibold">{agent.name}</h2>
          </div>
          <p className="text-sm text-gray-600 mb-3 min-h-[3em]">{agent.description ?? '—'}</p>
          <button
            type="button"
            className="px-3 py-1 bg-blue-600 text-white rounded text-sm"
            onClick={() => router.push(`/?prefill=@${agent.slug}+`)}
          >
            Probar
          </button>
        </article>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Wire `?prefill` query param en chat home**

En la página de chat raíz (probablemente `frontend/src/app/page.tsx` o `frontend/src/app/(authenticated)/page.tsx`), aceptar `searchParams` y pasar `prefill` al `EmmaChat` component que rellene el input + foco.

```tsx
// in EmmaChat or input component:
const searchParams = useSearchParams()
useEffect(() => {
  const prefill = searchParams.get('prefill')
  if (prefill) {
    inputRef.current?.setValue(decodeURIComponent(prefill).replace('+', ' '))
    inputRef.current?.focus()
  }
}, [searchParams])
```

- [ ] **Step 4: Smoke test manual** — visitar `/agents`, click "Probar" en `Contabilidad` (tras activarlo), verificar que el chat se abre con `@contabilidad ` pre-cargado.

---

### Task 4.2: Extender `entity-search-menu.tsx` con sección Asistentes

**Files:**
- Modify: `frontend/src/components/documents/entity-search-menu.tsx`

- [ ] **Step 1: Inspeccionar estructura actual**

```bash
sed -n '1,60p' /home/nexus/git/nexus-documents-ia/frontend/src/components/documents/entity-search-menu.tsx
sed -n '230,280p' /home/nexus/git/nexus-documents-ia/frontend/src/components/documents/entity-search-menu.tsx
```

- [ ] **Step 2: Añadir fetch + sección**

En el componente, añadir state + effect para cargar agentes activos (cache 60s en module-level Map):

```tsx
import { agentsService } from '@/lib/services/agents.service'
import type { Agent } from '@/lib/types/agent'

const _agentsCache: { value: Agent[] | null; ts: number } = { value: null, ts: 0 }
const CACHE_MS = 60_000

async function fetchActiveAgentsCached(): Promise<Agent[]> {
  const now = Date.now()
  if (_agentsCache.value && now - _agentsCache.ts < CACHE_MS) return _agentsCache.value
  const list = await agentsService.list({ active: true })
  _agentsCache.value = list
  _agentsCache.ts = now
  return list
}

// Inside the component:
const [agents, setAgents] = useState<Agent[]>([])
useEffect(() => {
  void fetchActiveAgentsCached().then(setAgents).catch(() => setAgents([]))
}, [])

const filteredAgents = useMemo(
  () => agents.filter((a) => a.slug.includes(searchTerm.toLowerCase())),
  [agents, searchTerm],
)
```

Y en el JSX, AGREGAR la primera sección ARRIBA de las existentes:

```tsx
{filteredAgents.length > 0 && (
  <CommandGroup heading="🤖 Asistentes">
    {filteredAgents.map((agent) => (
      <CommandItem
        key={`agent-${agent.slug}`}
        onSelect={() => onSelect({
          type: 'agent',
          id: agent.id,
          slug: agent.slug,
          label: agent.name,
          description: agent.description ?? '',
          icon: agent.icon,
          color: agent.color,
        })}
      >
        <IconRobot size={16} className={`text-${agent.color}-500 mr-2`} />
        <span>@{agent.slug}</span>
        <span className="ml-2 text-xs text-gray-500">— {agent.description ?? ''}</span>
      </CommandItem>
    ))}
  </CommandGroup>
)}
{/* existing entity sections below */}
```

- [ ] **Step 3: Verificar que `onSelect` propaga `type: 'agent'`**

Trazar el callback hasta `createEntityTag`. Confirmar que `entity-renderer.tsx` línea ~106 ya soporta `type === 'agent'`. Si NO crea el tag con icono+color, ampliar `createEntityTag` para usar `entity.color` y el icono.

- [ ] **Step 4: TypeScript + lint check**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npx tsc --noEmit 2>&1 | grep entity-search-menu
```

Expected: cero errores.

---

### Task 4.3: Extraer `agent_slug` en chat sender

**Files:**
- Modify: `frontend/src/components/ui/rich-input-with-mentions.tsx` o `frontend/src/lib/services/emma.service.ts` o el componente que invoca `queryStream`.

- [ ] **Step 1: Localizar el sender**

```bash
grep -rn "queryStream\|/emma/query/stream" /home/nexus/git/nexus-documents-ia/frontend/src/ --include="*.ts" --include="*.tsx" | head -10
```

- [ ] **Step 2: Helper que extrae `agent_slug` del input**

En `frontend/src/lib/utils/parse-agent-mention.ts` (nuevo):

```typescript
// frontend/src/lib/utils/parse-agent-mention.ts
import { parseEntityTags } from '@/components/ui/entity-renderer'

export function extractAgentSlug(input: string): string | null {
  const tags = parseEntityTags(input)
  const agentTag = tags.find((t: { type: string }) => t.type === 'agent')
  return agentTag?.entity?.slug ?? null
}
```

- [ ] **Step 3: Wire en el sender**

En el componente que llama a `emmaService.queryStream(...)`:

```tsx
import { extractAgentSlug } from '@/lib/utils/parse-agent-mention'

async function handleSend() {
  const agentSlug = extractAgentSlug(inputValue)
  await emmaService.queryStream({
    message: inputValue,
    thread_id: threadId,
    agent_slug: agentSlug ?? undefined,
  })
}
```

- [ ] **Step 4: Update `emma.service.ts` types**

Añadir `agent_slug?: string` a `QueryStreamPayload` type.

- [ ] **Step 5: Smoke test manual**

Levantar dev server. En chat, escribir `@contabilidad ¿qué facturas tengo?`. Abrir DevTools → Network → POST /emma/query/stream → confirmar payload tiene `agent_slug: "contabilidad"`.

---

### Task 4.4: Commit Phase 4

- [ ] **Step 1: Commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add frontend/src/app/agents/page.tsx
git add frontend/src/components/agents/agents-gallery.tsx
git add frontend/src/components/documents/entity-search-menu.tsx
git add frontend/src/components/ui/rich-input-with-mentions.tsx
git add frontend/src/lib/services/emma.service.ts
git add frontend/src/lib/utils/parse-agent-mention.ts
git commit -m "$(cat <<'EOF'
feat(phase-4): agents gallery + @-mention menu integration

Adds /agents page (read-only gallery, all authenticated users) with a
Probar button that prefills the chat with @<slug>. Extends the entity
search menu with an Asistentes section sourced from the active agent
catalog (60s client cache). Chat sender extracts the first agent tag's
slug as agent_slug on the request payload, flowing the user's @<slug>
choice through to invoke_agent. Spec §Phase 4.
EOF
)"
```

---

## Phase 5 — Bubble badge + SSE `agent_metadata` plumbing

**Goal:** Cuando una respuesta proviene de un agente no-default, el bubble muestra `🤖 <agent_name>` chip.

### Task 5.1: Backend — emit SSE `agent_metadata`

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/api/emma.py`
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py`

- [ ] **Step 1: En `classify_node`, devolver datos suficientes para el SSE event**

Cuando `agent_slug` está presente, además del short-circuit ya implementado en Task 2.6, populate state con metadata reusable downstream:

```python
# in classify.py
return {
    "intent": "agent_invocation",
    "forced_tool": {"name": "invoke_agent", "arguments": {"agent_slug": requested_slug}},
    "agent_slug": requested_slug,
    # Resolved name/icon/color come from AgentLoader cache for the SSE emitter:
    "agent_metadata": await _resolve_agent_metadata(requested_slug),
}


async def _resolve_agent_metadata(slug: str) -> dict:
    from app.services.main_api_client import MainAPIClient
    client = MainAPIClient()
    row = await client.get_agent_by_slug(slug)
    if row is None:
        return {"agent_slug": slug, "agent_name": slug, "agent_color": "blue", "agent_icon": "IconRobot"}
    return {
        "agent_id": row["id"],
        "agent_slug": row["slug"],
        "agent_name": row["name"],
        "agent_color": row.get("color", "blue"),
        "agent_icon": row.get("icon", "IconRobot"),
    }
```

- [ ] **Step 2: En `emma.py` — emit SSE event tras `classify`**

Localiza el handler `emma_query_stream`. Donde se hace el streaming del grafo y se generan eventos, añadir un emisor que detecte cuando `state.get("agent_metadata")` existe (o uno default `emma_general`):

```python
# inside the stream generator
async for event in graph.astream(initial_state, ...):
    if event.get("classify"):  # node finished
        meta = event["classify"].get("agent_metadata") or {
            "agent_slug": "emma_general",
            "agent_name": "Emma",
            "agent_color": "blue",
            "agent_icon": "IconRobot",
        }
        yield f"event: agent_metadata\ndata: {json.dumps(meta)}\n\n"
    # ... existing event emission ...
```

- [ ] **Step 3: Smoke test con curl**

```bash
TOKEN="<KeyCloak>"
curl -s -N -X POST "http://localhost:8000/api/v1/emma/query/stream" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"message":"hola","thread_id":"sse-1","agent_slug":"contabilidad"}' \
  | grep -A1 "agent_metadata" | head -5
```

Expected: `event: agent_metadata\ndata: {"agent_id":"...","agent_slug":"contabilidad",...}`

---

### Task 5.2: Frontend — capturar evento en `emma.service.ts`

**Files:**
- Modify: `frontend/src/lib/services/emma.service.ts`

- [ ] **Step 1: Localizar el SSE parser**

```bash
sed -n '180,260p' /home/nexus/git/nexus-documents-ia/frontend/src/lib/services/emma.service.ts
```

- [ ] **Step 2: Añadir handler para `agent_metadata`**

En el switch/match de eventos:

```typescript
case 'agent_metadata':
  onEvent({
    type: 'agent_metadata',
    payload: parsed.data as {
      agent_id?: string
      agent_slug: string
      agent_name: string
      agent_color: string
      agent_icon: string
    },
  })
  break
```

- [ ] **Step 3: Adjuntar metadata al mensaje en el reducer**

En el state reducer del chat (probablemente en `useEmmaChat` hook o en la página de chat), cuando llega `agent_metadata`, asignarlo al `currentMessage.metadata.agent`:

```typescript
if (event.type === 'agent_metadata') {
  setCurrentMessage((m) => ({ ...m, agent: event.payload }))
}
```

---

### Task 5.3: Frontend — render badge en `MessageBubble`

**Files:**
- Modify: `frontend/src/components/emma-chat/messages/MessageBubble.tsx`

- [ ] **Step 1: Inspeccionar estructura actual**

```bash
sed -n '1,80p' /home/nexus/git/nexus-documents-ia/frontend/src/components/emma-chat/messages/MessageBubble.tsx
```

- [ ] **Step 2: Render chip si `message.agent` existe y slug !== 'emma_general'**

Después del contenido principal del mensaje:

```tsx
{message.agent && message.agent.agent_slug !== 'emma_general' && (
  <div className={`mt-2 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs bg-${message.agent.agent_color}-100 text-${message.agent.agent_color}-700`}>
    <span>🤖</span>
    <span>{message.agent.agent_name}</span>
  </div>
)}
```

- [ ] **Step 3: Tipo `Message` actualizado**

Asegurar que el type incluye:

```typescript
type Message = {
  // ... existing fields ...
  agent?: { agent_id?: string; agent_slug: string; agent_name: string; agent_color: string; agent_icon: string }
}
```

- [ ] **Step 4: Smoke test manual E2E**

Levantar dev + emma. En chat, enviar `@contabilidad ¿qué facturas tengo?`. Verificar:
- Bubble de la respuesta muestra `🤖 Contabilidad` chip al final.
- Mensaje sin `@<slug>`: NO muestra chip.

---

### Task 5.4: Commit Phase 5

- [ ] **Step 1: Commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add backend/microservices/emma-agent-service/app/api/emma.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/nodes/classify.py
git add frontend/src/lib/services/emma.service.ts
git add frontend/src/components/emma-chat/messages/MessageBubble.tsx
git commit -m "$(cat <<'EOF'
feat(phase-5): agent_metadata SSE event + bubble badge

Backend emits agent_metadata SSE event once after classify with
{agent_id, agent_slug, agent_name, agent_color, agent_icon}. Frontend
captures it in the SSE consumer, attaches to the message object, and
the bubble renders a 🤖 <agent_name> chip when slug != emma_general.
Spec §Phase 5.
EOF
)"
```

---

## Phase 6 — Telemetry + docs

**Goal:** Métricas de uso, sort por popularidad, y documentación de arquitectura.

### Task 6.1: usage_count + metrics endpoint

**Files:**
- Modify: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/invoke_agent.py` (ya hecho — usage_counter)
- Create: `backend/app/services/agents/usage_counter.py` (interno al microservicio: ya tiene `usage_counter` mock; necesitamos un real impl que escriba en Main API).
- Modify: `backend/app/api/v1/agents.py` — añadir `/{id}/metrics` endpoint.

- [ ] **Step 1: Endpoint `POST /api/v1/agents/{id}/usage` (interno, llamado por usage_counter del microservicio)**

```python
# in backend/app/api/v1/agents.py
@router.post("/{agent_id}/usage", status_code=204, include_in_schema=False)
async def increment_usage(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    api_key: str = Depends(verify_internal_api_key),  # existing helper
) -> None:
    from sqlalchemy import update
    await db.execute(
        update(Agent).where(Agent.id == agent_id).values(usage_count=Agent.usage_count + 1)
    )
    await db.commit()
```

- [ ] **Step 2: Real `UsageCounter` en microservicio**

```python
# backend/microservices/emma-agent-service/app/services/agent_usage_counter.py
from app.services.main_api_client import MainAPIClient
import logging

logger = logging.getLogger(__name__)


class AgentUsageCounter:
    def __init__(self) -> None:
        self._client = MainAPIClient()

    async def increment(self, agent_id: str) -> None:
        try:
            await self._client.increment_agent_usage(agent_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("usage increment failed agent_id=%s: %s", agent_id, exc)
```

Extender `MainAPIClient` con `increment_agent_usage`:

```python
async def increment_agent_usage(self, agent_id: str) -> None:
    async with httpx.AsyncClient(timeout=2.0) as c:
        r = await c.post(f"{self._base_url}/api/v1/agents/{agent_id}/usage", headers=self._headers)
    r.raise_for_status()
```

Wire en `_default_agent_loader` / registry para pasar al `InvokeAgentTool`.

- [ ] **Step 3: Endpoint metrics**

```python
# in backend/app/api/v1/agents.py
@router.get("/{agent_id}/metrics", response_model=dict)
async def get_metrics(
    agent_id: uuid.UUID,
    _user: UserProfile = Depends(get_current_user),
    svc: AgentService = Depends(_service),
) -> dict:
    agent = await svc.get(agent_id)
    return {
        "usage_count": agent.usage_count,
        "last_used_at": None,  # TODO when last_used column added
        "avg_latency_ms": None,  # populate from Langfuse traces if needed
    }
```

- [ ] **Step 4: Sort `?order_by=usage_count` en list**

```python
# in service.list:
async def list(self, *, active_only: bool = False, order_by: str = "name") -> list[Agent]:
    stmt = select(Agent)
    if active_only:
        stmt = stmt.where(Agent.is_active.is_(True))
    if order_by == "usage_count":
        stmt = stmt.order_by(Agent.usage_count.desc())
    else:
        stmt = stmt.order_by(Agent.name)
    result = await self.db.execute(stmt)
    return list(result.scalars().all())
```

Y en el endpoint:

```python
async def list_agents(
    active: Optional[bool] = None,
    slug: Optional[str] = None,
    order_by: Optional[str] = "name",
    ...
):
    ...
    rows = await svc.list(active_only=bool(active), order_by=order_by or "name")
    ...
```

- [ ] **Step 5: Frontend — sort "Más usados" en `agents-gallery.tsx`**

Añadir `<select>` con opciones `Nombre` / `Más usados` que pasa `order_by` al service.

---

### Task 6.2: Update CLAUDE.md + AGENTS.md

**Files:**
- Modify: `/home/nexus/git/nexus-documents-ia/CLAUDE.md`
- Create: `/home/nexus/git/nexus-documents-ia/docs/architecture/AGENTS.md`

- [ ] **Step 1: AGENTS.md — architecture-level doc**

```markdown
# Admin-Curated Agents Catalog

> **Status:** Implemented 2026-05-XX (`feature/admin-curated-agents` merged).

## Overview

The agents catalog replaces the hardcoded `analyze_domain` list. Admins curate
specialist agents from `/admin/agents`; authenticated users invoke them with
`@<slug>` inside the Emma chat.

## Database

`agents` table — see `backend/app/db/agent_models.py` for the schema.

Invariants enforced at API level:
- `is_seed=True` rows cannot be deleted (409 Conflict).
- `is_seed=True` rows cannot be deactivated (409 Conflict).
- Slug pattern: `^[a-z][a-z0-9_]{1,49}$`.

## Runtime Flow

1. Frontend chat sender extracts `agent_slug` from the first `agent`-typed mention tag.
2. POST `/emma/query/stream` with `{ message, agent_slug?, thread_id }`.
3. Emma's `classify_node` short-circuits when `agent_slug` is set: ReAct loop is constrained to `invoke_agent` once.
4. `AgentLoader` (60s Redis cache) resolves slug → DB row + Langfuse persona (`agent_<slug>_persona`).
5. `InvokeAgentTool` calls the dual-model router with the persona as system prompt and the scope filters as context hint.
6. SSE emits `agent_metadata` once (after classify) so the frontend can render the badge.

## Source of Truth

- **DB row**: canonical replica. Admin writes here.
- **Langfuse `agent_<slug>_persona`**: runtime read. Pushed automatically on every CRUD write.
- **Recovery**: `python backend/scripts/sync_agents_to_langfuse.py` re-pushes every active agent.

## Files

- Model: `backend/app/db/agent_models.py`
- Schemas: `backend/app/schemas/agent.py`
- Service: `backend/app/services/agent_service.py`
- API: `backend/app/api/v1/agents.py`
- Loader: `backend/microservices/emma-agent-service/app/services/agent_loader.py`
- Tool: `backend/microservices/emma-agent-service/app/agents/langgraph/tools/invoke_agent.py`
- Frontend admin: `frontend/src/app/admin/agents/`
- Frontend gallery: `frontend/src/app/agents/page.tsx`
- Mention extension: `frontend/src/components/documents/entity-search-menu.tsx`
- Bubble badge: `frontend/src/components/emma-chat/messages/MessageBubble.tsx`
```

- [ ] **Step 2: CLAUDE.md — añadir sección "Agents Catalog"**

Insertar tras la sección `### TrustGraph — Knowledge Graph Triple Store`:

```markdown
### Agents Catalog (admin-curated)

> **Full docs**: [`docs/architecture/AGENTS.md`](docs/architecture/AGENTS.md)

Admin-curated specialist agents replace the legacy hardcoded
`analyze_domain` list. Each agent has identity (name/slug/icon/color),
persona (Langfuse prompt + style/language modifiers), data scope
(7 filter dimensions on the existing tools), and runtime params
(model_role/temperature). Invocation: `@<slug>` from the Emma chat.

**Tool**: `invoke_agent(agent_slug, question, context?)` — replaces
`analyze_domain`. Single LLM call per invocation, persona as system
prompt, scope injected as context hint into the sub-tools.
```

- [ ] **Step 3: Borrar referencia obsoleta**

```bash
grep -n "analyze_domain\|specialists\.py" /home/nexus/git/nexus-documents-ia/CLAUDE.md
```

Sustituir cualquier mención a `analyze_domain` por `invoke_agent`.

---

### Task 6.3: Recovery script

**Files:**
- Create: `backend/scripts/sync_agents_to_langfuse.py`

- [ ] **Step 1: Script idempotente**

```python
# backend/scripts/sync_agents_to_langfuse.py
"""Re-push every active agent's persona to Langfuse (disaster recovery)."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db.async_session import async_session_maker
from app.db.agent_models import Agent
from app.services.langfuse.persona import LangfusePersonaAdapter


async def main() -> None:
    adapter = LangfusePersonaAdapter()
    async with async_session_maker() as db:
        rows = (await db.execute(select(Agent).where(Agent.is_active.is_(True)))).scalars().all()
        for row in rows:
            await adapter.push_persona(
                slug=row.slug,
                instructions=(row.persona or {}).get("instructions", ""),
            )
            print(f"  + {row.slug}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Smoke run**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && python scripts/sync_agents_to_langfuse.py
```

Expected: una línea por agente activo.

---

### Task 6.4: Commit Phase 6

- [ ] **Step 1: Commit**

```bash
cd /home/nexus/git/nexus-documents-ia
git add backend/app/api/v1/agents.py backend/app/services/agent_service.py
git add backend/microservices/emma-agent-service/app/services/agent_usage_counter.py
git add backend/microservices/emma-agent-service/app/services/main_api_client.py
git add backend/microservices/emma-agent-service/app/agents/langgraph/tools/registry.py
git add backend/scripts/sync_agents_to_langfuse.py
git add frontend/src/components/agents/agents-gallery.tsx
git add docs/architecture/AGENTS.md CLAUDE.md
git commit -m "$(cat <<'EOF'
feat(phase-6): usage telemetry + sort-by-popularity + docs

Adds POST /agents/{id}/usage internal endpoint + AgentUsageCounter that
fires from invoke_agent on success. GET /agents accepts order_by=usage_count.
Gallery shows a "Más usados" sort. Adds disaster recovery script
sync_agents_to_langfuse.py. Documents the system in
docs/architecture/AGENTS.md and updates CLAUDE.md. Spec §Phase 6.
EOF
)"
```

---

## Final validation

### Task FINAL.1: Full backend test suite

- [ ] **Step 1: Run all backend tests**

```bash
cd /home/nexus/git/nexus-documents-ia/backend && pytest tests/ -v --tb=short
```

Expected: green; cero regresiones respecto a baseline.

- [ ] **Step 2: Run microservice tests**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/microservices/emma-agent-service && pytest tests/ -v --tb=short
```

Expected: green.

### Task FINAL.2: Frontend type-check + lint

- [ ] **Step 1**

```bash
cd /home/nexus/git/nexus-documents-ia/frontend && npx tsc --noEmit && npm run lint
```

Expected: cero errores nuevos.

### Task FINAL.3: Manual E2E happy path

- [ ] **Step 1: Levantar todo el stack**

```bash
cd /home/nexus/git/nexus-documents-ia/backend/docker && docker compose up -d --build
cd /home/nexus/git/nexus-documents-ia/frontend && npm run dev
```

- [ ] **Step 2: Checklist**

| Acción | Esperado |
|---|---|
| Login como admin → `/admin/agents` | Lista con 4 agentes (1 seed activo + 3 starters inactivos). |
| Crear agente nuevo "Marketing" con persona y scope | Toast OK, agente aparece en lista. |
| Activar `Contabilidad` (toggle) | OK. |
| Ir a `/agents` | Gallery muestra `Emma General` + `Contabilidad` (no `Ventas`/`Legal`/`Marketing` inactivos — salvo `Marketing` si lo activas). |
| En chat, escribir `@con` | Menú abre con sección "Asistentes" mostrando `@contabilidad`. |
| Seleccionar `@contabilidad`, escribir "¿qué facturas hay?", enviar | Bubble de respuesta muestra chip `🤖 Contabilidad`. |
| Borrar `Emma General` | Toast 409 "Seed agents cannot be deleted". |
| Cambiar a usuario non-admin → ir a `/admin/agents` | Redirección a home. |

### Task FINAL.4: Push branch

- [ ] **Step 1: Push**

```bash
cd /home/nexus/git/nexus-documents-ia
git push -u origin feature/admin-curated-agents
```

- [ ] **Step 2: Open PR**

Use `gh pr create` con título `feat: admin-curated agents catalog (replaces analyze_domain)`.

---

## Self-Review

**Spec coverage:**
- §Goals — covered en Phase 1 (CRUD), Phase 4 (gallery+mention), Phase 5 (badge), Phase 1 (`require_superuser` gating).
- §Non-Goals — respetados (no user-created, no sticky, no per-user visibility, no draft state, no migration de threads históricos).
- §Architecture diagram — Phase 1 (Main API), Phase 2 (Emma + Loader + Langfuse), Phase 3-5 (Frontend).
- §Data Model — Task 1.2 (model), 1.3 (migration), 1.4 (schemas) + invariants en service (Tasks 1.5-1.6).
- §Tool refactor — Phase 2 (Tasks 2.1-2.4).
- §Frontend (`/agents`, `/admin/agents`, mention, badge) — Phases 3 (admin), 4 (gallery+mention), 5 (badge).
- §Phase 0 (cleanup) — Phase 0 (Tasks 0.4-0.5).
- §Migration / Backwards Compatibility — Phase 2 (Task 2.4 borra specialists.py; Task 2.10 NO duplica los `emma_domain_<slug>` → la spec dice "kept as historical reference"; ningún paso los borra: ✅).
- §Risks & Mitigations:
  - Empty corpus warning → no implementado (live preview de scope queda como follow-up; mencionar en commit).
  - Inactive @<slug> graceful error → ToolResult.error en Task 2.4.
  - System prompt growth cap (50 active agents, sort by usage) → Task 2.9 + Task 6.1.
  - Langfuse drift → Task 1.6 (rollback transaction).
  - Slug collision → mention menu separa secciones (Task 4.2).
  - is_seed invariant → Task 1.5 tests + Task 1.6 service guard.

**Placeholder scan:**
- Task 1.6 `last_used_at: None  # TODO when last_used column added` — placeholder marcado intencionalmente como follow-up de Phase 6+; no bloquea v1.
- Task 2.8 step 1 `[Existing emma_react_system v11 body...]` — placeholder reemplazado por contenido real en Step 2-3.
- Ninguna referencia colgante a tipos/funciones no definidos.

**Type consistency:**
- `AgentLoader.load_by_slug` → `LoadedAgent` (Task 2.1, 2.2, 2.4) ✅.
- `AgentResponse.model_validate(...)` con `from_attributes=True` (Task 1.4 + 1.8) ✅.
- `agent_slug` field name consistente entre body schema, state, classify, SSE event, Frontend service.
- `ModelRole` importado desde `app.db.models` en Main API y desde `app.agents.llm_types` en microservicio (separados intencionalmente — la spec lo soporta).

Plan listo para ejecución.
