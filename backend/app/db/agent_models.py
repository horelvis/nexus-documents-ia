"""SQLAlchemy model for the admin-curated agents catalog.

Agents are specialist personas curated by the administrator from the
``/admin/agents`` UI and invoked by end users via ``@<slug>`` in the
Emma chat. See ``docs/architecture/AGENTS.md`` for the runtime flow.
"""
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
from app.db.enums import ModelRole


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
    model_role = Column(
        SQLEnum(ModelRole, name="modelrole"),
        nullable=False,
        default=ModelRole.CHAT,
    )
    temperature = Column(Float, nullable=False, default=0.5)
    usage_count = Column(BigInteger, nullable=False, default=0)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_agents_slug_active", "slug", "is_active"),
    )
