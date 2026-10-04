"""Analysis: transcript and extraction state on memories, people and places to review,
and a row per AI call.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("transcript_state", "transcript_source", "extraction_state"):
        op.add_column("memories", sa.Column(column, sa.String(16)))
    op.add_column("memories", sa.Column("analysis_error", sa.Text()))
    op.add_column("memories", sa.Column("extracted", postgresql.JSONB()))
    for table in ("people", "places"):
        op.add_column(
            table,
            sa.Column(
                "needs_review", sa.Boolean(), nullable=False, server_default="false"
            ),
        )
        op.alter_column(table, "needs_review", server_default=None)
    op.create_table(
        "ai_calls",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
        ),
        sa.Column("task", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False),
        sa.Column("error", sa.String(300)),
        sa.Column(
            "memory_id",
            sa.BigInteger(),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_calls_archive_id", "ai_calls", ["archive_id"])
    op.create_index("ix_ai_calls_created_at", "ai_calls", ["created_at"])


def downgrade() -> None:
    op.drop_table("ai_calls")
    for table in ("people", "places"):
        op.drop_column(table, "needs_review")
    for column in (
        "extracted",
        "analysis_error",
        "extraction_state",
        "transcript_source",
        "transcript_state",
    ):
        op.drop_column("memories", column)
