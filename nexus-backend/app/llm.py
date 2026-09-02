"""Local LLM (Ollama) helpers.

`complete_json(prompt)` is the shared primitive used by every classifier
(stock command, top-level router, family sub-router): one `/api/generate`
call with `"think": false` (JOURNAL.md #10) and a defensive parse that
recovers JSON from the `thinking` field and from surrounding prose. Returns
a dict, or None if nothing parseable came back.

`classify(message)` is the stock command classifier, ported verbatim from
the n8n "HTTP Request" + "LLM Parser" nodes.
"""

from __future__ import annotations

import json
import re

import httpx

from .config import get_settings

VALID_ACTIONS = {"check", "add", "remove", "list"}

# Verbatim from the n8n "HTTP Request" node (single line, exact punctuation).
CLASSIFY_PROMPT = (
    "Classify this stock command into JSON only, no other text: "
    '{{"action": "check|list|add|remove", "ticker": "SYMBOL or null"}}. '
    "Message: {message}"
)


async def complete_json(prompt: str) -> dict | None:
    """Ask the local model for a JSON object. Returns the parsed dict or None."""
    settings = get_settings()
    body = {
        "model": settings.llm_model,
        "prompt": prompt,
        "stream": False,
        "think": False,  # JOURNAL.md #10
        "format": "json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{settings.llm_base_url}/api/generate", json=body)
        resp.raise_for_status()
        return _extract_json(resp.json())


def _extract_json(data: dict) -> dict | None:
    raw = (data.get("response") or "").strip() or (data.get("thinking") or "")
    match = re.search(r"\{[\s\S]*\}", raw or "")
    try:
        parsed = json.loads(match.group(0) if match else raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


async def classify(message: str) -> dict:
    """Stock command classifier.

    {"action": <check|add|remove|list|unknown>, "ticker": <STR|None>}
    """
    parsed = await complete_json(CLASSIFY_PROMPT.format(message=message)) or {}

    action = parsed.get("action")
    if action not in VALID_ACTIONS:
        action = "unknown"

    ticker = parsed.get("ticker")
    ticker = ticker.strip().upper() or None if isinstance(ticker, str) else None

    return {"action": action, "ticker": ticker}
