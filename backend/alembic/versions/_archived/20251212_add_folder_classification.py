"""Add folder classification system

Revision ID: 20251212_add_folder_classification
Revises: 20251210_add_document_acl
Create Date: 2024-12-12

Adds folder-based document organization with RAG+LLM auto-classification:
- folder_path column to documents for physical folder organization
- auto_classification config to tenants
- folder_path column to document_acls for folder-level permissions

Learn-First approach:
1. Initially auto_classification_enabled = FALSE
2. Users organize manually, system learns from examples
3. When enough examples, suggest activation
4. RAG+LLM classifies based on similar documents
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '20251212_add_folder_classification'
down_revision = '20251210_add_document_acl'
branch_labels = None
depends_on = None


def upgrade():
    """Add folder classification columns to documents and tenants."""

    # --- Documents table: Add folder organization columns ---
    op.add_column('documents', sa.Column(
        'folder_path',
        sa.String(2000),
        nullable=True,
        server_default='/Sin Clasificar',
        comment='Physical folder path in GCS, e.g. /Proveedores/Acme/Facturas'
    ))

    op.add_column('documents', sa.Column(
        'auto_classified',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='True if document was auto-classified by RAG+LLM'
    ))

    op.add_column('documents', sa.Column(
        'classification_confidence',
        sa.Float(),
        nullable=True,
        comment='LLM confidence score (0-1) for auto-classification'
    ))

    op.add_column('documents', sa.Column(
        'classification_reasoning',
        sa.Text(),
        nullable=True,
        comment='LLM reasoning for classification decision'
    ))

    # Index for fast folder queries
    op.create_index(
        'idx_documents_folder_path',
        'documents',
        ['tenant_id', 'folder_path'],
        postgresql_using='btree'
    )

    # --- Tenants table: Add auto-classification config ---
    op.add_column('tenants', sa.Column(
        'auto_classification_enabled',
        sa.Boolean(),
        nullable=False,
        server_default='false',
        comment='Whether RAG+LLM auto-classification is active'
    ))

    op.add_column('tenants', sa.Column(
        'auto_classification_k',
        sa.Integer(),
        nullable=False,
        server_default='7',
        comment='Number of similar docs to retrieve for RAG context'
    ))

    op.add_column('tenants', sa.Column(
        'auto_classification_min_confidence',
        sa.Float(),
        nullable=False,
        server_default='0.6',
        comment='Minimum LLM confidence to auto-classify (0-1)'
    ))

    # --- Document ACLs: Add folder_path for folder-level permissions ---
    op.add_column('document_acls', sa.Column(
        'folder_path',
        sa.String(2000),
        nullable=True,
        comment='If set, ACL applies to all docs in this folder path'
    ))

    op.create_index(
        'idx_document_acls_folder',
        'document_acls',
        ['tenant_id', 'folder_path'],
        postgresql_using='btree'
    )

    # --- Backfill existing documents with default folder ---
    op.execute("""
        UPDATE documents
        SET folder_path = '/Sin Clasificar'
        WHERE folder_path IS NULL
    """)


def downgrade():
    """Remove folder classification columns."""

    # Remove indexes first
    op.drop_index('idx_document_acls_folder', table_name='document_acls')
    op.drop_index('idx_documents_folder_path', table_name='documents')

    # Remove columns from document_acls
    op.drop_column('document_acls', 'folder_path')

    # Remove columns from tenants
    op.drop_column('tenants', 'auto_classification_min_confidence')
    op.drop_column('tenants', 'auto_classification_k')
    op.drop_column('tenants', 'auto_classification_enabled')

    # Remove columns from documents
    op.drop_column('documents', 'classification_reasoning')
    op.drop_column('documents', 'classification_confidence')
    op.drop_column('documents', 'auto_classified')
    op.drop_column('documents', 'folder_path')
