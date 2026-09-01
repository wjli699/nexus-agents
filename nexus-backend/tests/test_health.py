"""Smoke tests for the scaffold.

Not using `with TestClient(app)` — that would run the lifespan handler, which
opens the DB pool. These only need the routes.

Run: cd nexus-backend && pip install -r requirements.txt pytest && python -m pytest
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
