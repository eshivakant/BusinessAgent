from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from business_agent.orchestrator.conversation import RedisConversationStore


class FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._lists: dict[str, list[str]] = defaultdict(list)
        self.expire_calls: list[tuple[str, int]] = []

    def rpush(self, key: str, value: str) -> None:
        self._lists[key].append(value)

    def ltrim(self, key: str, start: int, stop: int) -> None:
        values = self._lists[key]
        count = len(values)
        start_index = max(count + start, 0) if start < 0 else min(start, count)
        stop_index = count + stop if stop < 0 else stop
        stop_index = min(stop_index, count - 1)
        if stop_index < start_index:
            self._lists[key] = []
            return
        self._lists[key] = values[start_index : stop_index + 1]

    def expire(self, key: str, ttl_seconds: int) -> None:
        self.expire_calls.append((key, ttl_seconds))

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        del ex
        self._values[key] = value

    def lrange(self, key: str, start: int, stop: int) -> list[str]:
        values = self._lists.get(key, [])
        if stop == -1:
            stop = len(values) - 1
        return values[start : stop + 1]

    def delete(self, *keys: str) -> None:
        for key in keys:
            self._values.pop(key, None)
            self._lists.pop(key, None)


@pytest.fixture
def store(monkeypatch) -> RedisConversationStore:
    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "business_agent.orchestrator.conversation.Redis.from_url",
        lambda *args, **kwargs: fake_redis,
    )
    return RedisConversationStore(
        redis_url="redis://unused:6379/0",
        window_messages=3,
        summary_max_chars=120,
        context_max_chars=200,
        ttl_seconds=60,
    )


def test_append_turn_trims_to_window_and_updates_summary(store: RedisConversationStore) -> None:
    store.append_turn(1, "user", "first")
    store.append_turn(1, "assistant", "second")
    store.append_turn(1, "user", "third")
    store.append_turn(1, "assistant", "fourth")

    snapshot = store.get_snapshot(1)
    assert len(snapshot.recent_turns) == 3
    assert snapshot.recent_turns[0].text == "second"
    assert snapshot.recent_turns[-1].text == "fourth"
    assert "U: first" in snapshot.summary
    assert "A: fourth" in snapshot.summary


def test_build_query_includes_summary_and_recent_turns_with_budget(store: RedisConversationStore) -> None:
    store.append_turn(7, "user", "Need revenue trend for EMEA region.")
    store.append_turn(7, "assistant", "Checking existing sales notes.")
    store.append_turn(7, "user", "Compare this with last month.")

    query = store.build_query(chat_id=7, current_message="And what changed this week?", max_chars=170)

    assert query.startswith("Current message:")
    assert "Conversation summary:" in query
    assert "Recent turns:" in query
    assert len(query) <= 170


def test_clear_removes_summary_and_turns(store: RedisConversationStore) -> None:
    store.append_turn(9, "user", "hello")
    store.append_turn(9, "assistant", "hi")

    store.clear(9)
    snapshot = store.get_snapshot(9)
    assert snapshot.summary == ""
    assert snapshot.recent_turns == []


def test_append_turn_rejects_invalid_role(store: RedisConversationStore) -> None:
    with pytest.raises(ValueError, match="Unsupported conversation role"):
        store.append_turn(1, "system", "bad-role")  # type: ignore[arg-type]
