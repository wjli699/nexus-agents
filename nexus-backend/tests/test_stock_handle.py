"""Routing tests for /agents/stock/handle.

The LLM classify call is stubbed (no network); per-action executors are
still stubs, so a valid action currently surfaces as 501.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _stub_classify(monkeypatch, action, ticker):
    async def fake(message: str) -> dict:
        return {"action": action, "ticker": ticker}

    monkeypatch.setattr("app.agents.stock.llm.classify", fake)


@pytest.mark.parametrize(
    "action, ticker",
    [("check", "AAPL"), ("add", "TSLA"), ("remove", "NVDA"), ("list", None)],
)
def test_valid_action_routes_to_executor(monkeypatch, action, ticker):
    _stub_classify(monkeypatch, action, ticker)
    resp = client.post("/agents/stock/handle", json={"message": "..."})
    assert resp.status_code == 501  # executor stubbed, but routing reached it


def test_unknown_action_returns_usage_text(monkeypatch):
    _stub_classify(monkeypatch, "unknown", None)
    resp = client.post("/agents/stock/handle", json={"message": "hello there"})
    assert resp.status_code == 200
    assert "check AAPL" in resp.json()["text"]


def test_missing_ticker_prompts_for_one(monkeypatch):
    _stub_classify(monkeypatch, "check", None)
    resp = client.post("/agents/stock/handle", json={"message": "what's the price"})
    assert resp.status_code == 200
    assert "ticker" in resp.json()["text"].lower()


def test_classify_parse_is_defensive_about_thinking_field():
    from app.llm import _parse

    # JOURNAL.md #10: JSON lands in `thinking`, `response` empty.
    out = _parse({"response": "", "thinking": '{"action": "check", "ticker": "aapl"}'})
    assert out == {"action": "check", "ticker": "AAPL"}

    # Garbage -> unknown, never raises.
    assert _parse({"response": "no json here"}) == {"action": "unknown", "ticker": None}
