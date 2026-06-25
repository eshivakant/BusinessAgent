from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any

from business_agent.worker.contracts import DocumentIngestionTask
from business_agent.worker.queue import RedisSubagentQueue


class FakeQueue:
    last_instance: "FakeQueue | None" = None

    def __init__(self, name: str, connection: object) -> None:
        self.name = name
        self.connection = connection
        self.enqueued: dict[str, Any] | None = None
        FakeQueue.last_instance = self

    def enqueue(self, *args: Any, **kwargs: Any) -> SimpleNamespace:
        self.enqueued = {"args": args, "kwargs": kwargs}
        return SimpleNamespace(id="job-xyz")


def test_worker_queue_enqueues_document_ingestion(monkeypatch) -> None:
    fake_connection = object()
    monkeypatch.setattr("business_agent.worker.queue.Redis.from_url", lambda _: fake_connection)
    monkeypatch.setattr("business_agent.worker.queue.Queue", FakeQueue)

    queue = RedisSubagentQueue(redis_url="redis://unused:6379/0", queue_name="business-agent")
    job_id = queue.enqueue_document_ingestion(
        DocumentIngestionTask(
            source_uri="/data/docs/report.pdf",
            event_date=date(2026, 1, 15),
            requester_id=99,
        )
    )

    assert job_id == "job-xyz"
    assert FakeQueue.last_instance is not None
    payload = FakeQueue.last_instance.enqueued["kwargs"]["kwargs"]
    assert payload["source_uri"] == "/data/docs/report.pdf"
    assert payload["event_date"] == "2026-01-15"
    assert payload["requester_id"] == 99
