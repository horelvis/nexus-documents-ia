"""merge lgpd deletion audit with existing migrations

Revision ID: 764a0cdee789
Revises: Add_document_routing_analysis_table_20250814_164502, add_lgpd_deletion_audit
Create Date: 2025-09-09 08:40:32.602321

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '764a0cdee789'
down_revision = ('Add_document_routing_analysis_table_20250814_164502', 'add_lgpd_deletion_audit')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass