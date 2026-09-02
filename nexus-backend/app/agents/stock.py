"""Stock agent.

`handle()` is the single entry point n8n calls for commands
(api-spec-v0.1.md section 2): classify → route → per-action executor.

`heartbeat()` is the proactive path (api-spec-v0.1.md 1.6, ROADMAP M2):
scan the watchlist for big daily moves, deterministically. No LLM.
"""

from __future__ import annotations

from .. import db, llm, market
from ..config import get_settings

_USAGE = "Try: check AAPL / add AAPL / remove AAPL / list"


async def handle(message: str) -> str:
    intent = await llm.classify(message)
    action, ticker = intent["action"], intent["ticker"]

    if action in {"check", "add", "remove"} and not ticker:
        return f'Which ticker? e.g. "{action} AAPL"'

    if action == "check":
        return await check(ticker)
    if action == "add":
        return await add(ticker)
    if action == "remove":
        return await remove(ticker)
    if action == "list":
        return await list_()

    return f"Sorry, I didn't get that. {_USAGE}"


# --- per-action executors ---------------------------------------------------


async def check(ticker: str) -> str:
    # Port of "HTTP Request1" + "Code in JavaScript". Values are the raw
    # Alpha Vantage strings — no rounding, matching the n8n node.
    quote = await market.global_quote(ticker)
    if not quote:
        return "Couldn't find data for that ticker."
    return (
        f"{quote['01. symbol']}: ${quote['05. price']} "
        f"({quote['10. change percent']})"
    )


async def add(ticker: str) -> str:
    # Port of "Execute a SQL query" + "Add Responder". n8n used
    # UPPER('...') string interpolation; here it's a bound param + .upper().
    # ON CONFLICT DO NOTHING, and the reply is "Added" either way — same as
    # the n8n branch (the responder fires regardless of rows affected).
    ticker = ticker.upper()
    await db.get_pool().execute(
        "INSERT INTO watchlist (ticker) VALUES ($1) ON CONFLICT (ticker) DO NOTHING",
        ticker,
    )
    return f"Added {ticker} to your watchlist."


async def remove(ticker: str) -> str:
    # Port of "Execute a SQL query1" + "Remote Formatter". fetchval() returns
    # the RETURNING value or None — the clean equivalent of the n8n
    # `deleted[0]?.json?.ticker` optional-chaining fix (JOURNAL.md #3).
    ticker = ticker.upper()
    removed = await db.get_pool().fetchval(
        "DELETE FROM watchlist WHERE ticker = $1 RETURNING ticker", ticker
    )
    if removed:
        return f"Removed {removed} from your watchlist."
    return f"{ticker} wasn't on your watchlist."


async def list_() -> str:
    # Port of "Execute a SQL query2" + "List Formatter".
    rows = await db.get_pool().fetch("SELECT ticker FROM watchlist ORDER BY ticker")
    if not rows:
        return "Your watchlist is empty."
    return "Your watchlist:\n" + "\n".join(r["ticker"] for r in rows)


# --- heartbeat (ROADMAP Milestone 2) ---------------------------------------


async def heartbeat(threshold_pct: float | None = None) -> dict:
    """Scan the watchlist for big daily moves.

    Returns {"alert": False} on a normal day, or
    {"alert": True, "text": ...} when one or more tickers moved at least
    `threshold_pct` (abs). Detection and phrasing are both deterministic —
    the LLM is not involved. Tickers whose quote can't be fetched (unknown
    symbol, Alpha Vantage rate limit) are skipped, not treated as an alert.
    """
    threshold = (
        threshold_pct
        if threshold_pct is not None
        else get_settings().heartbeat_move_threshold_pct
    )

    rows = await db.get_pool().fetch("SELECT ticker FROM watchlist ORDER BY ticker")

    movers: list[tuple[str, float]] = []
    for row in rows:
        ticker = row["ticker"]
        quote = await market.global_quote(ticker)
        pct = _parse_pct(quote.get("10. change percent")) if quote else None
        if pct is not None and abs(pct) >= threshold:
            movers.append((ticker, pct))

    if not movers:
        return {"alert": False}

    movers.sort(key=lambda m: abs(m[1]), reverse=True)
    return {"alert": True, "text": _format_movers(movers)}


def _parse_pct(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.strip().rstrip("%"))
    except ValueError:
        return None


def _format_movers(movers: list[tuple[str, float]]) -> str:
    if len(movers) == 1:
        ticker, pct = movers[0]
        direction = "up" if pct > 0 else "down"
        return f"{ticker} {direction} {abs(pct):.1f}% today — biggest move on your watchlist."
    lines = "\n".join(f"{ticker}  {pct:+.1f}%" for ticker, pct in movers)
    return f"Watchlist movers today:\n{lines}"
