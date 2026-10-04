"""Where each date came from: `manual` dates are never overwritten by a job.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

COLUMNS = (
    ("events", "date_source"),
    ("memories", "date_source"),
    ("assets", "capture_source"),
    ("periods", "dates_source"),
    ("epics", "dates_source"),
    ("people", "birth_source"),
    ("people", "death_source"),
)


def upgrade() -> None:
    for table, column in COLUMNS:
        op.add_column(table, sa.Column(column, sa.String(16)))


def downgrade() -> None:
    for table, column in COLUMNS:
        op.drop_column(table, column)
