"""Drop Temporal workflow tables

Revision ID: 20251204_drop_temporal_workflow_tables
Revises: 20251120_000001_update_specific_user_subscription
Create Date: 2024-12-04

Removes all Temporal.io related tables as part of migration to Camunda 8.
Tables being dropped (in FK order):
1. workflow_execution_steps
2. workflow_executions
3. engine_template_fields
4. engine_templates
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251204_drop_temporal_workflow_tables'
down_revision = '20251120_000001_update_specific_user_subscription'
branch_labels = None
depends_on = None


def upgrade():
    """Drop Temporal workflow tables in correct FK order."""
    # Check if tables exist before dropping (safe migration)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    # Drop in FK-safe order (child tables first)
    tables_to_drop = [
        'workflow_execution_steps',
        'workflow_executions',
        'engine_template_fields',
        'engine_templates',
        'workflow_templates',  # Legacy table name
    ]

    for table_name in tables_to_drop:
        if table_name in existing_tables:
            op.drop_table(table_name)


def downgrade():
    """
    Note: Downgrade not implemented.
    These tables will be recreated with different structure when Camunda is implemented.
    """
    pass
