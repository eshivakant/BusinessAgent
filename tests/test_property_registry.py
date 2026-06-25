"""Tests for property domain models and registry."""

import pytest
from datetime import date, datetime
from decimal import Decimal

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
from business_agent.property.registry import InMemoryPropertyRegistry


class TestPropertyModel:
    def test_create_property_minimal(self):
        prop = Property(
            id="prop1",
            address="123 Main St",
            purchase_date=None,
            purchase_price=None,
            current_value=None,
            status=PropertyStatus.VIEWING,
        )
        assert prop.id == "prop1"
        assert prop.address == "123 Main St"
        assert prop.status == PropertyStatus.VIEWING
        assert prop.notes is None
    
    def test_create_property_full(self):
        prop = Property(
            id="prop2",
            address="456 Oak Ave",
            purchase_date=date(2022, 6, 15),
            purchase_price=Decimal("250000.00"),
            current_value=Decimal("280000.00"),
            status=PropertyStatus.OWNED,
            bedrooms=3,
            bathrooms=2,
            square_feet=1500,
            postcode="SW1A 1AA",
            notes="Great location near transport",
        )
        assert prop.purchase_price == Decimal("250000.00")
        assert prop.current_value == Decimal("280000.00")
        assert prop.bedrooms == 3
        assert prop.postcode == "SW1A 1AA"


class TestMortgageModel:
    def test_mortgage_expiry_calculation(self):
        # Mortgage expires in 4 months from June 2026
        mortgage = Mortgage(
            id="mort1",
            property_id="prop1",
            lender="Big Bank",
            principal=Decimal("200000"),
            interest_rate=Decimal("4.5"),
            term_months=240,
            start_date=date(2020, 1, 1),
            monthly_payment=Decimal("1500.00"),
            end_date=date(2026, 10, 1),
        )
        months_left = mortgage.months_until_expiry()
        assert months_left is not None
        # Should be ~4 months (June to October 2026)
        assert 3 <= months_left <= 5
    
    def test_mortgage_expired(self):
        mortgage = Mortgage(
            id="mort2",
            property_id="prop1",
            lender="Small Bank",
            principal=Decimal("150000"),
            interest_rate=Decimal("3.9"),
            term_months=180,
            start_date=date(2010, 1, 1),
            monthly_payment=Decimal("1200.00"),
            end_date=date(2020, 1, 1),  # Already expired
        )
        assert mortgage.months_until_expiry() == 0
    
    def test_is_expiring_soon_true(self):
        mortgage = Mortgage(
            id="mort3",
            property_id="prop1",
            lender="Quick Bank",
            principal=Decimal("180000"),
            interest_rate=Decimal("5.0"),
            term_months=120,
            start_date=date(2020, 1, 1),
            monthly_payment=Decimal("1800.00"),
            end_date=date(2026, 10, 1),  # ~4 months away from June 2026
        )
        assert mortgage.is_expiring_soon(months=6) is True
    
    def test_is_expiring_soon_false(self):
        mortgage = Mortgage(
            id="mort4",
            property_id="prop1",
            lender="Future Bank",
            principal=Decimal("250000"),
            interest_rate=Decimal("4.0"),
            term_months=300,
            start_date=date(2024, 1, 1),
            monthly_payment=Decimal("2000.00"),
            end_date=date(2030, 1, 1),  # Many years away
        )
        assert mortgage.is_expiring_soon(months=6) is False


class TestTenantModel:
    def test_tenant_months_until_lease_end(self):
        tenant = Tenant(
            id="tenant1",
            property_id="prop1",
            name="John Smith",
            email="john@example.com",
            phone="+44123456789",
            lease_start=date(2024, 1, 1),
            lease_end=date(2026, 12, 31),  # ~6 months from June 2026
            monthly_rent=Decimal("1500.00"),
            deposit=Decimal("1500.00"),
        )
        months_left = tenant.months_until_lease_end()
        # Should be ~6 months (June to December 2026)
        assert 5 <= months_left <= 7
    
    def test_tenant_lease_expired(self):
        tenant = Tenant(
            id="tenant2",
            property_id="prop2",
            name="Jane Doe",
            email="jane@example.com",
            phone=None,
            lease_start=date(2020, 1, 1),
            lease_end=date(2021, 12, 31),
            monthly_rent=Decimal("1200.00"),
            deposit=Decimal("1200.00"),
            is_active=False,
        )
        assert tenant.months_until_lease_end() == 0


class TestContactModel:
    def test_create_contact_solicitor(self):
        contact = Contact(
            id="contact1",
            name="Smith & Associates",
            contact_type=ContactType.SOLICITOR,
            company="Smith Legal",
            email="info@smithlegal.com",
            phone="+44207123456",
            specialty="Commercial property law",
            notes="Very responsive",
        )
        assert contact.contact_type == ContactType.SOLICITOR
        assert contact.specialty == "Commercial property law"
    
    def test_create_contact_mortgage_broker(self):
        contact = Contact(
            id="contact2",
            name="Bob Broker",
            contact_type=ContactType.MORTGAGE_BROKER,
            company="Mortgage Solutions Ltd",
            email="bob@mortgagesolutions.com",
            phone="+44207987654",
            specialty="Buy-to-let mortgages",
        )
        assert contact.contact_type == ContactType.MORTGAGE_BROKER


