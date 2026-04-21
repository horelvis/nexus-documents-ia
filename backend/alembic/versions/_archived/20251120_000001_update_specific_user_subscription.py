"""Update specific user subscription to NULL

Revision ID: 20251120_000001_update_specific_user_subscription
Revises: 20251120_000000_remove_sub_defaults
Create Date: 2025-11-20 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251120_000001_update_specific_user_subscription'
down_revision = '20251120_000000_remove_sub_defaults'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE users
            SET subscription_plan = NULL, subscription_status = NULL
            WHERE email = :email
            """
        ),
        {"email": "hcastillo.mendoza@venzia.es"},
    )

def downgrade():
    # No direct downgrade for this data change, as the intent is to clear it.
    # If specific values were needed, they would need to be set here.
    pass
