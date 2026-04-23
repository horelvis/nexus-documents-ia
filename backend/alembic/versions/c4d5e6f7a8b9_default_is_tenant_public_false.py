"""default is_tenant_public to false

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-04-23 09:55:00.000000

indexed_documents.is_tenant_public is a NOT NULL boolean with no default,
a leftover from the multi-tenant era. The sync path in background-worker
connector_tasks.py (IndexedDocument(...)) does not set it — new rows
therefore fail with "null value in column is_tenant_public ... violates
not-null constraint".

The column is documented in models.py as a legacy dead column (new code
uses the `roles` ARRAY for ACL), but JSONBACLProvider still reads it.
Dropping it would require refactoring that provider — out of scope here.

Minimal fix: add DEFAULT false so inserts without the column succeed, and
backfill any pre-existing NULL rows to false. Semantically `false` =
"document is not tenant-public"; the `roles` array drives visibility
(docs with 'EVERYONE' remain visible to all authenticated users).
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE indexed_documents "
        "ALTER COLUMN is_tenant_public SET DEFAULT false"
    )
    # Defensive: ensure no pre-existing NULL rows linger. The column is
    # currently NOT NULL so this is expected to be a no-op; included for
    # safety if a prior migration ever relaxed the constraint.
    op.execute(
        "UPDATE indexed_documents SET is_tenant_public = false "
        "WHERE is_tenant_public IS NULL"
    )


def downgrade():
    op.execute(
        "ALTER TABLE indexed_documents "
        "ALTER COLUMN is_tenant_public DROP DEFAULT"
    )
