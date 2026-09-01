"""Stock agent: classify + route + execute.

`handle()` is the single entry point n8n calls (api-spec-v0.1.md section 2).
It classifies the message, routes on the action, and dispatches to a
per-action executor.

The executors below are stubs — the next ROADMAP items port each one from
its n8n branch (Alpha Vantage node, Postgres INSERT/DELETE/SELECT nodes).
Routing, validation, and the unknown-command fallback are done here.
"""

from __future__ import annotations

from .. import llm, market

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


# --- per-action executors (stubs; ported by later ROADMAP M1 items) ---------


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
    raise NotImplementedError  # ROADMAP M1: port `add` (Postgres INSERT)


async def remove(ticker: str) -> str:
    raise NotImplementedError  # ROADMAP M1: port `remove` (Postgres DELETE...RETURNING)


async def list_() -> str:
    raise NotImplementedError  # ROADMAP M1: port `list` (Postgres SELECT)
