from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class TenantDocument:
    id: str
    tenancy_id: str
    filename: str
    stored_path: str
    document_type: str
    ingested_at: datetime
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    qdrant_ids: list[str] = field(default_factory=list)
    property_id: str | None = None
    source_uri: str | None = None
    summary: str | None = None
    chunk_count: int = 0


@dataclass
class GeneratedAgreement:
    id: str
    tenancy_id: str
    template_name: str
    generated_at: datetime
    stored_path: str
    pdf_path: str | None = None


@dataclass(frozen=True)
class TemplateSelectionResult:
    template_name: str | None
    candidates: list[str]
    needs_selection: bool
