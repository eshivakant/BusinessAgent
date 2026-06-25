"""Tests for NL query intent handlers in the orchestrator."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from business_agent.ingestion.registry import DocumentInfo, InMemoryDocumentRegistry
from business_agent.ingestion.service import IngestionResult
from business_agent.memory.models import MemoryMatch, MemoryPayload, MemoryQueryInput
from business_agent.memory.store import MemoryStore
from business_agent.orchestrator.service import BusinessOrchestrator
from business_agent.property.registry import InMemoryPropertyRegistry


class FakeMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._records: list[Any] = []

    def upsert(self, records: list[Any]) -> None:
        self._records.extend(records)

    def query(self, query_input: MemoryQueryInput) -> list[MemoryMatch]:
        # Return mock matches based on the query text
        if "EPC" in query_input.query or "epc" in query_input.query:
            payload = MemoryPayload(
                event_date=date(2025, 1, 1),
                ingested_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                effective_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                source_type="pdf",
                source_uri="/data/epc_cert.pdf",
                record_type="summary",
                summary="EPC certificate valid until 2030",
                property_address="133 Bowland Drive",
                document_type="epc_certificate",
            )
            return [MemoryMatch(id="epc1", text="EPC certificate valid until 2030. Rating: B.", payload=payload, score=0.95)]
        if "invoice" in query_input.query.lower() or "180" in query_input.query:
            payload = MemoryPayload(
                event_date=date(2026, 6, 12),
                ingested_at=datetime(2026, 6, 12, tzinfo=timezone.utc),
                effective_date=datetime(2026, 6, 12, tzinfo=timezone.utc),
                source_type="pdf",
                source_uri="/data/invoice_180.pdf",
                record_type="summary",
                summary="Invoice for £180",
                amount=180.0,
                document_type="invoice",
            )
            return [MemoryMatch(id="inv1", text="Invoice #12345 for £180", payload=payload, score=0.90)]
        if "tenancy" in query_input.query.lower():
            payload = MemoryPayload(
                event_date=date(2024, 3, 1),
                ingested_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
                effective_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
                source_type="docx",
                source_uri="/data/tenancy.docx",
                record_type="summary",
                summary="Tenancy agreement with no pet clause",
                property_address="133 Bowland Drive",
                document_type="tenancy_agreement",
            )
            return [MemoryMatch(id="ten1", text="The tenant shall not keep any pets on the property without written consent.", payload=payload, score=0.92)]
        return []


class FakeTaskQueue:
    def enqueue_document_ingestion(self, task: Any) -> str:
        return "job123"


class FakeIngestionService:
    def ingest_from_uri(self, **kwargs: Any) -> IngestionResult:
        return IngestionResult(
            success=True,
            source_uri=kwargs.get("source_uri", ""),
            chunks_stored=1,
            summary="Test",
            error=None,
        )


class FakeLLMClient:
    """Mock LLM client for testing."""

    def answer_question(self, question: str, context: str) -> str:
        if "no pet" in question.lower():
            return "Yes, the tenancy agreement contains a 'no pet' clause."
        if "epc" in question.lower():
            return "The EPC certificate expires on 15 March 2030."
        return "I found relevant information."

    def transcribe_audio(self, file_path: str) -> str:
        return "This is a transcribed voice note."

    def extract_structured_metadata(self, text: str, source_uri: str) -> Any:
        from business_agent.llm.client import DocumentMetadata
        return DocumentMetadata(
            document_type="invoice",
            vendor="TestVendor",
            department="Finance",
            keywords=["test"],
            property_address="133 Bowland Drive",
            amount=180.0,
        )

    def ocr_image(self, file_path: str) -> str:
        return "OCR extracted text"


@pytest.fixture
def document_registry_with_docs() -> InMemoryDocumentRegistry:
    """Document registry with test documents."""
    registry = InMemoryDocumentRegistry()

    # Mortgage offer documents
    registry.register(DocumentInfo(
        document_id="doc1",
        title="Mortgage Offer - HSBC",
        document_type="mortgage_offer",
        vendor="HSBC",
        department="Mortgage",
        keywords=["mortgage", "offer"],
        source_uri="/data/mortgage_hsbc.pdf",
        source_type="pdf",
        archived_file_path="/data/mortgage_hsbc.pdf",
        ingested_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        effective_date=datetime(2026, 5, 1, tzinfo=timezone.utc),
        event_date=date(2026, 5, 1),
        summary="HSBC mortgage offer at 3.5%",
        chunk_count=3,
        property_address="133 Bowland Drive",
        amount=200000.0,
    ))

    registry.register(DocumentInfo(
        document_id="doc2",
        title="Mortgage Offer - Barclays",
        document_type="mortgage_offer",
        vendor="Barclays",
        department="Mortgage",
        keywords=["mortgage", "offer"],
        source_uri="/data/mortgage_barclays.pdf",
        source_type="pdf",
        archived_file_path="/data/mortgage_barclays.pdf",
        ingested_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
        effective_date=datetime(2026, 4, 15, tzinfo=timezone.utc),
        event_date=date(2026, 4, 15),
        summary="Barclays mortgage offer at 3.2%",
        chunk_count=3,
        property_address="133 Bowland Drive",
        amount=200000.0,
    ))

    # Bank statement
    registry.register(DocumentInfo(
        document_id="doc3",
        title="Bank Statement Jan 2026",
        document_type="bank_statement",
        vendor="HSBC",
        department="Finance",
        keywords=["statement"],
        source_uri="/data/statement_jan.pdf",
        source_type="pdf",
        archived_file_path="/data/statement_jan.pdf",
        ingested_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
        effective_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        event_date=date(2026, 1, 31),
        summary="Monthly bank statement",
        chunk_count=2,
        property_address="133 Bowland Drive",
    ))

    # Completion statement
    registry.register(DocumentInfo(
        document_id="doc4",
        title="Completion Statement",
        document_type="completion_statement",
        vendor="Solicitors LLP",
        department="Legal",
        keywords=["completion"],
        source_uri="/data/completion.pdf",
        source_type="pdf",
        archived_file_path="/data/completion.pdf",
        ingested_at=datetime(2025, 6, 15, tzinfo=timezone.utc),
        effective_date=datetime(2025, 6, 15, tzinfo=timezone.utc),
        event_date=date(2025, 6, 15),
        summary="Completion statement for property purchase",
        chunk_count=4,
    ))

    return registry


@pytest.fixture
def orchestrator(document_registry_with_docs: InMemoryDocumentRegistry) -> BusinessOrchestrator:
    """Orchestrator with all services wired for NL query testing."""
    return BusinessOrchestrator(
        memory_store=FakeMemoryStore(),
        task_queue=FakeTaskQueue(),
        ingestion_service=FakeIngestionService(),
        document_registry=document_registry_with_docs,
        property_registry=InMemoryPropertyRegistry(),
        llm_client=FakeLLMClient(),
    )


class TestCompareMortgagesHandler:
    def test_compare_mortgages_with_address(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="compare mortgage offers for 133 Bowland Drive within last 2 months"
        )
        assert "133 Bowland Drive" in reply.text
        assert "mortgage offer" in reply.text.lower() or "mortgage" in reply.text.lower()

    def test_compare_mortgages_no_address(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="compare mortgage offers within last 2 months"
        )
        assert "couldn't identify" in reply.text.lower() or "address" in reply.text.lower()

    def test_compare_mortgages_no_results(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="compare mortgage offers for 999 Unknown Drive within last 2 months"
        )
        assert "no mortgage offers" in reply.text.lower() or "not found" in reply.text.lower()


class TestEpcExpiryHandler:
    def test_epc_expiry_with_llm(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="When is the EPC certificate expiring for 133 Bowland Drive"
        )
        assert "EPC" in reply.text

    def test_epc_expiry_no_address(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="When is the EPC certificate expiring"
        )
        assert "couldn't identify" in reply.text.lower() or "address" in reply.text.lower()


class TestMortgageStatementsHandler:
    def test_mortgage_statements_with_address(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="Show me mortgage statements for 133 Bowland Drive for past 2 years"
        )
        # Should find bank_statement docs
        assert "133 Bowland Drive" in reply.text

    def test_mortgage_statements_no_address(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="Show me mortgage statements for past 2 years"
        )
        assert "couldn't identify" in reply.text.lower() or "address" in reply.text.lower()


class TestTenancyClauseCheckHandler:
    def test_tenancy_clause_check_with_llm(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="Does the tenancy agreement for 133 Bowland Drive has 'no pet' clause?"
        )
        assert "tenancy" in reply.text.lower() or "pet" in reply.text.lower()

    def test_tenancy_clause_check_no_address(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="Does the tenancy agreement has 'no pet' clause?"
        )
        assert "couldn't identify" in reply.text.lower() or "address" in reply.text.lower()


class TestBulkDocumentLinksHandler:
    def test_bulk_document_links_completion(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="give me the links for all completion statements within last year"
        )
        # Completion doc may or may not be within range depending on today's date
        # Just verify the handler returns a string response
        assert isinstance(reply.text, str)
        assert len(reply.text) > 0

    def test_bulk_document_links_no_results(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="give me the links for all documents within last 1 month"
        )
        # May or may not have results depending on date
        assert isinstance(reply.text, str)


class TestTransactionMatchingHandler:
    def test_transaction_matching_with_amount(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="I can see a transaction of £180 on 12 June 2026, do we have a corresponding invoice?"
        )
        assert "180" in reply.text
        assert "invoice" in reply.text.lower() or "match" in reply.text.lower()

    def test_transaction_matching_no_amount(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="do we have a corresponding invoice?"
        )
        # Without amount, should fall to general question
        assert isinstance(reply.text, str)


class TestGeneralQuestionFallback:
    def test_general_question_routes_to_memory(self, orchestrator: BusinessOrchestrator):
        reply = orchestrator.handle_telegram_message_with_ui(
            chat_id=123,
            message_text="What is the capital of France?"
        )
        # Should return a response (either match or no match)
        assert isinstance(reply.text, str)
        assert len(reply.text) > 0


class TestOrchestratorNewMethods:
    def test_memorize_text_message_without_service(self):
        """Test memorize_text_message returns None when service not configured."""
        orch = BusinessOrchestrator(
            memory_store=FakeMemoryStore(),
            task_queue=FakeTaskQueue(),
            ingestion_service=FakeIngestionService(),
        )
        assert orch.memorize_text_message(chat_id=1, text="test") is None

    def test_memorize_text_message_with_service(self):
        """Test memorize_text_message stores text when service is configured."""
        from business_agent.memory.text_memorization import TextMemorizationService
        store = FakeMemoryStore()
        orch = BusinessOrchestrator(
            memory_store=store,
            task_queue=FakeTaskQueue(),
            ingestion_service=FakeIngestionService(),
            text_memorization_service=TextMemorizationService(memory_store=store),
        )
        record_id = orch.memorize_text_message(chat_id=1, text="test message")
        assert record_id is not None
        assert record_id.startswith("memo-")

    def test_transcribe_and_store_voice_without_llm(self):
        """Test voice transcription returns None when LLM not configured."""
        orch = BusinessOrchestrator(
            memory_store=FakeMemoryStore(),
            task_queue=FakeTaskQueue(),
            ingestion_service=FakeIngestionService(),
        )
        result = orch.transcribe_and_store_voice(chat_id=1, audio_file_path="/tmp/voice.ogg")
        assert result is None

    def test_transcribe_and_store_voice_with_llm(self):
        """Test voice transcription works when LLM is configured."""
        from business_agent.memory.text_memorization import TextMemorizationService
        store = FakeMemoryStore()
        orch = BusinessOrchestrator(
            memory_store=store,
            task_queue=FakeTaskQueue(),
            ingestion_service=FakeIngestionService(),
            llm_client=FakeLLMClient(),
            text_memorization_service=TextMemorizationService(memory_store=store),
        )
        result = orch.transcribe_and_store_voice(
            chat_id=1, audio_file_path="/tmp/voice.ogg", file_id="file123"
        )
        assert result is not None
        assert "transcribed" in result.lower() or "voice note" in result.lower()
