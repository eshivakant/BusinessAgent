from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from business_agent.api import routes, security
from business_agent.ingestion.service import IngestionResult
from business_agent.memory.models import MemoryMatch, MemoryPayload
from business_agent.orchestrator.service import TelegramReply
from business_agent.telegram.ui_state import TelegramUiPayload


class FakeOrchestrator:
    def __init__(self) -> None:
        self.last_message: tuple[int, str] | None = None
        self.last_query: Any = None
        self.last_enqueue: dict[str, Any] | None = None
        self.last_ingest: dict[str, Any] | None = None

    def handle_telegram_message(self, chat_id: int, message_text: str) -> str:
        self.last_message = (chat_id, message_text)
        return "reply-from-orchestrator"

    def handle_telegram_message_with_ui(self, chat_id: int, message_text: str) -> TelegramReply:
        self.last_message = (chat_id, message_text)
        if message_text == "/reset":
            return TelegramReply(text="Conversation context cleared.")
        return TelegramReply(
            text="compact reply",
            detailed_text="detailed reply",
            sources_text="sources reply",
            question_text=message_text,
            show_actions=True,
        )

    def query_memory(self, request: Any) -> list[MemoryMatch]:
        self.last_query = request
        payload = MemoryPayload(
            event_date=date(2026, 1, 15),
            ingested_at=datetime(2026, 1, 16, 12, 0, tzinfo=timezone.utc),
            effective_date=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
            source_type="pdf",
            source_uri="file:///data/docs/report.pdf",
            record_type="chunk",
            chunk_index=0,
            chunk_count=1,
            summary="summary",
        )
        return [
            MemoryMatch(
                id="doc-1",
                score=0.9,
                text="Revenue increased",
                payload=payload,
            )
        ]

    def enqueue_document_ingestion(
        self,
        source_uri: str,
        event_date: date | None = None,
        requester_id: int | None = None,
    ) -> str:
        self.last_enqueue = {
            "source_uri": source_uri,
            "event_date": event_date,
            "requester_id": requester_id,
        }
        return "job-123"

    def ingest_document_now(
        self,
        source_uri: str,
        event_date: date | None = None,
        requester_id: int | None = None,
    ) -> IngestionResult:
        self.last_ingest = {
            "source_uri": source_uri,
            "event_date": event_date,
            "requester_id": requester_id,
        }
        return IngestionResult(
            document_id="doc-1",
            source_uri=source_uri,
            source_type="txt",
            summary_id="doc-1:summary",
            chunk_count=1,
            records_written=2,
        )


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.callback_answers: list[dict[str, Any]] = []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> None:
        self.callback_answers.append(
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
            }
        )


class FakeSQLReader:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def fetch_rows(self, request: Any) -> list[dict[str, Any]]:
        del request
        return self.rows


class FakeUiState:
    def __init__(self) -> None:
        self._counter = 0
        self.saved: dict[tuple[int, str], TelegramUiPayload] = {}

    def store(self, chat_id: int, payload: TelegramUiPayload) -> str:
        self._counter += 1
        token = f"tok{self._counter}"
        self.saved[(chat_id, token)] = payload
        return token

    def load(self, chat_id: int, token: str) -> TelegramUiPayload | None:
        return self.saved.get((chat_id, token))


def _build_client(
    monkeypatch,
    settings: Any,
    orchestrator: FakeOrchestrator | None = None,
    sql_reader: FakeSQLReader | None = None,
    ui_state: FakeUiState | None = None,
) -> tuple[TestClient, FakeOrchestrator, FakeTelegramClient, FakeUiState]:
    fake_orchestrator = orchestrator or FakeOrchestrator()
    fake_telegram = FakeTelegramClient()
    fake_ui_state = ui_state or FakeUiState()
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    monkeypatch.setattr(routes, "get_orchestrator", lambda: fake_orchestrator)
    monkeypatch.setattr(routes, "get_sql_reader", lambda: sql_reader)
    monkeypatch.setattr(routes, "get_telegram_client", lambda: fake_telegram)
    monkeypatch.setattr(routes, "get_telegram_ui_state", lambda: fake_ui_state)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), fake_orchestrator, fake_telegram, fake_ui_state


def test_health_endpoint(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="",
        internal_api_token=None,
    )
    client, _, _, _ = _build_client(monkeypatch, settings=settings)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_rejects_invalid_secret(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret="secret",
        telegram_bot_token="token",
        internal_api_token=None,
    )
    client, _, _, _ = _build_client(monkeypatch, settings=settings)
    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json={"message": {"chat": {"id": 1}, "text": "hello"}},
    )
    assert response.status_code == 401


def test_webhook_calls_orchestrator_and_sends_actions_keyboard(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret="secret",
        telegram_bot_token="token",
        internal_api_token=None,
    )
    client, orchestrator, telegram_client, ui_state = _build_client(monkeypatch, settings=settings)
    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "secret"},
        json={"message": {"chat": {"id": 5}, "text": "hello"}},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert orchestrator.last_message == (5, "hello")
    assert telegram_client.sent[0]["text"] == "compact reply"
    keyboard = telegram_client.sent[0]["reply_markup"]["inline_keyboard"]
    callback_data_values = [button["callback_data"] for row in keyboard for button in row]
    assert any(value.startswith("act:refine:tok") for value in callback_data_values)
    assert (5, "tok1") in ui_state.saved


