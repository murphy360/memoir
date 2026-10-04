import json

from app.cli import main


def test_openapi_prints_the_document(capsys, monkeypatch):
    monkeypatch.setattr("app.cli.configure", lambda level: None)
    assert main(["openapi"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert "/api/health" in doc["paths"]
