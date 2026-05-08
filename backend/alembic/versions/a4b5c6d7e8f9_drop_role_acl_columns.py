"""drop role-acl columns

Revision ID: a4b5c6d7e8f9
Revises: f8a9b0c1d2e3
Create Date: 2026-05-06 12:00:00.000000

Irreversible: drops Document.roles and IndexedDocument.roles columns
plus their GIN indexes. Also drops Connector.default_document_roles.
After this migration, role-based ACL is physically gone from PostgreSQL.
Restore requires pg_dump backup taken in Phase 0 pre-flight.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'a4b5c6d7e8f9'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_index("idx_documents_roles", table_name="documents")
    op.drop_column("documents", "roles")

    op.drop_index("idx_indexed_documents_roles", table_name="indexed_documents")
    op.drop_column("indexed_documents", "roles")

    op.drop_column("connectors", "default_document_roles")


def downgrade():
    raise NotImplementedError(
        "Irreversible: roles columns dropped permanently. "
        "Restore from pg_dump backup."
    )
