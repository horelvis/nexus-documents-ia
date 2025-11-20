"""
Add template file metadata columns for workflow templates

Revision ID: add_template_file_metadata_20250915_120000
Revises: Remove_content_field_to_eliminate_duplication_20250909_132646
Create Date: 2025-09-15 12:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_template_file_metadata_20250915_120000'
down_revision = 'Remove_content_field_to_eliminate_duplication_20250909_132646'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workflow_templates', sa.Column('template_file_path', sa.String(), nullable=True))
    op.add_column('workflow_templates', sa.Column('template_file_name', sa.String(), nullable=True))
    op.add_column('workflow_templates', sa.Column('template_file_mime', sa.String(), nullable=True))
    op.add_column('workflow_templates', sa.Column('template_file_size', sa.Integer(), nullable=True))
    op.add_column('workflow_templates', sa.Column('template_file_updated_at', sa.DateTime(), nullable=True))
    op.add_column(
        'workflow_templates',
        sa.Column('template_source_document_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_workflow_templates_source_document',
        'workflow_templates',
        'documents',
        ['template_source_document_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_workflow_templates_source_document', 'workflow_templates', type_='foreignkey')
    op.drop_column('workflow_templates', 'template_source_document_id')
    op.drop_column('workflow_templates', 'template_file_updated_at')
    op.drop_column('workflow_templates', 'template_file_size')
    op.drop_column('workflow_templates', 'template_file_mime')
    op.drop_column('workflow_templates', 'template_file_name')
    op.drop_column('workflow_templates', 'template_file_path')
