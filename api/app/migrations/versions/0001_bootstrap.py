"""Bootstrap: archives, users, jobs, worker heartbeats, blobs.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "archives",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("time_zone", sa.String(64), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_users_archive_id", "users", ["archive_id"])
    op.create_index(
        "uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(80), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", TZ, nullable=False),
        sa.Column("idempotency_key", sa.String(200), unique=True),
        sa.Column("claimed_by", sa.String(80)),
        sa.Column("heartbeat_at", TZ),
        sa.Column("progress", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column(
            "requested_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("finished_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_jobs_kind", "jobs", ["kind"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index(
        "ix_jobs_due",
        "jobs",
        ["run_after", "id"],
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(80), primary_key=True),
        sa.Column("started_at", TZ, nullable=False),
        sa.Column("last_seen", TZ, nullable=False),
    )
    op.create_table(
        "blobs",
        sa.Column("sha256", sa.CHAR(64), primary_key=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )


def downgrade() -> None:
    for table in ("blobs", "worker_heartbeats", "jobs", "users", "archives"):
        op.drop_table(table)
