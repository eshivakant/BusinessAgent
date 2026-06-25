from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from redis import Redis

TurnRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ChatTurn:
    role: TurnRole
    text: str
    timestamp: datetime


@dataclass(frozen=True)
class ConversationSnapshot:
    summary: str
    recent_turns: list[ChatTurn]


class ConversationStore(Protocol):
    def append_turn(self, chat_id: int, role: TurnRole, text: str) -> None:
        ...

    def get_snapshot(self, chat_id: int) -> ConversationSnapshot:
        ...

    def build_query(self, chat_id: int, current_message: str, max_chars: int) -> str:
        ...

    def clear(self, chat_id: int) -> None:
        ...


class RedisConversationStore:
    def __init__(
        self,
        redis_url: str,
        window_messages: int,
        summary_max_chars: int,
        context_max_chars: int,
        ttl_seconds: int,
    ) -> None:
        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._window_messages = window_messages
        self._summary_max_chars = summary_max_chars
        self._context_max_chars = context_max_chars
        self._ttl_seconds = ttl_seconds

    def append_turn(self, chat_id: int, role: TurnRole, text: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported conversation role: {role}")
        normalized = self._normalize_text(text)
        if not normalized:
            return

        payload = json.dumps(
            {
                "role": role,
                "text": normalized,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        turns_key = self._turns_key(chat_id)
        self._redis.rpush(turns_key, payload)
        self._redis.ltrim(turns_key, -self._window_messages, -1)
        self._redis.expire(turns_key, self._ttl_seconds)

        self._update_summary(chat_id=chat_id, role=role, text=normalized)

    def get_snapshot(self, chat_id: int) -> ConversationSnapshot:
        summary_key = self._summary_key(chat_id)
        turns_key = self._turns_key(chat_id)
        summary = self._redis.get(summary_key) or ""
        raw_turns = self._redis.lrange(turns_key, 0, -1)

        turns: list[ChatTurn] = []
        for raw_entry in raw_turns:
            try:
                item = json.loads(raw_entry)
                timestamp = datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00"))
                role = str(item["role"])
                if role not in {"user", "assistant"}:
                    continue
                turns.append(
                    ChatTurn(
                        role=role,
                        text=str(item["text"]),
                        timestamp=timestamp,
                    )
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

        return ConversationSnapshot(summary=summary, recent_turns=turns)

    def build_query(self, chat_id: int, current_message: str, max_chars: int) -> str:
        normalized_current = self._normalize_text(current_message)
        if not normalized_current:
            raise ValueError("current_message must not be empty")

        budget = max(32, min(max_chars, self._context_max_chars))
        snapshot = self.get_snapshot(chat_id)
        current_block = f"Current message: {normalized_current}"
        if len(current_block) >= budget:
            return self._truncate_head(current_block, budget)

        parts = [current_block]
        remaining = budget - len(current_block)

        if snapshot.summary and remaining > 32:
            reserve_for_recent = 40 if snapshot.recent_turns else 0
            summary_header = "\n\nConversation summary: "
            summary_budget = remaining - reserve_for_recent - len(summary_header)
            if summary_budget > 0:
                summary_text = self._truncate(snapshot.summary, min(summary_budget, self._summary_max_chars))
                summary_block = f"{summary_header}{summary_text}"
                parts.append(summary_block)
                remaining -= len(summary_block)

        if snapshot.recent_turns and remaining > 18:
            recent_header = "\n\nRecent turns:"
            if len(recent_header) < remaining:
                parts.append(recent_header)
                remaining -= len(recent_header)
                lines: list[str] = []
                for turn in reversed(snapshot.recent_turns):
                    line = self._truncate_head(f"{turn.role}: {turn.text}", 120)
                    required = len(line) + 1
                    if required > remaining:
                        if not lines and remaining > 2:
                            lines.append(self._truncate_head(line, remaining - 1))
                        break
                    lines.append(line)
                    remaining -= required
                    if remaining <= 1:
                        break
                if lines:
                    parts.append("\n" + "\n".join(reversed(lines)))

        combined = "".join(parts)
        return self._truncate_head(combined, budget)

    def clear(self, chat_id: int) -> None:
        self._redis.delete(self._summary_key(chat_id), self._turns_key(chat_id))

    def _update_summary(self, chat_id: int, role: TurnRole, text: str) -> None:
        summary_key = self._summary_key(chat_id)
        prefix = "U" if role == "user" else "A"
        line = f"{prefix}: {self._truncate(text, 220)}"
        existing = self._redis.get(summary_key) or ""
        updated = f"{existing}\n{line}".strip()
        updated = self._truncate(updated, self._summary_max_chars)
        self._redis.set(summary_key, updated, ex=self._ttl_seconds)

    def _summary_key(self, chat_id: int) -> str:
        return f"chat:{chat_id}:summary"

    def _turns_key(self, chat_id: int) -> str:
        return f"chat:{chat_id}:turns"

    def _normalize_text(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _truncate(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def _truncate_head(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[:max_chars]
