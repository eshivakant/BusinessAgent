from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from business_agent.ingestion.registry import DocumentInfo
from business_agent.persistence.database import AppDatabase
from business_agent.persistence.registry import SqlAlchemyDocumentRegistry, SqlAlchemyPropertyRegistry
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


def _app_db_url(tmp_path, name: str = "app.db") -> str:
    return f"sqlite:///{tmp_path / name}"


def _sample_document(document_id: str, **overrides: object) -> DocumentInfo:
    now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    data = {
        "document_id": document_id,
        "title": "Mortgage offer",
        "document_type": "mortgage_offer",
        "vendor": "HSBC",
        "department": "finance",
        "keywords": ["mortgage", "offer"],
        "source_uri": f"/data/archive/{document_id}.pdf",
        "source_type": "pdf",
        "archived_file_path": f"/data/archive/{document_id}.pdf",
        "ingested_at": now,
        "event_date": now,
        "effective_date": now,
        "summary": "Offer for 133 Bowland Drive",
        "chunk_count": 3,
        "property_address": "133 Bowland Drive",
        "property_id": "prop-133",
        "amount": 180000.0,
    }
    data.update(overrides)
    return DocumentInfo(**data)


def _sample_property(property_id: str = "prop-133") -> Property:
    now = datetime.now(timezone.utc)
    return Property(
        id=property_id,
        address="133 Bowland Drive",
        purchase_date=date(2024, 6, 1),
        purchase_price=Decimal("250000.00"),
        current_value=Decimal("280000.00"),
        status=PropertyStatus.OWNED,
        bedrooms=3,
        bathrooms=2,
        square_feet=1200,
        postcode="AB1 2CD",
        notes="Primary buy-to-let",
        created_at=now,
        updated_at=now,
    )


