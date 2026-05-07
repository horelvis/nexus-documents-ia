"""Definition tests for the Agent SQLAlchemy model.

These are pure-Python checks (no DB required): verify column presence,
defaults, the unique/composite indexes, and that ModelRole is the
expected enum. The DB-level invariants (UNIQUE slug, NOT NULL,
server_default) are exercised end-to-end by the API smoke tests in
Task 1.9 once the Alembic migration has run.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, BigInteger, String

from app.db.agent_models import Agent
from app.db.models import ModelRole


class TestModelRoleEnum:
    def test_values(self) -> None:
        assert ModelRole.PLANNER.value == "PLANNER"
        assert ModelRole.CHAT.value == "CHAT"

    def test_membership(self) -> None:
        assert {m.value for m in ModelRole} == {"PLANNER", "CHAT"}


class TestAgentTable:
    def test_tablename(self) -> None:
        assert Agent.__tablename__ == "agents"

    def test_required_columns_present(self) -> None:
        cols = {c.name for c in Agent.__table__.columns}
        expected = {
            "id", "name", "slug", "description", "icon", "color",
            "persona", "scope", "is_active", "is_seed",
            "model_role", "temperature", "usage_count",
            "owner_id", "created_at", "updated_at",
        }
        missing = expected - cols
        assert not missing, f"Missing columns on agents table: {missing}"

    def test_slug_is_unique_and_indexed(self) -> None:
        slug_col = Agent.__table__.c.slug
        assert slug_col.unique is True
        assert slug_col.index is True
        assert isinstance(slug_col.type, String)

    def test_name_is_unique_and_indexed(self) -> None:
        name_col = Agent.__table__.c.name
        assert name_col.unique is True
        assert name_col.index is True

    def test_is_active_indexed(self) -> None:
        assert Agent.__table__.c.is_active.index is True

    def test_composite_index_slug_active(self) -> None:
        index_names = {ix.name for ix in Agent.__table__.indexes}
        assert "idx_agents_slug_active" in index_names

    def test_owner_id_fk_users(self) -> None:
        fks = list(Agent.__table__.c.owner_id.foreign_keys)
        assert len(fks) == 1
        assert fks[0].column.table.name == "users"

    def test_column_types(self) -> None:
        cols = Agent.__table__.c
        assert isinstance(cols.is_active.type, Boolean)
        assert isinstance(cols.is_seed.type, Boolean)
        assert isinstance(cols.temperature.type, Float)
        assert isinstance(cols.usage_count.type, BigInteger)


class TestAgentDefaults:
    """Construction-side defaults (Python defaults, NOT server_default)."""

    def test_defaults_via_construction(self) -> None:
        agent = Agent(
            name="Contabilidad",
            slug="contabilidad",
            owner_id=uuid.uuid4(),
        )
        # Defaults declared in Column(default=...) are applied on
        # INSERT-flush, not on Python construction. Confirming the
        # fields exist as attrs (they read None pre-flush) is enough
        # at this layer.
        assert agent.name == "Contabilidad"
        assert agent.slug == "contabilidad"
        # Defaults *as declared* on the column:
        cols = Agent.__table__.c
        assert cols.icon.default.arg == "IconRobot"
        assert cols.color.default.arg == "blue"
        assert cols.is_active.default.arg is False
        assert cols.is_seed.default.arg is False
        assert cols.temperature.default.arg == 0.5
        assert cols.usage_count.default.arg == 0
        assert cols.model_role.default.arg is ModelRole.CHAT
