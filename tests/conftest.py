from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

import business_agent.api.app as api_app_module
import business_agent.api.routes as api_routes_module
import business_agent.api.security as api_security_module
import business_agent.orchestrator.service as orchestrator_service_module
from business_agent.ingestion.registry import InMemoryDocumentRegistry
from business_agent.ingestion.service import DocumentIngestionService
from business_agent.ingestion.summarizer import ExtractiveSummarizer
from business_agent.memory.models import MemoryMatch, MemoryPayload, MemoryRecord
from business_agent.memory.text_memorization import TextMemorizationService
from business_agent.orchestrator.conversation import ConversationStore
from business_agent.orchestrator.service import BusinessOrchestrator
from business_agent.property.models import MaintenanceRequest, MaintenanceStatus, Mortgage, Property, PropertyStatus, Tenant
from business_agent.property.registry import InMemoryPropertyRegistry
from business_agent.tenancy.registry import InMemoryTenancyRegistry
from business_agent.tenancy.service import TenancyService
from business_agent.worker.queue import SubagentTaskQueue


class FrozenDateTime(datetime):
    fixed_now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz: timezone | None = None) -> datetime:
        return cls.fixed_now if tz is not None else cls.fixed_now.replace(tzinfo=None)


class FakeMemoryStore:
    def __init__(self) -> None:
        self.records: list[MemoryRecord] = []

    def ensure_collection(self) -> None:
        return None

    def upsert(self, records: list[MemoryRecord]) -> None:
        self.records.extend(records)

    def query(self, request: Any) -> list[MemoryMatch]:
        query_terms = [term.lower() for term in request.query.split() if len(term) > 2]
        matches: list[MemoryMatch] = []
        for record in self.records:
            payload = record.payload
            if request.source_type and payload.source_type != request.source_type:
                continue
            if request.source_uri and payload.source_uri != request.source_uri:
                continue
            if request.property_address and payload.property_address != request.property_address:
                continue
            if request.property_id and payload.property_id != request.property_id:
                continue
            if request.document_type and payload.document_type != request.document_type:
                continue
            if request.record_type and payload.record_type != request.record_type:
                continue
            if request.date_from and payload.effective_date.date() < request.date_from:
                continue
            if request.date_to and payload.effective_date.date() > request.date_to:
                continue
            if query_terms and not any(term in record.text.lower() for term in query_terms):
                continue
            score = 1.0 - (len(matches) * 0.01)
            matches.append(MemoryMatch(id=record.id, score=score, text=record.text, payload=record.payload))
        return matches[: request.top_k]


class FakeTaskQueue(SubagentTaskQueue):
    def __init__(self) -> None:
        self.tasks: list[Any] = []

    def enqueue_document_ingestion(self, task: Any) -> str:
        self.tasks.append(task)
        return f"job-{len(self.tasks)}"


class InMemoryConversationStore(ConversationStore):
    def __init__(self) -> None:
        self._history: dict[int, list[tuple[str, str]]] = {}

    def append_turn(self, chat_id: int, role: str, text: str) -> None:
        self._history.setdefault(chat_id, []).append((role, text))

    def build_query(self, chat_id: int, current_message: str, max_chars: int) -> str:
        turns = self._history.get(chat_id, [])
        parts = []
        for role, text in turns:
            parts.append(f"{role}: {text}")
        if current_message:
            parts.append(f"user: {current_message}")
        query = "\n".join(parts)
        if len(query) > max_chars:
            return query[-max_chars:]
        return query

    def clear(self, chat_id: int) -> None:
        self._history[chat_id] = []

    @property
    def history(self) -> dict[int, list[tuple[str, str]]]:
        return self._history


class FakeTelegramClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []
        self.downloads: dict[str, bytes] = {}

    async def send_message(self, chat_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        self.sent_messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    async def edit_message_text(self, chat_id: int, message_id: int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        self.sent_messages.append({"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup})

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None, show_alert: bool = False) -> None:
        self.sent_messages.append({"callback_query_id": callback_query_id, "text": text, "show_alert": show_alert})

    async def download_file(self, file_id: str) -> bytes:
        return self.downloads.get(file_id, b"test")


class FakeTelegramUiStateStore:
    def __init__(self) -> None:
        self.payloads: dict[str, Any] = {}

    def store(self, chat_id: int, payload: Any) -> str:
        token = f"token-{chat_id}"
        self.payloads[token] = payload
        return token

    def load(self, chat_id: int, token: str) -> Any | None:
        return self.payloads.get(token)


class FakeSQLReader:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def fetch_rows(self, request: Any) -> list[dict[str, Any]]:
        if request.table not in {"properties", "tenants"}:
            raise PermissionError(f"Table not allowed: {request.table}")
        return [dict(row) for row in self.rows]


class FastE2EHarness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
        self.settings = SimpleNamespace(
            internal_api_token=None,
            telegram_bot_token="test-token",
            telegram_webhook_secret=None,
            app_env="test",
            app_host="127.0.0.1",
            app_port=8000,
            redis_url="redis://localhost:6379/0",
            rq_queue_name="business-agent",
            conversation_enabled=True,
            conversation_window_messages=4,
            conversation_summary_max_chars=200,
            conversation_context_max_chars=500,
            conversation_ttl_seconds=60,
            telegram_ui_state_ttl_seconds=60,
            qdrant_url="http://localhost:6333",
            qdrant_collection="business_agent_test",
            qdrant_vector_size=8,
            qdrant_distance="Cosine",
            ingestion_allowed_local_dir=str(tmp_path / "docs"),
            ingestion_archive_dir=str(tmp_path / "archive"),
            ingestion_archive_enabled=False,
            ingestion_chunk_size=120,
            ingestion_chunk_overlap=20,
            ingestion_summary_sentences=2,
            ingestion_max_document_chars=20000,
            ingestion_enable_metadata_extraction=False,
            app_base_url=None,
            app_database_url=None,
            llm_openrouter_api_key=None,
            llm_request_timeout=5,
            sql_database_url=None,
            sql_allowed_tables="properties,tenants",
            sql_query_limit_default=10,
            sql_query_limit_max=100,
            external_docker_network="app-network",
            traefik_enable=False,
            traefik_host="business-agent.local",
        )

        self.memory_store = FakeMemoryStore()
        self.task_queue = FakeTaskQueue()
        self.conversation_store = InMemoryConversationStore()
        self.telegram_client = FakeTelegramClient()
        self.telegram_ui_state = FakeTelegramUiStateStore()
        self.sql_reader = FakeSQLReader(rows=[{"id": 1, "address": "133 Bowland Drive", "status": "owned"}])
        self.property_registry = InMemoryPropertyRegistry()
        self.document_registry = InMemoryDocumentRegistry()
        self.tenancy_registry = InMemoryTenancyRegistry()
        self.text_memorization_service = TextMemorizationService(memory_store=self.memory_store)
        self.tenancy_service = TenancyService(
            tenancy_registry=self.tenancy_registry,
            property_registry=self.property_registry,
            memory_store=self.memory_store,
            summarizer=ExtractiveSummarizer(max_sentences=2),
            chunk_size=120,
            chunk_overlap=20,
            max_document_chars=20000,
            storage_dir=self.settings.ingestion_allowed_local_dir,
            template_dir=str(tmp_path / "templates"),
            generated_dir=str(tmp_path / "generated"),
            llm_client=None,
            allowed_local_dir=self.settings.ingestion_allowed_local_dir,
        )

        self.ingestion_service = DocumentIngestionService(
            memory_store=self.memory_store,
            summarizer=ExtractiveSummarizer(max_sentences=2),
            chunk_size=120,
            chunk_overlap=20,
            max_document_chars=20000,
            allowed_local_dir=self.settings.ingestion_allowed_local_dir,
            archive_dir=self.settings.ingestion_archive_dir,
            archive_enabled=False,
            llm_client=None,
            document_registry=self.document_registry,
            enable_metadata_extraction=False,
        )
        self.orchestrator = BusinessOrchestrator(
            memory_store=self.memory_store,
            task_queue=self.task_queue,
            ingestion_service=self.ingestion_service,
            conversation_store=self.conversation_store,
            sql_reader=self.sql_reader,
            document_registry=self.document_registry,
            property_registry=self.property_registry,
            tenancy_service=self.tenancy_service,
            llm_client=None,
            text_memorization_service=self.text_memorization_service,
        )

        monkeypatch.setattr(api_routes_module, "get_settings", lambda: self.settings)
        monkeypatch.setattr(api_security_module, "get_settings", lambda: self.settings)
        monkeypatch.setattr(orchestrator_service_module, "get_settings", lambda: self.settings)

        monkeypatch.setattr(api_routes_module, "get_orchestrator", lambda: self.orchestrator)
        monkeypatch.setattr(api_routes_module, "get_property_registry", lambda: self.property_registry)
        monkeypatch.setattr(api_routes_module, "get_sql_reader", lambda: self.sql_reader)
        monkeypatch.setattr(api_routes_module, "get_document_registry", lambda: self.document_registry)
        monkeypatch.setattr(api_routes_module, "get_tenancy_service", lambda: self.tenancy_service)
        monkeypatch.setattr(api_routes_module, "get_telegram_client", lambda: self.telegram_client)
        monkeypatch.setattr(api_routes_module, "get_telegram_ui_state", lambda: self.telegram_ui_state)
        monkeypatch.setattr(api_routes_module, "get_text_memorization_service", lambda: self.text_memorization_service, raising=False)

        monkeypatch.setattr(api_app_module, "get_memory_store", lambda: self.memory_store)
        monkeypatch.setattr(api_app_module, "get_app_database", lambda: None)

        monkeypatch.setattr("business_agent.ingestion.service.datetime", FrozenDateTime)
        monkeypatch.setattr("business_agent.memory.text_memorization.datetime", FrozenDateTime)
        monkeypatch.setattr("business_agent.property.models.datetime", FrozenDateTime)

        self.app = api_app_module.create_app()
        self.client = TestClient(self.app)


@pytest.fixture
def fast_e2e_harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> FastE2EHarness:
    return FastE2EHarness(monkeypatch=monkeypatch, tmp_path=tmp_path)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "unit: fast unit tests")
    config.addinivalue_line("markers", "e2e: fast end-to-end tests")
    config.addinivalue_line("markers", "e2e_stack: docker-compose-backed end-to-end tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "e2e_stack" in item.keywords or "e2e" in item.keywords:
            continue
        item.add_marker(pytest.mark.unit)
