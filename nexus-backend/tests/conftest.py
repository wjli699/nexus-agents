"""Shared test helpers.

`fake_pool` stands in for the asyncpg pool so DB-backed executors can be
unit-tested without Postgres. Integration against a real DB is the
"side-by-side test" ROADMAP M1 item.
"""

import pytest


class FakePool:
    def __init__(self, *, fetch_rows=None, delete_returns=None):
        self._fetch_rows = fetch_rows or []
        self._delete_returns = delete_returns
        self.calls = []  # list of (method, query, args)

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return list(self._fetch_rows)

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        return self._delete_returns


@pytest.fixture
def fake_pool(monkeypatch):
    def _install(**kwargs):
        pool = FakePool(**kwargs)
        monkeypatch.setattr("app.agents.stock.db.get_pool", lambda: pool)
        return pool

    return _install
