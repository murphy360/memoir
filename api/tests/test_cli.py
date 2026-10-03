import json

from app.cli import main


def test_openapi_prints_the_document(capsys, monkeypatch):
    monkeypatch.setattr("app.cli.configure", lambda level: None)
    assert main(["openapi"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert "/api/health" in doc["paths"]


def test_create_owner_once_then_refuse(factory, monkeypatch, capsys):
    import io

    monkeypatch.setattr("app.cli.configure", lambda level: None)
    monkeypatch.setattr("sys.stdin", io.StringIO("a strong phrase here\n"))
    args = ["create-owner", "--email", "corey@example.org", "--name", "Corey"]
    assert main([*args, "--password-stdin"]) == 0
    assert "Owner corey@example.org created" in capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", io.StringIO("a strong phrase here\n"))
    assert main([*args, "--password-stdin"]) == 1
    assert "An owner already exists" in capsys.readouterr().err


def test_create_owner_refuses_a_weak_password(factory, monkeypatch, capsys):
    import io

    monkeypatch.setattr("app.cli.configure", lambda level: None)
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    args = [
        "create-owner",
        "--email",
        "c@example.org",
        "--name",
        "C",
        "--password-stdin",
    ]
    assert main(args) == 1
    assert "12 characters" in capsys.readouterr().err
