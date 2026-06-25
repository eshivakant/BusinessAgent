from __future__ import annotations

from datetime import date

import pytest

from business_agent.ingestion.service import IngestionResult
from business_agent.worker import tasks


class FakeMemoryStore:
    def __init__(self) -> None:
        self.ensure_collection_called = False

    def ensure_collection(self) -> None:
        self.ensure_collection_called = True


class FakeIngestionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def ingest_from_uri(
        self,
        source_uri: str,
        event_date: date | None = None,
        requester_id: int | None = None,
    ) -> IngestionResult:
        self.calls.append(
            {
                "source_uri": source_uri,
                "event_date": event_date,
                "requester_id": requester_id,
            }
        )
        return IngestionResult(
            document_id="doc-1",
            source_uri=source_uri,
            source_type="txt",
            summary_id="doc-1:summary",
            chunk_count=1,
            records_written=2,
        )


def test_worker_task_executes_ingestion(monkeypatch) -> None:
    fake_memory = FakeMemoryStore()
    fake_ingestion = FakeIngestionService()
    monkeypatch.setattr(tasks, "get_memory_store", lambda: fake_memory)
    monkeypatch.setattr(tasks, "get_ingestion_service", lambda: fake_ingestion)

    output = tasks.ingest_document_task(
        source_uri="/data/docs/report.txt",
        event_date="2026-01-15",
        requester_id=42,
    )

    assert fake_memory.ensure_collection_called is True
    assert fake_ingestion.calls[0]["event_date"] == date(2026, 1, 15)
    assert output["document_id"] == "doc-1"
    assert output["source_uri"] == "/data/docs/report.txt"


def test_worker_task_rejects_invalid_date(monkeypatch) -> None:
    monkeypatch.setattr(tasks, "get_memory_store", lambda: FakeMemoryStore())
    monkeypatch.setattr(tasks, "get_ingestion_service", lambda: FakeIngestionService())

    with pytest.raises(ValueError):
        tasks.ingest_document_task(source_uri="/data/docs/report.txt", event_date="invalid-date")
