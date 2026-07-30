from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from business_agent.ingestion.registry import DocumentInfo, DocumentQueryFilter, DocumentRegistry
from business_agent.persistence.database import (
    AppDatabase,
    ContactRecord,
    DocumentRecord,
    GeneratedAgreementRecord,
    MaintenanceRequestRecord,
    MortgageRecord,
    PropertyRecord,
    TenantDocumentRecord,
    TenantRecord,
    normalize_datetime,
)
from business_agent.property.models import (
    Contact,
    ContactType,
    MaintenanceRequest,
    MaintenanceStatus,
    Mortgage,
    Property,
    PropertyStatus,
    Tenant,
)
from business_agent.property.registry import PropertyRegistry
from business_agent.tenancy.models import GeneratedAgreement, TenantDocument
from business_agent.tenancy.registry import TenancyRegistry


def _to_document_info(record: DocumentRecord) -> DocumentInfo:
    return DocumentInfo(
        document_id=record.document_id,
        title=record.title,
        document_type=record.document_type,
        vendor=record.vendor,
        department=record.department,
        keywords=list(record.keywords or []),
        source_uri=record.source_uri,
        source_type=record.source_type,
        archived_file_path=record.archived_file_path,
        ingested_at=normalize_datetime(record.ingested_at),
        event_date=normalize_datetime(record.event_date) if record.event_date else None,
        effective_date=normalize_datetime(record.effective_date),
        summary=record.summary,
        chunk_count=record.chunk_count,
        property_address=record.property_address,
        property_id=record.property_id,
        amount=float(record.amount) if record.amount is not None else None,
    )


def _to_document_record(doc: DocumentInfo) -> DocumentRecord:
    return DocumentRecord(
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        vendor=doc.vendor,
        department=doc.department,
        keywords=list(doc.keywords),
        source_uri=doc.source_uri,
        source_type=doc.source_type,
        archived_file_path=doc.archived_file_path,
        ingested_at=normalize_datetime(doc.ingested_at),
        event_date=normalize_datetime(doc.event_date) if doc.event_date else None,
        effective_date=normalize_datetime(doc.effective_date),
        summary=doc.summary,
        chunk_count=doc.chunk_count,
        property_address=doc.property_address,
        property_id=doc.property_id,
        amount=Decimal(str(doc.amount)) if doc.amount is not None else None,
    )


def _to_property(record: PropertyRecord) -> Property:
    return Property(
        id=record.id,
        address=record.address,
        purchase_date=record.purchase_date,
        purchase_price=record.purchase_price,
        current_value=record.current_value,
        status=PropertyStatus(record.status),
        bedrooms=record.bedrooms,
        bathrooms=record.bathrooms,
        square_feet=record.square_feet,
        postcode=record.postcode,
        notes=record.notes,
        created_at=normalize_datetime(record.created_at),
        updated_at=normalize_datetime(record.updated_at),
    )


def _to_mortgage(record: MortgageRecord) -> Mortgage:
    return Mortgage(
        id=record.id,
        property_id=record.property_id,
        lender=record.lender,
        principal=record.principal,
        interest_rate=record.interest_rate,
        term_months=record.term_months,
        start_date=record.start_date,
        monthly_payment=record.monthly_payment,
        product_type=record.product_type,
        end_date=record.end_date,
        balance_remaining=record.balance_remaining,
        notes=record.notes,
        created_at=normalize_datetime(record.created_at),
        updated_at=normalize_datetime(record.updated_at),
    )


def _to_tenant(record: TenantRecord) -> Tenant:
    return Tenant(
        id=record.id,
        property_id=record.property_id,
        name=record.name,
        email=record.email,
        phone=record.phone,
        lease_start=record.lease_start,
        lease_end=record.lease_end,
        monthly_rent=record.monthly_rent,
        deposit=record.deposit,
        is_active=record.is_active,
        notes=record.notes,
        created_at=normalize_datetime(record.created_at),
        updated_at=normalize_datetime(record.updated_at),
        full_name=record.full_name,
        date_of_birth=record.date_of_birth,
        national_insurance_number=record.national_insurance_number,
        passport_number=record.passport_number,
        employer_name=record.employer_name,
        annual_income=record.annual_income,
    )


