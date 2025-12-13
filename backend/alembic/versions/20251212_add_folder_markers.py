"""Add folder_markers table for empty folders

Revision ID: 20251212_add_folder_markers
Revises: 20251212_add_folder_classification
Create Date: 2024-12-12

Adds a table to persist empty folders created by users.
In Google Drive style navigation, folders only "exist" when they have documents.
This table allows empty folders to appear in the sidebar until documents are added.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '20251212_add_folder_markers'
down_revision = '20251212_add_folder_classification'
branch_labels = None
depends_on = None


def upgrade():
    """Create folder_markers table."""
    op.create_table(
        'folder_markers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id'), nullable=False, index=True),
        sa.Column('folder_path', sa.String(2000), nullable=False),
        sa.Column('created_by', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('tenant_id', 'folder_path', name='uq_folder_marker_tenant_path'),
    )

    op.create_index(
        'idx_folder_markers_tenant_path',
        'folder_markers',
        ['tenant_id', 'folder_path'],
        postgresql_using='btree'
    )


def downgrade():
    """Drop folder_markers table."""
    op.drop_index('idx_folder_markers_tenant_path', table_name='folder_markers')
    op.drop_table('folder_markers')