class TestSqlAlchemyDocumentRegistry:
    def test_register_get_and_cross_instance_persistence(self, tmp_path) -> None:
        url = _app_db_url(tmp_path, "docs.db")
        db1 = AppDatabase(url)
        db1.ensure_schema()
        registry1 = SqlAlchemyDocumentRegistry(db1)
        document = _sample_document("doc-1")

        registry1.register(document)

        db2 = AppDatabase(url)
        db2.ensure_schema()
        registry2 = SqlAlchemyDocumentRegistry(db2)
        persisted = registry2.get("doc-1")

        assert persisted is not None
        assert persisted.document_id == "doc-1"
        assert persisted.property_address == "133 Bowland Drive"
        assert persisted.amount == 180000.0

    def test_query_filters_by_date_and_property_fields(self, tmp_path) -> None:
        database = AppDatabase(_app_db_url(tmp_path, "docs-filters.db"))
        database.ensure_schema()
        registry = SqlAlchemyDocumentRegistry(database)

        registry.register(
            _sample_document(
                "doc-old",
                document_type="invoice",
                effective_date=datetime(2025, 1, 10, tzinfo=timezone.utc),
                property_address="45 Oak Road",
                property_id="prop-45",
            )
        )
        registry.register(
            _sample_document(
                "doc-new",
                document_type="invoice",
                effective_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
                property_address="133 Bowland Drive",
                property_id="prop-133",
            )
        )

        results = registry.query(
            document_type="invoice",
            property_address="Bowland",
            property_id="prop-133",
            date_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 12, 31, tzinfo=timezone.utc),
            limit=10,
        )

        assert [doc.document_id for doc in results] == ["doc-new"]

    def test_list_all_orders_by_newest_ingested_first(self, tmp_path) -> None:
        database = AppDatabase(_app_db_url(tmp_path, "docs-list.db"))
        database.ensure_schema()
        registry = SqlAlchemyDocumentRegistry(database)

        registry.register(_sample_document("doc-early", ingested_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
        registry.register(_sample_document("doc-late", ingested_at=datetime(2026, 2, 1, tzinfo=timezone.utc)))

        results = registry.list_all(limit=10)

        assert [doc.document_id for doc in results] == ["doc-late", "doc-early"]


class TestSqlAlchemyPropertyRegistry:
    def test_property_related_entities_round_trip(self, tmp_path) -> None:
        database = AppDatabase(_app_db_url(tmp_path, "properties.db"))
        database.ensure_schema()
        registry = SqlAlchemyPropertyRegistry(database)
        property_record = _sample_property()
        now = datetime.now(timezone.utc)

        mortgage = Mortgage(
            id="mort-1",
            property_id=property_record.id,
            lender="Big Bank",
            principal=Decimal("200000.00"),
            interest_rate=Decimal("4.50"),
            term_months=240,
            start_date=date(2024, 6, 1),
            end_date=date.today() + timedelta(days=180),
            monthly_payment=Decimal("1500.00"),
            product_type="Fixed 5 year",
            balance_remaining=Decimal("192000.00"),
            notes="Existing product",
            created_at=now,
            updated_at=now,
        )
        tenant = Tenant(
            id="tenant-1",
            property_id=property_record.id,
            name="Jane Tenant",
            email="jane@example.com",
            phone="01234567890",
            lease_start=date(2025, 1, 1),
            lease_end=date.today() + timedelta(days=365),
            monthly_rent=Decimal("1800.00"),
            deposit=Decimal("1800.00"),
            notes="Reliable tenant",
            created_at=now,
            updated_at=now,
        )
        contact = Contact(
            id="contact-1",
            name="Smith Legal",
            contact_type=ContactType.SOLICITOR,
            company="Smith Legal LLP",
            email="solicitor@example.com",
            phone="02070000000",
            specialty="Conveyancing",
            notes="Primary solicitor",
            created_at=now,
            updated_at=now,
        )
        maintenance = MaintenanceRequest(
            id="maint-1",
            property_id=property_record.id,
            reported_date=date.today(),
            description="Boiler service",
            status=MaintenanceStatus.REPORTED,
            category="Heating",
            estimated_cost=Decimal("120.00"),
            contractor_id=contact.id,
            notes="Book next week",
            created_at=now,
            updated_at=now,
        )

        registry.add_property(property_record)
        registry.add_mortgage(mortgage)
        registry.add_tenant(tenant)
        registry.add_contact(contact)
        registry.add_maintenance_request(maintenance)

        assert registry.get_property(property_record.id) is not None
        assert registry.get_mortgage(mortgage.id) is not None
        assert registry.get_tenant(tenant.id) is not None
        assert registry.get_contact(contact.id) is not None
        assert registry.get_maintenance_request(maintenance.id) is not None

        assert len(registry.list_properties(status=PropertyStatus.OWNED)) == 1
        assert len(registry.list_mortgages(property_id=property_record.id)) == 1
        assert len(registry.list_tenants(property_id=property_record.id, active_only=True)) == 1
        assert len(registry.list_contacts(contact_type=ContactType.SOLICITOR)) == 1
        assert len(registry.list_maintenance_requests(property_id=property_record.id, status=MaintenanceStatus.REPORTED)) == 1
        assert len(registry.list_expiring_mortgages(months=12)) == 1

    def test_delete_property_cascades_to_mortgages_tenants_and_maintenance(self, tmp_path) -> None:
        database = AppDatabase(_app_db_url(tmp_path, "cascade.db"))
        database.ensure_schema()
        registry = SqlAlchemyPropertyRegistry(database)
        property_record = _sample_property("prop-cascade")
        now = datetime.now(timezone.utc)

        registry.add_property(property_record)
        registry.add_mortgage(
            Mortgage(
                id="mort-cascade",
                property_id=property_record.id,
                lender="Cascade Bank",
                principal=Decimal("100000.00"),
                interest_rate=Decimal("4.20"),
                term_months=120,
                start_date=date(2024, 1, 1),
                end_date=date.today() + timedelta(days=120),
                monthly_payment=Decimal("900.00"),
                created_at=now,
                updated_at=now,
            )
        )
        registry.add_tenant(
            Tenant(
                id="tenant-cascade",
                property_id=property_record.id,
                name="Tenant Cascade",
                email=None,
                phone=None,
                lease_start=date(2025, 1, 1),
                lease_end=date.today() + timedelta(days=365),
                monthly_rent=Decimal("1200.00"),
                deposit=Decimal("1200.00"),
                created_at=now,
                updated_at=now,
            )
        )
        registry.add_maintenance_request(
            MaintenanceRequest(
                id="maint-cascade",
                property_id=property_record.id,
                reported_date=date.today(),
                description="Replace lock",
                status=MaintenanceStatus.APPROVED,
                created_at=now,
                updated_at=now,
            )
        )

        deleted = registry.delete_property(property_record.id)

        assert deleted is True
        assert registry.get_property(property_record.id) is None
        assert registry.list_mortgages(property_id=property_record.id) == []
        assert registry.list_tenants(property_id=property_record.id, active_only=False) == []
        assert registry.list_maintenance_requests(property_id=property_record.id) == []

    def test_update_methods_change_existing_records(self, tmp_path) -> None:
        database = AppDatabase(_app_db_url(tmp_path, "updates.db"))
        database.ensure_schema()
        registry = SqlAlchemyPropertyRegistry(database)
        property_record = _sample_property("prop-update")
        registry.add_property(property_record)

        updated_property = _sample_property("prop-update")
        updated_property.current_value = Decimal("300000.00")
        updated_property.notes = "Updated note"
        registry.update_property(updated_property)

        fetched = registry.get_property("prop-update")
        assert fetched is not None
        assert fetched.current_value == Decimal("300000.00")
        assert fetched.notes == "Updated note"
