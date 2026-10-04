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


def test_worker_alive_answers_for_this_host(factory, monkeypatch, capsys):
    import socket
    from datetime import timedelta

    from app.core.db import utcnow
    from app.jobs.models import WorkerHeartbeat

    monkeypatch.setattr("app.cli.configure", lambda level: None)
    assert main(["worker-alive"]) == 1
    assert "No worker" in capsys.readouterr().err
    now = utcnow()
    with factory() as s:
        s.add(
            WorkerHeartbeat(worker_id="another-host:1", started_at=now, last_seen=now)
        )
        s.add(
            WorkerHeartbeat(
                worker_id=f"{socket.gethostname()}:7",
                started_at=now,
                last_seen=now - timedelta(minutes=5),
            )
        )
        s.commit()
    assert main(["worker-alive"]) == 1, "another host's worker, or a stale one"
    with factory() as s:
        row = s.get(WorkerHeartbeat, f"{socket.gethostname()}:7")
        row.last_seen = utcnow()
        s.commit()
    assert main(["worker-alive"]) == 0


def test_reset_password_from_the_host(factory, monkeypatch, capsys):
    import io

    from sqlalchemy import select

    from app.accounts.models import User
    from app.accounts.passwords import verify_password

    monkeypatch.setattr("app.cli.configure", lambda level: None)
    monkeypatch.setattr("sys.stdin", io.StringIO("a strong phrase here\n"))
    owner = ["create-owner", "--email", "corey@example.org", "--name", "Corey"]
    main([*owner, "--password-stdin"])
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO("a temporary phrase\n"))
    args = ["reset-password", "--email", "COREY@example.org", "--password-stdin"]
    assert main(args) == 0
    assert "picks their own" in capsys.readouterr().out
    with factory() as s:
        user = s.scalars(select(User)).one()
        assert user.must_change_password
        assert verify_password(user.password_hash, "a temporary phrase")
    monkeypatch.setattr("sys.stdin", io.StringIO("short\n"))
    assert main(args) == 1
    monkeypatch.setattr("sys.stdin", io.StringIO("a temporary phrase\n"))
    nobody = ["reset-password", "--email", "nobody@example.org", "--password-stdin"]
    assert main(nobody) == 1
    assert "No account" in capsys.readouterr().err
