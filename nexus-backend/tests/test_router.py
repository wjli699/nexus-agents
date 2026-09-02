"""Top-level router: /router/classify + app/router.py."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app import router as agent_router
from app.main import app

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
