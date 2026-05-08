"""add agents table

Creates the catalog table for the admin-curated agents feature.
Pure additive migration; downgrade drops the table and the
``modelrole`` Postgres enum type.

Revision ID: a7b8c9d0e1f2
Revises: f8a9b0c1d2e3
Create Date: 2026-05-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=False, server_default="IconRobot"),
        sa.Column("color", sa.String(length=20), nullable=False, server_default="blue"),
        sa.Column(
            "persona",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "scope",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "model_role",
            sa.Enum("PLANNER", "CHAT", name="modelrole"),
            nullable=False,
            server_default="CHAT",
        ),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("usage_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_agents_name"),
        sa.UniqueConstraint("slug", name="uq_agents_slug"),
    )
    op.create_index("ix_agents_name", "agents", ["name"], unique=False)
    op.create_index("ix_agents_slug", "agents", ["slug"], unique=False)
    op.create_index("ix_agents_is_active", "agents", ["is_active"], unique=False)
    op.create_index("idx_agents_slug_active", "agents", ["slug", "is_active"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_agents_slug_active", table_name="agents")
    op.drop_index("ix_agents_is_active", table_name="agents")
    op.drop_index("ix_agents_slug", table_name="agents")
    op.drop_index("ix_agents_name", table_name="agents")
    op.drop_table("agents")
    op.execute("DROP TYPE IF EXISTS modelrole")
