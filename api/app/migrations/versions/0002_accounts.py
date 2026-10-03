"""Accounts: passwords and roles on users, sessions, invitations, login attempts, audit.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def _audited(table: str) -> None:
    """The Audited mixin's columns: who made and changed a row, and soft deletion."""
    for col in ("created_by", "updated_by"):
        op.add_column(
            table,
            sa.Column(
                col, sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")
            ),
        )
    op.add_column(table, sa.Column("updated_at", TZ))
    op.add_column(table, sa.Column("deleted_at", TZ))


def _user_columns() -> None:
    columns = [
        sa.Column("password_hash", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", sa.String(16), nullable=False, server_default="contributor"),
        sa.Column("is_executor", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "must_change_password", sa.Boolean(), nullable=False, server_default="false"
        ),
    ]
    for column in columns:
        op.add_column("users", column)
        # The defaults only fill rows that exist now; the application always sets them.
        op.alter_column("users", column.name, server_default=None)


def _sessions() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("last_seen_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ),
        sa.Column("user_agent", sa.String(300)),
        sa.Column("ip", sa.String(64)),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])


def _invitations() -> None:
    op.create_table(
        "invitations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_executor", sa.Boolean(), nullable=False),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("accepted_at", TZ),
        sa.Column(
            "accepted_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("revoked_at", TZ),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_invitations_archive_id", "invitations", ["archive_id"])
    _audited("invitations")


def _login_attempts() -> None:
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_index("ix_login_attempts_ip_time", "login_attempts", ["ip", "created_at"])
    op.create_index(
        "ix_login_attempts_email_time", "login_attempts", ["email", "created_at"]
    )


def _audit_events() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
        ),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column(
            "actor_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "subject_user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
        ),
        sa.Column("ip", sa.String(64)),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
    )
    for col in ("archive_id", "kind", "created_at"):
        op.create_index(f"ix_audit_events_{col}", "audit_events", [col])


def upgrade() -> None:
    _user_columns()
    _audited("users")
    _audited("archives")
    _sessions()
    _invitations()
    _login_attempts()
    _audit_events()


def downgrade() -> None:
    for table in ("audit_events", "login_attempts", "invitations", "sessions"):
        op.drop_table(table)
    for table in ("archives", "users"):
        for col in ("created_by", "updated_by", "updated_at", "deleted_at"):
            op.drop_column(table, col)
    for col in ("password_hash", "role", "is_executor", "must_change_password"):
        op.drop_column("users", col)
