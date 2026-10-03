"""Capture: upload sessions, and a memory's recording (original and MP3).

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    for column in ("original_audio_sha256", "audio_sha256"):
        op.add_column(
            "memories",
            sa.Column(
                column, sa.CHAR(64), sa.ForeignKey("blobs.sha256", ondelete="RESTRICT")
            ),
        )
    op.add_column("memories", sa.Column("audio_state", sa.String(16)))
    op.add_column("memories", sa.Column("audio_seconds", sa.Float()))
    op.add_column("memories", sa.Column("capture_context", postgresql.JSONB()))
    op.create_table(
        "upload_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("received_bytes", sa.BigInteger(), nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column(
            "memory_id",
            sa.BigInteger(),
            sa.ForeignKey("memories.id", ondelete="SET NULL"),
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
    )
    op.create_index("ix_upload_sessions_archive_id", "upload_sessions", ["archive_id"])


def downgrade() -> None:
    op.drop_table("upload_sessions")
    for column in (
        "capture_context",
        "audio_seconds",
        "audio_state",
        "audio_sha256",
        "original_audio_sha256",
    ):
        op.drop_column("memories", column)
