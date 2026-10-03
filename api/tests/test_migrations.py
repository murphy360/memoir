from sqlalchemy import inspect

from app.core.db import Base


def test_the_migrations_create_the_bootstrap_tables(engine):
    tables = set(inspect(engine).get_table_names())
    assert {"archives", "users", "jobs", "worker_heartbeats", "blobs"} <= tables


def test_the_migrations_match_the_models(engine):
    """Every model column is in the migrated database: a missing migration fails."""
    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        migrated = {c["name"] for c in insp.get_columns(table.name)}
        assert {c.name for c in table.columns} == migrated, table.name
