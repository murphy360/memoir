"""The domain: people, places, threads, periods, epics, events, participants, memories,
assets, questions, archive settings.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
LIVE = sa.text("deleted_at IS NULL")


def _user_fk(name: str) -> sa.Column:
    return sa.Column(
        name, sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")
    )


def _row(table: str, *columns, **kw) -> None:
    """A domain table: id, archive, the columns, who and when, soft deletion."""
    op.create_table(
        table,
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *columns,
        sa.Column("created_at", TZ, nullable=False),
        _user_fk("created_by"),
        _user_fk("updated_by"),
        sa.Column("updated_at", TZ),
        sa.Column("deleted_at", TZ),
        **kw,
    )
    op.create_index(f"ix_{table}_archive_id", table, ["archive_id"])


def _fk(name: str, table: str, ondelete: str, nullable: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.BigInteger(),
        sa.ForeignKey(f"{table}.id", ondelete=ondelete),
        nullable=nullable,
    )


def _dates(prefix: str, precision: bool = True) -> list[sa.Column]:
    cols = [
        sa.Column(f"{prefix}_text", sa.String(100)),
        sa.Column(f"{prefix}_start", sa.Date()),
        sa.Column(f"{prefix}_end", sa.Date()),
    ]
    if precision:
        cols.append(sa.Column(f"{prefix}_precision", sa.String(16)))
    return cols


def _range() -> list[sa.Column]:
    return [
        sa.Column("start_text", sa.String(100)),
        sa.Column("start_on", sa.Date()),
        sa.Column("end_text", sa.String(100)),
        sa.Column("end_on", sa.Date()),
    ]


def _unique_lower(
    name: str, table: str, column: str, scope: str = "archive_id"
) -> None:
    op.create_index(
        name,
        table,
        [scope, sa.text(f"lower({column})")],
        unique=True,
        postgresql_where=LIVE,
    )


def _people() -> None:
    _row(
        "people",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(80)),
        sa.Column("email", sa.String(255)),
        sa.Column("address", sa.String(255)),
        sa.Column("notes", sa.Text()),
        *_dates("birth", precision=False),
        *_dates("death", precision=False),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            unique=True,
        ),
    )
    _unique_lower("uq_people_archive_name", "people", "name")
    op.create_table(
        "person_aliases",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        _fk("person_id", "people", "CASCADE", nullable=False),
        sa.Column("alias", sa.String(120), nullable=False),
    )
    op.create_index("ix_person_aliases_person_id", "person_aliases", ["person_id"])
    op.create_index(
        "uq_person_aliases_person_alias",
        "person_aliases",
        ["person_id", sa.text("lower(alias)")],
        unique=True,
    )


def _places_threads() -> None:
    _row(
        "places",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
    )
    _unique_lower("uq_places_archive_name", "places", "name")
    _row(
        "threads",
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("summary", sa.Text()),
    )
    _unique_lower("uq_threads_archive_title", "threads", "title")
    op.create_index(
        "uq_threads_archive_slug",
        "threads",
        ["archive_id", "slug"],
        unique=True,
        postgresql_where=LIVE,
    )


def _periods_epics() -> None:
    _row(
        "periods",
        _fk("person_id", "people", "CASCADE", nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        *_range(),
        sa.Column("summary", sa.Text()),
        sa.Column("summary_generated", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("id", "person_id", name="uq_periods_id_person"),
    )
    op.create_index("ix_periods_person_id", "periods", ["person_id"])
    op.create_index(
        "uq_periods_person_slug",
        "periods",
        ["person_id", "slug"],
        unique=True,
        postgresql_where=LIVE,
    )
    _row(
        "epics",
        _fk("period_id", "periods", "CASCADE", nullable=False),
        _fk("thread_id", "threads", "SET NULL"),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("weight", sa.Integer(), nullable=False),
        *_range(),
        sa.CheckConstraint("weight BETWEEN 1 AND 10", name="ck_epics_weight_1_10"),
        sa.UniqueConstraint("id", "period_id", name="uq_epics_id_period"),
    )
    for col in ("period_id", "thread_id"):
        op.create_index(f"ix_epics_{col}", "epics", [col])


def _events() -> None:
    _row(
        "events",
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("weight", sa.Integer(), nullable=False),
        *_dates("date"),
        sa.Column("location_text", sa.String(255)),
        _fk("place_id", "places", "SET NULL"),
        _fk("thread_id", "threads", "SET NULL"),
        sa.Column("summary", sa.Text()),
        sa.Column("relationship_effect", postgresql.JSONB()),
        sa.CheckConstraint("weight BETWEEN 1 AND 10", name="ck_events_weight_1_10"),
    )
    for col in ("date_start", "place_id", "thread_id"):
        op.create_index(f"ix_events_{col}", "events", [col])


def _participants() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        _fk("event_id", "events", "CASCADE", nullable=False),
        _fk("person_id", "people", "CASCADE", nullable=False),
        sa.Column("period_id", sa.BigInteger()),
        sa.Column("epic_id", sa.BigInteger()),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("confirmed_at", TZ),
        _user_fk("confirmed_by"),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint(
            "event_id", "person_id", name="uq_participants_event_person"
        ),
        sa.CheckConstraint(
            "epic_id IS NULL OR period_id IS NOT NULL",
            name="ck_participants_epic_needs_period",
        ),
    )
    for col in ("event_id", "person_id", "period_id", "epic_id"):
        op.create_index(f"ix_participants_{col}", "participants", [col])
    # A placement is in the participant's own period, and its epic is in that period.
    # Checked at commit, so a move or a merge can change both sides in one transaction.
    op.create_foreign_key(
        "fk_participants_own_period",
        "participants",
        "periods",
        ["period_id", "person_id"],
        ["id", "person_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_participants_epic_in_period",
        "participants",
        "epics",
        ["epic_id", "period_id"],
        ["id", "period_id"],
        deferrable=True,
        initially="DEFERRED",
    )


def _memories_questions() -> None:
    _row(
        "memories",
        _fk("event_id", "events", "SET NULL"),
        _fk("storyteller_id", "people", "SET NULL"),
        _user_fk("uploaded_by"),
        sa.Column("title", sa.String(180)),
        sa.Column("description", sa.Text()),
        sa.Column("transcript", sa.Text()),
        sa.Column("recorded_at", TZ, nullable=False),
        *_dates("date"),
        sa.Column("tone", sa.String(16)),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("response_to_question_id", sa.BigInteger()),
    )
    for col in ("event_id", "storyteller_id"):
        op.create_index(f"ix_memories_{col}", "memories", [col])
    _row(
        "questions",
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        _fk("source_memory_id", "memories", "SET NULL"),
        _fk("event_id", "events", "SET NULL"),
        _fk("period_id", "periods", "SET NULL"),
        _fk("person_id", "people", "SET NULL"),
        _fk("answered_by_memory_id", "memories", "SET NULL"),
    )
    op.create_index("ix_questions_status", "questions", ["status"])
    op.create_index(
        "uq_questions_pending_text",
        "questions",
        ["archive_id", "normalized"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND deleted_at IS NULL"),
    )
    op.create_foreign_key(
        "fk_memories_response_to_question_id_questions",
        "memories",
        "questions",
        ["response_to_question_id"],
        ["id"],
        ondelete="SET NULL",
    )
    for table, other in (("memory_mentions", "people"), ("memory_places", "places")):
        column = "person_id" if other == "people" else "place_id"
        op.create_table(
            table,
            sa.Column("id", sa.BigInteger(), primary_key=True),
            _fk("memory_id", "memories", "CASCADE", nullable=False),
            _fk(column, other, "CASCADE", nullable=False),
            sa.UniqueConstraint("memory_id", column),
        )
        op.create_index(f"ix_{table}_memory_id", table, ["memory_id"])
        op.create_index(f"ix_{table}_{column}", table, [column])


def _assets() -> None:
    _row(
        "assets",
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(180)),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "blob_sha256",
            sa.CHAR(64),
            sa.ForeignKey("blobs.sha256", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("excerpt", sa.Text()),
        *_dates("capture"),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("exif_place_name", sa.String(200)),
        sa.Column("geocoded_place_name", sa.String(200)),
        sa.Column("analyzed_place_name", sa.String(200)),
        _fk("place_id", "places", "SET NULL"),
    )
    for col in ("blob_sha256", "place_id"):
        op.create_index(f"ix_assets_{col}", "assets", [col])
    op.create_table(
        "event_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        _fk("event_id", "events", "CASCADE", nullable=False),
        _fk("asset_id", "assets", "CASCADE", nullable=False),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.UniqueConstraint("event_id", "asset_id"),
    )
    for col in ("event_id", "asset_id"):
        op.create_index(f"ix_event_assets_{col}", "event_assets", [col])


def _settings() -> None:
    flags = (
        "ai_transcription",
        "ai_extraction",
        "ai_questions",
        "ai_research",
        "ai_photos",
        "face_detection_on_upload",
        "auto_file_quick_memories",
    )
    op.create_table(
        "archive_settings",
        sa.Column(
            "archive_id",
            sa.BigInteger(),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("storyteller_name", sa.String(120)),
        *[sa.Column(f, sa.Boolean(), nullable=False) for f in flags],
        sa.Column("face_auto_assign_threshold", sa.Float(), nullable=False),
        _user_fk("created_by"),
        _user_fk("updated_by"),
        sa.Column("updated_at", TZ),
        sa.Column("deleted_at", TZ),
    )


def upgrade() -> None:
    _people()
    _places_threads()
    _periods_epics()
    _events()
    _participants()
    _memories_questions()
    _assets()
    _settings()


def downgrade() -> None:
    op.drop_constraint(
        "fk_memories_response_to_question_id_questions", "memories", type_="foreignkey"
    )
    for table in (
        "archive_settings",
        "event_assets",
        "assets",
        "memory_places",
        "memory_mentions",
        "questions",
        "memories",
        "participants",
        "events",
        "epics",
        "periods",
        "threads",
        "places",
        "person_aliases",
        "people",
    ):
        op.drop_table(table)
