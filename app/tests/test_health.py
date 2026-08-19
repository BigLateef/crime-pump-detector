from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "phase-1-foundation"
    assert body["dry_run"] is True


def test_liveness():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_shape():
    # In this sandbox there's no live Postgres/Redis, so we only assert the
    # response shape, not that the dependency checks pass.
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"status", "checks", "dry_run", "low_cost_mode"}
    assert set(body["checks"].keys()) == {"database", "redis"}
