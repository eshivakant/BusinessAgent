from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from business_agent.telegram.client import TelegramBotClient


def test_send_message_skips_http_when_token_missing(monkeypatch) -> None:
    called = {"value": False}

    class ShouldNotBeCalled:
        def __init__(self, **_: Any) -> None:
            called["value"] = True

    monkeypatch.setattr("business_agent.telegram.client.httpx.AsyncClient", ShouldNotBeCalled)
    client = TelegramBotClient(token="")
    asyncio.run(client.send_message(chat_id=123, text="hello"))
    assert called["value"] is False


def test_send_message_shapes_request_and_truncates_text(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("business_agent.telegram.client.httpx.AsyncClient", FakeAsyncClient)

    long_text = "x" * 4500
    client = TelegramBotClient(token="bot-token", api_base="https://api.telegram.org/")
    asyncio.run(client.send_message(chat_id=555, text=long_text, reply_markup={"inline_keyboard": []}))

    assert captured["timeout"] == 15.0
    assert captured["url"] == "https://api.telegram.org/botbot-token/sendMessage"
    assert captured["json"]["chat_id"] == 555
    assert len(captured["json"]["text"]) == 4000
    assert captured["json"]["reply_markup"] == {"inline_keyboard": []}


def test_send_message_propagates_http_error(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            request = httpx.Request("POST", "https://api.telegram.org/fail")
            response = httpx.Response(status_code=500, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            del timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
            del url, json
            return FakeResponse()

    monkeypatch.setattr("business_agent.telegram.client.httpx.AsyncClient", FakeAsyncClient)
    client = TelegramBotClient(token="bot-token")

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(client.send_message(chat_id=1, text="hello"))


def test_edit_message_text_calls_correct_telegram_method(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            del timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("business_agent.telegram.client.httpx.AsyncClient", FakeAsyncClient)
    client = TelegramBotClient(token="token")
    asyncio.run(
        client.edit_message_text(
            chat_id=5,
            message_id=12,
            text="updated text",
            reply_markup={"inline_keyboard": [[{"text": "A", "callback_data": "x"}]]},
        )
    )

    assert captured["url"].endswith("/editMessageText")
    assert captured["json"]["chat_id"] == 5
    assert captured["json"]["message_id"] == 12


def test_answer_callback_query_calls_correct_method(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            del timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            del exc_type, exc, tb

        async def post(self, url: str, json: dict[str, Any]) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("business_agent.telegram.client.httpx.AsyncClient", FakeAsyncClient)
    client = TelegramBotClient(token="token")
    asyncio.run(client.answer_callback_query(callback_query_id="abc", text="done"))

    assert captured["url"].endswith("/answerCallbackQuery")
    assert captured["json"]["callback_query_id"] == "abc"
