from __future__ import annotations

import re
import shutil
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from business_agent.conveyancing.models import ConveyancingDocument, ConveyancingTransaction, MortgageOffer
from business_agent.ingestion.chunking import chunk_text
from business_agent.ingestion.parser import load_document_from_uri
from business_agent.ingestion.summarizer import Summarizer
from business_agent.memory.models import MemoryPayload, MemoryRecord
from business_agent.memory.store import MemoryStore
from business_agent.property.models import Property
from business_agent.property.registry import PropertyRegistry

PURCHASE_STAGES = [
    "offer_accepted",
    "solicitor_instructed",
    "searches_ordered",
    "survey_booked",
    "survey_complete",
    "mortgage_offer_received",
    "exchange",
    "completion",
]

SALE_STAGES = ["listed", "offer_accepted", "solicitor_instructed", "draft_contracts_issued", "enquiries", "exchange", "completion"]

STAGE_ALERT_DAYS = {
    "solicitor_instructed": 7,
    "searches_ordered": 21,
    "survey_booked": 14,
    "mortgage_offer_received": 30,
    "exchange": 56,
}


class ConveyancingService:
    def __init__(
        self,
        property_registry: PropertyRegistry,
        memory_store: MemoryStore | None = None,
        summarizer: Summarizer | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        max_document_chars: int = 200000,
        storage_dir: str = "/data/conveyancing",
        llm_client: Any | None = None,
        allowed_local_dir: str | None = None,
    ) -> None:
        self._property_registry = property_registry
        self._memory_store = memory_store
        self._summarizer = summarizer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_document_chars = max_document_chars
        self._storage_dir = Path(storage_dir)
        self._llm_client = llm_client
        self._allowed_local_dir = Path(allowed_local_dir) if allowed_local_dir else self._storage_dir
        self._transactions: dict[str, ConveyancingTransaction] = {}
        self._documents: dict[str, ConveyancingDocument] = {}
        self._mortgage_offers: dict[str, MortgageOffer] = {}

    def create_transaction(
        self,
        property_id: str,
        transaction_type: str,
        *,
        stage: str | None = None,
        notes: str | None = None,
    ) -> ConveyancingTransaction:
        if self._property_registry.get_property(property_id) is None:
            raise ValueError(f"Property not found: {property_id}")
        if transaction_type not in {"purchase", "sale"}:
            raise ValueError("transaction_type must be purchase or sale")
        allowed_stages = PURCHASE_STAGES if transaction_type == "purchase" else SALE_STAGES
        if stage is None:
            stage = allowed_stages[0] if transaction_type == "purchase" else allowed_stages[1]
        if stage not in allowed_stages:
            raise ValueError(f"Invalid stage for {transaction_type}: {stage}")
        transaction = ConveyancingTransaction(
            id=f"txn-{uuid.uuid4().hex[:8]}",
            property_id=property_id,
            transaction_type=transaction_type,
            stage=stage,
            notes=notes,
        )
        self._transactions[transaction.id] = transaction
        return transaction

    def get_transaction(self, transaction_id: str) -> ConveyancingTransaction | None:
        return self._transactions.get(transaction_id)

    def list_transactions(self, property_id: str | None = None, status: str | None = None) -> list[ConveyancingTransaction]:
        transactions = list(self._transactions.values())
        if property_id:
            transactions = [item for item in transactions if item.property_id == property_id]
        if status == "open":
            transactions = [item for item in transactions if item.stage != "completion"]
        return sorted(transactions, key=lambda item: item.created_at, reverse=True)

    def update_transaction(self, transaction_id: str, updates: dict[str, Any]) -> ConveyancingTransaction | None:
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            return None
        for field_name, value in updates.items():
            if value is not None and hasattr(transaction, field_name):
                setattr(transaction, field_name, value)
        transaction.updated_at = datetime.now(timezone.utc)
        self._transactions[transaction.id] = transaction
        return transaction

    def advance_stage(self, transaction_id: str, stage: str) -> ConveyancingTransaction:
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise ValueError(f"Transaction not found: {transaction_id}")
        allowed_stages = PURCHASE_STAGES if transaction.transaction_type == "purchase" else SALE_STAGES
        if stage not in allowed_stages:
            raise ValueError(f"Invalid stage: {stage}")
        if stage not in allowed_stages[allowed_stages.index(transaction.stage) + 1 :]:
            raise ValueError(f"Stage {stage} is not a valid progression from {transaction.stage}")
        transaction.stage = stage
        today = date.today()
        if stage == "offer_accepted":
            transaction.offer_date = transaction.offer_date or today
        elif stage == "solicitor_instructed":
            transaction.solicitor_instructed_date = transaction.solicitor_instructed_date or today
        elif stage == "searches_ordered":
            transaction.searches_ordered_date = transaction.searches_ordered_date or today
        elif stage == "survey_booked":
            transaction.survey_date = transaction.survey_date or today
        elif stage == "mortgage_offer_received":
            transaction.mortgage_offer_date = transaction.mortgage_offer_date or today
        elif stage == "exchange":
            transaction.exchange_date = transaction.exchange_date or today
        elif stage == "completion":
            transaction.completion_date = transaction.completion_date or today
        transaction.updated_at = datetime.now(timezone.utc)
        self._transactions[transaction.id] = transaction
        return transaction

    def ingest_document(
        self,
        transaction_id: str,
        source_path: str | Path,
        *,
        filename: str | None = None,
        document_subtype: str | None = None,
        event_date: date | None = None,
    ) -> ConveyancingDocument:
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise ValueError(f"Transaction not found: {transaction_id}")
        source_path = Path(source_path)
        if not source_path.exists():
            raise ValueError(f"Document does not exist: {source_path}")

        destination_dir = self._storage_dir / transaction_id
        destination_dir.mkdir(parents=True, exist_ok=True)
        if document_subtype == "mortgage_offer":
            destination_dir = destination_dir / "mortgage-offers"
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
                source_type="conveyancing_document",
                source_uri=str(stored_path),
                archived_file_path=None,
                record_type="summary",
                chunk_index=None,
                chunk_count=len(chunks),
                summary=summary,
                property_id=transaction.property_id,
                transaction_id=transaction.id,
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
                    source_type="conveyancing_document",
                    source_uri=str(stored_path),
                    archived_file_path=None,
                    record_type="chunk",
                    chunk_index=index,
                    chunk_count=len(chunks),
                    summary=summary,
                    property_id=transaction.property_id,
                    transaction_id=transaction.id,
                    document_subtype=document_subtype or self._infer_subtype(source_path.name),
                    document_type=parsed.source_type,
                    amount=None,
                )
                chunk_id = f"{document_id}:chunk:{index}"
                qdrant_ids.append(chunk_id)
                records.append(MemoryRecord(id=chunk_id, text=chunk, payload=payload))
            self._memory_store.upsert(records)

        inferred_subtype = document_subtype or self._infer_subtype(source_path.name)
        document = ConveyancingDocument(
            id=document_id,
            transaction_id=transaction.id,
            document_subtype=inferred_subtype,
            filename=filename or source_path.name,
            stored_path=str(stored_path),
            ingested_at=ingested_at,
            extracted_fields={},
            qdrant_ids=qdrant_ids,
        )
        self._documents[document.id] = document

        if inferred_subtype == "mortgage_offer":
            extracted = self._extract_mortgage_offer_fields(text)
            document.extracted_fields = extracted
            offer = MortgageOffer(
                id=f"offer-{uuid.uuid4().hex[:8]}",
                transaction_id=transaction.id,
                lender_name=extracted.get("lender_name", ""),
                loan_amount=Decimal(str(extracted.get("loan_amount", "0"))),
                initial_rate=Decimal(str(extracted.get("initial_rate", "0"))),
                revert_rate=Decimal(str(extracted.get("revert_rate", "0"))) if extracted.get("revert_rate") else None,
                fix_period_months=int(extracted["fix_period_months"]) if extracted.get("fix_period_months") is not None else None,
                monthly_payment=Decimal(str(extracted.get("monthly_payment", "0"))) if extracted.get("monthly_payment") else None,
                arrangement_fee=Decimal(str(extracted.get("arrangement_fee", "0"))) if extracted.get("arrangement_fee") else None,
                early_repayment_charges=extracted.get("early_repayment_charges"),
                offer_expiry_date=extracted.get("offer_expiry_date"),
                document_id=document.id,
            )
            self._mortgage_offers[offer.id] = offer

        return document

    def list_documents(self, transaction_id: str) -> list[ConveyancingDocument]:
        return [item for item in self._documents.values() if item.transaction_id == transaction_id]

    def compare_mortgage_offers(self, transaction_id: str) -> list[dict[str, Any]]:
        offers = [offer for offer in self._mortgage_offers.values() if offer.transaction_id == transaction_id]
        comparisons = []
        for offer in offers:
            comparisons.append(
                {
                    "offer_id": offer.id,
                    "lender_name": offer.lender_name,
                    "loan_amount": float(offer.loan_amount),
                    "monthly_payment": float(offer.monthly_payment or Decimal("0")),
                    "arrangement_fee": float(offer.arrangement_fee or Decimal("0")),
                    "total_cost_5yr": float(offer.total_cost_5yr()),
                    "recommended": False,
                }
            )
        if comparisons:
            cheapest = min(comparisons, key=lambda item: item["total_cost_5yr"])
            cheapest["recommended"] = True
        return comparisons

    def draft_chase_message(self, transaction_id: str) -> str:
        transaction = self._transactions.get(transaction_id)
        if transaction is None:
            raise ValueError(f"Transaction not found: {transaction_id}")
        return f"Hi {transaction.counterparty_solicitor_name or 'solicitor'}, please provide an update on transaction {transaction.id}."

    def list_overdue(self, *, now: date | None = None) -> list[dict[str, Any]]:
        reference_day = now or date.today()
        overdue = []
        for transaction in self._transactions.values():
            for stage, threshold_days in STAGE_ALERT_DAYS.items():
                if transaction.stage != stage:
                    continue
                reference_date = self._stage_reference_date(transaction, stage)
                if reference_date is None:
                    continue
                age = (reference_day - reference_date).days
                if age > threshold_days:
                    overdue.append(
                        {
                            "transaction_id": transaction.id,
                            "property_id": transaction.property_id,
                            "stage": stage,
                            "days_overdue": age - threshold_days,
                        }
                    )
        return overdue

    def _stage_reference_date(self, transaction: ConveyancingTransaction, stage: str) -> date | None:
        mapping = {
            "solicitor_instructed": transaction.solicitor_instructed_date,
            "searches_ordered": transaction.searches_ordered_date,
            "survey_booked": transaction.survey_date,
            "mortgage_offer_received": transaction.mortgage_offer_date,
            "exchange": transaction.offer_date,
        }
        return mapping.get(stage)

    def _infer_subtype(self, filename: str) -> str:
        lowered = filename.lower()
        if "mortgage" in lowered:
            return "mortgage_offer"
        if lowered.endswith(".pdf"):
            return "other"
        return "other"

    def _extract_mortgage_offer_fields(self, text: str) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        match = re.search(r"lender(?: name)?[:\s]+([A-Za-z0-9 &.-]+)", text, re.IGNORECASE)
        if match:
            fields["lender_name"] = match.group(1).strip()
        match = re.search(r"loan amount[:\s]+£?([0-9,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if match:
            fields["loan_amount"] = match.group(1).replace(",", "")
        match = re.search(r"initial rate[:\s]+([0-9.]+)%?", text, re.IGNORECASE)
        if match:
            fields["initial_rate"] = match.group(1)
        match = re.search(r"revert rate[:\s]+([0-9.]+)%?", text, re.IGNORECASE)
        if match:
            fields["revert_rate"] = match.group(1)
        match = re.search(r"fix period[:\s]+([0-9]+)", text, re.IGNORECASE)
        if match:
            fields["fix_period_months"] = int(match.group(1))
        match = re.search(r"monthly payment[:\s]+£?([0-9,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if match:
            fields["monthly_payment"] = match.group(1).replace(",", "")
        match = re.search(r"arrangement fee[:\s]+£?([0-9,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if match:
            fields["arrangement_fee"] = match.group(1).replace(",", "")
        match = re.search(r"offer expiry[:\s]+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
        if match:
            fields["offer_expiry_date"] = date.fromisoformat(match.group(1))
        return fields

    def _compute_effective_date(self, event_date: date | None, ingested_at: datetime) -> datetime:
        if event_date is None:
            return ingested_at
        return datetime.combine(event_date, time.min, tzinfo=timezone.utc)
