"""Tests for orchestrator _handle_list_command."""

from datetime import date, datetime, timezone
from typing import Sequence
from unittest.mock import MagicMock, patch

import pytest

from business_agent.ingestion.registry import DocumentInfo, DocumentRegistry
from business_agent.memory.models import MemoryMatch, MemoryQueryInput, MemoryRecord
from business_agent.orchestrator.service import BusinessOrchestrator


class FakeMemoryStore:
    """Test double for MemoryStore."""
    
    def __init__(self):
        self._data: dict[str, MemoryRecord] = {}
    
    def ensure_collection(self) -> None:
        pass
    
    def upsert(self, records: Sequence[MemoryRecord]) -> None:
        for record in records:
            self._data[record.id] = record
    
    def query(self, request: MemoryQueryInput) -> list[MemoryMatch]:
        return []


class FakeTaskQueue:
    """Test double for SubagentTaskQueue."""
    
    def enqueue_document_ingestion(self, task) -> str:
        return "fake_job_id"


class MockRegistry(DocumentRegistry):
    """Mock registry for testing."""

    def __init__(self, docs: list[DocumentInfo]):
        self.docs = {doc.document_id: doc for doc in docs}

    def register(self, doc_info: DocumentInfo) -> None:
        self.docs[doc_info.document_id] = doc_info

    def get(self, document_id: str) -> DocumentInfo | None:
        return self.docs.get(document_id)

    def query(
        self,
        document_type: str | None = None,
        vendor: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> list[DocumentInfo]:
        results = []
        for doc in self.docs.values():
            if document_type and doc.document_type != document_type:
                continue
            if vendor and doc.vendor != vendor:
                continue
            if date_from and doc.effective_date < date_from:
                continue
            if date_to and doc.effective_date > date_to:
                continue
            results.append(doc)
        return results[:limit]


@pytest.fixture
def mock_registry():
    docs = [
        DocumentInfo(
            document_id="inv1",
            title="Invoice Q1",
            document_type="invoice",
            vendor="ACME",
            department="Finance",
            keywords=["invoice", "q1"],
            source_uri="http://example.com/inv1.pdf",
            source_type="pdf",
            archived_file_path="/archive/inv1/original.pdf",
            ingested_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
            event_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
            effective_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
            summary="Q1 invoice summary",
            chunk_count=5,
        ),
        DocumentInfo(
            document_id="rep1",
            title="Annual Report",
            document_type="report",
            vendor="Internal",
            department="Management",
            keywords=["report", "annual"],
            source_uri="/data/reports/annual.pdf",
            source_type="pdf",
            archived_file_path="/archive/rep1/original.pdf",
            ingested_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
            event_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            effective_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
            summary="Annual report summary",
            chunk_count=10,
        ),
    ]
    registry = MockRegistry(docs)
    return registry


@pytest.fixture
def orchestrator():
    memory_store = FakeMemoryStore()
    task_queue = FakeTaskQueue()
    
    with patch("business_agent.dependencies.get_ingestion_service"):
        orchestrator = BusinessOrchestrator(
            memory_store=memory_store,
            task_queue=task_queue,
            ingestion_service=MagicMock(),
        )
    return orchestrator


def test_handle_list_no_registry(orchestrator):
    """Test /list when registry is not configured."""
    with patch("business_agent.dependencies.get_document_registry", return_value=None):
        reply = orchestrator._handle_list_command("/list")
        assert "not configured" in reply.text.lower()


def test_handle_list_all_documents(orchestrator, mock_registry):
    """Test /list returns all documents."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list")
        assert "Found 2 document(s)" in reply.text
        assert "Invoice Q1" in reply.text
        assert "Annual Report" in reply.text


def test_handle_list_filter_by_type(orchestrator, mock_registry):
    """Test /list filters by document type."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list type=invoice")
        assert "Found 1 document(s)" in reply.text
        assert "Invoice Q1" in reply.text
        assert "Annual Report" not in reply.text


def test_handle_list_filter_by_vendor(orchestrator, mock_registry):
    """Test /list filters by vendor."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list vendor=ACME")
        assert "Found 1 document(s)" in reply.text
        assert "Invoice Q1" in reply.text
        assert "ACME" in reply.text


def test_handle_list_filter_by_date(orchestrator, mock_registry):
    """Test /list filters by date range."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list date_from=2025-01-01 date_to=2025-12-31")
        assert "Found 1 document(s)" in reply.text  # Only Q1 invoice in 2025
        assert "Invoice Q1" in reply.text


def test_handle_list_with_limit(orchestrator, mock_registry):
    """Test /list respects limit parameter."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list limit=1")
        assert "Found 1 document(s)" in reply.text


def test_handle_list_no_matches(orchestrator, mock_registry):
    """Test /list with no matching documents."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list type=contract")
        assert "No documents found" in reply.text


def test_handle_list_includes_summary(orchestrator, mock_registry):
    """Test /list includes document summary."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list")
        assert "Summary:" in reply.text
        assert "Q1 invoice summary" in reply.text or "Annual report summary" in reply.text


def test_handle_list_includes_metadata(orchestrator, mock_registry):
    """Test /list includes vendor and document type."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list type=invoice")
        assert "invoice" in reply.text.lower()
        assert "ACME" in reply.text or "Vendor" in reply.text


def test_handle_list_shows_date(orchestrator, mock_registry):
    """Test /list shows ingestion date."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list")
        assert "2025-01" in reply.text or "2024-12" in reply.text


def test_handle_list_parsing_error(orchestrator, mock_registry):
    """Test /list with invalid syntax."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list invalid syntax")
        assert "Could not parse" in reply.text or "error" in reply.text.lower()


def test_handle_list_combined_filters(orchestrator, mock_registry):
    """Test /list with multiple filters."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command(
            "/list type=invoice vendor=ACME date_from=2025-01-01 limit=10"
        )
        assert "Found" in reply.text
        assert "Invoice Q1" in reply.text


def test_handle_list_date_only(orchestrator, mock_registry):
    """Test /list with only date filter."""
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry):
        reply = orchestrator._handle_list_command("/list date_from=2024-12-01 date_to=2025-01-31")
        assert "Found" in reply.text
