"""drop document_acls and document_acl_audits tables

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-04-23 00:00:00.000000

Follow-up to the multi-tenancy removal (2026-04-21). The SaaS module that
owned these tables has been deleted; both tables were verified empty before
this migration was generated. JSONBACLProvider is now the only ACL provider
on-premise and uses IndexedDocument JSONB fields instead.

Downgrade is intentionally irreversible: the SaaS module and the
DocumentACL / DocumentACLAudit SQLAlchemy models are gone. Rolling this
migration back would leave orphan tables no code writes to.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade():
    # document_acls indexes
    op.drop_index('idx_document_acls_document_view', table_name='document_acls')
    op.drop_index(op.f('ix_document_acls_document_id'), table_name='document_acls')
    op.drop_index(op.f('ix_document_acls_expires_at'), table_name='document_acls')
    op.drop_index(op.f('ix_document_acls_grantee_id'), table_name='document_acls')
    op.drop_table('document_acls')

    # document_acl_audits indexes
    op.drop_index('idx_acl_audits_document_action', table_name='document_acl_audits')
    op.drop_index(op.f('ix_document_acl_audits_action'), table_name='document_acl_audits')
    op.drop_index(op.f('ix_document_acl_audits_document_id'), table_name='document_acl_audits')
    op.drop_table('document_acl_audits')


def downgrade():
    raise NotImplementedError(
        "Irreversible: SaaS module and DocumentACL / DocumentACLAudit models "
        "have been removed from the codebase. Restore from a pre-b3c4d5e6f7a8 "
        "snapshot if you truly need these tables back."
    )
