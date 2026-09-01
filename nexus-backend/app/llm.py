"""LLM intent classification for the stock agent.

Port of the n8n HTTP Request (Ollama) node + Code (parse) node.

The exact prompt text is refined by the next ROADMAP item ("Port classify
prompt from n8n's HTTP Request node"); this module owns the request shape
and the defensive parse.

JOURNAL.md #10: local reasoning models (Qwen3) put JSON in `thinking` unless
`"think": false` is passed. We pass it *and* parse defensively.
"""

from __future__ import annotations

import json
import re

import httpx

from .config import get_settings

VALID_ACTIONS = {"check", "add", "remove", "list"}

# TODO(ROADMAP M1): replace with the exact prompt from the n8n node.
CLASSIFY_PROMPT = (
    "Classify this stock command into JSON only, no other text:\n"
    '{{"action": "check|list|add|remove", "ticker": "SYMBOL or null"}}.\n'
    "Message: {message}"
)


async def classify(message: str) -> dict:
    """Return {"action": <check|add|remove|list|unknown>, "ticker": <STR|None>}."""
    settings = get_settings()
    body = {
        "model": settings.llm_model,
        "prompt": CLASSIFY_PROMPT.format(message=message),
        "stream": False,
        "think": False,  # JOURNAL.md #10
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.llm_base_url}/api/generate", json=body)
        resp.raise_for_status()
        return _parse(resp.json())


def _parse(data: dict) -> dict:
    raw = (data.get("response") or "").strip() or (data.get("thinking") or "")
    match = re.search(r"\{[\s\S]*\}", raw)
    try:
        parsed = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, TypeError):
        return {"action": "unknown", "ticker": None}

    action = parsed.get("action")
    if action not in VALID_ACTIONS:
        action = "unknown"

    ticker = parsed.get("ticker")
    ticker = ticker.strip().upper() or None if isinstance(ticker, str) else None

    return {"action": action, "ticker": ticker}
