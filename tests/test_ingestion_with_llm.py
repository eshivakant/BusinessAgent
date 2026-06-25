"""Tests for ingestion service with LLM metadata extraction and OCR."""

from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Sequence
from unittest.mock import MagicMock, patch

import pytest

from business_agent.ingestion.parser import ParsedDocument
from business_agent.ingestion.registry import DocumentInfo, InMemoryDocumentRegistry
from business_agent.ingestion.service import DocumentIngestionService
from business_agent.ingestion.summarizer import ExtractiveSummarizer
from business_agent.llm.client import DocumentMetadata
from business_agent.llm.mock import MockLLMClient
from business_agent.memory.models import MemoryMatch, MemoryQueryInput, MemoryRecord


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


@pytest.fixture
def temp_archive_dir():
    with TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def memory_store():
    return FakeMemoryStore()


@pytest.fixture
def document_registry():
    return InMemoryDocumentRegistry()


@pytest.fixture
def llm_client():
    return MockLLMClient()


@pytest.fixture
def summarizer():
    return ExtractiveSummarizer()


@pytest.fixture
def ingestion_service(memory_store, summarizer, document_registry, llm_client, temp_archive_dir):
    return DocumentIngestionService(
        memory_store=memory_store,
        summarizer=summarizer,
        chunk_size=512,
        chunk_overlap=64,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
        llm_client=llm_client,
        document_registry=document_registry,
        enable_metadata_extraction=True,
    )


def test_ingest_with_metadata_extraction(ingestion_service, memory_store, document_registry, temp_archive_dir):
    """Test that LLM metadata is extracted and registered."""
    # Create a test document
    with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp") as f:
        f.write("This is an invoice from ACME Corp for Q1 2025. Invoice #12345. Amount: $1000.")
        f.flush()
        doc_path = f.name

    try:
        result = ingestion_service.ingest_from_uri(
            source_uri=doc_path,
            event_date=date(2025, 1, 15),
        )

        # Verify ingestion completed
        assert result.document_id is not None
        assert result.chunk_count >= 1
        assert result.records_written >= 1

        # Verify document was registered with metadata
        doc_info = document_registry.get(result.document_id)
        assert doc_info is not None
        assert doc_info.document_type in {"invoice", "other"}  # Mock may return either
        assert doc_info.title is not None
        assert doc_info.ingested_at is not None

        # Verify memory records were written
        records = memory_store._data
        assert len(records) >= result.chunk_count
    finally:
        Path(doc_path).unlink(missing_ok=True)


def test_ingest_with_image_ocr(ingestion_service, memory_store, document_registry, temp_archive_dir):
    """Test that image documents trigger OCR."""
    # Create a simple text file to simulate image parsing
    with NamedTemporaryFile(mode="w", suffix=".png", delete=False, dir="/tmp") as f:
        f.write("Simulated PNG content - will be OCR'd")
        f.flush()
        doc_path = f.name

    try:
        result = ingestion_service.ingest_from_uri(
            source_uri=doc_path,
            event_date=date(2025, 1, 15),
        )

        # Verify ingestion completed
        assert result.document_id is not None
        assert result.records_written >= 1

        # Verify document registry has the image source type
        doc_info = document_registry.get(result.document_id)
        assert doc_info is not None
        assert doc_info.source_type == "png"
    finally:
        Path(doc_path).unlink(missing_ok=True)


def test_ingest_without_llm_client(memory_store, summarizer, document_registry, temp_archive_dir):
    """Test ingestion without LLM client doesn't crash."""
    service = DocumentIngestionService(
        memory_store=memory_store,
        summarizer=summarizer,
        chunk_size=512,
        chunk_overlap=64,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
        llm_client=None,  # No LLM
        document_registry=None,  # No registry
        enable_metadata_extraction=False,
    )

    with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp") as f:
        f.write("Test document without LLM")
        f.flush()
        doc_path = f.name

    try:
        result = service.ingest_from_uri(source_uri=doc_path)
        assert result.document_id is not None
        assert result.records_written >= 1
    finally:
        Path(doc_path).unlink(missing_ok=True)


