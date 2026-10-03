"""Fixtures: one migrated database for the whole run, emptied after each test."""

import os
import tempfile

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.db import Base, get_engine
from app.core.settings import get_settings
from app.migrate import upgrade
from tests.pg import database_url

# Settings are read on first use, so setting the environment here is in time.
_URL, _PG = database_url()
os.environ["MEMOIR_DATABASE_URL"] = _URL
os.environ["MEMOIR_BLOB_ROOT"] = tempfile.mkdtemp(prefix="memoir-blobs-")


def pytest_sessionfinish(session, exitstatus):
    if _PG:
        _PG.stop()


@pytest.fixture(scope="session")
def engine():
    eng = get_engine()
    upgrade(eng)
    return eng


@pytest.fixture
def factory(engine):
    yield sessionmaker(bind=engine, expire_on_commit=False)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def session(factory):
    with factory() as s:
        yield s


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def client(engine):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def broken_engine():
    """An engine that cannot reach any database, for the health test."""
    return create_engine("postgresql+psycopg://nobody@/none?host=/nonexistent")
