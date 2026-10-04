"""Placement: what auto-filing made, and when it ran for a memory.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("events", "periods"):
        op.add_column(
            table,
            sa.Column(
                "auto_created_for_memory_id",
                sa.BigInteger(),
                sa.ForeignKey("memories.id", ondelete="SET NULL"),
            ),
        )
    op.add_column("memories", sa.Column("autofiled_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("memories", "autofiled_at")
    for table in ("events", "periods"):
        op.drop_column(table, "auto_created_for_memory_id")
