from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


@dataclass
class MaintenanceJob:
    id: str
    property_id: str
    tenancy_id: str | None
    title: str
    description: str
    urgency: str
    stage: str
    contractor_id: str | None = None
    scheduled_date: date | None = None
    completed_date: date | None = None
    quote_amount: Decimal | None = None
    approved_amount: Decimal | None = None
    invoice_amount: Decimal | None = None
    paid_amount: Decimal | None = None
    paid_date: date | None = None
    warranty_until: date | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ComplianceCertificate:
    id: str
    property_id: str
    certificate_type: str
    issue_date: date | None = None
    expiry_date: date | None = None
    certificate_number: str | None = None
    document_id: str | None = None
    notes: str | None = None
    reminders_sent: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MaintenanceDocument:
    id: str
    job_id: str
    document_subtype: str
    contractor_name: str | None = None
    amount: Decimal | None = None
    vat_amount: Decimal | None = None
    document_date: date | None = None
    filename: str = ""
    stored_path: str = ""
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    qdrant_ids: list[str] = field(default_factory=list)
