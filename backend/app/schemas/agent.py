"""Pydantic schemas for the agents catalog.

The schemas validate admin-curated agent definitions: identity (name/slug),
persona block, scope filters, and runtime parameters. ``slug`` is the
@<slug> token used in chat — must match a strict lowercase pattern.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import ModelRole

SLUG_REGEX = re.compile(r"^[a-z][a-z0-9_]{1,49}$")


class Persona(BaseModel):
    """Author content (instructions) + runtime modifiers (style, language)."""

    model_config = ConfigDict(extra="forbid")

    style: Literal["concise", "detailed", "conversational"] = "concise"
    language: Literal["es", "en", "auto"] = "es"
    instructions: str = ""


class DateRange(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

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
                "slug must match ^[a-z][a-z0-9_]{1,49}$ "
                "(lowercase, starts with letter, allows _ separator)"
            )
        return v


class AgentCreate(AgentBase):
    """Request body for POST /api/v1/agents/."""


class AgentUpdate(BaseModel):
    """Request body for PUT /api/v1/agents/{id}; all fields optional."""

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
    """Response model with server-managed fields."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    is_seed: bool
    usage_count: int
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
