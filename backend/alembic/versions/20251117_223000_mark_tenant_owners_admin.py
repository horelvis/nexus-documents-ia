"""ensure tenant owners are treated as admins

Revision ID: 20251117_223000_mark_tenant_owners_admin
Revises: 20251117_180500_add_google_drive_tokens_table
Create Date: 2025-11-17 22:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251117_223000_mark_tenant_owners_admin"
down_revision = "20251117_180500_add_google_drive_tokens_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # Mark the earliest user per tenant as non-team-member (tenant admin/owner)
    conn.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    tenant_id,
                    ROW_NUMBER() OVER (
                        PARTITION BY tenant_id
                        ORDER BY created_at ASC NULLS LAST, id ASC
                    ) AS rn
                FROM users
                WHERE tenant_id IS NOT NULL
            )
            UPDATE users u
            SET is_team_member = FALSE
            FROM ranked r
            WHERE u.id = r.id
              AND r.rn = 1
              AND (u.is_team_member IS DISTINCT FROM FALSE);
            """
        )
    )

    # Ensure the reported account is explicitly marked as admin/owner.
    conn.execute(
        sa.text(
            """
            UPDATE users
            SET is_team_member = FALSE
            WHERE email = :email
            """
        ),
        {"email": "hcastillo.mendoza@venzia.es"},
    )


def downgrade() -> None:
    # Data migration is not easily reversible; no-op downgrade.
    pass
