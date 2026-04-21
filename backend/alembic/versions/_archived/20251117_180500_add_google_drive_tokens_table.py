"""add google drive tokens table

Revision ID: 20251117_180500_add_google_drive_tokens_table
Revises: 20251117_104700_create_template_edit_sessions_table
Create Date: 2025-11-17 18:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20251117_180500_add_google_drive_tokens_table"
down_revision = "20251117_104700_create_template_edit_sessions_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "google_drive_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("google_user_id", sa.String(), nullable=False),
        sa.Column("google_email", sa.String(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("access_token_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("token_expiry", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_google_drive_tokens_user_id", "google_drive_tokens", ["user_id"], unique=True)
    op.create_index("ix_google_drive_tokens_tenant_id", "google_drive_tokens", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_google_drive_tokens_tenant_id", table_name="google_drive_tokens")
    op.drop_index("ix_google_drive_tokens_user_id", table_name="google_drive_tokens")
    op.drop_table("google_drive_tokens")
