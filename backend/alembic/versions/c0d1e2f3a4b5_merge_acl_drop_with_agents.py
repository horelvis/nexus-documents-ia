"""merge ACL drop with agents catalog + emma_sessions cleanup

Revision ID: c0d1e2f3a4b5
Revises: a4b5c6d7e8f9, b8c9d0e1f2a3
Create Date: 2026-05-08

This is an Alembic merge migration with no DDL of its own. It exists
purely to converge the two heads that emerged when development moved
forward (admin-curated agents + emma_sessions drop) while the role-based
ACL removal was being prepared on a separate branch:

    f8a9b0c1d2e3 ─┬─► a4b5c6d7e8f9  (drop role ACL columns)        [our branch]
                  │
                  └─► a7b8c9d0e1f2 ─► b8c9d0e1f2a3                  [development]
                       (add agents)    (drop emma_sessions)

Both heads are independent of each other (no shared tables, no shared
columns), so no DDL is needed here — Alembic just needs the merge node
to know the two histories converge.
"""
from __future__ import annotations

# revision identifiers, used by Alembic.
revision = "c0d1e2f3a4b5"
down_revision = ("a4b5c6d7e8f9", "b8c9d0e1f2a3")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op merge: both parent heads are already at their final state."""
    pass


def downgrade() -> None:
    """No-op merge: downgrading splits the history back into two heads."""
    pass
