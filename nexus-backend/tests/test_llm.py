"""Classify prompt/parse port — checked against workflows/workflows.json."""

from app.llm import CLASSIFY_PROMPT, _parse


def test_prompt_matches_n8n_node_verbatim():
    rendered = CLASSIFY_PROMPT.format(message="what is AAPL trading at")
    assert rendered == (
        "Classify this stock command into JSON only, no other text: "
        '{"action": "check|list|add|remove", "ticker": "SYMBOL or null"}. '
        "Message: what is AAPL trading at"
    )


def test_parse_prefers_response_field():
    out = _parse({"response": '{"action": "add", "ticker": "tsla"}', "thinking": ""})
    assert out == {"action": "add", "ticker": "TSLA"}


def test_parse_falls_back_to_thinking_field():
    # JOURNAL.md #10
    out = _parse({"response": "  ", "thinking": '{"action": "list", "ticker": null}'})
    assert out == {"action": "list", "ticker": None}


def test_parse_extracts_json_from_surrounding_text():
    out = _parse({"response": 'sure: {"action": "check", "ticker": "NVDA"} done'})
    assert out == {"action": "check", "ticker": "NVDA"}


def test_parse_unknown_on_garbage():
    assert _parse({"response": "not json"}) == {"action": "unknown", "ticker": None}
    assert _parse({"response": '{"action": "buy", "ticker": 5}'}) == {
        "action": "unknown",
        "ticker": None,
    }
