"""Add document_analyses table for Emma AI analysis queue

Revision ID: 20251206_add_document_analyses_table
Revises: 20251204_drop_temporal_workflow_tables
Create Date: 2024-12-06

Creates the document_analyses table for persisting Emma AI analysis results.
This enables:
- Background processing queue for document analysis
- Historical analysis retrieval
- Analysis result caching
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '20251206_add_document_analyses_table'
down_revision = '20251204_drop_temporal_workflow_tables'
branch_labels = None
depends_on = None


def upgrade():
    """Create document_analyses table."""
    # Check if table already exists (safe migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'document_analyses' not in existing_tables:
        op.create_table(
            'document_analyses',
            # Primary key
            sa.Column('id', UUID(as_uuid=True), primary_key=True),

            # Foreign keys
            sa.Column('document_id', UUID(as_uuid=True),
                      sa.ForeignKey('documents.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('tenant_id', UUID(as_uuid=True),
                      sa.ForeignKey('tenants.id', ondelete='CASCADE'),
                      nullable=False, index=True),
            sa.Column('created_by', UUID(as_uuid=True),
                      sa.ForeignKey('users.id', ondelete='SET NULL'),
                      nullable=True),

            # Analysis state
            sa.Column('status', sa.String(30), nullable=False, default='pending', index=True),
            sa.Column('progress', sa.Integer(), nullable=False, default=0),
            sa.Column('current_step', sa.String(200), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),

            # Analysis configuration
            sa.Column('analysis_type', sa.String(50), nullable=False, default='legal'),
            sa.Column('detected_document_type', sa.String(100), nullable=True),
            sa.Column('detected_document_type_display', sa.String(200), nullable=True),
            sa.Column('detection_confidence', sa.Float(), nullable=True),

            # Plan information
            sa.Column('plan_id', sa.String(100), nullable=True),
            sa.Column('plan_title', sa.String(500), nullable=True),
            sa.Column('total_steps', sa.Integer(), nullable=True, default=0),
            sa.Column('steps_completed', sa.Integer(), nullable=True, default=0),

            # Results
            sa.Column('summary', sa.Text(), nullable=True),
            sa.Column('risks', JSONB(), nullable=True, server_default='[]'),
            sa.Column('recommendations', JSONB(), nullable=True, server_default='[]'),
            sa.Column('findings', JSONB(), nullable=True, server_default='[]'),
            sa.Column('annotations', JSONB(), nullable=True, server_default='[]'),
            sa.Column('execution_log', JSONB(), nullable=True, server_default='[]'),

            # Output files
            sa.Column('annotated_pdf_path', sa.String(1000), nullable=True),
            sa.Column('annotated_pdf_url', sa.String(2000), nullable=True),

            # Metrics
            sa.Column('confidence_score', sa.Float(), nullable=True),
            sa.Column('execution_time_ms', sa.Integer(), nullable=True),

            # Timestamps
            sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True),
                      server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        )

        # Create additional indexes for common queries
        op.create_index(
            'idx_document_analyses_tenant_status',
            'document_analyses',
            ['tenant_id', 'status']
        )
        op.create_index(
            'idx_document_analyses_document',
            'document_analyses',
            ['document_id']
        )
        op.create_index(
            'idx_document_analyses_created',
            'document_analyses',
            ['created_at']
        )
        op.create_index(
            'idx_document_analyses_tenant_created',
            'document_analyses',
            ['tenant_id', 'created_at']
        )


def downgrade():
    """Drop document_analyses table."""
    # Drop indexes first
    op.drop_index('idx_document_analyses_tenant_created', table_name='document_analyses')
    op.drop_index('idx_document_analyses_created', table_name='document_analyses')
    op.drop_index('idx_document_analyses_document', table_name='document_analyses')
    op.drop_index('idx_document_analyses_tenant_status', table_name='document_analyses')

    # Drop table
    op.drop_table('document_analyses')
