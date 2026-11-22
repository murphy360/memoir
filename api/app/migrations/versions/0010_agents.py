"""Connected agents: OAuth clients, grants, codes and tokens; the agent a memory was
told through.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def _grant_fk() -> sa.Column:
    return sa.Column(
        "grant_id",
        sa.BigInteger(),
        sa.ForeignKey("agent_grants.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    op.add_column("memories", sa.Column("told_through", sa.String(120)))
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("client_id", sa.String(64), nullable=False, unique=True),
        sa.Column("client_name", sa.String(120), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(), nullable=False),
        sa.Column("auth_method", sa.String(32), nullable=False),
        sa.Column("secret_hash", sa.CHAR(64)),
        sa.Column("created_at", TZ, nullable=False),
    )
    op.create_table(
        "agent_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            sa.BigInteger(),
            sa.ForeignKey("oauth_clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("last_used_at", TZ),
        sa.Column("revoked_at", TZ),
    )
    op.create_index("ix_agent_grants_user_id", "agent_grants", ["user_id"])
    op.create_index("ix_agent_grants_client_id", "agent_grants", ["client_id"])
    op.create_table(
        "oauth_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("code_hash", sa.CHAR(64), nullable=False, unique=True),
        _grant_fk(),
        sa.Column("redirect_uri", sa.String(500), nullable=False),
        sa.Column("code_challenge", sa.String(128), nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("used_at", TZ),
    )
    op.create_index("ix_oauth_codes_grant_id", "oauth_codes", ["grant_id"])
    op.create_table(
        "oauth_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("token_hash", sa.CHAR(64), nullable=False, unique=True),
        _grant_fk(),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("expires_at", TZ, nullable=False),
        sa.Column("revoked_at", TZ),
    )
    op.create_index("ix_oauth_tokens_grant_id", "oauth_tokens", ["grant_id"])


def downgrade() -> None:
    for table in ("oauth_tokens", "oauth_codes", "agent_grants", "oauth_clients"):
        op.drop_table(table)
    op.drop_column("memories", "told_through")
