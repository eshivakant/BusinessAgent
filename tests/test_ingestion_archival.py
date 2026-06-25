from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from business_agent.ingestion.parser import ParsedDocument
from business_agent.ingestion.service import DocumentIngestionService
from business_agent.ingestion.summarizer import ExtractiveSummarizer


@pytest.fixture
def temp_archive_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_memory_store():
    store = MagicMock()
    store.upsert = MagicMock()
    return store


@pytest.fixture
def mock_summarizer():
    summarizer = MagicMock()
    summarizer.summarize = MagicMock(return_value="Test summary.")
    return summarizer


def test_archive_document_creates_directory(mock_memory_store, mock_summarizer, temp_archive_dir):
    """Test that archive creates document directory structure."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
    )

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/doc.pdf",
            source_type="pdf",
            text="Test document content.",
        )

        with patch("business_agent.ingestion.service.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"%PDF-1.4\ntest"
            mock_get.return_value = mock_response

            result = service.ingest_from_uri("http://example.com/doc.pdf")

            # Verify archive directory was created
            archive_path = Path(temp_archive_dir) / result.document_id
            assert archive_path.exists(), "Archive directory should be created"
            assert archive_path.is_dir(), "Archive path should be a directory"


def test_archive_document_saves_file_with_correct_extension(
    mock_memory_store, mock_summarizer, temp_archive_dir
):
    """Test that archived file has correct extension based on source type."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
    )

    pdf_content = b"%PDF-1.4\ntest content"

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/report.pdf",
            source_type="pdf",
            text="PDF content extracted.",
        )

        with patch("business_agent.ingestion.service.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = pdf_content
            mock_get.return_value = mock_response

            result = service.ingest_from_uri("http://example.com/report.pdf")

            archive_path = Path(temp_archive_dir) / result.document_id / "original.pdf"
            assert archive_path.exists(), "PDF file should be archived"
            assert archive_path.read_bytes() == pdf_content, "Archived content should match source"


def test_archive_document_txt_extension(mock_memory_store, mock_summarizer, temp_archive_dir):
    """Test that .txt files are archived with txt extension."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
    )

    txt_content = b"Plain text document content."

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/notes.txt",
            source_type="txt",
            text="Plain text extracted.",
        )

        with patch("business_agent.ingestion.service.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = txt_content
            mock_get.return_value = mock_response

            result = service.ingest_from_uri("http://example.com/notes.txt")

            archive_path = Path(temp_archive_dir) / result.document_id / "original.txt"
            assert archive_path.exists(), "TXT file should be archived"
            assert archive_path.read_bytes() == txt_content


def test_archive_document_docx_extension(mock_memory_store, mock_summarizer, temp_archive_dir):
    """Test that .docx files are archived with docx extension."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
    )

    docx_content = b"PK\x03\x04test docx content"

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/report.docx",
            source_type="docx",
            text="Word document extracted.",
        )

        with patch("business_agent.ingestion.service.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = docx_content
            mock_get.return_value = mock_response

            result = service.ingest_from_uri("http://example.com/report.docx")

            archive_path = Path(temp_archive_dir) / result.document_id / "original.docx"
            assert archive_path.exists(), "DOCX file should be archived"


def test_archive_payload_includes_file_path(mock_memory_store, mock_summarizer, temp_archive_dir):
    """Test that memory payload includes archived_file_path."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
    )

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/doc.txt",
            source_type="txt",
            text="Test document content.",
        )

        with patch("business_agent.ingestion.service.httpx.get") as mock_get:
            mock_response = MagicMock()
            mock_response.content = b"Test document content."
            mock_get.return_value = mock_response

            result = service.ingest_from_uri("http://example.com/doc.txt")

            # Check that upsert was called with records containing archived_file_path
            mock_memory_store.upsert.assert_called_once()
            records = mock_memory_store.upsert.call_args[0][0]

            # All records (summary and chunks) should have archived_file_path
            for record in records:
                assert record.payload.archived_file_path is not None
                assert "original.txt" in record.payload.archived_file_path


def test_archive_disabled_no_file_stored(mock_memory_store, mock_summarizer, temp_archive_dir):
    """Test that when archive is disabled, no files are stored."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=False,  # Disabled
    )

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/doc.txt",
            source_type="txt",
            text="Test document content.",
        )

        result = service.ingest_from_uri("http://example.com/doc.txt")

        # Verify no files were created
        archive_root = Path(temp_archive_dir)
        assert not list(archive_root.glob("*")), "No files should be archived when disabled"

        # Verify payload has no archived_file_path
        records = mock_memory_store.upsert.call_args[0][0]
        for record in records:
            assert record.payload.archived_file_path is None


