"""Tests for Agent Pydantic schemas (validation rules from spec §Data Model)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.db.enums import ModelRole
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    Persona,
    Scope,
)


class TestSlugValidation:
    @pytest.mark.parametrize("good_slug", ["co", "contabilidad", "ventas", "legal_es", "agent_v2"])
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
        AgentCreate(name="X", slug="x_x", temperature=1.5)

    @pytest.mark.parametrize("bad", [-0.1, 2.01, 5.0])
    def test_rejects_out_of_range(self, bad: float) -> None:
        with pytest.raises(ValidationError):
            AgentCreate(name="X", slug="x_x", temperature=bad)


class TestExtraForbid:
    def test_create_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            AgentCreate(name="X", slug="x_x", unknown_field="oops")


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

    def test_partial_update(self) -> None:
        u = AgentUpdate(is_active=True)
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {"is_active": True}


class TestModelRoleAccepted:
    def test_planner(self) -> None:
        agent = AgentCreate(name="P", slug="planner_x", model_role=ModelRole.PLANNER)
        assert agent.model_role == ModelRole.PLANNER

    def test_chat_default(self) -> None:
        agent = AgentCreate(name="C", slug="chat_x")
        assert agent.model_role == ModelRole.CHAT
