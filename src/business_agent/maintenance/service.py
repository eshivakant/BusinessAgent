from __future__ import annotations

import re
import shutil
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from business_agent.ingestion.chunking import chunk_text
from business_agent.ingestion.parser import load_document_from_uri
from business_agent.ingestion.summarizer import Summarizer
from business_agent.maintenance.models import ComplianceCertificate, MaintenanceDocument, MaintenanceJob
from business_agent.memory.models import MemoryPayload, MemoryRecord
from business_agent.memory.store import MemoryStore
from business_agent.property.models import Property
from business_agent.property.registry import PropertyRegistry

STAGES = ["reported", "assigned", "quoted", "approved", "in_progress", "completed", "invoiced", "paid"]
URGENCY_THRESHOLDS = {"emergency": 4, "high": 24, "medium": 72, "low": 168}
REMINDER_DAYS = [90, 60, 30, 7]


class MaintenanceService:
    def __init__(
        self,
        property_registry: PropertyRegistry,
        memory_store: MemoryStore | None = None,
        summarizer: Summarizer | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        max_document_chars: int = 200000,
        storage_dir: str = "/data/maintenance",
        allowed_local_dir: str | None = None,
    ) -> None:
        self._property_registry = property_registry
        self._memory_store = memory_store
        self._summarizer = summarizer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_document_chars = max_document_chars
        self._storage_dir = Path(storage_dir)
        self._allowed_local_dir = Path(allowed_local_dir) if allowed_local_dir else self._storage_dir
        self._jobs: dict[str, MaintenanceJob] = {}
        self._documents: dict[str, MaintenanceDocument] = {}
        self._certificates: dict[str, ComplianceCertificate] = {}

    def create_job(self, property_id: str, title: str, description: str, *, urgency: str = "medium", tenancy_id: str | None = None) -> MaintenanceJob:
        if self._property_registry.get_property(property_id) is None:
            raise ValueError(f"Property not found: {property_id}")
        job = MaintenanceJob(
            id=f"job-{uuid.uuid4().hex[:8]}",
            property_id=property_id,
            tenancy_id=tenancy_id,
            title=title,
            description=description,
            urgency=urgency,
            stage="reported",
        )
        self._jobs[job.id] = job
        return job

    def get_job(self, job_id: str) -> MaintenanceJob | None:
        return self._jobs.get(job_id)

    def list_jobs(self, property_id: str | None = None, stage: str | None = None) -> list[MaintenanceJob]:
        jobs = list(self._jobs.values())
        if property_id:
            jobs = [item for item in jobs if item.property_id == property_id]
        if stage:
            jobs = [item for item in jobs if item.stage == stage]
        return sorted(jobs, key=lambda item: item.created_at, reverse=True)

    def advance_stage(self, job_id: str, stage: str) -> MaintenanceJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        if stage not in STAGES:
            raise ValueError(f"Invalid stage: {stage}")
        if STAGES.index(stage) != STAGES.index(job.stage) + 1:
            raise ValueError(f"Stage {stage} is not a valid progression from {job.stage}")
        job.stage = stage
        job.updated_at = datetime.now(timezone.utc)
        self._jobs[job.id] = job
        return job

    def assign_contractor(self, job_id: str, contractor_id: str) -> MaintenanceJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        job.contractor_id = contractor_id
        job.updated_at = datetime.now(timezone.utc)
        self._jobs[job.id] = job
        return job

    def ingest_document(
        self,
        job_id: str,
        source_path: str | Path,
        *,
        filename: str | None = None,
        document_subtype: str | None = None,
        event_date: date | None = None,
    ) -> MaintenanceDocument:
        job = self._jobs.get(job_id)
        if job is None:
            raise ValueError(f"Job not found: {job_id}")
        source_path = Path(source_path)
        if not source_path.exists():
            raise ValueError(f"Document does not exist: {source_path}")

        destination_dir = self._storage_dir / job_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        document_id = uuid.uuid4().hex
        stored_path = destination_dir / f"{document_id}{source_path.suffix.lower() or '.bin'}"
        shutil.copy2(source_path, stored_path)

        parsed = load_document_from_uri(str(stored_path), allowed_local_dir=str(self._storage_dir))
        text = parsed.text[: self._max_document_chars]
        summary = self._summarizer.summarize(text) if self._summarizer else text[:400]
        chunks = chunk_text(text, chunk_size=self._chunk_size, overlap=self._chunk_overlap)

        ingested_at = datetime.now(timezone.utc)
        effective_date = self._compute_effective_date(event_date, ingested_at)
        qdrant_ids: list[str] = []
        if self._memory_store is not None:
            summary_payload = MemoryPayload(
                event_date=event_date,
                ingested_at=ingested_at,
                effective_date=effective_date,
                source_type="maintenance_document",
                source_uri=str(stored_path),
                archived_file_path=None,
                record_type="summary",
                chunk_index=None,
                chunk_count=len(chunks),
                summary=summary,
                property_id=job.property_id,
                job_id=job.id,
                document_subtype=document_subtype or self._infer_subtype(source_path.name),
                document_type=parsed.source_type,
                amount=None,
            )
            summary_id = f"{document_id}:summary"
            qdrant_ids.append(summary_id)
            records = [MemoryRecord(id=summary_id, text=summary, payload=summary_payload)]
            for index, chunk in enumerate(chunks):
                payload = MemoryPayload(
                    event_date=event_date,
                    ingested_at=ingested_at,
                    effective_date=effective_date,
                    source_type="maintenance_document",
                    source_uri=str(stored_path),
                    archived_file_path=None,
                    record_type="chunk",
                    chunk_index=index,
                    chunk_count=len(chunks),
                    summary=summary,
                    property_id=job.property_id,
                    job_id=job.id,
                    document_subtype=document_subtype or self._infer_subtype(source_path.name),
                    document_type=parsed.source_type,
                    amount=None,
                )
                chunk_id = f"{document_id}:chunk:{index}"
                qdrant_ids.append(chunk_id)
                records.append(MemoryRecord(id=chunk_id, text=chunk, payload=payload))
            self._memory_store.upsert(records)

        inferred_subtype = document_subtype or self._infer_subtype(source_path.name)
        document = MaintenanceDocument(
            id=document_id,
            job_id=job.id,
            document_subtype=inferred_subtype,
            filename=filename or source_path.name,
            stored_path=str(stored_path),
            ingested_at=ingested_at,
            extracted_fields=self._extract_fields(text),
            qdrant_ids=qdrant_ids,
        )
        self._documents[document.id] = document
        return document

    def compare_quotes(self, job_id: str) -> list[dict[str, Any]]:
        documents = [item for item in self._documents.values() if item.job_id == job_id]
        comparisons = []
        for document in documents:
            comparisons.append(
                {
                    "document_id": document.id,
                    "contractor_name": document.contractor_name or "",
                    "amount": float(document.amount or Decimal("0")),
                    "vat_amount": float(document.vat_amount or Decimal("0")),
                    "total": float((document.amount or Decimal("0")) + (document.vat_amount or Decimal("0"))),
                    "document_subtype": document.document_subtype,
                    "recommended": False,
                }
            )
        if comparisons:
            cheapest = min(comparisons, key=lambda item: item["total"])
            cheapest["recommended"] = True
        return comparisons

    def spend(self, property_id: str, year: int | None = None) -> dict[str, Any]:
        jobs = [job for job in self._jobs.values() if job.property_id == property_id]
        if year is not None:
            jobs = [job for job in jobs if job.created_at.year == year]
        total_spend = sum((job.invoice_amount or Decimal("0")) for job in jobs)
        return {
            "property_id": property_id,
            "year": year,
            "total_spend": float(total_spend),
            "jobs": [
                {
                    "job_id": job.id,
                    "title": job.title,
                    "invoice_amount": float(job.invoice_amount or Decimal("0")),
                }
                for job in jobs
            ],
        }

    def add_certificate(self, property_id: str, certificate_type: str, *, expiry_date: date | None = None) -> ComplianceCertificate:
        certificate = ComplianceCertificate(
            id=f"cert-{uuid.uuid4().hex[:8]}",
            property_id=property_id,
            certificate_type=certificate_type,
            issue_date=date.today(),
            expiry_date=expiry_date,
        )
        self._certificates[certificate.id] = certificate
        return certificate

    def list_certificates(self, property_id: str | None = None) -> list[ComplianceCertificate]:
        certificates = list(self._certificates.values())
        if property_id:
            certificates = [item for item in certificates if item.property_id == property_id]
        return sorted(certificates, key=lambda item: item.expiry_date or date.max, reverse=False)

    def overdue_certificates(self) -> list[ComplianceCertificate]:
        today = date.today()
        return [cert for cert in self._certificates.values() if cert.expiry_date is not None and cert.expiry_date < today]

    def reminders_for_certificate(self, certificate: ComplianceCertificate, *, now: date | None = None) -> list[str]:
        if certificate.expiry_date is None:
            return []
        reference_day = now or date.today()
        days_left = (certificate.expiry_date - reference_day).days
        if days_left <= 7:
            threshold = 7
        elif days_left <= 30:
            threshold = 30
        elif days_left <= 60:
            threshold = 60
        elif days_left <= 90:
            threshold = 90
        else:
            return []
        if str(threshold) in certificate.reminders_sent:
            return []
        return [str(threshold)]

    def mark_reminder_sent(self, certificate_id: str, reminder: str) -> None:
        certificate = self._certificates.get(certificate_id)
        if certificate is None:
            return
        if reminder not in certificate.reminders_sent:
            certificate.reminders_sent.append(reminder)

    def _extract_fields(self, text: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        match = re.search(r"contractor[:\s]+([A-Za-z0-9 &.-]+)", text, re.IGNORECASE)
        if match:
            fields["contractor_name"] = match.group(1).strip()
        match = re.search(r"amount[:\s]+£?([0-9,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if match:
            fields["amount"] = match.group(1).replace(",", "")
        match = re.search(r"vat[:\s]+£?([0-9,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if match:
            fields["vat_amount"] = match.group(1).replace(",", "")
        match = re.search(r"warranty[:\s]+([0-9]+)", text, re.IGNORECASE)
        if match:
            fields["warranty_period"] = int(match.group(1))
        return fields

    def _infer_subtype(self, filename: str) -> str:
        lowered = filename.lower()
        if "quote" in lowered:
            return "quote"
        if "invoice" in lowered:
            return "invoice"
        return "other"

    def _compute_effective_date(self, event_date: date | None, ingested_at: datetime) -> datetime:
        if event_date is None:
            return ingested_at
        return datetime.combine(event_date, time.min, tzinfo=timezone.utc)
