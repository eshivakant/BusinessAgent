"""Document registry for storing and retrieving document metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from pydantic import BaseModel


class DocumentInfo(BaseModel):
    """Document-level metadata record."""

    document_id: str
    title: str | None = None
    document_type: str  # invoice, report, contract, etc.
    vendor: str | None = None
    department: str | None = None
    keywords: list[str] = []
    source_uri: str
    source_type: str  # txt, pdf, docx, png, jpg, etc.
    archived_file_path: str | None = None
    ingested_at: datetime
    event_date: datetime | None = None
    effective_date: datetime
    summary: str | None = None
    chunk_count: int = 0
    property_address: str | None = None
    property_id: str | None = None
    amount: float | None = None


class DocumentQueryFilter(BaseModel):
    """Filters for document retrieval."""

    document_type: str | None = None
    vendor: str | None = None
    department: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    keyword: str | None = None
    limit: int = 20
    property_address: str | None = None
    property_id: str | None = None

    def matches(self, doc: DocumentInfo) -> bool:
        """Check if document matches all filters."""
        if self.document_type and doc.document_type != self.document_type:
            return False
        if self.vendor and doc.vendor != self.vendor:
            return False
        if self.department and doc.department != self.department:
            return False
        if self.date_from and doc.effective_date < self.date_from:
            return False
        if self.date_to and doc.effective_date > self.date_to:
            return False
        if self.property_address:
            if not doc.property_address:
                return False
            if self.property_address.lower() not in doc.property_address.lower():
                return False
        if self.property_id and doc.property_id != self.property_id:
            return False
        if self.keyword:
            keyword_lower = self.keyword.lower()
            if not any(keyword_lower in k.lower() for k in doc.keywords):
                if not (doc.title and keyword_lower in doc.title.lower()):
                    if not (doc.summary and keyword_lower in doc.summary.lower()):
                        return False
        return True


class DocumentRegistry:
    """In-memory document registry (protocol)."""

    def register(self, doc: DocumentInfo) -> None:
        """Register a document."""
        raise NotImplementedError

    def get(self, document_id: str) -> DocumentInfo | None:
        """Retrieve a document by ID."""
        raise NotImplementedError

    def query(
        self,
        filters: DocumentQueryFilter | None = None,
        **kwargs: object,
    ) -> list[DocumentInfo]:
        """Query documents by filters."""
        raise NotImplementedError

    def list_all(self, limit: int = 100) -> list[DocumentInfo]:
        """List all documents."""
        raise NotImplementedError


class InMemoryDocumentRegistry(DocumentRegistry):
    """Simple in-memory implementation for testing."""

    def __init__(self) -> None:
        self.documents: dict[str, DocumentInfo] = {}

    def register(self, doc: DocumentInfo) -> None:
        self.documents[doc.document_id] = doc

    def get(self, document_id: str) -> DocumentInfo | None:
        return self.documents.get(document_id)

    def query(
        self,
        filters: DocumentQueryFilter | None = None,
        *,
        document_type: str | None = None,
        vendor: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
        property_address: str | None = None,
        property_id: str | None = None,
        keyword: str | None = None,
    ) -> list[DocumentInfo]:
        """Query documents by filters.

        Accepts either a DocumentQueryFilter object or keyword arguments.
        Keyword arguments take precedence when both are provided.
        """
        if filters is None:
            filters = DocumentQueryFilter(
                document_type=document_type,
                vendor=vendor,
                date_from=date_from,
                date_to=date_to,
                limit=limit,
                property_address=property_address,
                property_id=property_id,
                keyword=keyword,
            )
        matches = [doc for doc in self.documents.values() if filters.matches(doc)]
        return matches[: filters.limit]

    def list_all(self, limit: int = 100) -> list[DocumentInfo]:
        return list(self.documents.values())[:limit]
