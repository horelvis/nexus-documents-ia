"""drop emma_sessions table

The legacy ``emma_sessions`` table duplicated message storage that the
LangGraph AsyncPostgresSaver already owns (checkpoints / checkpoint_blobs
/ checkpoint_writes). The chat history surface (sidebar list, single
thread fetch, delete) now reads/writes the checkpointer tables directly;
the parallel table is removed.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_emma_sessions_user_last_message")
    op.execute("DROP INDEX IF EXISTS ix_emma_sessions_session_id")
    op.execute("DROP INDEX IF EXISTS ix_emma_sessions_user_id")
    op.execute("DROP TABLE IF EXISTS emma_sessions")


def downgrade() -> None:
    """Recreate the table empty.

    The table never carried production data in this branch (it was
    populated only by code now removed); a downgrade restores the
    schema for compatibility but no row backfill is possible.
    """
    op.create_table(
        "emma_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("session_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", name="uq_emma_sessions_session_id"),
    )
    op.create_index("ix_emma_sessions_user_id", "emma_sessions", ["user_id"])
    op.create_index("ix_emma_sessions_session_id", "emma_sessions", ["session_id"])
    op.create_index("idx_emma_sessions_user_last_message", "emma_sessions", ["user_id", "last_message_at"])