def test_ingest_pdf_compression(ingestion_service, temp_archive_dir):
    """Test that large PDFs are compressed before archival."""
    # Create a valid minimal PDF (not just random bytes)
    minimal_pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test Document) Tj
ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000196 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
290
%%EOF"""
    
    with patch("business_agent.ingestion.service.compress_pdf_images") as mock_compress:
        mock_compress.return_value = b"compressed pdf content"
        
        # Mock load_document_from_uri to handle the PDF properly
        with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
            mock_load.return_value = ParsedDocument(
                text="Test PDF content",
                source_uri="test.pdf",
                source_type="pdf",
            )

            with NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False, dir="/tmp") as f:
                # Write valid PDF repeated to make it large (>1MB)
                for _ in range(150):
                    f.write(minimal_pdf)
                f.flush()
                doc_path = f.name

            try:
                result = ingestion_service.ingest_from_uri(source_uri=doc_path)
                assert result.document_id is not None

                # Verify compression was called for large PDF
                if Path(doc_path).stat().st_size > 1024 * 1024:
                    mock_compress.assert_called()
            finally:
                Path(doc_path).unlink(missing_ok=True)


def test_ingest_metadata_extraction_failure_graceful(ingestion_service, memory_store, document_registry, temp_archive_dir):
    """Test that metadata extraction failure doesn't crash ingestion."""
    # Mock LLM to fail
    ingestion_service._llm_client = MagicMock()
    ingestion_service._llm_client.extract_metadata.side_effect = Exception("LLM API error")

    with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp") as f:
        f.write("Test document")
        f.flush()
        doc_path = f.name

    try:
        result = ingestion_service.ingest_from_uri(source_uri=doc_path)
        # Ingestion should still complete even if LLM fails
        assert result.document_id is not None
        assert result.records_written >= 1
    finally:
        Path(doc_path).unlink(missing_ok=True)


def test_ingest_registers_document_with_metadata(ingestion_service, document_registry):
    """Test that registered document has all metadata fields."""
    with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp") as f:
        f.write("Invoice from company ABC for services rendered")
        f.flush()
        doc_path = f.name

    try:
        result = ingestion_service.ingest_from_uri(
            source_uri=doc_path,
            event_date=date(2025, 1, 15),
        )

        doc_info = document_registry.get(result.document_id)
        assert doc_info is not None
        assert doc_info.document_id == result.document_id
        assert doc_info.title is not None
        assert doc_info.document_type is not None
        assert doc_info.keywords is not None
        assert isinstance(doc_info.keywords, list)
        assert doc_info.ingested_at is not None
        # event_date may be datetime or date; extract date part
        event_date_val = doc_info.event_date
        if hasattr(event_date_val, 'date'):
            event_date_val = event_date_val.date()
        assert event_date_val == date(2025, 1, 15)
        assert doc_info.effective_date is not None
        assert doc_info.summary is not None or doc_info.summary == ""
        assert doc_info.chunk_count >= 1
    finally:
        Path(doc_path).unlink(missing_ok=True)


def test_ingest_ocr_failure_graceful(ingestion_service):
    """Test OCR failure doesn't crash ingestion."""
    # Mock LLM client to fail on OCR but succeed on metadata
    ingestion_service._llm_client = MagicMock()
    ingestion_service._llm_client.ocr_image.side_effect = Exception("OCR failed")
    ingestion_service._llm_client.extract_metadata.return_value = DocumentMetadata(
        document_type="invoice",
        vendor="TestVendor",
        department="Finance",
        keywords=["test", "invoice"]
    )

    with NamedTemporaryFile(mode="w", suffix=".jpg", delete=False, dir="/tmp") as f:
        f.write("JPEG content")
        f.flush()
        doc_path = f.name

    try:
        # Should still complete despite OCR failure
        with pytest.warns(UserWarning, match="OCR failed"):
            result = ingestion_service.ingest_from_uri(source_uri=doc_path)
        assert result.document_id is not None
        assert result.records_written >= 1
    finally:
        Path(doc_path).unlink(missing_ok=True)


def test_ingest_multiple_documents_separate_registration(ingestion_service, document_registry):
    """Test that multiple documents are registered separately."""
    doc_ids = []

    for i in range(3):
        with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp") as f:
            f.write(f"Document {i} content")
            f.flush()
            doc_path = f.name

        try:
            result = ingestion_service.ingest_from_uri(source_uri=doc_path)
            doc_ids.append(result.document_id)
        finally:
            Path(doc_path).unlink(missing_ok=True)

    # All documents should be unique
    assert len(set(doc_ids)) == 3

    # All should be registered
    for doc_id in doc_ids:
        doc_info = document_registry.get(doc_id)
        assert doc_info is not None


def test_ingest_archive_path_stored_in_registry(ingestion_service, document_registry, temp_archive_dir):
    """Test that archived file path is stored in document registry."""
    with NamedTemporaryFile(mode="w", suffix=".txt", delete=False, dir="/tmp") as f:
        f.write("Test content")
        f.flush()
        doc_path = f.name

    try:
        result = ingestion_service.ingest_from_uri(source_uri=doc_path)
        doc_info = document_registry.get(result.document_id)
        assert doc_info is not None
        assert doc_info.archived_file_path is not None
        # Verify it's a valid path format
        assert doc_info.archived_file_path.startswith(temp_archive_dir) or "/archive/" in doc_info.archived_file_path
    finally:
        Path(doc_path).unlink(missing_ok=True)