def test_webhook_menu_text_maps_to_prompt(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="token",
        internal_api_token=None,
    )
    client, orchestrator, telegram_client, _ = _build_client(monkeypatch, settings=settings)
    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 5}, "text": "Query data"}},
    )
    assert response.status_code == 200
    assert orchestrator.last_message is None
    assert "Run read-only SQL query" in telegram_client.sent[0]["text"]


def test_callback_menu_reset_calls_orchestrator(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="token",
        internal_api_token=None,
    )
    client, orchestrator, telegram_client, _ = _build_client(monkeypatch, settings=settings)
    response = client.post(
        "/telegram/webhook",
        json={
            "callback_query": {
                "id": "cb1",
                "data": "menu:reset",
                "message": {"message_id": 15, "chat": {"id": 8}},
            }
        },
    )
    assert response.status_code == 200
    assert orchestrator.last_message == (8, "/reset")
    assert telegram_client.callback_answers[0]["callback_query_id"] == "cb1"
    assert telegram_client.edited[0]["message_id"] == 15
    assert telegram_client.edited[0]["text"] == "Conversation context cleared."


def test_callback_details_uses_cached_payload(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="token",
        internal_api_token=None,
    )
    ui_state = FakeUiState()
    ui_state.saved[(8, "tok1")] = TelegramUiPayload(
        compact_text="compact",
        detailed_text="detailed",
        sources_text="sources",
        question_text="revenue",
    )
    client, _, telegram_client, _ = _build_client(monkeypatch, settings=settings, ui_state=ui_state)
    response = client.post(
        "/telegram/webhook",
        json={
            "callback_query": {
                "id": "cb2",
                "data": "act:details:tok1",
                "message": {"message_id": 99, "chat": {"id": 8}},
            }
        },
    )
    assert response.status_code == 200
    assert telegram_client.edited[0]["text"] == "detailed"


def test_callback_refine_sends_prompt(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="token",
        internal_api_token=None,
    )
    ui_state = FakeUiState()
    ui_state.saved[(8, "tok1")] = TelegramUiPayload(
        compact_text="compact",
        detailed_text="detailed",
        sources_text="sources",
        question_text="revenue growth",
    )
    client, _, telegram_client, _ = _build_client(monkeypatch, settings=settings, ui_state=ui_state)
    response = client.post(
        "/telegram/webhook",
        json={
            "callback_query": {
                "id": "cb3",
                "data": "act:refine:tok1",
                "message": {"message_id": 11, "chat": {"id": 8}},
            }
        },
    )
    assert response.status_code == 200
    assert "Refine this question" in telegram_client.sent[0]["text"]


def test_callback_handles_expired_payload(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="token",
        internal_api_token=None,
    )
    client, _, telegram_client, _ = _build_client(monkeypatch, settings=settings)
    response = client.post(
        "/telegram/webhook",
        json={
            "callback_query": {
                "id": "cb4",
                "data": "act:details:missing",
                "message": {"message_id": 12, "chat": {"id": 8}},
            }
        },
    )
    assert response.status_code == 200
    assert "Action expired" in telegram_client.edited[0]["text"]


def test_webhook_ignores_non_message_payload(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="token",
        internal_api_token=None,
    )
    client, _, _, _ = _build_client(monkeypatch, settings=settings)
    response = client.post("/telegram/webhook", json={"update_id": 123})
    assert response.status_code == 200
    assert response.json()["ignored"] is True


def test_memory_query_endpoint_requires_token(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="",
        internal_api_token="api-token",
    )
    client, _, _, _ = _build_client(monkeypatch, settings=settings)
    blocked = client.post("/api/memory/query", json={"query": "revenue"})
    allowed = client.post(
        "/api/memory/query",
        headers={"X-API-Token": "api-token"},
        json={"query": "revenue"},
    )

    assert blocked.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["matches"][0]["id"] == "doc-1"


def test_ingest_endpoint_enqueues_job(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="",
        internal_api_token=None,
    )
    client, orchestrator, _, _ = _build_client(monkeypatch, settings=settings)
    response = client.post(
        "/api/documents/ingest",
        json={"source_uri": "/data/docs/report.txt", "event_date": "2026-01-15", "async_mode": True},
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "job-123"
    assert orchestrator.last_enqueue is not None
    assert orchestrator.last_enqueue["event_date"] == date(2026, 1, 15)


def test_sql_read_endpoint_handles_missing_and_present_reader(monkeypatch) -> None:
    settings = SimpleNamespace(
        telegram_webhook_secret=None,
        telegram_bot_token="",
        internal_api_token=None,
    )
    client_missing, _, _, _ = _build_client(monkeypatch, settings=settings, sql_reader=None)
    missing_response = client_missing.post(
        "/api/sql/read",
        json={"table": "orders", "columns": ["id"]},
    )
    assert missing_response.status_code == 503

    sql_reader = FakeSQLReader(rows=[{"id": 1}, {"id": 2}])
    client_present, _, _, _ = _build_client(monkeypatch, settings=settings, sql_reader=sql_reader)
    present_response = client_present.post(
        "/api/sql/read",
        json={"table": "orders", "columns": ["id"]},
    )
    assert present_response.status_code == 200
    assert present_response.json()["row_count"] == 2
