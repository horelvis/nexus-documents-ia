"""drop legacy ACL columns from indexed_documents

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-23 20:00:00.000000

Plan 5 Phase B follow-up. On 2026-04-23 we deleted the dead
JSONBACLProvider tree (commit dba67f29) — the three columns it consumed
(is_tenant_public, shared_with_users, shared_with_groups) had no
runtime readers left. This migration drops them from the DB.

The `roles` ARRAY column on indexed_documents is now the sole ACL
mechanism, used by app.core.auth.acl.filter_visible_to_user.

Downgrade is intentionally irreversible — the model no longer declares
these columns and the provider that understood them is gone. Restore
from a pre-d5e6f7a8b9c0 snapshot if the columns really need to come
back.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('indexed_documents', 'is_tenant_public')
    op.drop_column('indexed_documents', 'shared_with_users')
    op.drop_column('indexed_documents', 'shared_with_groups')


def downgrade():
    raise NotImplementedError(
        "Irreversible: JSONBACLProvider and the model fields that consumed "
        "these columns have been removed. Restore from a pre-d5e6f7a8b9c0 "
        "snapshot if they truly need to come back."
    )
