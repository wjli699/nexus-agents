"""Top-level router: which agent does this message belong to?

Local Ollama, one classification call. n8n calls this first (or the
top-level POST /handle does it), then dispatches to the chosen agent's
own handler, which does its own sub-classification.
"""

from __future__ import annotations

from . import llm

AGENTS = {"stock", "family"}

ROUTE_PROMPT = (
    "Route this message to one agent. Reply JSON only, no other text: "
    '{{"agent": "stock|family"}}.\n'
    "- stock: stock prices, tickers, watchlist, market moves, trading\n"
    "- family: household events, appointments, birthdays, dates, "
    "reminders, to-dos, chores\n"
    "Message: {message}"
)


async def classify(message: str) -> str:
    """Return an agent name from AGENTS, or 'unknown'."""
    parsed = await llm.complete_json(ROUTE_PROMPT.format(message=message)) or {}
    agent = parsed.get("agent")
    return agent if agent in AGENTS else "unknown"
