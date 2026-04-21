"""Database models for Emma User Memory.

Tables:
    - emma_user_memory_facts: Cross-session user facts (identity, preferences, etc.)
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Float, Index, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base_class import Base


class EmmaUserMemoryFact(Base):
    """Persistent cross-session facts about users.

    Stores declared facts ("Me llamo Carlos") and inferred facts
    ("trabaja frecuentemente con contratos") for personalization.

    Facts are scoped to user_id and deduplicated by
    (category, fact_key) via a partial unique index on active facts.
    """
    __tablename__ = "emma_user_memory_facts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), nullable=False, index=True)

    # Fact classification
    category = Column(String(50), nullable=False)  # identity | work | preference | interest
    fact_key = Column(String(100), nullable=False)  # e.g. "name", "department", "language"
    fact_value = Column(Text, nullable=False)  # e.g. "Carlos", "Legal", "español"

    # Confidence and provenance
    confidence = Column(Float, nullable=False, default=1.0)  # 1.0 declared, 0.5-0.9 inferred
    source = Column(String(20), nullable=False, default="declared")  # declared | inferred
    source_query = Column(Text, nullable=True)  # The user message that originated this fact

    # Lifecycle
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # Unique active fact per user+category+key (allows soft-deleted duplicates)
        Index(
            "uq_user_memory_active_fact",
            "user_id", "category", "fact_key",
            unique=True,
            postgresql_where=Column("is_active") == True,  # noqa: E712
        ),
        # Fast lookup for user facts
        Index("idx_user_memory_user", "user_id"),
        # Fast lookup for active facts
        Index("idx_user_memory_active", "user_id", "is_active"),
    )
