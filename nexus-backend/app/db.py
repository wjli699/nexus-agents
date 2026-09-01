"""asyncpg connection pool, created on app startup and reused per request.

Only the pool lifecycle lives here. Actual queries belong with the agent
logic that owns them (e.g. app/agents/stock.py), ported from the per-branch
Postgres nodes in the n8n workflow.
"""

from __future__ import annotations

import asyncpg

from .config import get_settings

_pool: asyncpg.Pool | None = None


async def connect() -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(get_settings().database_url)


async def disconnect() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call connect() on startup")
    return _pool
