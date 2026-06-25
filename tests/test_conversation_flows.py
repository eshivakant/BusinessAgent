"""Tests for interactive conversation flows (property add, mortgage add)."""
import pytest
from decimal import Decimal
from datetime import date
from typing import Any

from business_agent.orchestrator.service import BusinessOrchestrator
from business_agent.memory.store import MemoryStore
from business_agent.ingestion.service import IngestionResult
from business_agent.property.registry import InMemoryPropertyRegistry


class FakeMemoryStore(MemoryStore):
    def store(self, text, metadata, event_date, embedding):
        pass
    
    def query(self, query_input):
        return []


class FakeTaskQueue:
    def enqueue_document_ingestion(self, task):
        return "job123"


class FakeIngestionService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
    
    def ingest_from_uri(
        self,
        source_uri: str,
        event_date: date | None = None,
        requester_id: int | None = None,
    ) -> IngestionResult:
        self.calls.append({
            "source_uri": source_uri,
            "event_date": event_date,
            "requester_id": requester_id,
        })
        return IngestionResult(
            success=True,
            source_uri=source_uri,
            chunks_stored=1,
            summary="Test summary",
            error=None,
        )


@pytest.fixture
def property_registry():
    """Property registry with some test data."""
    registry = InMemoryPropertyRegistry()
    
    from business_agent.property.models import Property, PropertyStatus
    
    prop1 = Property(
        id="prop1",
        address="123 Main St",
        postcode="W1A 1AA",
        bedrooms=2,
        bathrooms=1,
        purchase_date=date(2020, 1, 15),
        purchase_price=Decimal("250000"),
        current_value=Decimal("300000"),
        status=PropertyStatus.OWNED,
    )
    
    registry.add_property(prop1)
    
    return registry


@pytest.fixture
def orchestrator(property_registry):
    """Orchestrator with property registry."""
    return BusinessOrchestrator(
        memory_store=FakeMemoryStore(),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        property_registry=property_registry,
    )


