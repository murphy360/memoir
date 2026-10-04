from datetime import timedelta

from app.core.db import get_session, utcnow
from app.jobs.models import WorkerHeartbeat
from app.main import create_app
from tests.conftest import broken_engine


def test_health_with_no_worker_is_degraded(client):
    body = client.get("/api/health").json()
    assert body["database"] == "ok"
    assert body["worker"]["status"] == "never"
    assert body["status"] == "degraded"


def test_health_with_a_live_worker_is_ok(client, session):
    session.add(
        WorkerHeartbeat(worker_id="w1", started_at=utcnow(), last_seen=utcnow())
    )
    session.commit()
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["worker"]["status"] == "ok"


def test_health_with_an_old_heartbeat_is_stale(client, session):
    old = utcnow() - timedelta(minutes=10)
    session.add(WorkerHeartbeat(worker_id="w1", started_at=old, last_seen=old))
    session.commit()
    assert client.get("/api/health").json()["worker"]["status"] == "stale"


def test_health_with_the_database_down_is_a_structured_503():
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker

    app = create_app()
    down = sessionmaker(bind=broken_engine())

    def no_db():
        with down() as s:
            yield s

    app.dependency_overrides[get_session] = no_db
    response = TestClient(app).get("/api/health")
    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "The database is not reachable.",
            "field": None,
        }
    }


def test_every_response_carries_a_request_id(client):
    response = client.get("/api/health", headers={"x-request-id": "abc"})
    assert response.headers["x-request-id"] == "abc"
    assert client.get("/api/health").headers["x-request-id"]


def test_unknown_route_is_a_structured_404(client):
    response = client.get("/api/nothing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_wrong_method_is_a_structured_405(client):
    response = client.post("/api/health")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
