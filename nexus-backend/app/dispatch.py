"""Shared message-dispatch logic: classify -> agent -> reply text.

Extracted from routers/root.py (M4) so the native Telegram gateway
(telegram.py) can call it in-process instead of looping back through its own
HTTP endpoint. `POST /handle` still exists for curl/tests and calls the same
function.
"""

from . import router as agent_router
from .agents import family as family_agent
from .agents import stock as stock_agent

UNKNOWN = (
    "I can help with stocks (prices, watchlist) or family (events, to-dos). "
    'Try "AAPL price" or "add task ...".'
)


async def process_message(message: str) -> str:
    agent = await agent_router.classify(message)
    if agent == "stock":
        return await stock_agent.handle(message)
    if agent == "family":
        return await family_agent.handle(message)
    return UNKNOWN
