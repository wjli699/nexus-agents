"""Top-level router: /router/classify + app/router.py."""

import asyncio
import logging

import pytest
from fastapi.testclient import TestClient

from app import router as agent_router
from app.main import app
from app.routers import root

client = TestClient(app)


@pytest.mark.parametrize(
    "model_output, expected",
    [
        ({"agent": "stock"}, "stock"),
        ({"agent": "family"}, "family"),
        ({"agent": "weather"}, "unknown"),
        ({}, "unknown"),
        (None, "unknown"),
    ],
)
def test_classify_maps_and_guards(monkeypatch, model_output, expected):
    async def fake(prompt):
        return model_output

    monkeypatch.setattr(agent_router.llm, "complete_json", fake)
    assert asyncio.run(agent_router.classify("...")) == expected


def test_classify_endpoint(monkeypatch):
    async def fake(prompt):
        return {"agent": "family"}

    monkeypatch.setattr(agent_router.llm, "complete_json", fake)
    resp = client.post("/router/classify", json={"message": "when is mom's birthday"})
    assert resp.status_code == 200
    assert resp.json() == {"agent": "family"}


def test_handle_dispatches_to_agent(monkeypatch):
    async def route(msg):
        return "family"

    async def family_handle(msg):
        return "handled by family"

    monkeypatch.setattr(agent_router, "classify", route)
    monkeypatch.setattr("app.routers.root.family_agent.handle", family_handle)
    resp = client.post("/handle", json={"message": "add task walk dog"})
    assert resp.json() == {"text": "handled by family"}


def test_handle_unknown_agent_returns_help(monkeypatch):
    async def route(msg):
        return "unknown"

    monkeypatch.setattr(agent_router, "classify", route)
    resp = client.post("/handle", json={"message": "sing me a song"})
    assert "stocks" in resp.json()["text"] and "family" in resp.json()["text"]


# --- owner check -----------------------------------------------------------


@pytest.fixture
def owner(monkeypatch):
    """Configure TELEGRAM_OWNER_ID. get_settings() is lru_cached, so patch the
    resolved object rather than the environment."""

    def _set(user_id):
        settings = root.get_settings()
        monkeypatch.setattr(settings, "telegram_owner_id", user_id)

    return _set


@pytest.fixture
def never_classify(monkeypatch):
    """Fail loudly if a rejected request still reaches the agents."""

    async def boom(msg):
        raise AssertionError("classify must not run for a rejected sender")

    monkeypatch.setattr(agent_router, "classify", boom)


def test_handle_rejects_a_stranger(owner, never_classify):
    owner(111)
    resp = client.post("/handle", json={"message": "list", "user_id": 222})
    assert resp.status_code == 403


def test_handle_rejects_a_missing_user_id(owner, never_classify):
    # n8n not sending user_id must fail closed, not fall through to "open".
    owner(111)
    resp = client.post("/handle", json={"message": "list"})
    assert resp.status_code == 403


def test_handle_allows_the_owner(monkeypatch, owner):
    owner(111)

    async def route(msg):
        return "family"

    async def family_handle(msg):
        return "handled by family"

    monkeypatch.setattr(agent_router, "classify", route)
    monkeypatch.setattr("app.routers.root.family_agent.handle", family_handle)
    resp = client.post("/handle", json={"message": "list", "user_id": 111})
    assert resp.json() == {"text": "handled by family"}


def test_handle_stays_open_when_owner_unset(monkeypatch, owner):
    # 0 = unset: local curl and the existing tests keep working.
    owner(0)

    async def route(msg):
        return "unknown"

    monkeypatch.setattr(agent_router, "classify", route)
    assert client.post("/handle", json={"message": "hi"}).status_code == 200


def test_rejection_does_not_log_the_message(owner, never_classify, caplog):
    owner(111)
    with caplog.at_level(logging.WARNING):
        client.post("/handle", json={"message": "my private secret", "user_id": 222})
    assert "222" in caplog.text
    assert "my private secret" not in caplog.text
