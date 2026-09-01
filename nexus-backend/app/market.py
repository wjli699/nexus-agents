"""Alpha Vantage market data.

Port of the "HTTP Request1" node (GLOBAL_QUOTE lookup) from
workflows/workflows.json. Formatting lives with the caller (agents/stock.py),
same split as the n8n node + its Code node.
"""

from __future__ import annotations

import httpx

from .config import get_settings

_QUOTE_URL = "https://www.alphavantage.co/query"


async def global_quote(ticker: str) -> dict:
    """Return the "Global Quote" object, or {} when there's no data.

    An unknown ticker and a rate-limit response both come back without a
    populated "Global Quote" — the n8n node treated both as "not found".
    """
    settings = get_settings()
    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker.upper(),
        "apikey": settings.alpha_vantage_api_key,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(_QUOTE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    return data.get("Global Quote") or {}
