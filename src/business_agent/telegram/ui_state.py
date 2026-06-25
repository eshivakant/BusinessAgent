from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from typing import Protocol

from redis import Redis


@dataclass(frozen=True)
class TelegramUiPayload:
    compact_text: str
    detailed_text: str | None = None
    sources_text: str | None = None
    question_text: str | None = None


class TelegramUiStateStore(Protocol):
    def store(self, chat_id: int, payload: TelegramUiPayload) -> str:
        ...

    def load(self, chat_id: int, token: str) -> TelegramUiPayload | None:
        ...


class RedisTelegramUiStateStore:
    def __init__(self, redis_url: str, ttl_seconds: int) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._ttl_seconds = ttl_seconds

    def store(self, chat_id: int, payload: TelegramUiPayload) -> str:
        token = self._new_token()
        key = self._key(chat_id, token)
        self._redis.set(key, json.dumps(asdict(payload)), ex=self._ttl_seconds)
        return token

    def load(self, chat_id: int, token: str) -> TelegramUiPayload | None:
        key = self._key(chat_id, token)
        raw = self._redis.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return TelegramUiPayload(
                compact_text=str(data["compact_text"]),
                detailed_text=str(data["detailed_text"]) if data.get("detailed_text") else None,
                sources_text=str(data["sources_text"]) if data.get("sources_text") else None,
                question_text=str(data["question_text"]) if data.get("question_text") else None,
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def _key(self, chat_id: int, token: str) -> str:
        return f"telegram:ui:{chat_id}:{token}"

    def _new_token(self) -> str:
        return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:12]

