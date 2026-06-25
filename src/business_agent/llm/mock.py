"""Mock LLM client for testing (deterministic responses)."""

from __future__ import annotations

import json
from pathlib import Path


class MockLLMClient:
    """Mock LLM client for testing without calling OpenRouter."""

    def __init__(self, api_key: str = "mock", **kwargs) -> None:
        self.api_key = api_key
        self.call_count = 0

    def extract_metadata(
        self,
        document_text: str,
        source_uri: str,
    ) -> MockDocumentMetadata:
        """Extract metadata from text deterministically."""
        self.call_count += 1

        # Determine type from URI
        uri_lower = source_uri.lower()
        if "invoice" in uri_lower:
            doc_type = "invoice"
        elif "report" in uri_lower:
            doc_type = "report"
        elif "contract" in uri_lower:
            doc_type = "contract"
        elif "receipt" in uri_lower:
            doc_type = "receipt"
        else:
            doc_type = "other"

        # Extract keywords from text
        words = document_text.lower().split()
        keywords = [w for w in words if len(w) > 5][:3]

        # Determine vendor from text
        vendor = None
        for word in words:
            if word.isupper() and len(word) > 2:
                vendor = word
                break

        return MockDocumentMetadata(
            document_type=doc_type,
            vendor=vendor,
            department="finance",
            keywords=keywords,
        )

    def ocr_image(self, image_path: str | Path) -> str:
        """Mock OCR: return fixed text."""
        self.call_count += 1
        return f"[OCR text from {Path(image_path).name}: Sample extracted text from image.]"


class MockDocumentMetadata:
    """Mock document metadata."""

    def __init__(
        self,
        document_type: str,
        vendor: str | None = None,
        department: str | None = None,
        keywords: list[str] | None = None,
    ) -> None:
        self.document_type = document_type
        self.vendor = vendor
        self.department = department
        self.keywords = keywords or []

    def to_dict(self) -> dict:
        return {
            "document_type": self.document_type,
            "vendor": self.vendor,
            "department": self.department,
            "keywords": self.keywords,
        }
