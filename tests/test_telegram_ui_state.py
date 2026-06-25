from __future__ import annotations

from collections import defaultdict

from business_agent.telegram.ui_state import RedisTelegramUiStateStore, TelegramUiPayload


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expires: dict[str, int] = {}
        self.lists = defaultdict(list)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expires[key] = ex

    def get(self, key: str) -> str | None:
        return self.values.get(key)


def test_ui_state_store_roundtrip(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "business_agent.telegram.ui_state.Redis.from_url",
        lambda *args, **kwargs: fake_redis,
    )
    store = RedisTelegramUiStateStore(redis_url="redis://unused:6379/0", ttl_seconds=180)
    payload = TelegramUiPayload(
        compact_text="compact",
        detailed_text="details",
        sources_text="sources",
        question_text="question",
    )

    token = store.store(chat_id=7, payload=payload)
    loaded = store.load(chat_id=7, token=token)

    assert loaded is not None
    assert loaded.compact_text == "compact"
    assert loaded.detailed_text == "details"
    assert loaded.sources_text == "sources"
    assert loaded.question_text == "question"


def test_ui_state_store_returns_none_for_unknown_token(monkeypatch) -> None:
    fake_redis = FakeRedis()
    monkeypatch.setattr(
        "business_agent.telegram.ui_state.Redis.from_url",
        lambda *args, **kwargs: fake_redis,
    )
    store = RedisTelegramUiStateStore(redis_url="redis://unused:6379/0", ttl_seconds=180)
    assert store.load(chat_id=1, token="missing") is None