def _to_tenant_document(record: TenantDocumentRecord) -> TenantDocument:
    return TenantDocument(
        id=record.id,
        tenancy_id=record.tenancy_id,
        filename=record.filename,
        stored_path=record.stored_path,
        document_type=record.document_type,
        ingested_at=normalize_datetime(record.ingested_at),
        extracted_fields=dict(record.extracted_fields or {}),
        qdrant_ids=list(record.qdrant_ids or []),
        property_id=record.property_id,
        source_uri=record.source_uri,
        summary=record.summary,
        chunk_count=record.chunk_count,
    )


def _to_generated_agreement(record: GeneratedAgreementRecord) -> GeneratedAgreement:
    return GeneratedAgreement(
        id=record.id,
        tenancy_id=record.tenancy_id,
        template_name=record.template_name,
        generated_at=normalize_datetime(record.generated_at),
        stored_path=record.stored_path,
        pdf_path=record.pdf_path,
    )


def _to_contact(record: ContactRecord) -> Contact:
    return Contact(
        id=record.id,
        name=record.name,
        contact_type=ContactType(record.contact_type),
        company=record.company,
        email=record.email,
        phone=record.phone,
        specialty=record.specialty,
        notes=record.notes,
        created_at=normalize_datetime(record.created_at),
        updated_at=normalize_datetime(record.updated_at),
    )


def _to_maintenance(record: MaintenanceRequestRecord) -> MaintenanceRequest:
    return MaintenanceRequest(
        id=record.id,
        property_id=record.property_id,
        reported_date=record.reported_date,
        description=record.description,
        status=MaintenanceStatus(record.status),
        category=record.category,
        estimated_cost=record.estimated_cost,
        actual_cost=record.actual_cost,
        contractor_id=record.contractor_id,
        completed_date=record.completed_date,
        notes=record.notes,
        created_at=normalize_datetime(record.created_at),
        updated_at=normalize_datetime(record.updated_at),
    )


class SqlAlchemyDocumentRegistry(DocumentRegistry):
    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def register(self, doc: DocumentInfo) -> None:
        record = _to_document_record(doc)
        with self._database.session() as session:
            session.merge(record)
            session.commit()

    def get(self, document_id: str) -> DocumentInfo | None:
        with self._database.session() as session:
            record = session.get(DocumentRecord, document_id)
            return _to_document_info(record) if record is not None else None

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

        stmt = select(DocumentRecord).order_by(DocumentRecord.effective_date.desc())
        if filters.document_type:
            stmt = stmt.where(DocumentRecord.document_type == filters.document_type)
        if filters.vendor:
            stmt = stmt.where(DocumentRecord.vendor == filters.vendor)
        if filters.department:
            stmt = stmt.where(DocumentRecord.department == filters.department)
        if filters.property_id:
            stmt = stmt.where(DocumentRecord.property_id == filters.property_id)
        if filters.date_from:
            stmt = stmt.where(DocumentRecord.effective_date >= normalize_datetime(filters.date_from))
        if filters.date_to:
            stmt = stmt.where(DocumentRecord.effective_date <= normalize_datetime(filters.date_to))

        with self._database.session() as session:
            docs = [_to_document_info(item) for item in session.execute(stmt).scalars().all()]

        return [doc for doc in docs if filters.matches(doc)][: filters.limit]

    def list_all(self, limit: int = 100) -> list[DocumentInfo]:
        stmt = select(DocumentRecord).order_by(DocumentRecord.ingested_at.desc()).limit(limit)
        with self._database.session() as session:
            return [_to_document_info(item) for item in session.execute(stmt).scalars().all()]