class TestMaintenanceRequestModel:
    def test_create_maintenance_request(self):
        req = MaintenanceRequest(
            id="maint1",
            property_id="prop1",
            reported_date=date(2025, 6, 1),
            description="Leaking tap in bathroom",
            status=MaintenanceStatus.REPORTED,
            category="Plumbing",
            estimated_cost=Decimal("150.00"),
        )
        assert req.status == MaintenanceStatus.REPORTED
        assert req.estimated_cost == Decimal("150.00")
        assert req.actual_cost is None
    
    def test_maintenance_request_completed(self):
        req = MaintenanceRequest(
            id="maint2",
            property_id="prop2",
            reported_date=date(2025, 5, 15),
            description="Broken window",
            status=MaintenanceStatus.COMPLETED,
            category="Windows",
            estimated_cost=Decimal("300.00"),
            actual_cost=Decimal("280.00"),
            contractor_id="contact3",
            completed_date=date(2025, 5, 20),
        )
        assert req.status == MaintenanceStatus.COMPLETED
        assert req.actual_cost == Decimal("280.00")
        assert req.completed_date == date(2025, 5, 20)


class TestInMemoryPropertyRegistry:
    @pytest.fixture
    def registry(self):
        return InMemoryPropertyRegistry()
    
    @pytest.fixture
    def sample_property(self):
        return Property(
            id="prop1",
            address="123 Test St",
            purchase_date=date(2023, 1, 1),
            purchase_price=Decimal("200000"),
            current_value=Decimal("220000"),
            status=PropertyStatus.OWNED,
            bedrooms=3,
        )
    
    def test_add_and_get_property(self, registry, sample_property):
        registry.add_property(sample_property)
        retrieved = registry.get_property("prop1")
        assert retrieved is not None
        assert retrieved.id == "prop1"
        assert retrieved.address == "123 Test St"
    
    def test_get_nonexistent_property(self, registry):
        assert registry.get_property("nonexistent") is None
    
    def test_list_properties_empty(self, registry):
        assert registry.list_properties() == []
    
    def test_list_properties_all(self, registry, sample_property):
        prop2 = Property(
            id="prop2",
            address="456 Oak Ave",
            purchase_date=None,
            purchase_price=None,
            current_value=None,
            status=PropertyStatus.VIEWING,
        )
        registry.add_property(sample_property)
        registry.add_property(prop2)
        
        props = registry.list_properties()
        assert len(props) == 2
    
    def test_list_properties_filter_by_status(self, registry, sample_property):
        prop2 = Property(
            id="prop2",
            address="456 Oak Ave",
            purchase_date=None,
            purchase_price=None,
            current_value=None,
            status=PropertyStatus.VIEWING,
        )
        registry.add_property(sample_property)
        registry.add_property(prop2)
        
        owned = registry.list_properties(status=PropertyStatus.OWNED)
        assert len(owned) == 1
        assert owned[0].id == "prop1"
        
        viewing = registry.list_properties(status=PropertyStatus.VIEWING)
        assert len(viewing) == 1
        assert viewing[0].id == "prop2"
    
    def test_update_property(self, registry, sample_property):
        registry.add_property(sample_property)
        
        sample_property.current_value = Decimal("250000")
        registry.update_property(sample_property)
        
        updated = registry.get_property("prop1")
        assert updated.current_value == Decimal("250000")
    
    def test_delete_property(self, registry, sample_property):
        registry.add_property(sample_property)
        assert registry.delete_property("prop1") is True
        assert registry.get_property("prop1") is None
    
    def test_delete_nonexistent_property(self, registry):
        assert registry.delete_property("nonexistent") is False
    
    def test_add_and_get_mortgage(self, registry):
        mortgage = Mortgage(
            id="mort1",
            property_id="prop1",
            lender="Test Bank",
            principal=Decimal("150000"),
            interest_rate=Decimal("4.5"),
            term_months=240,
            start_date=date(2023, 1, 1),
            monthly_payment=Decimal("1200.00"),
        )
        registry.add_mortgage(mortgage)
        
        retrieved = registry.get_mortgage("mort1")
        assert retrieved is not None
        assert retrieved.lender == "Test Bank"
    
    def test_list_mortgages_by_property(self, registry):
        mort1 = Mortgage(
            id="mort1",
            property_id="prop1",
            lender="Bank A",
            principal=Decimal("150000"),
            interest_rate=Decimal("4.5"),
            term_months=240,
            start_date=date(2023, 1, 1),
            monthly_payment=Decimal("1200.00"),
        )
        mort2 = Mortgage(
            id="mort2",
            property_id="prop2",
            lender="Bank B",
            principal=Decimal("200000"),
            interest_rate=Decimal("5.0"),
            term_months=300,
            start_date=date(2023, 1, 1),
            monthly_payment=Decimal("1500.00"),
        )
        registry.add_mortgage(mort1)
        registry.add_mortgage(mort2)
        
        prop1_mortgages = registry.list_mortgages(property_id="prop1")
        assert len(prop1_mortgages) == 1
        assert prop1_mortgages[0].id == "mort1"
    
    def test_list_expiring_mortgages(self, registry):
        # Mortgage expiring soon (4 months from June 2026)
        mort_soon = Mortgage(
            id="mort_soon",
            property_id="prop1",
            lender="Bank A",
            principal=Decimal("150000"),
            interest_rate=Decimal("4.5"),
            term_months=240,
            start_date=date(2023, 1, 1),
            monthly_payment=Decimal("1200.00"),
            end_date=date(2026, 10, 1),
        )
        # Mortgage far in future
        mort_future = Mortgage(
            id="mort_future",
            property_id="prop2",
            lender="Bank B",
            principal=Decimal("200000"),
            interest_rate=Decimal("5.0"),
            term_months=300,
            start_date=date(2024, 1, 1),
            monthly_payment=Decimal("1500.00"),
            end_date=date(2030, 1, 1),
        )
        registry.add_mortgage(mort_soon)
        registry.add_mortgage(mort_future)
        
        expiring = registry.list_expiring_mortgages(months=6)
        assert len(expiring) == 1
        assert expiring[0].id == "mort_soon"
    
    def test_add_and_list_tenants(self, registry):
        tenant1 = Tenant(
            id="tenant1",
            property_id="prop1",
            name="John Smith",
            email="john@example.com",
            phone=None,
            lease_start=date(2024, 1, 1),
            lease_end=date(2025, 12, 31),
            monthly_rent=Decimal("1500.00"),
            deposit=Decimal("1500.00"),
            is_active=True,
        )
        tenant2 = Tenant(
            id="tenant2",
            property_id="prop1",
            name="Jane Doe",
            email="jane@example.com",
            phone=None,
            lease_start=date(2022, 1, 1),
            lease_end=date(2023, 12, 31),
            monthly_rent=Decimal("1400.00"),
            deposit=Decimal("1400.00"),
            is_active=False,
        )
        registry.add_tenant(tenant1)
        registry.add_tenant(tenant2)
        
        # List active only
        active = registry.list_tenants(property_id="prop1", active_only=True)
        assert len(active) == 1
        assert active[0].name == "John Smith"
        
        # List all
        all_tenants = registry.list_tenants(property_id="prop1", active_only=False)
        assert len(all_tenants) == 2
    
    def test_add_and_list_contacts(self, registry):
        solicitor = Contact(
            id="contact1",
            name="Smith & Associates",
            contact_type=ContactType.SOLICITOR,
            company="Smith Legal",
            email="info@smithlegal.com",
            phone="+44207123456",
            specialty=None,
        )
        broker = Contact(
            id="contact2",
            name="Bob Broker",
            contact_type=ContactType.MORTGAGE_BROKER,
            company="Mortgage Solutions",
            email="bob@mortgagesolutions.com",
            phone="+44207987654",
            specialty=None,
        )
        registry.add_contact(solicitor)
        registry.add_contact(broker)
        
        # List all
        all_contacts = registry.list_contacts()
        assert len(all_contacts) == 2
        
        # Filter by type
        solicitors = registry.list_contacts(contact_type=ContactType.SOLICITOR)
        assert len(solicitors) == 1
        assert solicitors[0].name == "Smith & Associates"
    
    def test_add_and_list_maintenance_requests(self, registry):
        req1 = MaintenanceRequest(
            id="maint1",
            property_id="prop1",
            reported_date=date(2025, 6, 1),
            description="Leaking tap",
            status=MaintenanceStatus.REPORTED,
        )
        req2 = MaintenanceRequest(
            id="maint2",
            property_id="prop1",
            reported_date=date(2025, 5, 15),
            description="Broken window",
            status=MaintenanceStatus.COMPLETED,
        )
        req3 = MaintenanceRequest(
            id="maint3",
            property_id="prop2",
            reported_date=date(2025, 6, 5),
            description="Door repair",
            status=MaintenanceStatus.IN_PROGRESS,
        )
        registry.add_maintenance_request(req1)
        registry.add_maintenance_request(req2)
        registry.add_maintenance_request(req3)
        
        # List by property
        prop1_requests = registry.list_maintenance_requests(property_id="prop1")
        assert len(prop1_requests) == 2
        
        # Filter by status
        reported = registry.list_maintenance_requests(status=MaintenanceStatus.REPORTED)
        assert len(reported) == 1
        assert reported[0].id == "maint1"
