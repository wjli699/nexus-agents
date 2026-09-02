"""llm.py — JSON extraction + the stock command classifier."""

import asyncio

import pytest

from app import llm
from app.llm import CLASSIFY_PROMPT, _extract_json


def test_prompt_matches_n8n_node_verbatim():
    rendered = CLASSIFY_PROMPT.format(message="what is AAPL trading at")
    assert rendered == (
        "Classify this stock command into JSON only, no other text: "
        '{"action": "check|list|add|remove", "ticker": "SYMBOL or null"}. '
        "Message: what is AAPL trading at"
    )


def test_extract_prefers_response_over_thinking():
    assert _extract_json({"response": '{"a": 1}', "thinking": '{"a": 2}'}) == {"a": 1}


def test_extract_falls_back_to_thinking_field():
    # JOURNAL.md #10
    assert _extract_json({"response": "  ", "thinking": '{"a": 2}'}) == {"a": 2}


def test_extract_from_surrounding_prose():
    assert _extract_json({"response": 'sure: {"x": "y"} done'}) == {"x": "y"}


def test_extract_none_on_garbage_or_non_object():
    assert _extract_json({"response": "not json"}) is None
    assert _extract_json({"response": "[1, 2, 3]"}) is None
    assert _extract_json({"response": ""}) is None


@pytest.mark.parametrize(
    "parsed, expected",
    [
        ({"action": "add", "ticker": "tsla"}, {"action": "add", "ticker": "TSLA"}),
        ({"action": "list", "ticker": None}, {"action": "list", "ticker": None}),
        ({"action": "buy", "ticker": 5}, {"action": "unknown", "ticker": None}),
        ({}, {"action": "unknown", "ticker": None}),
        (None, {"action": "unknown", "ticker": None}),
    ],
)
def test_classify_normalizes(monkeypatch, parsed, expected):
    async def fake(prompt):
        return parsed

    monkeypatch.setattr(llm, "complete_json", fake)
    assert asyncio.run(llm.classify("whatever")) == expected
