"""Tests for property management API endpoints."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from business_agent.api.app import create_app
from business_agent.property.models import (
    MaintenanceRequest,
    MaintenanceStatus,
    Mortgage,
    Property,
    PropertyStatus,
    Tenant,
)
from business_agent.property.registry import InMemoryPropertyRegistry


@pytest.fixture
def property_registry():
    """Property registry with sample data."""
    registry = InMemoryPropertyRegistry()
    
    # Add properties
    prop1 = Property(
        id="prop1",
        address="123 Main St",
        purchase_date=date(2023, 1, 15),
        purchase_price=Decimal("250000"),
        current_value=Decimal("280000"),
        status=PropertyStatus.OWNED,
        bedrooms=3,
        postcode="SW1A 1AA",
    )
    prop2 = Property(
        id="prop2",
        address="456 Oak Ave",
        purchase_date=None,
        purchase_price=None,
        current_value=None,
        status=PropertyStatus.VIEWING,
        bedrooms=2,
    )
    prop3 = Property(
        id="prop3",
        address="789 Pine Rd",
        purchase_date=date(2022, 6, 1),
        purchase_price=Decimal("300000"),
        current_value=Decimal("320000"),
        status=PropertyStatus.UNDER_OFFER,
        bedrooms=4,
    )
    registry.add_property(prop1)
    registry.add_property(prop2)
    registry.add_property(prop3)
    
    # Add mortgage expiring soon
    mort1 = Mortgage(
        id="mort1",
        property_id="prop1",
        lender="Big Bank",
        principal=Decimal("200000"),
        interest_rate=Decimal("4.5"),
        term_months=240,
        start_date=date(2023, 1, 15),
        monthly_payment=Decimal("1500.00"),
        end_date=date(2026, 10, 1),  # ~4 months from now
    )
    registry.add_mortgage(mort1)
    
    # Add active tenants
    tenant1 = Tenant(
        id="tenant1",
        property_id="prop1",
        name="John Smith",
        email="john@example.com",
        phone=None,
        lease_start=date(2024, 1, 1),
        lease_end=date(2026, 12, 31),
        monthly_rent=Decimal("1800.00"),
        deposit=Decimal("1800.00"),
        is_active=True,
    )
    tenant2 = Tenant(
        id="tenant2",
        property_id="prop3",
        name="Jane Doe",
        email="jane@example.com",
        phone=None,
        lease_start=date(2024, 1, 1),
        lease_end=date(2026, 12, 31),
        monthly_rent=Decimal("2200.00"),
        deposit=Decimal("2200.00"),
        is_active=True,
    )
    registry.add_tenant(tenant1)
    registry.add_tenant(tenant2)
    
    # Add maintenance requests
    maint1 = MaintenanceRequest(
        id="maint1",
        property_id="prop1",
        reported_date=date(2026, 6, 1),
        description="Leaking tap",
        status=MaintenanceStatus.REPORTED,
    )
    maint2 = MaintenanceRequest(
        id="maint2",
        property_id="prop2",
        reported_date=date(2026, 5, 15),
        description="Broken window",
        status=MaintenanceStatus.COMPLETED,
    )
    registry.add_maintenance_request(maint1)
    registry.add_maintenance_request(maint2)
    
    return registry


@pytest.fixture
def client(property_registry):
    """FastAPI test client with mocked dependencies."""
    app = create_app()
    
    with patch("business_agent.api.routes.verify_internal_api_token", return_value=None):
        with patch("business_agent.api.routes.get_property_registry", return_value=property_registry):
            yield TestClient(app)


class TestListPropertiesEndpoint:
    def test_list_all_properties(self, client):
        response = client.get("/api/properties")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        assert data[0]["address"] in ["123 Main St", "456 Oak Ave", "789 Pine Rd"]
    
    def test_list_properties_filter_by_owned(self, client):
        response = client.get("/api/properties?property_status=owned")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["address"] == "123 Main St"
        assert data[0]["status"] == "owned"
    
    def test_list_properties_filter_by_viewing(self, client):
        response = client.get("/api/properties?property_status=viewing")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["address"] == "456 Oak Ave"
        assert data[0]["status"] == "viewing"
    
    def test_list_properties_invalid_status(self, client):
        response = client.get("/api/properties?property_status=invalid")
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


class TestCreatePropertyEndpoint:
    def test_create_property_minimal(self, client):
        payload = {
            "id": "new-prop",
            "address": "999 New St",
            "status": "viewing",
        }
        response = client.post("/api/properties", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-prop"
        assert data["address"] == "999 New St"
        assert data["status"] == "viewing"
        assert data["purchase_price"] is None
    
    def test_create_property_full(self, client):
        payload = {
            "id": "new-prop-2",
            "address": "888 Full St",
            "purchase_date": "2023-06-15",
            "purchase_price": 350000.0,
            "current_value": 380000.0,
            "status": "owned",
            "bedrooms": 3,
            "bathrooms": 2,
            "square_feet": 1500,
            "postcode": "SW2B 2BB",
            "notes": "Great investment",
        }
        response = client.post("/api/properties", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["id"] == "new-prop-2"
        assert data["purchase_price"] == 350000.0
        assert data["bedrooms"] == 3
        assert data["notes"] == "Great investment"
    
    def test_create_property_duplicate_id(self, client):
        payload = {
            "id": "prop1",  # Already exists
            "address": "Duplicate St",
            "status": "viewing",
        }
        response = client.post("/api/properties", json=payload)
        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]
    
    def test_create_property_invalid_status(self, client):
        payload = {
            "id": "bad-prop",
            "address": "Bad St",
            "status": "invalid_status",
        }
        response = client.post("/api/properties", json=payload)
        assert response.status_code == 400
        assert "Invalid status" in response.json()["detail"]


class TestExpiringMortgagesEndpoint:
    def test_expiring_mortgages_default_6_months(self, client):
        response = client.get("/api/mortgages/expiring")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["lender"] == "Big Bank"
        assert data[0]["property_id"] == "prop1"
        assert data[0]["interest_rate"] == 4.5
        assert data[0]["months_until_expiry"] is not None
    
    def test_expiring_mortgages_custom_months(self, client):
        response = client.get("/api/mortgages/expiring?months=3")
        assert response.status_code == 200
        data = response.json()
        # Mortgage expires in ~4 months, so won't show in 3-month window
        assert len(data) == 0
    
    def test_expiring_mortgages_long_window(self, client):
        response = client.get("/api/mortgages/expiring?months=12")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["lender"] == "Big Bank"
    
    def test_expiring_mortgages_invalid_months_too_low(self, client):
        response = client.get("/api/mortgages/expiring?months=0")
        assert response.status_code == 400
        assert "must be between 1 and 120" in response.json()["detail"]
    
    def test_expiring_mortgages_invalid_months_too_high(self, client):
        response = client.get("/api/mortgages/expiring?months=200")
        assert response.status_code == 400
        assert "must be between 1 and 120" in response.json()["detail"]


class TestPortfolioSummaryEndpoint:
    def test_portfolio_summary_default(self, client):
        response = client.get("/api/portfolio/summary")
        assert response.status_code == 200
        data = response.json()
        
        # Verify counts
        assert data["total_properties"] == 3
        assert data["owned_count"] == 1
        assert data["under_offer_count"] == 1
        assert data["viewing_count"] == 1
        
        # Verify rent (1800 + 2200 = 4000)
        assert data["total_monthly_rent"] == 4000.0
        assert data["active_tenants"] == 2
        
        # Verify maintenance (1 open: REPORTED)
        assert data["open_maintenance_count"] == 1
        
        # Verify expiring mortgages (default 6 months)
        assert data["expiring_mortgages_count"] == 1
    
    def test_portfolio_summary_custom_expiring_window(self, client):
        response = client.get("/api/portfolio/summary?expiring_window_months=3")
        assert response.status_code == 200
        data = response.json()
        
        # Mortgage expires in ~4 months, so won't show in 3-month window
        assert data["expiring_mortgages_count"] == 0
        
        # Other metrics should remain the same
        assert data["total_properties"] == 3
        assert data["total_monthly_rent"] == 4000.0
