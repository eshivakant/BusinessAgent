from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from business_agent.ingestion.service import IngestionResult
from business_agent.memory.models import MemoryMatch, MemoryPayload, MemoryQueryInput
from business_agent.orchestrator.service import BusinessOrchestrator
from business_agent.worker.contracts import DocumentIngestionTask


class FakeMemoryStore:
    def __init__(self, matches: list[MemoryMatch]) -> None:
        self.matches = matches
        self.last_query: MemoryQueryInput | None = None

    def query(self, request: MemoryQueryInput) -> list[MemoryMatch]:
        self.last_query = request
        return self.matches


class FakeTaskQueue:
    def __init__(self) -> None:
        self.tasks: list[DocumentIngestionTask] = []

    def enqueue_document_ingestion(self, task: DocumentIngestionTask) -> str:
        self.tasks.append(task)
        return "job-123"


class FakeIngestionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
            chunk_count=2,
            records_written=3,
        )


class FakeSQLReader:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.last_request: Any = None

    def fetch_rows(self, request: Any) -> list[dict[str, Any]]:
        self.last_request = request
        return self.rows


class FakeConversationStore:
    def __init__(self) -> None:
        self.turns: list[tuple[int, str, str]] = []
        self.query_inputs: list[tuple[int, str, int]] = []
        self.cleared_chat_ids: list[int] = []

    def append_turn(self, chat_id: int, role: str, text: str) -> None:
        self.turns.append((chat_id, role, text))

    def build_query(self, chat_id: int, current_message: str, max_chars: int) -> str:
        self.query_inputs.append((chat_id, current_message, max_chars))
        return f"context::{current_message}"

    def clear(self, chat_id: int) -> None:
        self.cleared_chat_ids.append(chat_id)


def _build_match() -> MemoryMatch:
    payload = MemoryPayload(
        event_date=date(2026, 1, 15),
        ingested_at=datetime(2026, 1, 16, 12, 0, tzinfo=timezone.utc),
        effective_date=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
        source_type="pdf",
        source_uri="file:///data/docs/q1-report.pdf",
        record_type="chunk",
        chunk_index=0,
        chunk_count=2,
        summary="Q1 summary",
    )
    return MemoryMatch(
        id="doc-1",
        score=0.9,
        text="Revenue grew by 12 percent in Q1.",
        payload=payload,
    )


def test_orchestrator_handles_ingest_command() -> None:
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        sql_reader=None,
    )
    response = orchestrator.handle_telegram_message(
        chat_id=1,
        message_text="/ingest /data/docs/report.txt event_date=2026-01-15",
    )

    assert "Ingestion started." in response
    assert "job_id: job-123" in response


def test_orchestrator_handles_ask_command() -> None:
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([_build_match()]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        sql_reader=None,
    )
    response = orchestrator.handle_telegram_message(
        chat_id=1,
        message_text="/ask revenue growth",
    )

    assert "Best answer:" in response
    assert "file:///data/docs/q1-report.pdf" in response


def test_orchestrator_handles_data_command_with_sql_reader() -> None:
    sql_reader = FakeSQLReader(rows=[{"id": 1, "status": "paid"}])
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        sql_reader=sql_reader,
    )
    response = orchestrator.handle_telegram_message(
        chat_id=1,
        message_text="/data table=orders columns=id,status filters=status:paid limit=5",
    )

    assert "Rows returned: 1" in response
    assert "status" in response


def test_orchestrator_handles_data_command_without_sql_reader() -> None:
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        sql_reader=None,
    )
    response = orchestrator.handle_telegram_message(
        chat_id=1,
        message_text="/data table=orders columns=id",
    )
    assert "SQL read-only access is not configured." in response


def test_orchestrator_ingest_document_now_parses_string_date() -> None:
    ingestion_service = FakeIngestionService()
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([]),
        task_queue=FakeTaskQueue(),
        ingestion_service=ingestion_service,
        sql_reader=None,
    )

    orchestrator.ingest_document_now("/data/docs/report.txt", event_date="2026-03-01")

    assert ingestion_service.calls[0]["event_date"] == date(2026, 3, 1)


def test_orchestrator_uses_conversation_store_for_query_context() -> None:
    memory_store = FakeMemoryStore([_build_match()])
    conversation_store = FakeConversationStore()
    orchestrator = BusinessOrchestrator(
        memory_store=memory_store,
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        conversation_store=conversation_store,
        sql_reader=None,
    )

    response = orchestrator.handle_telegram_message(chat_id=9, message_text="/ask revenue growth")

    assert "Best answer:" in response
    assert memory_store.last_query is not None
    assert memory_store.last_query.query == "context::revenue growth"
    assert conversation_store.query_inputs[0][0] == 9
    assert conversation_store.turns[0][1] == "user"
    assert conversation_store.turns[1][1] == "assistant"


def test_orchestrator_reset_clears_conversation_context() -> None:
    conversation_store = FakeConversationStore()
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        conversation_store=conversation_store,
        sql_reader=None,
    )

    response = orchestrator.handle_telegram_message(chat_id=77, message_text="/reset")
    assert response == "Conversation context cleared."
    assert conversation_store.cleared_chat_ids == [77]


def test_orchestrator_reset_when_conversation_disabled() -> None:
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        conversation_store=None,
        sql_reader=None,
    )

    response = orchestrator.handle_telegram_message(chat_id=77, message_text="/reset")
    assert response == "Conversation memory is disabled."


def test_orchestrator_returns_ui_payload_for_question() -> None:
    orchestrator = BusinessOrchestrator(
        memory_store=FakeMemoryStore([_build_match()]),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        conversation_store=None,
        sql_reader=None,
    )

    reply = orchestrator.handle_telegram_message_with_ui(chat_id=1, message_text="/ask revenue")
    assert reply.show_actions is True
    assert reply.detailed_text is not None
    assert reply.sources_text is not None
    assert reply.question_text == "revenue"
