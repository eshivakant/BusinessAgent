from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterator

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class PropertyRecord(Base):
    __tablename__ = "properties"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    current_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    square_feet: Mapped[int | None] = mapped_column(Integer, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    mortgages: Mapped[list["MortgageRecord"]] = relationship(
        back_populates="property_record",
        cascade="all, delete-orphan",
    )
    tenants: Mapped[list["TenantRecord"]] = relationship(
        back_populates="property_record",
        cascade="all, delete-orphan",
    )
    maintenance_requests: Mapped[list["MaintenanceRequestRecord"]] = relationship(
        back_populates="property_record",
        cascade="all, delete-orphan",
    )


class MortgageRecord(Base):
    __tablename__ = "mortgages"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lender: Mapped[str] = mapped_column(String(255), nullable=False)
    principal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    product_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    balance_remaining: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    property_record: Mapped[PropertyRecord] = relationship(back_populates="mortgages")


class TenantRecord(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_start: Mapped[date] = mapped_column(Date, nullable=False)
    lease_end: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_rent: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    deposit: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    national_insurance_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    passport_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    annual_income: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    property_record: Mapped[PropertyRecord] = relationship(back_populates="tenants")


class TenantDocumentRecord(Base):
    __tablename__ = "tenant_documents"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenancy_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    extracted_fields: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    qdrant_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    property_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class GeneratedAgreementRecord(Base):
    __tablename__ = "generated_agreements"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    tenancy_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class ContactRecord(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    specialty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MaintenanceRequestRecord(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    property_id: Mapped[str] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reported_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    contractor_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    property_record: Mapped[PropertyRecord] = relationship(back_populates="maintenance_requests")


class DocumentRecord(Base):
    __tablename__ = "documents"

    document_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    archived_file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    event_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    property_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    property_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AppDatabase:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        engine_kwargs: dict[str, object] = {"future": True}

        url = make_url(database_url)
        if url.get_backend_name() == "sqlite":
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if url.database in {None, "", ":memory:"}:
                engine_kwargs["poolclass"] = StaticPool

        self._engine = create_engine(database_url, **engine_kwargs)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False, future=True)

    def ensure_schema(self) -> None:
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
