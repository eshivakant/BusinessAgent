from __future__ import annotations

import httpx
from typing import Any


class TelegramBotClient:
    def __init__(self, token: str, api_base: str = "https://api.telegram.org") -> None:
        self._token = token
        self._api_base = api_base.rstrip("/")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        if not self._token:
            return
        payload = {
            "chat_id": chat_id,
            "text": text[:4000],
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._post("sendMessage", payload)

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        if not self._token:
            return
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text[:4000],
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        await self._post("editMessageText", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        if not self._token:
            return
        payload: dict[str, Any] = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }
        if text:
            payload["text"] = text[:200]
        await self._post("answerCallbackQuery", payload)

    async def _post(self, method: str, payload: dict[str, Any]) -> None:
        url = f"{self._api_base}/bot{self._token}/{method}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