class SqlAlchemyTenancyRegistry(TenancyRegistry):
    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def create_tenancy(self, tenancy: Tenant) -> None:
        with self._database.session() as session:
            session.merge(
                TenantRecord(
                    id=tenancy.id,
                    property_id=tenancy.property_id,
                    name=tenancy.name,
                    email=tenancy.email,
                    phone=tenancy.phone,
                    lease_start=tenancy.lease_start,
                    lease_end=tenancy.lease_end,
                    monthly_rent=tenancy.monthly_rent,
                    deposit=tenancy.deposit,
                    is_active=tenancy.is_active,
                    notes=tenancy.notes,
                    created_at=normalize_datetime(tenancy.created_at),
                    updated_at=normalize_datetime(tenancy.updated_at),
                    full_name=tenancy.full_name,
                    date_of_birth=tenancy.date_of_birth,
                    national_insurance_number=tenancy.national_insurance_number,
                    passport_number=tenancy.passport_number,
                    employer_name=tenancy.employer_name,
                    annual_income=tenancy.annual_income,
                )
            )
            session.commit()

    def get_tenancy(self, tenancy_id: str) -> Tenant | None:
        with self._database.session() as session:
            record = session.get(TenantRecord, tenancy_id)
            return _to_tenant(record) if record is not None else None

    def list_tenancies(self, property_id: str | None = None, active_only: bool = True) -> list[Tenant]:
        stmt = select(TenantRecord).order_by(TenantRecord.created_at.desc())
        if property_id:
            stmt = stmt.where(TenantRecord.property_id == property_id)
        if active_only:
            stmt = stmt.where(TenantRecord.is_active.is_(True))
        with self._database.session() as session:
            return [_to_tenant(item) for item in session.execute(stmt).scalars().all()]

    def update_tenancy(self, tenancy: Tenant) -> None:
        with self._database.session() as session:
            record = session.get(TenantRecord, tenancy.id)
            if record is None:
                return
            record.property_id = tenancy.property_id
            record.name = tenancy.name
            record.email = tenancy.email
            record.phone = tenancy.phone
            record.lease_start = tenancy.lease_start
            record.lease_end = tenancy.lease_end
            record.monthly_rent = tenancy.monthly_rent
            record.deposit = tenancy.deposit
            record.is_active = tenancy.is_active
            record.notes = tenancy.notes
            record.created_at = normalize_datetime(tenancy.created_at)
            record.updated_at = normalize_datetime(tenancy.updated_at)
            record.full_name = tenancy.full_name
            record.date_of_birth = tenancy.date_of_birth
            record.national_insurance_number = tenancy.national_insurance_number
            record.passport_number = tenancy.passport_number
            record.employer_name = tenancy.employer_name
            record.annual_income = tenancy.annual_income
            session.commit()

    def add_document(self, document: TenantDocument) -> None:
        with self._database.session() as session:
            session.merge(
                TenantDocumentRecord(
                    id=document.id,
                    tenancy_id=document.tenancy_id,
                    filename=document.filename,
                    stored_path=document.stored_path,
                    document_type=document.document_type,
                    ingested_at=normalize_datetime(document.ingested_at),
                    extracted_fields=dict(document.extracted_fields),
                    qdrant_ids=list(document.qdrant_ids),
                    property_id=document.property_id,
                    source_uri=document.source_uri,
                    summary=document.summary,
                    chunk_count=document.chunk_count,
                )
            )
            session.commit()

    def list_documents(self, tenancy_id: str) -> list[TenantDocument]:
        stmt = select(TenantDocumentRecord).where(TenantDocumentRecord.tenancy_id == tenancy_id).order_by(TenantDocumentRecord.ingested_at.desc())
        with self._database.session() as session:
            return [_to_tenant_document(item) for item in session.execute(stmt).scalars().all()]

    def create_agreement(self, agreement: GeneratedAgreement) -> None:
        with self._database.session() as session:
            session.merge(
                GeneratedAgreementRecord(
                    id=agreement.id,
                    tenancy_id=agreement.tenancy_id,
                    template_name=agreement.template_name,
                    generated_at=normalize_datetime(agreement.generated_at),
                    stored_path=agreement.stored_path,
                    pdf_path=agreement.pdf_path,
                )
            )
            session.commit()

    def get_agreement(self, agreement_id: str) -> GeneratedAgreement | None:
        with self._database.session() as session:
            record = session.get(GeneratedAgreementRecord, agreement_id)
            return _to_generated_agreement(record) if record is not None else None


