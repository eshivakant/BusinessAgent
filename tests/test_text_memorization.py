"""Tests for the text memorization service."""
from __future__ import annotations

from datetime import datetime, timezone

from business_agent.memory.models import MemoryRecord
from business_agent.memory.text_memorization import TextMemorizationService


class FakeMemoryStore:
    """In-memory fake for MemoryStore."""

    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []

    def upsert(self, records: list[MemoryRecord]) -> None:
        self.records.extend(records)

    def query(self, request):  # type: ignore[no-untyped-def]
        return []


class TestMemorizeText:
    def test_memorize_text_returns_record_id(self):
        service = TextMemorizationService(memory_store=FakeMemoryStore())
        record_id = service.memorize_text(text="Hello world", chat_id=123)
        assert record_id is not None
        assert record_id.startswith("memo-")

    def test_memorize_text_stores_in_memory(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Important note", chat_id=456)
        assert len(store.records) == 1
        assert store.records[0].text == "Important note"

    def test_memorize_text_sets_source_type(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Test", chat_id=1, source_type="note")
        assert store.records[0].payload.source_type == "note"

    def test_memorize_text_default_source_type(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Test", chat_id=1)
        assert store.records[0].payload.source_type == "text_message"

    def test_memorize_text_sets_source_uri_with_chat_id(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Test", chat_id=123)
        assert "123" in store.records[0].payload.source_uri
        assert "telegram" in store.records[0].payload.source_uri

    def test_memorize_text_sets_source_uri_without_chat_id(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Test", chat_id=None)
        assert store.records[0].payload.source_uri == "text://message"

    def test_memorize_text_sets_ingested_at(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        before = datetime.now(timezone.utc)
        service.memorize_text(text="Test", chat_id=1)
        after = datetime.now(timezone.utc)
        record = store.records[0]
        assert before <= record.payload.ingested_at <= after

    def test_memorize_text_sets_record_type(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Test", chat_id=1)
        assert store.records[0].payload.record_type == "memorized_text"

    def test_memorize_text_long_text_truncates_summary(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        long_text = "A" * 500
        service.memorize_text(text=long_text, chat_id=1)
        assert len(store.records[0].payload.summary) <= 200

    def test_memorize_text_short_text_full_summary(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_text(text="Short note", chat_id=1)
        assert store.records[0].payload.summary == "Short note"


class TestMemorizeVoiceTranscription:
    def test_voice_transcription_returns_record_id(self):
        service = TextMemorizationService(memory_store=FakeMemoryStore())
        record_id = service.memorize_voice_transcription(
            transcription="Hello from voice", audio_file_id="file123", chat_id=789
        )
        assert record_id is not None
        assert record_id.startswith("memo-")

    def test_voice_transcription_stores_text(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_voice_transcription(
            transcription="Voice message content", audio_file_id="file456", chat_id=111
        )
        assert len(store.records) == 1
        assert store.records[0].text == "Voice message content"

    def test_voice_transcription_sets_source_type(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_voice_transcription(
            transcription="Test", audio_file_id="f1", chat_id=1
        )
        assert store.records[0].payload.source_type == "voice_note"

    def test_voice_transcription_without_file_id(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_voice_transcription(
            transcription="Test", audio_file_id=None, chat_id=1
        )
        assert len(store.records) == 1
        assert store.records[0].payload.source_type == "voice_note"

    def test_voice_transcription_sets_record_type(self):
        store = FakeMemoryStore()
        service = TextMemorizationService(memory_store=store)
        service.memorize_voice_transcription(
            transcription="Test", audio_file_id="f1", chat_id=1
        )
        assert store.records[0].payload.record_type == "memorized_text"
