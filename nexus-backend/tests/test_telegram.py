"""Native Telegram gateway (ROADMAP M4, step 1): app/telegram.py.

Exercises authorisation, command/callback dispatch and the HTTP calls it
makes, against a fake client instead of the real Telegram API.
"""

import asyncio

import pytest

from app import dispatch, telegram


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = str(json_data)

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception(f"status {self.status_code}")


class FakeClient:
    def __init__(self):
        self.calls = []  # list of (method, url, kwargs)

    async def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return FakeResponse()

    async def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return FakeResponse(json_data={"result": []})

    async def aclose(self):
        pass


@pytest.fixture
def gateway():
    gw = telegram.TelegramGateway(token="TOKEN", owner_id=111)
    gw._client = FakeClient()
    return gw


def _private_chat(chat_id=1):
    return {"id": chat_id, "type": "private"}


def test_authorised_owner_private_chat(gateway):
    assert gateway._authorised(111, "private") is True


def test_rejects_non_owner(gateway):
    assert gateway._authorised(222, "private") is False


def test_rejects_group_chat_even_for_owner(gateway):
    assert gateway._authorised(111, "group") is False


def test_open_when_owner_unset():
    gw = telegram.TelegramGateway(token="TOKEN", owner_id=0)
    assert gw._authorised(999, "private") is True


def test_handle_message_dispatches_and_replies(monkeypatch, gateway):
    async def fake_process(message):
        assert message == "list"
        return "your watchlist is empty"

    monkeypatch.setattr(dispatch, "process_message", fake_process)
    asyncio.run(
        gateway._handle_message(
            {"chat": _private_chat(42), "from": {"id": 111}, "text": "list"}
        )
    )
    sends = [c for c in gateway._client.calls if c[1].endswith("/sendMessage")]
    assert len(sends) == 1
    assert sends[0][2]["json"]["chat_id"] == 42
    assert sends[0][2]["json"]["text"] == "your watchlist is empty"


def test_handle_message_rejects_a_stranger(monkeypatch, gateway):
    async def boom(message):
        raise AssertionError("process_message must not run for a rejected sender")

    monkeypatch.setattr(dispatch, "process_message", boom)
    asyncio.run(
        gateway._handle_message(
            {"chat": _private_chat(), "from": {"id": 999}, "text": "list"}
        )
    )
    assert gateway._client.calls == []


def test_handle_message_runs_registered_command(gateway):
    seen = []

    @gateway.command("start")
    async def start(chat_id, text):
        seen.append((chat_id, text))

    asyncio.run(
        gateway._handle_message(
            {"chat": _private_chat(7), "from": {"id": 111}, "text": "/start"}
        )
    )
    assert seen == [(7, "/start")]


def test_handle_callback_runs_registered_prefix_and_answers(gateway):
    seen = []

    @gateway.callback("confirm")
    async def on_confirm(chat_id, message_id, data):
        seen.append((chat_id, message_id, data))

    asyncio.run(
        gateway._handle_callback(
            {
                "id": "cbid1",
                "from": {"id": 111},
                "message": {"chat": _private_chat(5), "message_id": 9},
                "data": "confirm:3",
            }
        )
    )
    assert seen == [(5, 9, "confirm:3")]
    answers = [c for c in gateway._client.calls if c[1].endswith("/answerCallbackQuery")]
    assert len(answers) == 1
    assert answers[0][2]["json"]["callback_query_id"] == "cbid1"


def test_handle_callback_rejects_a_stranger_but_still_answers(gateway):
    seen = []

    @gateway.callback("confirm")
    async def on_confirm(chat_id, message_id, data):
        seen.append((chat_id, message_id, data))

    asyncio.run(
        gateway._handle_callback(
            {
                "id": "cbid2",
                "from": {"id": 999},
                "message": {"chat": _private_chat(), "message_id": 1},
                "data": "confirm:3",
            }
        )
    )
    assert seen == []
    answers = [c for c in gateway._client.calls if c[1].endswith("/answerCallbackQuery")]
    assert len(answers) == 1


def test_send_message_uses_html_parse_mode(gateway):
    asyncio.run(gateway.send_message(1, "<b>hi</b>"))
    call = gateway._client.calls[0]
    assert call[2]["json"] == {"chat_id": 1, "text": "<b>hi</b>", "parse_mode": "HTML"}


def test_delete_webhook_calls_the_right_method(gateway):
    asyncio.run(gateway._delete_webhook())
    assert gateway._client.calls[0][1] == telegram._API.format(
        token="TOKEN", method="deleteWebhook"
    )
