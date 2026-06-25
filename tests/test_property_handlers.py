"""Tests for property and mortgage command handlers in orchestrator."""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

import pytest

from business_agent.orchestrator.service import BusinessOrchestrator, TelegramReply
from business_agent.property.models import (
    Contact,
    ContactType,
    Mortgage,
    Property,
    PropertyStatus,
    Tenant,
)
from business_agent.property.registry import InMemoryPropertyRegistry


class FakeMemoryStore:
    """Fake memory store for testing."""
    def ensure_collection(self):
        pass
    def upsert(self, records):
        pass
    def query(self, request):
        return []


class FakeTaskQueue:
    """Fake task queue for testing."""
    def enqueue(self, task):
        pass


class FakeIngestionService:
    """Fake ingestion service for testing."""
    def ingest_from_uri(self, source_uri, event_date=None):
        return Mock(document_id="doc123", chunk_ids=["chunk1"])


@pytest.fixture
def property_registry():
    """Property registry with sample data."""
    registry = InMemoryPropertyRegistry()
    
    # Add sample properties
    prop1 = Property(
        id="prop1",
        address="123 Main St",
        purchase_date=date(2023, 1, 15),
        purchase_price=Decimal("250000"),
        current_value=Decimal("280000"),
        status=PropertyStatus.OWNED,
        bedrooms=3,
        bathrooms=2,
        postcode="SW1A 1AA",
        notes="Great location",
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
    registry.add_property(prop1)
    registry.add_property(prop2)
    
    # Add mortgage for prop1
    mort1 = Mortgage(
        id="mort1",
        property_id="prop1",
        lender="Big Bank",
        principal=Decimal("200000"),
        interest_rate=Decimal("4.5"),
        term_months=240,
        start_date=date(2023, 1, 15),
        monthly_payment=Decimal("1500.00"),
        end_date=date(2026, 10, 1),  # ~4 months from now (June 2026)
    )
    registry.add_mortgage(mort1)
    
    # Add tenant for prop1
    tenant1 = Tenant(
        id="tenant1",
        property_id="prop1",
        name="John Smith",
        email="john@example.com",
        phone="+44123456789",
        lease_start=date(2024, 1, 1),
        lease_end=date(2026, 12, 31),
        monthly_rent=Decimal("1800.00"),
        deposit=Decimal("1800.00"),
        is_active=True,
    )
    registry.add_tenant(tenant1)
    
    return registry


@pytest.fixture
def orchestrator(property_registry):
    """Orchestrator with fake dependencies."""
    return BusinessOrchestrator(
        memory_store=FakeMemoryStore(),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        property_registry=property_registry,
    )


class TestPropertyCommandHandlers:
    def test_property_list_all(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property list")
        assert isinstance(reply, TelegramReply)
        assert "Found 2 properties" in reply.text
        assert "123 Main St" in reply.text
        assert "456 Oak Ave" in reply.text
    
    def test_property_list_filter_by_status(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property list status=owned")
        assert "Found 1 property" in reply.text
        assert "123 Main St" in reply.text
        assert "456 Oak Ave" not in reply.text
    
    def test_property_list_filter_by_viewing(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property list status=viewing")
        assert "Found 1 property" in reply.text
        assert "456 Oak Ave" in reply.text
        assert "123 Main St" not in reply.text
    
    def test_property_list_invalid_status(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property list status=invalid")
        assert "Invalid status" in reply.text
    
    def test_property_list_no_results(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property list status=sold")
        assert "No properties found" in reply.text
    
    def test_property_show_found(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property show prop1")
        assert "123 Main St" in reply.text
        assert "owned" in reply.text
        assert "SW1A 1AA" in reply.text
        assert "3" in reply.text  # bedrooms
        assert "250,000" in reply.text or "250000" in reply.text  # purchase price
        assert "280,000" in reply.text or "280000" in reply.text  # current value
        assert "Great location" in reply.text
        # Should also show mortgage
        assert "Big Bank" in reply.text
        assert "1,500" in reply.text or "1500" in reply.text  # monthly payment
        # Should also show tenant
        assert "John Smith" in reply.text
        assert "1,800" in reply.text or "1800" in reply.text  # rent
    
    def test_property_show_not_found(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property show nonexistent")
        assert "Property not found" in reply.text
    
    def test_property_show_missing_id(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property show")
        assert "Could not parse property command" in reply.text
        assert "requires a property ID" in reply.text
    
    def test_property_add_not_implemented(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property add")
        assert "not yet implemented" in reply.text
        assert "POST /api/properties" in reply.text
    
    def test_property_unknown_subcommand(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/property delete prop1")
        assert "Could not parse property command" in reply.text


class TestMortgageCommandHandlers:
    def test_mortgage_expiring_default_6_months(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage expiring")
        assert "1 mortgage(s) expiring within 6 months" in reply.text
        assert "123 Main St" in reply.text
        assert "Big Bank" in reply.text
        assert "4.5%" in reply.text
        assert "2026-10-01" in reply.text
    
    def test_mortgage_expiring_custom_months(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage expiring months=3")
        # Mortgage expires in ~4 months (June to October 2026), so won't show in 3-month window
        assert "No mortgages expiring within 3 months" in reply.text
    
    def test_mortgage_expiring_long_window(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage expiring months=12")
        assert "1 mortgage(s) expiring within 12 months" in reply.text
        assert "Big Bank" in reply.text
    
    def test_mortgage_add_not_implemented(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage add prop1")
        assert "not yet implemented" in reply.text
        assert "POST /api/mortgages" in reply.text
    
    def test_mortgage_add_missing_property_id(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage add")
        assert "Could not parse mortgage command" in reply.text
        assert "requires a property ID" in reply.text
    
    def test_mortgage_unknown_subcommand(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage delete mort1")
        assert "Could not parse mortgage command" in reply.text


class TestPropertyRegistryNotConfigured:
    def test_property_command_without_registry(self):
        orch = BusinessOrchestrator(
            memory_store=FakeMemoryStore(),
            task_queue=FakeTaskQueue(),
            ingestion_service=FakeIngestionService(),
            property_registry=None,
        )
        reply = orch.handle_telegram_message_with_ui(chat_id=12345, message_text="/property list")
        assert "Property registry is not configured" in reply.text
    
    def test_mortgage_command_without_registry(self):
        orch = BusinessOrchestrator(
            memory_store=FakeMemoryStore(),
            task_queue=FakeTaskQueue(),
            ingestion_service=FakeIngestionService(),
            property_registry=None,
        )
        reply = orch.handle_telegram_message_with_ui(chat_id=12345, message_text="/mortgage expiring")
        assert "Property registry is not configured" in reply.text


class TestHelpTextIncludesPropertyCommands:
    def test_help_includes_property_commands(self, orchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=12345, message_text="/help")
        assert "/property" in reply.text
        assert "/mortgage" in reply.text
