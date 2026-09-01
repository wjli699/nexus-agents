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


@pytest.mark.parametrize("action, ticker", [("remove", "NVDA"), ("list", None)])
def test_unported_action_routes_to_stub(monkeypatch, action, ticker):
    _stub_classify(monkeypatch, action, ticker)
    resp = client.post("/agents/stock/handle", json={"message": "..."})
    assert resp.status_code == 501  # executor stubbed, but routing reached it


def test_add_inserts_uppercased_and_confirms(monkeypatch, fake_pool):
    _stub_classify(monkeypatch, "add", "tsla")
    pool = fake_pool()
    resp = client.post("/agents/stock/handle", json={"message": "watch tsla"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "Added TSLA to your watchlist."
    method, query, args = pool.calls[0]
    assert method == "execute" and args == ("TSLA",)
    assert "ON CONFLICT (ticker) DO NOTHING" in query
    assert "'" not in query.split("VALUES")[1]  # bound param, not interpolated


def test_check_returns_formatted_quote(monkeypatch):
    _stub_classify(monkeypatch, "check", "AAPL")

    async def fake_quote(ticker: str) -> dict:
        return {
            "01. symbol": "AAPL",
            "05. price": "227.1400",
            "10. change percent": "0.7965%",
        }

    monkeypatch.setattr("app.agents.stock.market.global_quote", fake_quote)
    resp = client.post("/agents/stock/handle", json={"message": "price of AAPL"})
    assert resp.status_code == 200
    assert resp.json()["text"] == "AAPL: $227.1400 (0.7965%)"


def test_check_unknown_ticker(monkeypatch):
    _stub_classify(monkeypatch, "check", "ZZZZ")

    async def fake_quote(ticker: str) -> dict:
        return {}

    monkeypatch.setattr("app.agents.stock.market.global_quote", fake_quote)
    resp = client.post("/agents/stock/handle", json={"message": "price of ZZZZ"})
    assert resp.json()["text"] == "Couldn't find data for that ticker."


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
