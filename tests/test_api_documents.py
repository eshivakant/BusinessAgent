"""Tests for document API endpoints."""

from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from business_agent.ingestion.registry import DocumentInfo, DocumentRegistry


class MockDocumentRegistry(DocumentRegistry):
    """Mock registry with predefined documents."""

    def __init__(self):
        self._docs: dict[str, DocumentInfo] = {
            "doc1": DocumentInfo(
                document_id="doc1",
                title="Invoice 2025",
                document_type="invoice",
                vendor="ACME Corp",
                department="Finance",
                keywords=["invoice", "2025", "Q1"],
                source_uri="http://example.com/invoice.pdf",
                source_type="pdf",
                archived_file_path="/archive/doc1/original.pdf",
                ingested_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
                event_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
                effective_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
                summary="Q1 Invoice from ACME",
                chunk_count=5,
            ),
            "doc2": DocumentInfo(
                document_id="doc2",
                title="Annual Report 2024",
                document_type="report",
                vendor="Internal",
                department="Management",
                keywords=["report", "annual", "2024"],
                source_uri="/data/reports/annual_2024.pdf",
                source_type="pdf",
                archived_file_path="/archive/doc2/original.pdf",
                ingested_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
                event_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
                effective_date=datetime(2024, 12, 31, tzinfo=timezone.utc),
                summary="Annual report summary",
                chunk_count=10,
            ),
        }

    def register(self, doc_info: DocumentInfo) -> None:
        self._docs[doc_info.document_id] = doc_info

    def get(self, document_id: str) -> DocumentInfo | None:
        return self._docs.get(document_id)

    def query(
        self,
        document_type: str | None = None,
        vendor: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> list[DocumentInfo]:
        results = []
        for doc in self._docs.values():
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
def client_with_docs():
    """Create test client with mock registry and no auth."""
    from business_agent.api.app import create_app
    
    mock_registry = MockDocumentRegistry()
    
    # Patch both dependencies and security
    with patch("business_agent.dependencies.get_document_registry", return_value=mock_registry), \
         patch("business_agent.api.routes.verify_internal_api_token") as mock_verify:
        app = create_app()
        client = TestClient(app)
        yield client, mock_registry


def test_list_documents_all(client_with_docs):
    """Test listing all documents."""
    client, mock_registry = client_with_docs
    response = client.get("/api/documents/list")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert len(data["documents"]) == 2


def test_list_documents_filter_by_type(client_with_docs):
    """Test filtering documents by type."""
    client, mock_registry = client_with_docs
    response = client.get("/api/documents/list?document_type=invoice")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    assert data["documents"][0]["document_type"] == "invoice"


def test_list_documents_no_results(client_with_docs):
    """Test no documents matching criteria."""
    client, mock_registry = client_with_docs
    response = client.get("/api/documents/list?document_type=contract")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0


def test_get_document_success(client_with_docs):
    """Test retrieving single document metadata."""
    client, mock_registry = client_with_docs
    response = client.get("/api/documents/doc1")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "doc1"
    assert data["title"] == "Invoice 2025"
    assert data["document_type"] == "invoice"


def test_get_document_not_found(client_with_docs):
    """Test retrieving nonexistent document."""
    client, mock_registry = client_with_docs
    response = client.get("/api/documents/nonexistent")
    assert response.status_code == 404


def test_download_document_not_found(client_with_docs):
    """Test downloading nonexistent document."""
    client, mock_registry = client_with_docs
    response = client.get("/api/documents/nonexistent/download")
    assert response.status_code == 404