class TestPropertyAddConversationFlow:
    """Test complete property add conversation flow."""
    
    def test_complete_property_add_minimal(self, orchestrator, property_registry):
        """Test adding property with minimal required fields."""
        chat_id = 98765
        
        # Step 1: Start the conversation
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        assert "Let's add a new property" in reply.text
        assert "provide the property address" in reply.text
        
        # Step 2: Provide address
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="456 Oak Avenue, London")
        assert "What's the postcode" in reply.text
        
        # Step 3: Skip postcode
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "How many bedrooms" in reply.text
        
        # Step 4: Skip bedrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "How many bathrooms" in reply.text
        
        # Step 5: Skip bathrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Square feet" in reply.text
        
        # Step 6: Skip square feet
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Purchase date" in reply.text
        
        # Step 7: Skip purchase date
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Purchase price" in reply.text
        
        # Step 8: Skip purchase price
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Current value" in reply.text
        
        # Step 9: Skip current value
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Property status" in reply.text
        
        # Step 10: Provide status
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="owned")
        assert "Any notes" in reply.text
        
        # Step 11: Skip notes
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Please confirm the property details" in reply.text
        assert "456 Oak Avenue, London" in reply.text
        assert "owned" in reply.text
        
        # Step 12: Confirm
        initial_count = len(property_registry.list_properties())
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="yes")
        assert "Property added successfully" in reply.text
        assert "prop-" in reply.text  # Generated ID
        
        # Verify property was added
        assert len(property_registry.list_properties()) == initial_count + 1
    
    def test_complete_property_add_full(self, orchestrator, property_registry):
        """Test adding property with all fields."""
        chat_id = 11111
        
        # Start conversation
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        
        # Provide address
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="789 Elm Street, Manchester")
        
        # Provide postcode
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="M1 1AA")
        assert "How many bedrooms" in reply.text
        
        # Provide bedrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="3")
        assert "How many bathrooms" in reply.text
        
        # Provide bathrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2")
        assert "Square feet" in reply.text
        
        # Provide square feet
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="1500")
        assert "Purchase date" in reply.text
        
        # Provide purchase date
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2023-05-20")
        assert "Purchase price" in reply.text
        
        # Provide purchase price
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="£350,000")
        assert "Current value" in reply.text
        
        # Provide current value
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="400000")
        assert "Property status" in reply.text
        
        # Provide status
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="owned")
        assert "Any notes" in reply.text
        
        # Provide notes
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Near city center, excellent transport links")
        assert "Please confirm the property details" in reply.text
        assert "789 Elm Street, Manchester" in reply.text
        assert "M1 1AA" in reply.text
        assert "3" in reply.text  # bedrooms
        assert "2" in reply.text  # bathrooms
        assert "1500" in reply.text  # square feet
        assert "2023-05-20" in reply.text
        assert "£350,000" in reply.text
        assert "£400,000" in reply.text
        assert "owned" in reply.text
        assert "Near city center" in reply.text
        
        # Confirm
        initial_count = len(property_registry.list_properties())
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="yes")
        assert "Property added successfully" in reply.text
        
        # Verify property was added with all fields
        assert len(property_registry.list_properties()) == initial_count + 1
        properties = property_registry.list_properties()
        new_prop = [p for p in properties if p.address == "789 Elm Street, Manchester"][0]
        assert new_prop.postcode == "M1 1AA"
        assert new_prop.bedrooms == 3
        assert new_prop.bathrooms == 2
        assert new_prop.square_feet == 1500
        assert new_prop.purchase_price == Decimal("350000")
        assert new_prop.current_value == Decimal("400000")
        assert new_prop.notes == "Near city center, excellent transport links"
    
    def test_property_add_cancel_during_conversation(self, orchestrator, property_registry):
        """Test cancelling property add mid-conversation."""
        chat_id = 22222
        
        # Start conversation
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        
        # Provide address
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Cancel Test St")
        
        # Cancel
        initial_count = len(property_registry.list_properties())
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/cancel")
        assert "Conversation cancelled" in reply.text
        
        # Verify nothing was added
        assert len(property_registry.list_properties()) == initial_count
        
        # Verify we can start a new command
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property list")
        assert "propert" in reply.text  # Should show properties list
    
    def test_property_add_reject_at_confirmation(self, orchestrator, property_registry):
        """Test rejecting property at confirmation step."""
        chat_id = 33333
        
        # Go through full flow
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Reject Test Ave")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="owned")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        
        # Reject at confirmation
        initial_count = len(property_registry.list_properties())
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="no")
        assert "cancelled" in reply.text
        
        # Verify nothing was added
        assert len(property_registry.list_properties()) == initial_count
    
    def test_property_add_invalid_bedrooms(self, orchestrator):
        """Test validation for invalid bedrooms."""
        chat_id = 44444
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Validation Test")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # postcode
        
        # Try invalid bedrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="not a number")
        assert "valid number" in reply.text
        
        # Try negative bedrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="-5")
        assert "must be positive" in reply.text
        
        # Provide valid bedrooms
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2")
        assert "bathrooms" in reply.text
    
    def test_property_add_invalid_price(self, orchestrator):
        """Test validation for invalid price."""
        chat_id = 55555
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Price Test")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # postcode
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # bedrooms
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # bathrooms
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # square_feet
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # purchase_date
        
        # Try invalid price
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="not a price")
        assert "valid price" in reply.text
        
        # Try negative price
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="-50000")
        assert "must be positive" in reply.text
    
    def test_property_add_invalid_status(self, orchestrator):
        """Test validation for invalid status."""
        chat_id = 66666
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/property add")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Status Test")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # postcode
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # bedrooms
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # bathrooms
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # square_feet
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # purchase_date
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # purchase_price
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")  # current_value
        
        # Try invalid status
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="invalid_status")
        assert "Invalid status" in reply.text
        assert "owned" in reply.text
        assert "viewing" in reply.text
        assert "under_offer" in reply.text


