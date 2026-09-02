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
