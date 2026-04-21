"""create template edit sessions table

Revision ID: 20251117_104700_create_template_edit_sessions_table
Revises: 20250915_120000_add_template_file_metadata
Create Date: 2025-11-17 10:47:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20251117_104700_create_template_edit_sessions_table"
down_revision = "add_template_file_metadata_20250915_120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edit_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_name", sa.String(), nullable=False),
        sa.Column("template_file_name", sa.String(), nullable=True),
        sa.Column("template_file_mime", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("user_email", sa.String(), nullable=False),
        sa.Column("google_doc_id", sa.String(), nullable=False),
        sa.Column("google_doc_url", sa.Text(), nullable=False),
        sa.Column("google_doc_edit_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("last_activity", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.Column("original_content_hash", sa.String(), nullable=True),
        sa.Column("final_content_hash", sa.String(), nullable=True),
        sa.Column("changes_detected", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("content_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cleanup_attempted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cleanup_completed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cleanup_error", sa.Text(), nullable=True),
        sa.UniqueConstraint("google_doc_id", name="uq_edit_sessions_google_doc_id"),
    )
    op.create_index("ix_edit_sessions_tenant_id", "edit_sessions", ["tenant_id"])
    op.create_index("ix_edit_sessions_template_id", "edit_sessions", ["template_id"])
    op.create_index("ix_edit_sessions_user_id", "edit_sessions", ["user_id"])
    op.create_index("ix_edit_sessions_status", "edit_sessions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_edit_sessions_status", table_name="edit_sessions")
    op.drop_index("ix_edit_sessions_user_id", table_name="edit_sessions")
    op.drop_index("ix_edit_sessions_template_id", table_name="edit_sessions")
    op.drop_index("ix_edit_sessions_tenant_id", table_name="edit_sessions")
    op.drop_table("edit_sessions")
