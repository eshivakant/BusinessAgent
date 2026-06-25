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

    async def download_file(self, file_id: str) -> bytes:
        """Download a file from Telegram (voice notes, documents, etc.)."""
        # Get file path from Telegram
        url = f"{self._api_base}/bot{self._token}/getFile"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json={"file_id": file_id})
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram getFile failed: {data}")
            file_path = data["result"]["file_path"]
            
            # Download the actual file
            download_url = f"https://api.telegram.org/file/bot{self._token}/{file_path}"
            file_response = await client.get(download_url)
            file_response.raise_for_status()
            return file_response.content

    async def send_document(
        self,
        chat_id: int,
        file_path: str,
        caption: str | None = None,
    ) -> None:
        """Send a document file to a chat."""
        if not self._token:
            return
        import httpx as _httpx
        from pathlib import Path
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        url = f"{self._api_base}/bot{self._token}/sendDocument"
        async with _httpx.AsyncClient(timeout=60.0) as client:
            with open(path, "rb") as f:
                files = {"document": (path.name, f)}
                data: dict[str, Any] = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption[:1024]
                response = await client.post(url, files=files, data=data)
                response.raise_for_status()
