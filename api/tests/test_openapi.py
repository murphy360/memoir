"""The web client is generated from web/src/api/openapi.json, so it must be current."""

from pathlib import Path

from app.cli import openapi_document

COMMITTED = Path(__file__).resolve().parents[2] / "web" / "src" / "api" / "openapi.json"


def test_the_committed_openapi_document_is_current():
    assert (
        COMMITTED.read_text() == openapi_document()
    ), "web/src/api/openapi.json is out of date: run `make openapi` and commit it"
