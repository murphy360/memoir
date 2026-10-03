"""Alembic's entry point. Migrations run online only, with the URL from the settings."""

import importlib

from alembic import context
from sqlalchemy import create_engine

from app.core.db import Base
from app.core.settings import get_settings

# Registers every table on Base.metadata.
importlib.import_module("app.models")
target_metadata = Base.metadata


def run() -> None:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(get_settings().database_url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
