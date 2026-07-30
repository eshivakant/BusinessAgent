from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


@dataclass
class ConveyancingTransaction:
    id: str
    property_id: str
    transaction_type: str
    stage: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str | None = None
    own_solicitor_id: str | None = None
    counterparty_solicitor_name: str | None = None
    counterparty_solicitor_email: str | None = None
    estate_agent_id: str | None = None
    offer_date: date | None = None
    solicitor_instructed_date: date | None = None
    searches_ordered_date: date | None = None
    survey_date: date | None = None
    mortgage_offer_date: date | None = None
    exchange_date: date | None = None
    completion_date: date | None = None
    target_completion_date: date | None = None


@dataclass
class MortgageOffer:
    id: str
    transaction_id: str
    lender_name: str
    loan_amount: Decimal
    initial_rate: Decimal
    revert_rate: Decimal | None = None
    fix_period_months: int | None = None
    monthly_payment: Decimal | None = None
    arrangement_fee: Decimal | None = None
    early_repayment_charges: str | None = None
    offer_expiry_date: date | None = None
    document_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def total_cost_5yr(self) -> Decimal:
        monthly = self.monthly_payment or Decimal("0")
        fee = self.arrangement_fee or Decimal("0")
        return monthly * Decimal("60") + fee


@dataclass
class ConveyancingDocument:
    id: str
    transaction_id: str
    document_subtype: str
    filename: str
    stored_path: str
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    qdrant_ids: list[str] = field(default_factory=list)
