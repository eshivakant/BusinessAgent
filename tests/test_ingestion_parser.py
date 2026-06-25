from __future__ import annotations

from pathlib import Path

import pytest

from business_agent.ingestion import parser


def test_resolve_source_type_by_extension() -> None:
    assert parser.resolve_source_type("report.txt", None) == "txt"
    assert parser.resolve_source_type("report.pdf", None) == "pdf"
    assert parser.resolve_source_type("report.docx", None) == "docx"


def test_resolve_source_type_rejects_unsupported() -> None:
    with pytest.raises(ValueError, match="Unsupported source type"):
        parser.resolve_source_type("report.csv", "text/csv")


def test_load_document_from_local_file(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    file_path = docs_dir / "sample.txt"
    file_path.write_text("line one\n\nline two\n", encoding="utf-8")

    parsed = parser.load_document_from_uri(str(file_path), allowed_local_dir=str(docs_dir))
    assert parsed.source_type == "txt"
    assert parsed.text == "line one\nline two"


def test_load_document_blocks_file_outside_allowed_dir(tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    file_path = other_dir / "sample.txt"
    file_path.write_text("data", encoding="utf-8")

    with pytest.raises(PermissionError, match="outside INGESTION_ALLOWED_LOCAL_DIR"):
        parser.load_document_from_uri(str(file_path), allowed_local_dir=str(docs_dir))


def test_parse_document_bytes_pdf_uses_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePage:
        def extract_text(self) -> str:
            return "PDF text"

    class FakePdfReader:
        def __init__(self, _: object) -> None:
            self.pages = [FakePage(), FakePage()]

    monkeypatch.setattr(parser, "PdfReader", FakePdfReader)
    output = parser.parse_document_bytes(b"%PDF-fake", "pdf")
    assert output == "PDF text\nPDF text"


def test_parse_document_bytes_docx_uses_document(monkeypatch: pytest.MonkeyPatch) -> None:
    class Paragraph:
        def __init__(self, text: str) -> None:
            self.text = text

    class FakeDoc:
        def __init__(self, _: object) -> None:
            self.paragraphs = [Paragraph("Row 1"), Paragraph("Row 2")]

    monkeypatch.setattr(parser, "Document", FakeDoc)
    output = parser.parse_document_bytes(b"docx-bytes", "docx")
    assert output == "Row 1\nRow 2"


def test_load_document_from_http(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def __init__(self) -> None:
            self.content = b"remote content"
            self.headers = {"Content-Type": "text/plain"}

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, timeout: float, follow_redirects: bool) -> FakeResponse:
        assert url == "https://example.com/info.txt"
        assert timeout == 30.0
        assert follow_redirects is True
        return FakeResponse()

    monkeypatch.setattr(parser.httpx, "get", fake_get)
    parsed = parser.load_document_from_uri("https://example.com/info.txt", allowed_local_dir=None)
    assert parsed.source_type == "txt"
    assert parsed.text == "remote content"
