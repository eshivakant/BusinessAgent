"""Mock LLM client for testing (deterministic responses)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


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
        return self._extract_structured(document_text, source_uri)

    def extract_structured_metadata(
        self,
        document_text: str,
        source_uri: str,
    ) -> MockDocumentMetadata:
        """Extract structured metadata including property address and amount."""
        self.call_count += 1
        return self._extract_structured(document_text, source_uri)

    def _extract_structured(self, document_text: str, source_uri: str) -> "MockDocumentMetadata":
        """Shared extraction logic for mock."""
        # Determine type from URI and text
        uri_lower = source_uri.lower()
        text_lower = document_text.lower()

        if "invoice" in uri_lower or "invoice" in text_lower:
            doc_type = "invoice"
        elif "mortgage" in uri_lower or "mortgage_offer" in text_lower:
            doc_type = "mortgage_offer"
        elif "tenancy" in uri_lower or "tenancy" in text_lower or "tenancy_agreement" in text_lower:
            doc_type = "tenancy_agreement"
        elif "epc" in uri_lower or "epc" in text_lower or "energy performance" in text_lower:
            doc_type = "epc_certificate"
        elif "completion" in uri_lower or "completion" in text_lower:
            doc_type = "completion_statement"
        elif "bank_statement" in uri_lower or "bank statement" in text_lower:
            doc_type = "bank_statement"
        elif "report" in uri_lower:
            doc_type = "report"
        elif "contract" in uri_lower or "contract" in text_lower:
            doc_type = "contract"
        elif "receipt" in uri_lower:
            doc_type = "receipt"
        else:
            doc_type = "other"

        # Extract keywords from text
        words = document_text.lower().split()
        keywords = [w for w in words if len(w) > 5][:5]

        # Determine vendor from text
        vendor = None
        for word in words:
            if word.isupper() and len(word) > 2:
                vendor = word
                break

        # Extract property address (look for patterns like "123 Main St")
        import re
        property_address = None
        address_patterns = [
            r'\b(\d+\s+[A-Z][a-z]+\s+(?:Street|St|Drive|Dr|Avenue|Ave|Road|Rd|Lane|Ln|Way|Close|Court|Ct|Place|Pl))\b',
            r'\b(\d+\s+[A-Z][a-z]+\s+[A-Z][a-z]+\s+(?:Street|St|Drive|Dr|Avenue|Ave|Road|Rd|Lane|Ln|Way|Close|Court|Ct|Place|Pl))\b',
        ]
        for pattern in address_patterns:
            match = re.search(pattern, document_text)
            if match:
                property_address = match.group(1)
                break

        # Extract amount (look for £ or $ followed by numbers)
        amount = None
        amount_match = re.search(r'[£$]\s*([\d,]+\.?\d*)', document_text)
        if amount_match:
            try:
                amount = float(amount_match.group(1).replace(",", ""))
            except ValueError:
                pass

        return MockDocumentMetadata(
            document_type=doc_type,
            vendor=vendor,
            department="finance",
            keywords=keywords,
            property_address=property_address,
            amount=amount,
        )

    def ocr_image(self, image_path: str | Path) -> str:
        """Mock OCR: return fixed text."""
        self.call_count += 1
        return f"[OCR text from {Path(image_path).name}: Sample extracted text from image.]"

    def transcribe_audio(self, audio_path: str | Path) -> str:
        """Mock transcription: return fixed text."""
        self.call_count += 1
        return f"[Transcribed text from {Path(audio_path).name}: This is a sample transcription of a voice note.]"

    def answer_question(self, question: str, context: str) -> str:
        """Mock question answering: return a formatted response."""
        self.call_count += 1
        # Simple keyword matching for deterministic responses
        q_lower = question.lower()
        if "pet" in q_lower and "no pet" in context.lower():
            return "Yes, the tenancy agreement contains a 'no pet' clause."
        elif "epc" in q_lower and "expir" in q_lower:
            # Try to find a date in context
            import re
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', context)
            if date_match:
                return f"The EPC certificate expires on {date_match.group(1)}."
            return "I couldn't find the EPC expiry date in the available documents."
        elif "compare" in q_lower and "mortgage" in q_lower:
            return "Based on the available mortgage offers, here is a comparison of rates and terms."
        elif "invoice" in q_lower:
            return "I found a matching invoice for that transaction amount."
        return f"Based on the available context, here is what I found regarding: {question[:100]}"


class MockDocumentMetadata:
    """Mock document metadata."""

    def __init__(
        self,
        document_type: str,
        vendor: str | None = None,
        department: str | None = None,
        keywords: list[str] | None = None,
        property_address: str | None = None,
        amount: float | None = None,
    ) -> None:
        self.document_type = document_type
        self.vendor = vendor
        self.department = department
        self.keywords = keywords or []
        self.property_address = property_address
        self.amount = amount

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_type": self.document_type,
            "vendor": self.vendor,
            "department": self.department,
            "keywords": self.keywords,
            "property_address": self.property_address,
            "amount": self.amount,
        }
