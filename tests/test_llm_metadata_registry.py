"""Tests for LLM-based metadata extraction and document registry."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from business_agent.ingestion.registry import DocumentInfo, DocumentQueryFilter, InMemoryDocumentRegistry
from business_agent.llm.client import DocumentMetadata, LLMClient


class TestLLMClient:
    """Test LLM client for metadata extraction."""

    def test_extract_metadata_returns_document_metadata(self):
        """Test that metadata extraction returns DocumentMetadata."""
        client = LLMClient(api_key="test-key")

        with patch("business_agent.llm.client.httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": '{"document_type":"invoice","vendor":"ACME","department":"finance","keywords":["Q1","2025"]}'
                        }
                    }
                ]
            }
            mock_post.return_value = mock_response

            metadata = client.extract_metadata(
                "Invoice for Q1 2025 from ACME corp",
                "http://example.com/invoice.pdf",
            )

            assert metadata.document_type == "invoice"
            assert metadata.vendor == "ACME"
            assert metadata.department == "finance"
            assert "Q1" in metadata.keywords

    def test_extract_metadata_handles_invalid_json(self):
        """Test that invalid JSON response falls back to defaults."""
        client = LLMClient(api_key="test-key")

        with patch("business_agent.llm.client.httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": "not valid json"}}]
            }
            mock_post.return_value = mock_response

            metadata = client.extract_metadata("Some text", "http://example.com/doc.txt")

            assert metadata.document_type == "other"
            assert metadata.vendor is None
            assert metadata.keywords == []

    def test_extract_metadata_sends_correct_request(self):
        """Test that LLM API is called with correct payload."""
        client = LLMClient(api_key="test-key", base_url="https://openrouter.ai/api/v1")

        with patch("business_agent.llm.client.httpx.Client.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "choices": [{"message": {"content": '{"document_type":"report"}'}}]
            }
            mock_post.return_value = mock_response

            client.extract_metadata("Test content", "http://example.com/doc.pdf")

            # Verify correct API endpoint
            call_args = mock_post.call_args
            assert "https://openrouter.ai/api/v1/chat/completions" in call_args[0]


class TestDocumentRegistry:
    """Test document registry operations."""

    def test_register_and_retrieve_document(self):
        """Test registering and retrieving a document."""
        registry = InMemoryDocumentRegistry()
        doc = DocumentInfo(
            document_id="doc-001",
            document_type="invoice",
            source_uri="http://example.com/inv.pdf",
            source_type="pdf",
            ingested_at=datetime.now(timezone.utc),
            effective_date=datetime.now(timezone.utc),
            vendor="ACME",
        )

        registry.register(doc)
        retrieved = registry.get("doc-001")

        assert retrieved is not None
        assert retrieved.document_id == "doc-001"
        assert retrieved.vendor == "ACME"

    def test_query_by_document_type(self):
        """Test filtering documents by type."""
        registry = InMemoryDocumentRegistry()
        now = datetime.now(timezone.utc)

        registry.register(
            DocumentInfo(
                document_id="inv-001",
                document_type="invoice",
                source_uri="http://example.com/inv1.pdf",
                source_type="pdf",
                ingested_at=now,
                effective_date=now,
            )
        )
        registry.register(
            DocumentInfo(
                document_id="rep-001",
                document_type="report",
                source_uri="http://example.com/rep1.pdf",
                source_type="pdf",
                ingested_at=now,
                effective_date=now,
            )
        )

        filters = DocumentQueryFilter(document_type="invoice")
        results = registry.query(filters)

        assert len(results) == 1
        assert results[0].document_id == "inv-001"

    def test_query_by_date_range(self):
        """Test filtering documents by date range."""
        registry = InMemoryDocumentRegistry()
        date_jan = datetime(2025, 1, 15, tzinfo=timezone.utc)
        date_mar = datetime(2025, 3, 15, tzinfo=timezone.utc)
        date_dec = datetime(2025, 12, 15, tzinfo=timezone.utc)

        registry.register(
            DocumentInfo(
                document_id="doc-jan",
                document_type="invoice",
                source_uri="http://example.com/jan.pdf",
                source_type="pdf",
                ingested_at=date_jan,
                effective_date=date_jan,
            )
        )
        registry.register(
            DocumentInfo(
                document_id="doc-dec",
                document_type="invoice",
                source_uri="http://example.com/dec.pdf",
                source_type="pdf",
                ingested_at=date_dec,
                effective_date=date_dec,
            )
        )

        filters = DocumentQueryFilter(
            date_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2025, 6, 30, tzinfo=timezone.utc),
        )
        results = registry.query(filters)

        assert len(results) == 1
        assert results[0].document_id == "doc-jan"

    def test_query_by_vendor(self):
        """Test filtering documents by vendor."""
        registry = InMemoryDocumentRegistry()
        now = datetime.now(timezone.utc)

        registry.register(
            DocumentInfo(
                document_id="acme-inv",
                document_type="invoice",
                vendor="ACME",
                source_uri="http://example.com/inv.pdf",
                source_type="pdf",
                ingested_at=now,
                effective_date=now,
            )
        )
        registry.register(
            DocumentInfo(
                document_id="bcorp-inv",
                document_type="invoice",
                vendor="B-Corp",
                source_uri="http://example.com/inv2.pdf",
                source_type="pdf",
                ingested_at=now,
                effective_date=now,
            )
        )

        filters = DocumentQueryFilter(vendor="ACME")
        results = registry.query(filters)

        assert len(results) == 1
        assert results[0].vendor == "ACME"

    def test_query_by_keyword(self):
        """Test filtering documents by keyword."""
        registry = InMemoryDocumentRegistry()
        now = datetime.now(timezone.utc)

        registry.register(
            DocumentInfo(
                document_id="doc-q1",
                document_type="invoice",
                keywords=["Q1", "2025"],
                source_uri="http://example.com/q1.pdf",
                source_type="pdf",
                ingested_at=now,
                effective_date=now,
            )
        )
        registry.register(
            DocumentInfo(
                document_id="doc-q2",
                document_type="invoice",
                keywords=["Q2", "2025"],
                source_uri="http://example.com/q2.pdf",
                source_type="pdf",
                ingested_at=now,
                effective_date=now,
            )
        )

        filters = DocumentQueryFilter(keyword="Q1")
        results = registry.query(filters)

        assert len(results) == 1
        assert results[0].document_id == "doc-q1"

    def test_query_combined_filters(self):
        """Test querying with multiple filters."""
        registry = InMemoryDocumentRegistry()
        date_2025 = datetime(2025, 6, 15, tzinfo=timezone.utc)

        registry.register(
            DocumentInfo(
                document_id="acme-inv-2025",
                document_type="invoice",
                vendor="ACME",
                keywords=["2025"],
                source_uri="http://example.com/inv.pdf",
                source_type="pdf",
                ingested_at=date_2025,
                effective_date=date_2025,
            )
        )
        registry.register(
            DocumentInfo(
                document_id="bcorp-rep-2024",
                document_type="report",
                vendor="B-Corp",
                keywords=["2024"],
                source_uri="http://example.com/rep.pdf",
                source_type="pdf",
                ingested_at=datetime(2024, 6, 15, tzinfo=timezone.utc),
                effective_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
            )
        )

        filters = DocumentQueryFilter(
            document_type="invoice",
            vendor="ACME",
            date_from=datetime(2025, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2025, 12, 31, tzinfo=timezone.utc),
        )
        results = registry.query(filters)

        assert len(results) == 1
        assert results[0].document_id == "acme-inv-2025"

    def test_query_respects_limit(self):
        """Test that query respects limit parameter."""
        registry = InMemoryDocumentRegistry()
        now = datetime.now(timezone.utc)

        for i in range(5):
            registry.register(
                DocumentInfo(
                    document_id=f"doc-{i}",
                    document_type="invoice",
                    source_uri=f"http://example.com/inv{i}.pdf",
                    source_type="pdf",
                    ingested_at=now,
                    effective_date=now,
                )
            )

        filters = DocumentQueryFilter(limit=3)
        results = registry.query(filters)

        assert len(results) <= 3

    def test_list_all_documents(self):
        """Test listing all documents."""
        registry = InMemoryDocumentRegistry()
        now = datetime.now(timezone.utc)

        for i in range(3):
            registry.register(
                DocumentInfo(
                    document_id=f"doc-{i}",
                    document_type="invoice",
                    source_uri=f"http://example.com/inv{i}.pdf",
                    source_type="pdf",
                    ingested_at=now,
                    effective_date=now,
                )
            )

        results = registry.list_all(limit=100)
        assert len(results) == 3


class TestDocumentMetadata:
    """Test DocumentMetadata model."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        metadata = DocumentMetadata(
            document_type="invoice",
            vendor="ACME",
            department="finance",
            keywords=["Q1", "2025"],
        )

        result = metadata.to_dict()

        assert result["document_type"] == "invoice"
        assert result["vendor"] == "ACME"
        assert result["department"] == "finance"
        assert "Q1" in result["keywords"]

    def test_to_dict_with_none_values(self):
        """Test conversion to dict with None values."""
        metadata = DocumentMetadata(
            document_type="other",
            vendor=None,
            department=None,
            keywords=[],
        )

        result = metadata.to_dict()

        assert result["vendor"] is None
        assert result["department"] is None
        assert result["keywords"] == []
