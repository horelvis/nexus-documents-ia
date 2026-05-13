"""drop google_drive_tokens table

The ``google_drive_tokens`` table backed a per-user Google Drive OAuth
flow whose only consumer was an orphan frontend component (TemplateEditor)
that was never wired into any route. The backend endpoints
(``/google-drive/oauth-url``, ``/oauth/callback``, ``/status``,
``/disconnect``), the ``GoogleDriveTokenService``, the
``internal_google_drive_tokens`` microservice API, and the schemas have
all been removed. This migration drops the now-unreferenced table.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-05-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "d1e2f3a4b5c6"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_google_drive_tokens_user_id")
    op.execute("DROP INDEX IF EXISTS ix_google_drive_tokens_id")
    op.execute("DROP TABLE IF EXISTS google_drive_tokens")


def downgrade() -> None:
    """Recreate the table empty.

    The table never carried operational data in this branch (the OAuth
    flow that populated it was never wired into the UI); a downgrade
    restores the schema for compatibility but no row backfill is
    possible.
    """
    op.create_table(
        "google_drive_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("google_user_id", sa.String(), nullable=False),
        sa.Column("google_email", sa.String(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb")),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_google_drive_tokens_id", "google_drive_tokens", ["id"])
    op.create_index("ix_google_drive_tokens_user_id", "google_drive_tokens", ["user_id"], unique=True)
