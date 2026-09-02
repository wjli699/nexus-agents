"""Shared test helpers.

`fake_pool` stands in for the asyncpg pool so DB-backed code can be
unit-tested without Postgres. It patches `app.db.get_pool` globally, so it
covers every module that calls `db.get_pool()` (stock, tasks, family, ...).
"""

import pytest


class FakePool:
    def __init__(
        self,
        *,
        fetch_rows=None,
        fetchval=None,
        fetchval_queue=None,
        delete_returns=None,  # back-compat alias for fetchval
    ):
        self._fetch_rows = fetch_rows or []
        self._fetchval_queue = list(fetchval_queue) if fetchval_queue is not None else None
        self._fetchval = fetchval if fetchval is not None else delete_returns
        self.calls = []  # list of (method, query, args)

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "EXECUTE"

    async def fetch(self, query, *args):
        self.calls.append(("fetch", query, args))
        return list(self._fetch_rows)

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if self._fetchval_queue is not None:
            return self._fetchval_queue.pop(0) if self._fetchval_queue else None
        return self._fetchval


@pytest.fixture
def fake_pool(monkeypatch):
    def _install(**kwargs):
        pool = FakePool(**kwargs)
        monkeypatch.setattr("app.db.get_pool", lambda: pool)
        return pool

    return _install
