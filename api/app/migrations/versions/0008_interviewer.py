"""The interviewer: whom a question is for, and whether a memory's questions came.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questions",
        sa.Column(
            "asked_of_id",
            sa.BigInteger(),
            sa.ForeignKey("people.id", ondelete="SET NULL"),
        ),
    )
    op.create_index("ix_questions_asked_of_id", "questions", ["asked_of_id"])
    op.add_column("memories", sa.Column("questions_state", sa.String(16)))


def downgrade() -> None:
    op.drop_column("memories", "questions_state")
    op.drop_index("ix_questions_asked_of_id", "questions")
    op.drop_column("questions", "asked_of_id")