def test_archive_no_dir_specified_gracefully_disabled(mock_memory_store, mock_summarizer):
    """Test that when archive_dir is None, archival is gracefully disabled."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=None,  # No directory
        archive_enabled=True,
    )

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        mock_load.return_value = ParsedDocument(
            source_uri="http://example.com/doc.txt",
            source_type="txt",
            text="Test document content.",
        )

        result = service.ingest_from_uri("http://example.com/doc.txt")

        # Verify payload has no archived_file_path
        records = mock_memory_store.upsert.call_args[0][0]
        for record in records:
            assert record.payload.archived_file_path is None


def test_archive_handles_permission_error_gracefully(mock_memory_store, mock_summarizer):
    """Test that ingestion continues if archive permission denied (simulated)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        readonly_dir = Path(tmpdir) / "readonly"
        readonly_dir.mkdir()

        service = DocumentIngestionService(
            memory_store=mock_memory_store,
            summarizer=mock_summarizer,
            chunk_size=500,
            chunk_overlap=50,
            max_document_chars=10000,
            allowed_local_dir="/tmp",
            archive_dir=str(readonly_dir),
            archive_enabled=True,
        )

        with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
            mock_load.return_value = ParsedDocument(
                source_uri="http://example.com/doc.txt",
                source_type="txt",
                text="Test document content.",
            )

            # Simulate an archive error by making httpx.get raise an exception
            with patch("business_agent.ingestion.service.httpx.get") as mock_get:
                mock_get.side_effect = Exception("Network error during archive fetch")

                # Should not raise; ingestion proceeds with archived_file_path=None
                result = service.ingest_from_uri("http://example.com/doc.txt")

                # Records should have None for archived_file_path due to error
                records = mock_memory_store.upsert.call_args[0][0]
                for record in records:
                    assert record.payload.archived_file_path is None


def test_archive_local_file_source(mock_memory_store, mock_summarizer, temp_archive_dir):
    """Test archival of local file source (not HTTP)."""
    with tempfile.TemporaryDirectory() as source_dir:
        source_file = Path(source_dir) / "test.pdf"
        source_file.write_bytes(b"%PDF-1.4\ntest")

        service = DocumentIngestionService(
            memory_store=mock_memory_store,
            summarizer=mock_summarizer,
            chunk_size=500,
            chunk_overlap=50,
            max_document_chars=10000,
            allowed_local_dir=source_dir,
            archive_dir=temp_archive_dir,
            archive_enabled=True,
        )

        with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
            mock_load.return_value = ParsedDocument(
                source_uri=str(source_file),
                source_type="pdf",
                text="PDF extracted.",
            )

            result = service.ingest_from_uri(str(source_file))

            archive_path = Path(temp_archive_dir) / result.document_id / "original.pdf"
            assert archive_path.exists()
            assert archive_path.read_bytes() == b"%PDF-1.4\ntest"


def test_archive_same_document_id_overwrites_previous(
    mock_memory_store, mock_summarizer, temp_archive_dir
):
    """Test that ingesting same doc twice with same ID overwrites archive."""
    service = DocumentIngestionService(
        memory_store=mock_memory_store,
        summarizer=mock_summarizer,
        chunk_size=500,
        chunk_overlap=50,
        max_document_chars=10000,
        allowed_local_dir="/tmp",
        archive_dir=temp_archive_dir,
        archive_enabled=True,
    )

    with patch("business_agent.ingestion.service.load_document_from_uri") as mock_load:
        with patch("business_agent.ingestion.service.uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "same-doc-id"

            # First ingest
            mock_load.return_value = ParsedDocument(
                source_uri="http://example.com/v1.txt",
                source_type="txt",
                text="Version 1 content.",
            )

            with patch("business_agent.ingestion.service.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = b"Version 1"
                mock_get.return_value = mock_response

                service.ingest_from_uri("http://example.com/v1.txt")

            archive_file = Path(temp_archive_dir) / "same-doc-id" / "original.txt"
            assert archive_file.read_bytes() == b"Version 1"

            # Second ingest (overwrites)
            with patch("business_agent.ingestion.service.httpx.get") as mock_get:
                mock_response = MagicMock()
                mock_response.content = b"Version 2 updated"
                mock_get.return_value = mock_response

                service.ingest_from_uri("http://example.com/v2.txt")

            assert archive_file.read_bytes() == b"Version 2 updated"
