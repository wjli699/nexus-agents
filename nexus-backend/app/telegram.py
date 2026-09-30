"""Native Telegram gateway (ROADMAP M4, step 1).

Replaces n8n's Telegram Trigger -> HTTP Request -> Telegram nodes
(workflows/agent-slim.json) with an in-process async long-poller that calls
`dispatch.process_message` directly — no HTTP round-trip to our own /handle.

Authorisation happens here, at the update layer, not by delegating to
routers/root.py's `_check_owner`: unlike an HTTP caller, a Telegram update
we don't own should never even get a reply, so private-chat + owner-id are
checked before any agent logic runs (same fail-closed policy as `/handle`,
applied one layer up). Only the sender id is ever logged, never message text.

Command and callback registries are here as reusable infrastructure; no
command or inline-keyboard flow uses them yet (ROADMAP M4's "move family's
confirm N / skip N onto buttons" is explicitly optional/later).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

import httpx

from . import dispatch

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"
_POLL_TIMEOUT = 30  # seconds; Telegram long-poll wait
_RETRY_DELAY = 5  # seconds; backoff after a getUpdates network error

CommandHandler = Callable[[int, str], Awaitable[None]]
# (chat_id, message_id, callback_data) -> None
CallbackHandler = Callable[[int, Optional[int], str], Awaitable[None]]


class TelegramGateway:
    def __init__(self, token: str, owner_id: int):
        self._token = token
        self._owner_id = owner_id
        self._client = httpx.AsyncClient(timeout=_POLL_TIMEOUT + 10)
        self._offset: Optional[int] = None
        self._commands: dict[str, CommandHandler] = {}
        self._callbacks: dict[str, CallbackHandler] = {}

    def command(self, name: str) -> Callable[[CommandHandler], CommandHandler]:
        def deco(fn: CommandHandler) -> CommandHandler:
            self._commands[name] = fn
            return fn

        return deco

    def callback(self, prefix: str) -> Callable[[CallbackHandler], CallbackHandler]:
        def deco(fn: CallbackHandler) -> CallbackHandler:
            self._callbacks[prefix] = fn
            return fn

        return deco

    def _url(self, method: str) -> str:
        return _API.format(token=self._token, method=method)

    async def send_message(
        self, chat_id: int, text: str, reply_markup: Optional[dict] = None
    ) -> None:
        payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = await self._client.post(self._url("sendMessage"), json=payload)
        if resp.status_code != 200:
            log.warning("sendMessage failed: %s %s", resp.status_code, resp.text)

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[dict] = None,
    ) -> None:
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = await self._client.post(self._url("editMessageText"), json=payload)
        if resp.status_code != 200:
            log.warning("editMessageText failed: %s %s", resp.status_code, resp.text)

    async def answer_callback(self, callback_query_id: str, text: Optional[str] = None) -> None:
        payload: dict = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        await self._client.post(self._url("answerCallbackQuery"), json=payload)

    async def _delete_webhook(self) -> None:
        # Cutover gotcha (ROADMAP M4): a bot token has exactly one consumer —
        # getUpdates 409s forever if n8n's Telegram Trigger webhook is still
        # registered. Idempotent, safe to call even if no webhook is set.
        resp = await self._client.post(self._url("deleteWebhook"))
        if resp.status_code != 200:
            log.warning("deleteWebhook failed: %s %s", resp.status_code, resp.text)

    async def _get_updates(self) -> list[dict]:
        params: dict = {
            "timeout": _POLL_TIMEOUT,
            "allowed_updates": ["message", "callback_query"],
        }
        if self._offset is not None:
            params["offset"] = self._offset
        resp = await self._client.get(self._url("getUpdates"), params=params)
        resp.raise_for_status()
        return resp.json().get("result", [])

    def _authorised(self, user_id: Optional[int], chat_type: Optional[str]) -> bool:
        if chat_type != "private":
            return False
        if not self._owner_id:
            return True
        return user_id == self._owner_id

    async def _handle_message(self, message: dict) -> None:
        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        user_id = sender.get("id")
        if not self._authorised(user_id, chat.get("type")):
            log.warning("rejected telegram message from user %s", user_id)
            return
        text = message.get("text")
        if not text:
            return
        chat_id = chat["id"]
        command = text.split()[0].lstrip("/").split("@")[0] if text.startswith("/") else None
        handler = self._commands.get(command) if command else None
        if handler:
            await handler(chat_id, text)
            return
        reply = await dispatch.process_message(text)
        await self.send_message(chat_id, reply)

    async def _handle_callback(self, callback_query: dict) -> None:
        sender = callback_query.get("from") or {}
        user_id = sender.get("id")
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        if not self._authorised(user_id, chat.get("type")):
            log.warning("rejected telegram callback from user %s", user_id)
            await self.answer_callback(callback_query["id"])
            return
        data = callback_query.get("data") or ""
        handler = self._callbacks.get(data.split(":")[0])
        if handler:
            await handler(chat.get("id"), message.get("message_id"), data)
        await self.answer_callback(callback_query["id"])

    async def run(self) -> None:
        await self._delete_webhook()
        log.info("telegram gateway: long-polling started")
        while True:
            try:
                updates = await self._get_updates()
            except asyncio.CancelledError:
                raise
            except httpx.HTTPError:
                log.warning("getUpdates failed, retrying in %ss", _RETRY_DELAY, exc_info=True)
                await asyncio.sleep(_RETRY_DELAY)
                continue
            for update in updates:
                self._offset = update["update_id"] + 1
                try:
                    if "message" in update:
                        await self._handle_message(update["message"])
                    elif "callback_query" in update:
                        await self._handle_callback(update["callback_query"])
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("error handling telegram update %s", update.get("update_id"))

    async def aclose(self) -> None:
        await self._client.aclose()