class TestMortgageAddConversationFlow:
    """Test complete mortgage add conversation flow."""
    
    def test_complete_mortgage_add(self, orchestrator, property_registry):
        """Test adding mortgage with all fields."""
        chat_id = 77777
        
        # Start conversation
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/mortgage add prop1")
        assert "Let's add a mortgage for property prop1" in reply.text
        assert "lender name" in reply.text
        
        # Provide lender
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Test Bank")
        assert "principal" in reply.text.lower() or "loan amount" in reply.text.lower()
        
        # Provide principal
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="200000")
        assert "interest rate" in reply.text.lower()
        
        # Provide interest_rate
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="3.5")
        assert "term" in reply.text.lower() or "months" in reply.text.lower()
        
        # Provide term_months
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="300")
        assert "monthly payment" in reply.text.lower()
        
        # Provide monthly payment
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="£1,200")
        assert "start date" in reply.text.lower()
        
        # Provide start date
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2024-01-01")
        assert "product type" in reply.text.lower()
        
        # Provide product type
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Fixed 5 year")
        assert "notes" in reply.text.lower()
        
        # Provide notes
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Good rate")
        assert "Please confirm the mortgage details" in reply.text
        assert "prop1" in reply.text
        assert "Test Bank" in reply.text
        assert "3.5%" in reply.text
        
        # Confirm
        initial_mortgages = property_registry.list_mortgages(property_id="prop1")
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="yes")
        assert "Mortgage added successfully" in reply.text
        assert "mort-" in reply.text
        
        # Verify mortgage was added
        mortgages = property_registry.list_mortgages(property_id="prop1")
        assert len(mortgages) == len(initial_mortgages) + 1
        new_mortgage = mortgages[-1]
        assert new_mortgage.lender == "Test Bank"
        assert new_mortgage.interest_rate == Decimal("3.5")
        assert new_mortgage.principal == Decimal("200000")
        assert new_mortgage.term_months == 300
        assert new_mortgage.monthly_payment == Decimal("1200")
    
    def test_mortgage_add_minimal(self, orchestrator, property_registry):
        """Test adding mortgage with minimal fields (skip optional)."""
        chat_id = 88888
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/mortgage add prop1")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Minimal Bank")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="250000")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2.5")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="360")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="1000")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2025-01-01")
        
        # Skip product_type
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        
        # Skip notes
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="skip")
        assert "Please confirm" in reply.text
        
        # Confirm
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="yes")
        assert "Mortgage added successfully" in reply.text
    
    def test_mortgage_add_cancel(self, orchestrator, property_registry):
        """Test cancelling mortgage add."""
        chat_id = 99999
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/mortgage add prop1")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Cancel Bank")
        
        # Cancel
        initial_mortgages = property_registry.list_mortgages(property_id="prop1")
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/cancel")
        assert "Conversation cancelled" in reply.text
        
        # Verify nothing was added
        mortgages = property_registry.list_mortgages(property_id="prop1")
        assert len(mortgages) == len(initial_mortgages)
    
    def test_mortgage_add_invalid_rate(self, orchestrator):
        """Test validation for invalid rate."""
        chat_id = 111111
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/mortgage add prop1")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Test Bank")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="200000")
        
        # Try invalid rate
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="not a rate")
        assert "valid rate" in reply.text
        
        # Try negative rate
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="-5")
        assert "between 0 and 100" in reply.text
        
        # Try rate over 100
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="150")
        assert "between 0 and 100" in reply.text
    
    def test_mortgage_add_invalid_date(self, orchestrator):
        """Test validation for invalid date."""
        chat_id = 222222
        
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="/mortgage add prop1")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="Test Bank")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="200000")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="3.5")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="300")
        orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="1200")
        
        # Try invalid date format
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="01/01/2024")
        assert "format YYYY-MM-DD" in reply.text or "Invalid date" in reply.text
        
        # Try invalid date values
        reply = orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text="2024-13-45")
        assert "Invalid date" in reply.text or "format YYYY-MM-DD" in reply.text


class TestMultipleUsersConversations:
    """Test handling multiple concurrent conversations."""
    
    def test_multiple_users_independent_conversations(self, orchestrator, property_registry):
        """Test that multiple users can have independent conversations."""
        user1 = 1001
        user2 = 1002
        
        # User 1 starts property add
        reply1 = orchestrator.handle_telegram_message_with_ui(chat_id=user1, message_text="/property add")
        assert "property address" in reply1.text
        
        # User 2 starts mortgage add
        reply2 = orchestrator.handle_telegram_message_with_ui(chat_id=user2, message_text="/mortgage add prop1")
        assert "lender name" in reply2.text
        
        # User 1 continues property add
        reply1 = orchestrator.handle_telegram_message_with_ui(chat_id=user1, message_text="User1 Property")
        assert "postcode" in reply1.text
        
        # User 2 continues mortgage add
        reply2 = orchestrator.handle_telegram_message_with_ui(chat_id=user2, message_text="User2 Bank")
        assert "principal" in reply2.text.lower() or "loan amount" in reply2.text.lower()
        
        # Verify conversations are independent
        assert "property" not in reply2.text.lower() or "mortgage" in reply2.text.lower()
        assert "bank" not in reply1.text.lower()