class SqlAlchemyPropertyRegistry(PropertyRegistry):
    def __init__(self, database: AppDatabase) -> None:
        self._database = database

    def add_property(self, prop: Property) -> None:
        with self._database.session() as session:
            session.merge(
                PropertyRecord(
                    id=prop.id,
                    address=prop.address,
                    purchase_date=prop.purchase_date,
                    purchase_price=prop.purchase_price,
                    current_value=prop.current_value,
                    status=prop.status.value,
                    bedrooms=prop.bedrooms,
                    bathrooms=prop.bathrooms,
                    square_feet=prop.square_feet,
                    postcode=prop.postcode,
                    notes=prop.notes,
                    created_at=normalize_datetime(prop.created_at),
                    updated_at=normalize_datetime(prop.updated_at),
                )
            )
            session.commit()

    def get_property(self, property_id: str) -> Property | None:
        with self._database.session() as session:
            record = session.get(PropertyRecord, property_id)
            return _to_property(record) if record is not None else None

    def list_properties(self, status: PropertyStatus | None = None) -> list[Property]:
        stmt = select(PropertyRecord).order_by(PropertyRecord.created_at.desc())
        if status:
            stmt = stmt.where(PropertyRecord.status == status.value)
        with self._database.session() as session:
            return [_to_property(item) for item in session.execute(stmt).scalars().all()]

    def update_property(self, prop: Property) -> None:
        with self._database.session() as session:
            record = session.get(PropertyRecord, prop.id)
            if record is None:
                return
            record.address = prop.address
            record.purchase_date = prop.purchase_date
            record.purchase_price = prop.purchase_price
            record.current_value = prop.current_value
            record.status = prop.status.value
            record.bedrooms = prop.bedrooms
            record.bathrooms = prop.bathrooms
            record.square_feet = prop.square_feet
            record.postcode = prop.postcode
            record.notes = prop.notes
            record.created_at = normalize_datetime(prop.created_at)
            record.updated_at = normalize_datetime(prop.updated_at)
            session.commit()

    def delete_property(self, property_id: str) -> bool:
        with self._database.session() as session:
            record = session.get(PropertyRecord, property_id)
            if record is None:
                return False
            session.delete(record)
            session.commit()
            return True

    def add_mortgage(self, mortgage: Mortgage) -> None:
        with self._database.session() as session:
            session.merge(
                MortgageRecord(
                    id=mortgage.id,
                    property_id=mortgage.property_id,
                    lender=mortgage.lender,
                    principal=mortgage.principal,
                    interest_rate=mortgage.interest_rate,
                    term_months=mortgage.term_months,
                    start_date=mortgage.start_date,
                    monthly_payment=mortgage.monthly_payment,
                    product_type=mortgage.product_type,
                    end_date=mortgage.end_date,
                    balance_remaining=mortgage.balance_remaining,
                    notes=mortgage.notes,
                    created_at=normalize_datetime(mortgage.created_at),
                    updated_at=normalize_datetime(mortgage.updated_at),
                )
            )
            session.commit()

    def get_mortgage(self, mortgage_id: str) -> Mortgage | None:
        with self._database.session() as session:
            record = session.get(MortgageRecord, mortgage_id)
            return _to_mortgage(record) if record is not None else None

    def list_mortgages(self, property_id: str | None = None) -> list[Mortgage]:
        stmt = select(MortgageRecord).order_by(MortgageRecord.created_at.desc())
        if property_id:
            stmt = stmt.where(MortgageRecord.property_id == property_id)
        with self._database.session() as session:
            return [_to_mortgage(item) for item in session.execute(stmt).scalars().all()]

    def list_expiring_mortgages(self, months: int = 6) -> list[Mortgage]:
        return [mortgage for mortgage in self.list_mortgages() if mortgage.is_expiring_soon(months)]

    def update_mortgage(self, mortgage: Mortgage) -> None:
        with self._database.session() as session:
            record = session.get(MortgageRecord, mortgage.id)
            if record is None:
                return
            record.property_id = mortgage.property_id
            record.lender = mortgage.lender
            record.principal = mortgage.principal
            record.interest_rate = mortgage.interest_rate
            record.term_months = mortgage.term_months
            record.start_date = mortgage.start_date
            record.monthly_payment = mortgage.monthly_payment
            record.product_type = mortgage.product_type
            record.end_date = mortgage.end_date
            record.balance_remaining = mortgage.balance_remaining
            record.notes = mortgage.notes
            record.created_at = normalize_datetime(mortgage.created_at)
            record.updated_at = normalize_datetime(mortgage.updated_at)
            session.commit()

    def add_tenant(self, tenant: Tenant) -> None:
        with self._database.session() as session:
            session.merge(
                TenantRecord(
                    id=tenant.id,
                    property_id=tenant.property_id,
                    name=tenant.name,
                    email=tenant.email,
                    phone=tenant.phone,
                    lease_start=tenant.lease_start,
                    lease_end=tenant.lease_end,
                    monthly_rent=tenant.monthly_rent,
                    deposit=tenant.deposit,
                    is_active=tenant.is_active,
                    notes=tenant.notes,
                    created_at=normalize_datetime(tenant.created_at),
                    updated_at=normalize_datetime(tenant.updated_at),
                )
            )
            session.commit()

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        with self._database.session() as session:
            record = session.get(TenantRecord, tenant_id)
            return _to_tenant(record) if record is not None else None

    def list_tenants(self, property_id: str | None = None, active_only: bool = True) -> list[Tenant]:
        stmt = select(TenantRecord).order_by(TenantRecord.created_at.desc())
        if property_id:
            stmt = stmt.where(TenantRecord.property_id == property_id)
        if active_only:
            stmt = stmt.where(TenantRecord.is_active.is_(True))
        with self._database.session() as session:
            return [_to_tenant(item) for item in session.execute(stmt).scalars().all()]

    def update_tenant(self, tenant: Tenant) -> None:
        with self._database.session() as session:
            record = session.get(TenantRecord, tenant.id)
            if record is None:
                return
            record.property_id = tenant.property_id
            record.name = tenant.name
            record.email = tenant.email
            record.phone = tenant.phone
            record.lease_start = tenant.lease_start
            record.lease_end = tenant.lease_end
            record.monthly_rent = tenant.monthly_rent
            record.deposit = tenant.deposit
            record.is_active = tenant.is_active
            record.notes = tenant.notes
            record.created_at = normalize_datetime(tenant.created_at)
            record.updated_at = normalize_datetime(tenant.updated_at)
            session.commit()

    def add_contact(self, contact: Contact) -> None:
        with self._database.session() as session:
            session.merge(
                ContactRecord(
                    id=contact.id,
                    name=contact.name,
                    contact_type=contact.contact_type.value,
                    company=contact.company,
                    email=contact.email,
                    phone=contact.phone,
                    specialty=contact.specialty,
                    notes=contact.notes,
                    created_at=normalize_datetime(contact.created_at),
                    updated_at=normalize_datetime(contact.updated_at),
                )
            )
            session.commit()

    def get_contact(self, contact_id: str) -> Contact | None:
        with self._database.session() as session:
            record = session.get(ContactRecord, contact_id)
            return _to_contact(record) if record is not None else None

    def list_contacts(self, contact_type: ContactType | None = None) -> list[Contact]:
        stmt = select(ContactRecord).order_by(ContactRecord.name.asc())
        if contact_type:
            stmt = stmt.where(ContactRecord.contact_type == contact_type.value)
        with self._database.session() as session:
            return [_to_contact(item) for item in session.execute(stmt).scalars().all()]

    def update_contact(self, contact: Contact) -> None:
        with self._database.session() as session:
            record = session.get(ContactRecord, contact.id)
            if record is None:
                return
            record.name = contact.name
            record.contact_type = contact.contact_type.value
            record.company = contact.company
            record.email = contact.email
            record.phone = contact.phone
            record.specialty = contact.specialty
            record.notes = contact.notes
            record.created_at = normalize_datetime(contact.created_at)
            record.updated_at = normalize_datetime(contact.updated_at)
            session.commit()

    def add_maintenance_request(self, request: MaintenanceRequest) -> None:
        with self._database.session() as session:
            session.merge(
                MaintenanceRequestRecord(
                    id=request.id,
                    property_id=request.property_id,
                    reported_date=request.reported_date,
                    description=request.description,
                    status=request.status.value,
                    category=request.category,
                    estimated_cost=request.estimated_cost,
                    actual_cost=request.actual_cost,
                    contractor_id=request.contractor_id,
                    completed_date=request.completed_date,
                    notes=request.notes,
                    created_at=normalize_datetime(request.created_at),
                    updated_at=normalize_datetime(request.updated_at),
                )
            )
            session.commit()

    def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        with self._database.session() as session:
            record = session.get(MaintenanceRequestRecord, request_id)
            return _to_maintenance(record) if record is not None else None

    def list_maintenance_requests(
        self,
        property_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]:
        stmt = select(MaintenanceRequestRecord).order_by(MaintenanceRequestRecord.reported_date.desc())
        if property_id:
            stmt = stmt.where(MaintenanceRequestRecord.property_id == property_id)
        if status:
            stmt = stmt.where(MaintenanceRequestRecord.status == status.value)
        with self._database.session() as session:
            return [_to_maintenance(item) for item in session.execute(stmt).scalars().all()]

    def update_maintenance_request(self, request: MaintenanceRequest) -> None:
        with self._database.session() as session:
            record = session.get(MaintenanceRequestRecord, request.id)
            if record is None:
                return
            record.property_id = request.property_id
            record.reported_date = request.reported_date
            record.description = request.description
            record.status = request.status.value
            record.category = request.category
            record.estimated_cost = request.estimated_cost
            record.actual_cost = request.actual_cost
            record.contractor_id = request.contractor_id
            record.completed_date = request.completed_date
            record.notes = request.notes
            record.created_at = normalize_datetime(request.created_at)
            record.updated_at = normalize_datetime(request.updated_at)
            session.commit()
