"""Tests for /agents/stock/heartbeat (ROADMAP M2).

DB via fake_pool; Alpha Vantage stubbed with a per-ticker quote map.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _quote(pct: str) -> dict:
    return {"01. symbol": "X", "05. price": "100", "10. change percent": pct}


def _stub_market(monkeypatch, quotes: dict[str, dict]):
    async def fake(ticker: str) -> dict:
        return quotes.get(ticker, {})

    monkeypatch.setattr("app.agents.stock.market.global_quote", fake)


def test_quiet_day_no_alert(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[{"ticker": "AAPL"}, {"ticker": "TSLA"}])
    _stub_market(monkeypatch, {"AAPL": _quote("0.8%"), "TSLA": _quote("-2.1%")})
    resp = client.post("/agents/stock/heartbeat", json={})
    assert resp.status_code == 200
    assert resp.json() == {"alert": False, "text": None}


def test_empty_watchlist_no_alert(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[])
    _stub_market(monkeypatch, {})
    assert client.post("/agents/stock/heartbeat", json={}).json()["alert"] is False


def test_single_mover(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[{"ticker": "AAPL"}, {"ticker": "TSLA"}])
    _stub_market(monkeypatch, {"AAPL": _quote("0.5%"), "TSLA": _quote("-6.2%")})
    body = client.post("/agents/stock/heartbeat", json={}).json()
    assert body["alert"] is True
    assert body["text"] == "TSLA down 6.2% today — biggest move on your watchlist."


def test_multiple_movers_sorted_by_magnitude(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[{"ticker": "AAPL"}, {"ticker": "NVDA"}, {"ticker": "TSLA"}])
    _stub_market(
        monkeypatch,
        {"AAPL": _quote("0.1%"), "NVDA": _quote("+5.4%"), "TSLA": _quote("-8.9%")},
    )
    body = client.post("/agents/stock/heartbeat", json={}).json()
    assert body["alert"] is True
    assert body["text"] == "Watchlist movers today:\nTSLA  -8.9%\nNVDA  +5.4%"


def test_threshold_override_in_body(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[{"ticker": "AAPL"}])
    _stub_market(monkeypatch, {"AAPL": _quote("3.0%")})
    assert client.post("/agents/stock/heartbeat", json={}).json()["alert"] is False
    body = client.post("/agents/stock/heartbeat", json={"threshold_pct": 2.5}).json()
    assert body["alert"] is True


def test_unfetchable_ticker_is_skipped_not_alerted(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[{"ticker": "AAPL"}, {"ticker": "ZZZZ"}])
    _stub_market(monkeypatch, {"AAPL": _quote("0.2%")})  # ZZZZ -> {}
    assert client.post("/agents/stock/heartbeat", json={}).json()["alert"] is False


def test_empty_body_allowed(monkeypatch, fake_pool):
    fake_pool(fetch_rows=[])
    _stub_market(monkeypatch, {})
    assert client.post("/agents/stock/heartbeat").status_code == 200
