"""Recordings in which nothing was said: transcribed as empty before transcription
marked them, so they read "empty" too.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


MARK_EMPTY = (
    "UPDATE memories SET transcript_state = 'empty' "
    "WHERE transcript_state = 'done' AND transcript_source = 'machine' "
    "AND coalesce(btrim(transcript), '') = ''"
)


def upgrade() -> None:
    op.execute(MARK_EMPTY)


def downgrade() -> None:
    op.execute(
        "UPDATE memories SET transcript_state = 'done' WHERE transcript_state = 'empty'"
    )
