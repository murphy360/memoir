"""Run the migrations under a Postgres advisory lock, so two processes never race."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Any fixed number; every Memoir process that migrates takes the same lock.
LOCK_KEY = 7_303_202_609
# Inside the package, so an installed image carries its migrations.
SCRIPTS = Path(__file__).resolve().parent / "migrations"


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPTS))
    return cfg


def upgrade(engine: Engine, revision: str = "head") -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
        try:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, revision)
            conn.commit()
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            conn.commit()
