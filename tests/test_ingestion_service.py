from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Sequence

from business_agent.ingestion.parser import ParsedDocument
from business_agent.ingestion.service import DocumentIngestionService
from business_agent.memory.models import MemoryRecord


class FakeMemoryStore:
    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []

    def upsert(self, records: Sequence[MemoryRecord]) -> None:
        self.records.extend(records)


class FakeSummarizer:
    def summarize(self, text: str) -> str:
        return f"summary::{text[:20]}"


def test_ingestion_service_writes_summary_and_chunks(monkeypatch) -> None:
    fake_memory = FakeMemoryStore()
    service = DocumentIngestionService(
        memory_store=fake_memory,
        summarizer=FakeSummarizer(),
        chunk_size=20,
        chunk_overlap=5,
        max_document_chars=1000,
        allowed_local_dir="/data/docs",
    )

    monkeypatch.setattr(
        "business_agent.ingestion.service.load_document_from_uri",
        lambda source_uri, allowed_local_dir: ParsedDocument(
            source_uri=source_uri,
            source_type="txt",
            text="This is sentence one. This is sentence two. This is sentence three.",
        ),
    )

    result = service.ingest_from_uri("/data/docs/report.txt", event_date=date(2026, 1, 15))

    assert result.source_type == "txt"
    assert result.chunk_count > 0
    assert result.records_written == result.chunk_count + 1

    summary_record = fake_memory.records[0]
    assert summary_record.payload.record_type == "summary"
    assert summary_record.payload.source_uri == "/data/docs/report.txt"
    assert summary_record.payload.event_date == date(2026, 1, 15)
    assert summary_record.payload.effective_date == datetime.combine(
        date(2026, 1, 15), time.min, tzinfo=timezone.utc
    )

    chunk_records = fake_memory.records[1:]
    assert all(record.payload.record_type == "chunk" for record in chunk_records)
    assert all(record.payload.summary.startswith("summary::") for record in chunk_records)


def test_ingestion_service_uses_ingested_at_when_event_date_missing(monkeypatch) -> None:
    fake_memory = FakeMemoryStore()
    service = DocumentIngestionService(
        memory_store=fake_memory,
        summarizer=FakeSummarizer(),
        chunk_size=50,
        chunk_overlap=10,
        max_document_chars=1000,
        allowed_local_dir="/data/docs",
    )

    monkeypatch.setattr(
        "business_agent.ingestion.service.load_document_from_uri",
        lambda source_uri, allowed_local_dir: ParsedDocument(
            source_uri=source_uri,
            source_type="txt",
            text="Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda.",
        ),
    )

    service.ingest_from_uri("/data/docs/missing-date.txt", event_date=None)

    for record in fake_memory.records:
        assert record.payload.event_date is None
        assert record.payload.effective_date == record.payload.ingested_at


def test_ingestion_service_applies_max_document_chars(monkeypatch) -> None:
    fake_memory = FakeMemoryStore()
    service = DocumentIngestionService(
        memory_store=fake_memory,
        summarizer=FakeSummarizer(),
        chunk_size=100,
        chunk_overlap=10,
        max_document_chars=25,
        allowed_local_dir="/data/docs",
    )

    monkeypatch.setattr(
        "business_agent.ingestion.service.load_document_from_uri",
        lambda source_uri, allowed_local_dir: ParsedDocument(
            source_uri=source_uri,
            source_type="txt",
            text="ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        ),
    )

    service.ingest_from_uri("/data/docs/trimmed.txt")
    chunk_records = [record for record in fake_memory.records if record.payload.record_type == "chunk"]
    assert len(chunk_records) == 1
    assert len(chunk_records[0].text) <= 25
