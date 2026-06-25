"""Domain models for property management."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional


class PropertyStatus(str, Enum):
    """Property status in portfolio."""
    OWNED = "owned"
    UNDER_OFFER = "under_offer"
    VIEWING = "viewing"
    SOLD = "sold"
    PENDING_PURCHASE = "pending_purchase"


class MaintenanceStatus(str, Enum):
    """Maintenance request status."""
    REPORTED = "reported"
    QUOTED = "quoted"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ContactType(str, Enum):
    """Type of business contact."""
    SOLICITOR = "solicitor"
    MORTGAGE_BROKER = "mortgage_broker"
    ESTATE_AGENT = "estate_agent"
    CONTRACTOR = "contractor"
    SURVEYOR = "surveyor"
    ACCOUNTANT = "accountant"
    OTHER = "other"


@dataclass
class Property:
    """Represents a buy-to-let property."""
    id: str
    address: str
    purchase_date: date | None
    purchase_price: Decimal | None
    current_value: Decimal | None
    status: PropertyStatus
    bedrooms: int | None = None
    bathrooms: int | None = None
    square_feet: int | None = None
    postcode: str | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class Mortgage:
    """Represents a mortgage on a property."""
    id: str
    property_id: str
    lender: str
    principal: Decimal
    interest_rate: Decimal  # Annual rate as percentage (e.g., 4.5)
    term_months: int
    start_date: date
    monthly_payment: Decimal
    product_type: str | None = None  # e.g., "Fixed 2 year", "Tracker", "Variable"
    end_date: date | None = None  # Calculated or set
    balance_remaining: Decimal | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def months_until_expiry(self) -> int | None:
        """Calculate months until mortgage expires."""
        if not self.end_date:
            return None
        today = date.today()
        if self.end_date < today:
            return 0
        months = (self.end_date.year - today.year) * 12 + (self.end_date.month - today.month)
        return max(0, months)

    def is_expiring_soon(self, months: int = 6) -> bool:
        """Check if mortgage expires within specified months."""
        months_left = self.months_until_expiry()
        return months_left is not None and 0 < months_left <= months


@dataclass
class Tenant:
    """Represents a tenant renting a property."""
    id: str
    property_id: str
    name: str
    email: str | None
    phone: str | None
    lease_start: date
    lease_end: date
    monthly_rent: Decimal
    deposit: Decimal
    is_active: bool = True
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def months_until_lease_end(self) -> int:
        """Calculate months until lease ends."""
        today = date.today()
        if self.lease_end < today:
            return 0
        months = (self.lease_end.year - today.year) * 12 + (self.lease_end.month - today.month)
        return max(0, months)


@dataclass
class Contact:
    """Business contact (solicitor, broker, contractor, etc.)."""
    id: str
    name: str
    contact_type: ContactType
    company: str | None
    email: str | None
    phone: str | None
    specialty: str | None  # e.g., "Commercial property", "Plumbing", "Residential mortgages"
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class MaintenanceRequest:
    """Maintenance or repair request for a property."""
    id: str
    property_id: str
    reported_date: date
    description: str
    status: MaintenanceStatus
    category: str | None = None  # e.g., "Plumbing", "Electrical", "Roofing"
    estimated_cost: Decimal | None = None
    actual_cost: Decimal | None = None
    contractor_id: str | None = None  # Reference to Contact
    completed_date: date | None = None
    notes: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
