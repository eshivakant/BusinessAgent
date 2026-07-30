from __future__ import annotations

import shlex
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from textwrap import shorten
from typing import Any

from business_agent.config import get_settings
from business_agent.conveyancing.service import ConveyancingService
from business_agent.data.readonly_sql import ReadOnlySQLDataAccess, SQLReadRequest
from business_agent.ingestion.registry import DocumentRegistry
from business_agent.ingestion.service import DocumentIngestionService, IngestionResult
from business_agent.maintenance.service import MaintenanceService
from business_agent.memory.models import MemoryMatch, MemoryQueryInput
from business_agent.memory.store import MemoryStore
from business_agent.orchestrator.commands import (
    AskCommand,
    ListCommand,
    MortgageExpiringCommand,
    PropertyListCommand,
    PropertyShowCommand,
    parse_ask_command,
    parse_data_command,
    parse_ingest_command,
    parse_list_command,
    parse_mortgage_command,
    parse_property_command,
    parse_question_with_optional_dates,
)
from business_agent.orchestrator.conversation import ConversationStore
from business_agent.orchestrator.conversation_state import ConversationFlow, ConversationManager
from business_agent.orchestrator.nl_query import QueryIntent, ParsedNLQuery, parse_natural_language_query
from business_agent.property.registry import PropertyRegistry
from business_agent.tenancy.service import TenancyService
from business_agent.worker.contracts import DocumentIngestionTask, SubagentTaskQueue


HELP_TEXT = (
    "Commands:\n"
    "/ask [from=YYYY-MM-DD] [to=YYYY-MM-DD] <question>\n"
    "/ingest <source_uri> [event_date=YYYY-MM-DD]\n"
    "/list [type=<type>] [vendor=<vendor>] [date_from=YYYY-MM-DD] [date_to=YYYY-MM-DD] [limit=<n>]\n"
    "/property list [status=<status>]\n"
    "/property show <property_id>\n"
    "/property add\n"
    "/mortgage add <property_id>\n"
    "/mortgage expiring [months=<n>]\n"
    "/tenant add <property_id>\n"
    "/tenant list <property_id>\n"
    "/tenant show <tenancy_id>\n"
    "/tenant search <query> [tenancy_id=<id>]\n"
    "/agreement generate <tenancy_id>\n"
    "/conveyancing list\n"
    "/conveyancing new purchase <property_id>\n"
    "/conveyancing show <transaction_id>\n"
    "/maintenance list <property_id>\n"
    "/data table=<name> columns=<c1,c2> filters=<key:value,...> limit=<n>\n"
    "/reset\n\n"
    "📝 You can also send documents (PDF, DOCX, TXT) or photos for automatic ingestion.\n"
    "🎙️ Send voice notes - they'll be transcribed and memorized.\n"
    "💬 Send text messages - they'll be memorized for future reference.\n\n"
    "Natural language queries you can ask:\n"
    "• 'compare mortgage offers for 133 Bowland Drive within last 2 months'\n"
    "• 'When is the EPC certificate expiring for 133 Bowland Drive'\n"
    "• 'Show me mortgage statements for 133 Bowland Drive for past 2 years'\n"
    "• 'Does the tenancy agreement for 133 Bowland Drive has no pet clause?'\n"
    "• 'Give me links for all completion statements within last year'\n"
    "• 'I see a transaction of £180 on 12 June 2026, do we have a corresponding invoice?'\n"
)


@dataclass(frozen=True)
class TelegramReply:
    text: str
    detailed_text: str | None = None
    sources_text: str | None = None
    question_text: str | None = None
    show_actions: bool = False


class BusinessOrchestrator:
    def __init__(
        self,
        memory_store: MemoryStore,
        task_queue: SubagentTaskQueue,
        ingestion_service: DocumentIngestionService,
        conversation_store: ConversationStore | None = None,
        sql_reader: ReadOnlySQLDataAccess | None = None,
        document_registry: DocumentRegistry | None = None,
        property_registry: PropertyRegistry | None = None,
        tenancy_service: TenancyService | None = None,
        conveyancing_service: ConveyancingService | None = None,
        maintenance_service: MaintenanceService | None = None,
        llm_client: Any | None = None,
        text_memorization_service: Any | None = None,
    ) -> None:
        self._memory_store = memory_store
        self._task_queue = task_queue
        self._ingestion_service = ingestion_service
        self._conversation_store = conversation_store
        self._sql_reader = sql_reader
        self._document_registry = document_registry
        self._property_registry = property_registry
        self._tenancy_service = tenancy_service
        self._conveyancing_service = conveyancing_service
        self._maintenance_service = maintenance_service
        self._llm_client = llm_client
        self._text_memorization_service = text_memorization_service
        self._settings = get_settings()
        self._conversation_manager = ConversationManager()

    def handle_telegram_message(self, chat_id: int, message_text: str) -> str:
        return self.handle_telegram_message_with_ui(chat_id=chat_id, message_text=message_text).text

    def handle_telegram_message_with_ui(self, chat_id: int, message_text: str) -> TelegramReply:
        text = message_text.strip()
        if not text:
            return TelegramReply(text="Send /help for available actions.")
        
        # Check for active conversation first
        user_id = str(chat_id)
        active_conv = self._conversation_manager.get_conversation(user_id)
        if active_conv:
            # Handle cancel command
            if text.lower() in ["/cancel", "cancel", "quit", "exit"]:
                self._conversation_manager.end_conversation(user_id)
                return TelegramReply(text="Conversation cancelled.")
            
            # Route to appropriate conversation handler
            if active_conv.flow == ConversationFlow.PROPERTY_ADD:
                return self._handle_property_add_conversation(user_id, text, active_conv)
            elif active_conv.flow == ConversationFlow.MORTGAGE_ADD:
                return self._handle_mortgage_add_conversation(user_id, text, active_conv)
            elif active_conv.flow == ConversationFlow.TENANT_ADD:
                return self._handle_tenant_add_conversation(user_id, text, active_conv)
        
        # Handle commands normally
        if text.startswith("/reset"):
            return self._handle_reset_command(chat_id)
        if text.startswith("/help"):
            return TelegramReply(text=HELP_TEXT)
        if text.startswith("/list"):
            return self._handle_list_command(text)
        if text.startswith("/property"):
            return self._handle_property_command(chat_id, text)
        if text.startswith("/mortgage"):
            return self._handle_mortgage_command(chat_id, text)
        if text.startswith("/tenant"):
            return self._handle_tenant_command(chat_id, text)
        if text.startswith("/agreement"):
            return self._handle_agreement_command(chat_id, text)
        if text.startswith("/conveyancing"):
            return self._handle_conveyancing_command(chat_id, text)
        if text.startswith("/maintenance"):
            return self._handle_maintenance_command(chat_id, text)
        if text.startswith("/ingest"):
            return self._handle_ingest_command(text)
        if text.startswith("/data"):
            return self._handle_data_command(text)
        if text.startswith("/ask") or text.startswith("/knowledge"):
            return self._handle_ask_command(chat_id, text)
        return self._handle_freeform_question(chat_id, text)

    def enqueue_document_ingestion(
        self,
        source_uri: str,
        event_date: str | date | None = None,
        requester_id: int | None = None,
    ) -> str:
        parsed_date = self._parse_optional_date(event_date)
        job_id = self._task_queue.enqueue_document_ingestion(
            DocumentIngestionTask(
                source_uri=source_uri,
                event_date=parsed_date,
                requester_id=requester_id,
            )
        )
        return job_id

    def ingest_document_now(
        self,
        source_uri: str,
        event_date: str | date | None = None,
        requester_id: int | None = None,
    ) -> IngestionResult:
        parsed_date = self._parse_optional_date(event_date)
        return self._ingestion_service.ingest_from_uri(
            source_uri=source_uri,
            event_date=parsed_date,
            requester_id=requester_id,
        )

    def query_memory(self, request: MemoryQueryInput) -> list[MemoryMatch]:
        return self._memory_store.query(request)

    def _handle_ask_command(self, chat_id: int, text: str) -> TelegramReply:
        try:
            command = parse_ask_command(text)
        except ValueError as exc:
            return TelegramReply(
                text=(
                    f"Could not parse /ask command: {exc}\n"
                    "Try: /ask from=2026-01-01 to=2026-01-31 revenue trend"
                )
            )

        query_text = self._build_query_text(chat_id=chat_id, question=command.question)
        request = MemoryQueryInput(
            query=query_text,
            date_from=command.date_from,
            date_to=command.date_to,
            top_k=5,
        )
        response = self._answer_with_memory(request=request, question_text=command.question)
        self._record_assistant_turn(chat_id=chat_id, response=response.text)
        return response

    def _handle_freeform_question(self, chat_id: int, text: str) -> TelegramReply:
        """Handle freeform text by parsing NL intent first, falling back to memory search."""
        parsed = parse_natural_language_query(text)
        
        if parsed.intent == QueryIntent.COMPARE_MORTGAGES:
            return self._handle_compare_mortgages(parsed)
        elif parsed.intent == QueryIntent.EPC_EXPIRY:
            return self._handle_epc_expiry(parsed)
        elif parsed.intent == QueryIntent.MORTGAGE_STATEMENTS:
            return self._handle_mortgage_statements(parsed)
        elif parsed.intent == QueryIntent.TENANCY_CLAUSE_CHECK:
            return self._handle_tenancy_clause_check(parsed)
        elif parsed.intent == QueryIntent.BULK_DOCUMENT_LINKS:
            return self._handle_bulk_document_links(parsed)
        elif parsed.intent == QueryIntent.TRANSACTION_MATCHING:
            return self._handle_transaction_matching(parsed)
        else:
            # Fall back to standard memory-based answer
            try:
                command = parse_question_with_optional_dates(text)
            except ValueError:
                command = AskCommand(question=text)

            query_text = self._build_query_text(chat_id=chat_id, question=command.question)
            request = MemoryQueryInput(
                query=query_text,
                date_from=command.date_from or parsed.date_from,
                date_to=command.date_to or parsed.date_to,
                top_k=5,
            )
            response = self._answer_with_memory(request=request, question_text=command.question)
            self._record_assistant_turn(chat_id=chat_id, response=response.text)
            return response

    def _handle_ingest_command(self, text: str) -> TelegramReply:
        try:
            command = parse_ingest_command(text)
        except ValueError as exc:
            return TelegramReply(
                text=(
                    f"Could not queue ingestion: {exc}\n"
                    "Try: /ingest /data/docs/report.pdf event_date=2026-01-15"
                )
            )
        job_id = self.enqueue_document_ingestion(
            source_uri=command.source_uri,
            event_date=command.event_date,
        )
        return TelegramReply(
            text=(
                "Ingestion started.\n"
                "Status: queued\n"
                f"job_id: {job_id}\n"
                f"source: {command.source_uri}\n"
                f"event_date: {command.event_date.isoformat() if command.event_date else 'none'}"
            )
        )

    def _handle_list_command(self, text: str) -> TelegramReply:
        """Handle /list command to query document registry."""
        try:
            command = parse_list_command(text)
        except ValueError as exc:
            return TelegramReply(
                text=(
                    f"Could not parse list command: {exc}\n"
                    "Try: /list type=invoice vendor=acme date_from=2025-01-01 limit=10"
                )
            )
        
        from business_agent.dependencies import get_document_registry
        registry = get_document_registry()
        if registry is None:
            return TelegramReply(text="Document registry is not configured.")
        
        # Query registry
        from datetime import datetime, timezone
        date_from = None
        date_to = None
        if command.date_from:
            date_from = datetime.combine(command.date_from, datetime.min.time(), tzinfo=timezone.utc)
        if command.date_to:
            date_to = datetime.combine(command.date_to, datetime.max.time(), tzinfo=timezone.utc)
        
        docs = registry.query(
            document_type=command.document_type,
            vendor=command.vendor,
            date_from=date_from,
            date_to=date_to,
            limit=command.limit,
        )
        
        if not docs:
            return TelegramReply(text="No documents found matching your query.")
        
        # Format document list
        lines = [f"Found {len(docs)} document(s):"]
        for doc in docs:
            lines.append(
                f"• {doc.title} ({doc.document_type}, {doc.ingested_at.strftime('%Y-%m-%d')})"
            )
            if doc.vendor:
                lines.append(f"  Vendor: {doc.vendor}")
            if doc.summary:
                short_summary = (doc.summary[:80] + "...") if len(doc.summary) > 80 else doc.summary
                lines.append(f"  Summary: {short_summary}")
        
        text = "\n".join(lines)
        return TelegramReply(text=text, show_actions=False)

    def _handle_property_command(self, chat_id: int, text: str) -> TelegramReply:
        """Handle /property commands."""
        if self._property_registry is None:
            return TelegramReply(text="Property registry is not configured.")
        
        try:
            command = parse_property_command(text)
        except ValueError as exc:
            return TelegramReply(
                text=(
                    f"Could not parse property command: {exc}\n"
                    "Try: /property list [status=owned] or /property show <property_id>"
                )
            )
        
        # Handle "add" flow (interactive)
        if command == "add":
            user_id = str(chat_id)
            self._conversation_manager.start_conversation(
                user_id=user_id,
                flow=ConversationFlow.PROPERTY_ADD,
                initial_step="address"
            )
            return TelegramReply(
                text="Let's add a new property. Please provide the property address.\n\n(Send /cancel to abort)"
            )
        
        # Handle list command
        if isinstance(command, PropertyListCommand):
            from business_agent.property.models import PropertyStatus
            
            status_filter = None
            if command.status:
                try:
                    status_filter = PropertyStatus(command.status)
                except ValueError:
                    return TelegramReply(
                        text=f"Invalid status: {command.status}. Valid: owned, under_offer, viewing, sold, pending_purchase"
                    )
            
            properties = self._property_registry.list_properties(status=status_filter)
            
            if not properties:
                return TelegramReply(text="No properties found.")
            
            lines = [f"Found {len(properties)} propert{'y' if len(properties) == 1 else 'ies'}:"]
            for prop in properties:
                status_emoji = {"owned": "🏠", "viewing": "👀", "under_offer": "📝"}.get(prop.status.value, "📌")
                lines.append(f"{status_emoji} {prop.address} ({prop.status.value})")
                if prop.purchase_price:
                    lines.append(f"  Purchase: £{prop.purchase_price:,.0f}")
                if prop.current_value:
                    lines.append(f"  Current value: £{prop.current_value:,.0f}")
            
            return TelegramReply(text="\n".join(lines), show_actions=False)
        
        # Handle show command
        if isinstance(command, PropertyShowCommand):
            prop = self._property_registry.get_property(command.property_id)
            if not prop:
                return TelegramReply(text=f"Property not found: {command.property_id}")
            
            lines = [
                f"🏠 {prop.address}",
                f"Status: {prop.status.value}",
            ]
            if prop.postcode:
                lines.append(f"Postcode: {prop.postcode}")
            if prop.bedrooms:
                lines.append(f"Bedrooms: {prop.bedrooms}")
            if prop.bathrooms:
                lines.append(f"Bathrooms: {prop.bathrooms}")
            if prop.purchase_date and prop.purchase_price:
                lines.append(f"Purchased: {prop.purchase_date} for £{prop.purchase_price:,.0f}")
            if prop.current_value:
                lines.append(f"Current value: £{prop.current_value:,.0f}")
            if prop.notes:
                lines.append(f"Notes: {prop.notes}")
            
            # Add mortgage info if any
            mortgages = self._property_registry.list_mortgages(property_id=prop.id)
            if mortgages:
                lines.append(f"\n💷 Mortgages ({len(mortgages)}):")
                for mort in mortgages:
                    lines.append(f"  • {mort.lender}: £{mort.monthly_payment:,.0f}/mo @ {mort.interest_rate}%")
            
            # Add tenant info if any
            tenants = self._property_registry.list_tenants(property_id=prop.id, active_only=True)
            if tenants:
                lines.append(f"\n👤 Active Tenants ({len(tenants)}):")
                for tenant in tenants:
                    lines.append(f"  • {tenant.name}: £{tenant.monthly_rent:,.0f}/mo (lease ends {tenant.lease_end})")
            
            return TelegramReply(text="\n".join(lines), show_actions=False)
        
        return TelegramReply(text="Unknown property command.")

    def _handle_mortgage_command(self, chat_id: int, text: str) -> TelegramReply:
        """Handle /mortgage commands."""
        if self._property_registry is None:
            return TelegramReply(text="Property registry is not configured.")
        
        try:
            command = parse_mortgage_command(text)
        except ValueError as exc:
            return TelegramReply(
                text=(
                    f"Could not parse mortgage command: {exc}\n"
                    "Try: /mortgage expiring [months=6]"
                )
            )
        
        # Handle "add" flow (interactive)
        if isinstance(command, str) and command.startswith("add:"):
            property_id = command.split(":", 1)[1]
            user_id = str(chat_id)
            self._conversation_manager.start_conversation(
                user_id=user_id,
                flow=ConversationFlow.MORTGAGE_ADD,
                initial_step="lender",
                initial_data={"property_id": property_id}
            )
            return TelegramReply(
                text=f"Let's add a mortgage for property {property_id}. Please provide the lender name.\n\n(Send /cancel to abort)"
            )
        
        # Handle expiring command
        if isinstance(command, MortgageExpiringCommand):
            expiring = self._property_registry.list_expiring_mortgages(months=command.months)
            
            if not expiring:
                return TelegramReply(text=f"No mortgages expiring within {command.months} months.")
            
            lines = [f"⚠️ {len(expiring)} mortgage(s) expiring within {command.months} months:"]
            for mort in expiring:
                months_left = mort.months_until_expiry()
                prop = self._property_registry.get_property(mort.property_id)
                prop_address = prop.address if prop else mort.property_id
                lines.append(f"• {prop_address} - {mort.lender}")
                lines.append(f"  Expires in {months_left} month(s) on {mort.end_date}")
                lines.append(f"  Current rate: {mort.interest_rate}%, £{mort.monthly_payment:,.0f}/mo")
            
            return TelegramReply(text="\n".join(lines), show_actions=False)
        
        return TelegramReply(text="Unknown mortgage command.")

    def _handle_tenant_command(self, chat_id: int, text: str) -> TelegramReply:
        if self._tenancy_service is None:
            return TelegramReply(text="Tenancy service is not configured.")

        command_text = text.strip()[7:].strip()
        if not command_text:
            return TelegramReply(
                text=(
                    "Usage: /tenant add <property_id> | /tenant list <property_id> | "
                    "/tenant show <tenancy_id> | /tenant search <query> [tenancy_id=<id>]"
                )
            )

        parts = shlex.split(command_text)
        action = parts[0].lower() if parts else ""

        if action == "add":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /tenant add <property_id>")
            property_id = parts[1]
            user_id = str(chat_id)
            self._conversation_manager.start_conversation(
                user_id=user_id,
                flow=ConversationFlow.TENANT_ADD,
                initial_step="full_name",
                initial_data={"property_id": property_id},
            )
            return TelegramReply(
                text=(
                    f"Let's add a tenant for property {property_id}. Please provide the full name.\n\n"
                    "(Send /cancel to abort)"
                )
            )

        if action == "list":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /tenant list <property_id>")
            tenancies = self._tenancy_service.list_tenancies(property_id=parts[1], active_only=True)
            if not tenancies:
                return TelegramReply(text=f"No active tenants found for property {parts[1]}.")
            lines = [f"Active tenants for {parts[1]}:"]
            for tenancy in tenancies:
                lines.append(f"• {tenancy.full_name or tenancy.name} ({tenancy.id})")
            return TelegramReply(text="\n".join(lines), show_actions=False)

        if action == "show":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /tenant show <tenancy_id>")
            tenancy = self._tenancy_service.get_tenancy(parts[1])
            if not tenancy:
                return TelegramReply(text=f"Tenancy not found: {parts[1]}")
            lines = [f"Tenant: {tenancy.full_name or tenancy.name}", f"Property ID: {tenancy.property_id}"]
            if tenancy.email:
                lines.append(f"Email: {tenancy.email}")
            if tenancy.phone:
                lines.append(f"Phone: {tenancy.phone}")
            lines.append(f"Lease: {tenancy.lease_start} to {tenancy.lease_end}")
            lines.append(f"Rent: £{tenancy.monthly_rent:,.2f}")
            lines.append(f"Deposit: £{tenancy.deposit:,.2f}")
            return TelegramReply(text="\n".join(lines), show_actions=False)

        if action == "search":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /tenant search <query> [tenancy_id=<id>]")
            tenancy_id = None
            query_parts: list[str] = []
            for token in parts[1:]:
                if token.startswith("tenancy_id="):
                    tenancy_id = token.split("=", 1)[1]
                else:
                    query_parts.append(token)
            query = " ".join(query_parts)
            if not query:
                return TelegramReply(text="Please provide a search query.")
            matches = self._tenancy_service.search_documents(query=query, tenancy_id=tenancy_id)
            if not matches:
                return TelegramReply(text="No tenant documents found for that query.")
            lines = [f"Found {len(matches)} result(s):"]
            for match in matches:
                lines.append(f"• {match.text[:120]} ({match.payload.tenancy_id})")
            return TelegramReply(text="\n".join(lines), show_actions=False)

        return TelegramReply(text="Unknown tenant command.")

    def _handle_agreement_command(self, chat_id: int, text: str) -> TelegramReply:
        if self._tenancy_service is None:
            return TelegramReply(text="Tenancy service is not configured.")

        command_text = text.strip()[10:].strip()
        if not command_text:
            return TelegramReply(text="Usage: /agreement generate <tenancy_id> [template_name]")

        parts = shlex.split(command_text)
        action = parts[0].lower() if parts else ""
        if action != "generate":
            return TelegramReply(text="Unknown agreement command.")
        if len(parts) < 2:
            return TelegramReply(text="Usage: /agreement generate <tenancy_id> [template_name]")

        tenancy_id = parts[1]
        template_name = parts[2] if len(parts) > 2 else None
        try:
            agreement, unresolved = self._tenancy_service.generate_agreement(
                tenancy_id,
                template_name=template_name,
            )
        except ValueError as exc:
            return TelegramReply(text=str(exc))

        unresolved_text = ", ".join(unresolved) if unresolved else "none"
        return TelegramReply(
            text=(
                f"Agreement generated successfully.\n"
                f"Path: {agreement.stored_path}\n"
                f"Unresolved placeholders: {unresolved_text}"
            )
        )

    def _handle_conveyancing_command(self, chat_id: int, text: str) -> TelegramReply:
        if self._conveyancing_service is None:
            return TelegramReply(text="Conveyancing service is not configured.")

        command_text = text.strip()[13:].strip()
        if not command_text:
            return TelegramReply(text="Usage: /conveyancing list | /conveyancing new purchase <property_id> | /conveyancing show <transaction_id>")

        parts = shlex.split(command_text)
        action = parts[0].lower() if parts else ""

        if action == "list":
            transactions = self._conveyancing_service.list_transactions()
            if not transactions:
                return TelegramReply(text="No conveyancing transactions found.")
            lines = [f"Found {len(transactions)} transaction(s):"]
            for transaction in transactions:
                lines.append(f"• {transaction.id} ({transaction.transaction_type}) stage={transaction.stage}")
            return TelegramReply(text="\n".join(lines), show_actions=False)

        if action == "new":
            if len(parts) < 3:
                return TelegramReply(text="Usage: /conveyancing new purchase <property_id>")
            transaction_type = parts[1].lower()
            property_id = parts[2]
            transaction = self._conveyancing_service.create_transaction(property_id, transaction_type)
            return TelegramReply(text=f"Created {transaction.transaction_type} transaction {transaction.id} for {property_id}.", show_actions=False)

        if action == "show":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /conveyancing show <transaction_id>")
            transaction = self._conveyancing_service.get_transaction(parts[1])
            if transaction is None:
                return TelegramReply(text=f"Transaction not found: {parts[1]}")
            return TelegramReply(text=f"Transaction {transaction.id}: stage={transaction.stage} type={transaction.transaction_type}", show_actions=False)

        if action == "advance":
            if len(parts) < 3:
                return TelegramReply(text="Usage: /conveyancing advance <transaction_id> <stage>")
            transaction = self._conveyancing_service.advance_stage(parts[1], parts[2])
            return TelegramReply(text=f"Advanced transaction {transaction.id} to {transaction.stage}.", show_actions=False)

        if action == "compare" and len(parts) > 1 and parts[1].lower() == "mortgages":
            if len(parts) < 3:
                return TelegramReply(text="Usage: /conveyancing compare mortgages <transaction_id>")
            comparisons = self._conveyancing_service.compare_mortgage_offers(parts[2])
            if not comparisons:
                return TelegramReply(text="No mortgage offers found for that transaction.")
            lines = [f"Compared {len(comparisons)} offer(s):"]
            for item in comparisons:
                lines.append(f"• {item['lender_name']} total={item['total_cost_5yr']:.2f} recommended={item['recommended']}")
            return TelegramReply(text="\n".join(lines), show_actions=False)

        return TelegramReply(text="Unknown conveyancing command.")

    def _handle_maintenance_command(self, chat_id: int, text: str) -> TelegramReply:
        if self._maintenance_service is None:
            return TelegramReply(text="Maintenance service is not configured.")

        command_text = text.strip()[12:].strip()
        if not command_text:
            return TelegramReply(text="Usage: /maintenance list <property_id> | /maintenance new <property_id>")

        parts = shlex.split(command_text)
        action = parts[0].lower() if parts else ""

        if action == "list":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /maintenance list <property_id>")
            jobs = self._maintenance_service.list_jobs(property_id=parts[1])
            if not jobs:
                return TelegramReply(text=f"No maintenance jobs found for property {parts[1]}.")
            lines = [f"Found {len(jobs)} job(s):"]
            for job in jobs:
                lines.append(f"• {job.id} {job.title} stage={job.stage}")
            return TelegramReply(text="\n".join(lines), show_actions=False)

        if action == "new":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /maintenance new <property_id>")
            job = self._maintenance_service.create_job(property_id=parts[1], title="New maintenance request", description="Logged via Telegram")
            return TelegramReply(text=f"Created job {job.id} for property {parts[1]}.", show_actions=False)

        if action == "spend":
            if len(parts) < 2:
                return TelegramReply(text="Usage: /maintenance spend <property_id> [year=YYYY]")
            year = None
            if len(parts) > 2:
                year = int(parts[2])
            summary = self._maintenance_service.spend(parts[1], year=year)
            return TelegramReply(text=f"Total spend: £{summary['total_spend']:.2f}", show_actions=False)

        return TelegramReply(text="Unknown maintenance command.")

    def _handle_data_command(self, text: str) -> TelegramReply:
        if self._sql_reader is None:
            return TelegramReply(
                text=(
                    "SQL read-only access is not configured.\n"
                    "Set SQL_DATABASE_URL and SQL_ALLOWED_TABLES in .env."
                )
            )
        try:
            command = parse_data_command(
                text,
                default_limit=self._settings.sql_query_limit_default,
                max_limit=self._settings.sql_query_limit_max,
            )
            request = SQLReadRequest(
                table=command.table,
                columns=command.columns,
                filters=command.filters,
                limit=command.limit,
            )
            rows = self._sql_reader.fetch_rows(request)
        except (PermissionError, ValueError) as exc:
            return TelegramReply(
                text=(
                    f"Data query failed: {exc}\n"
                    "Try: /data table=orders columns=id,total filters=status:paid limit=20"
                )
            )

        if not rows:
            return TelegramReply(
                text=(
                    "No rows found.\n"
                    "Try relaxing filters or checking the selected table/columns."
                )
            )

        preview_rows = rows[:5]
        return TelegramReply(
            text=f"Rows returned: {len(rows)}\nPreview: {preview_rows}",
        )

    def _answer_with_memory(self, request: MemoryQueryInput, question_text: str) -> TelegramReply:
        matches = self._memory_store.query(request)
        if not matches:
            return TelegramReply(
                text=(
                    "No matching knowledge found.\n"
                    "Try refining keywords or adding from=YYYY-MM-DD and to=YYYY-MM-DD."
                ),
                question_text=question_text,
                show_actions=True,
            )

        compact_lines = []
        lead = shorten(matches[0].text, width=180, placeholder="...")
        compact_lines.append(f"Best answer: {lead}")
        compact_lines.append("Evidence:")

        for match in matches[:3]:
            timestamp_text = (
                match.payload.event_date.isoformat()
                if match.payload.event_date
                else f"ingested {match.payload.ingested_at.date().isoformat()}"
            )
            snippet = shorten(match.text, width=110, placeholder="...")
            compact_lines.append(f"- {snippet} ({match.payload.source_uri}, {timestamp_text})")

        if len(matches) > 3:
            compact_lines.append(f"... {len(matches) - 3} more matches available in More details.")

        detailed_lines = ["Detailed match view:"]
        source_lines = ["Sources:"]
        for index, match in enumerate(matches, start=1):
            timestamp_text = (
                match.payload.event_date.isoformat()
                if match.payload.event_date
                else f"ingested {match.payload.ingested_at.date().isoformat()}"
            )
            snippet = shorten(match.text, width=240, placeholder="...")
            detailed_lines.append(
                f"{index}. {snippet}\n"
                f"   source={match.payload.source_uri} ({match.payload.source_type}, {timestamp_text})"
            )
            source_lines.append(
                f"{index}. {match.payload.source_uri} ({match.payload.source_type}, {timestamp_text})"
            )

        return TelegramReply(
            text="\n".join(compact_lines),
            detailed_text="\n".join(detailed_lines),
            sources_text="\n".join(source_lines),
            question_text=question_text,
            show_actions=True,
        )

    def _parse_date(self, value: str) -> date:
        parts = value.strip().split("-")
        if len(parts) != 3:
            raise ValueError("Expected YYYY-MM-DD")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))

    def _parse_optional_date(self, value: str | date | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(value)

    def _build_query_text(self, chat_id: int, question: str) -> str:
        if self._conversation_store is None:
            return question
        self._conversation_store.append_turn(chat_id=chat_id, role="user", text=question)
        return self._conversation_store.build_query(
            chat_id=chat_id,
            current_message=question,
            max_chars=self._settings.conversation_context_max_chars,
        )

    def _record_assistant_turn(self, chat_id: int, response: str) -> None:
        if self._conversation_store is None:
            return
        self._conversation_store.append_turn(chat_id=chat_id, role="assistant", text=response)

    def _handle_reset_command(self, chat_id: int) -> TelegramReply:
        if self._conversation_store is None:
            return TelegramReply(text="Conversation memory is disabled.")
        self._conversation_store.clear(chat_id=chat_id)
        return TelegramReply(text="Conversation context cleared.")
    
    def _handle_property_add_conversation(
        self, user_id: str, text: str, conv: Any
    ) -> TelegramReply:
        """Handle multi-turn property add conversation."""
        from business_agent.property.models import Property, PropertyStatus
        from decimal import Decimal, InvalidOperation
        import uuid
        
        # Step: address
        if conv.step == "address":
            conv.set_data("address", text)
            conv.update_step("postcode")
            return TelegramReply(text="Great! What's the postcode? (or send 'skip')")
        
        # Step: postcode
        if conv.step == "postcode":
            if text.lower() != "skip":
                conv.set_data("postcode", text)
            conv.update_step("bedrooms")
            return TelegramReply(text="How many bedrooms? (or send 'skip')")
        
        # Step: bedrooms
        if conv.step == "bedrooms":
            if text.lower() != "skip":
                try:
                    bedrooms = int(text)
                    if bedrooms < 0:
                        return TelegramReply(text="Bedrooms must be positive. Please try again:")
                    conv.set_data("bedrooms", bedrooms)
                except ValueError:
                    return TelegramReply(text="Please enter a valid number for bedrooms:")
            conv.update_step("bathrooms")
            return TelegramReply(text="How many bathrooms? (or send 'skip')")
        
        # Step: bathrooms
        if conv.step == "bathrooms":
            if text.lower() != "skip":
                try:
                    bathrooms = int(text)
                    if bathrooms < 0:
                        return TelegramReply(text="Bathrooms must be positive. Please try again:")
                    conv.set_data("bathrooms", bathrooms)
                except ValueError:
                    return TelegramReply(text="Please enter a valid number for bathrooms:")
            conv.update_step("square_feet")
            return TelegramReply(text="Square feet? (or send 'skip')")
        
        # Step: square_feet
        if conv.step == "square_feet":
            if text.lower() != "skip":
                try:
                    square_feet = int(text)
                    if square_feet < 0:
                        return TelegramReply(text="Square feet must be positive. Please try again:")
                    conv.set_data("square_feet", square_feet)
                except ValueError:
                    return TelegramReply(text="Please enter a valid number for square feet:")
            conv.update_step("purchase_date")
            return TelegramReply(text="Purchase date (YYYY-MM-DD)? (or send 'skip')")
        
        # Step: purchase_date
        if conv.step == "purchase_date":
            if text.lower() != "skip":
                try:
                    from datetime import date
                    parts = text.split("-")
                    if len(parts) != 3:
                        return TelegramReply(text="Please use format YYYY-MM-DD:")
                    purchase_date = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    conv.set_data("purchase_date", purchase_date.isoformat())
                except (ValueError, IndexError):
                    return TelegramReply(text="Invalid date format. Please use YYYY-MM-DD:")
            conv.update_step("purchase_price")
            return TelegramReply(text="Purchase price (£)? (or send 'skip')")
        
        # Step: purchase_price
        if conv.step == "purchase_price":
            if text.lower() != "skip":
                try:
                    # Remove currency symbols and commas
                    clean_text = text.replace("£", "").replace(",", "").strip()
                    purchase_price = Decimal(clean_text)
                    if purchase_price < 0:
                        return TelegramReply(text="Price must be positive. Please try again:")
                    conv.set_data("purchase_price", float(purchase_price))
                except (ValueError, InvalidOperation):
                    return TelegramReply(text="Please enter a valid price (numbers only):")
            conv.update_step("current_value")
            return TelegramReply(text="Current value (£)? (or send 'skip')")
        
        # Step: current_value
        if conv.step == "current_value":
            if text.lower() != "skip":
                try:
                    clean_text = text.replace("£", "").replace(",", "").strip()
                    current_value = Decimal(clean_text)
                    if current_value < 0:
                        return TelegramReply(text="Value must be positive. Please try again:")
                    conv.set_data("current_value", float(current_value))
                except (ValueError, InvalidOperation):
                    return TelegramReply(text="Please enter a valid value (numbers only):")
            conv.update_step("status")
            return TelegramReply(text="Property status? (owned / viewing / under_offer)")
        
        # Step: status
        if conv.step == "status":
            try:
                status = PropertyStatus(text.lower())
                conv.set_data("status", status.value)
            except ValueError:
                return TelegramReply(text="Invalid status. Please choose: owned, viewing, or under_offer")
            conv.update_step("notes")
            return TelegramReply(text="Any notes? (or send 'skip')")
        
        # Step: notes
        if conv.step == "notes":
            if text.lower() != "skip":
                conv.set_data("notes", text)
            conv.update_step("confirm")
            
            # Build confirmation message
            lines = ["Please confirm the property details:"]
            lines.append(f"Address: {conv.get_data('address')}")
            if conv.get_data("postcode"):
                lines.append(f"Postcode: {conv.get_data('postcode')}")
            if conv.get_data("bedrooms") is not None:
                lines.append(f"Bedrooms: {conv.get_data('bedrooms')}")
            if conv.get_data("bathrooms") is not None:
                lines.append(f"Bathrooms: {conv.get_data('bathrooms')}")
            if conv.get_data("square_feet") is not None:
                lines.append(f"Square feet: {conv.get_data('square_feet')}")
            if conv.get_data("purchase_date"):
                lines.append(f"Purchase date: {conv.get_data('purchase_date')}")
            if conv.get_data("purchase_price") is not None:
                lines.append(f"Purchase price: £{conv.get_data('purchase_price'):,.0f}")
            if conv.get_data("current_value") is not None:
                lines.append(f"Current value: £{conv.get_data('current_value'):,.0f}")
            lines.append(f"Status: {conv.get_data('status')}")
            if conv.get_data("notes"):
                lines.append(f"Notes: {conv.get_data('notes')}")
            lines.append("\nSend 'yes' to save or 'no' to cancel.")
            
            return TelegramReply(text="\n".join(lines))
        
        # Step: confirm
        if conv.step == "confirm":
            if text.lower() in ["yes", "y", "confirm"]:
                # Create property
                property_id = f"prop-{uuid.uuid4().hex[:8]}"
                prop = Property(
                    id=property_id,
                    address=conv.get_data("address"),
                    postcode=conv.get_data("postcode"),
                    bedrooms=conv.get_data("bedrooms"),
                    bathrooms=conv.get_data("bathrooms"),
                    square_feet=conv.get_data("square_feet"),
                    purchase_date=conv.get_data("purchase_date"),
                    purchase_price=Decimal(str(conv.get_data("purchase_price"))) if conv.get_data("purchase_price") is not None else None,
                    current_value=Decimal(str(conv.get_data("current_value"))) if conv.get_data("current_value") is not None else None,
                    status=PropertyStatus(conv.get_data("status")),
                    notes=conv.get_data("notes"),
                )
                
                if self._property_registry:
                    self._property_registry.add_property(prop)
                
                self._conversation_manager.end_conversation(user_id)
                return TelegramReply(text=f"✅ Property added successfully! ID: {property_id}")
            else:
                self._conversation_manager.end_conversation(user_id)
                return TelegramReply(text="Property registration cancelled.")
        
        return TelegramReply(text="Unknown conversation step. Please start over with /property add")
    
    def _handle_mortgage_add_conversation(
        self, user_id: str, text: str, conv: Any
    ) -> TelegramReply:
        """Handle multi-turn mortgage add conversation."""
        from business_agent.property.models import Mortgage
        from decimal import Decimal, InvalidOperation
        from datetime import date as Date
        import uuid
        
        # Step: lender
        if conv.step == "lender":
            conv.set_data("lender", text)
            conv.update_step("principal")
            return TelegramReply(text="What's the mortgage principal/loan amount (£)?")
        
        # Step: principal
        if conv.step == "principal":
            try:
                clean_text = text.replace("£", "").replace(",", "").strip()
                principal = Decimal(clean_text)
                if principal <= 0:
                    return TelegramReply(text="Principal must be positive. Please try again:")
                conv.set_data("principal", float(principal))
            except (ValueError, InvalidOperation):
                return TelegramReply(text="Please enter a valid amount (e.g. 200000):")
            conv.update_step("interest_rate")
            return TelegramReply(text="What's the annual interest rate (e.g. 3.5)?")
        
        # Step: interest_rate
        if conv.step == "interest_rate":
            try:
                clean_text = text.replace("%", "").strip()
                interest_rate = Decimal(clean_text)
                if interest_rate < 0 or interest_rate > 100:
                    return TelegramReply(text="Rate must be between 0 and 100. Please try again:")
                conv.set_data("interest_rate", float(interest_rate))
            except (ValueError, InvalidOperation):
                return TelegramReply(text="Please enter a valid rate (e.g. 3.5):")
            conv.update_step("term_months")
            return TelegramReply(text="Mortgage term in months (e.g. 300 for 25 years)?")
        
        # Step: term_months
        if conv.step == "term_months":
            try:
                term_months = int(text)
                if term_months <= 0:
                    return TelegramReply(text="Term must be positive. Please try again:")
                conv.set_data("term_months", term_months)
            except ValueError:
                return TelegramReply(text="Please enter a valid number of months:")
            conv.update_step("monthly_payment")
            return TelegramReply(text="Monthly payment amount (£)?")
        
        # Step: monthly_payment
        if conv.step == "monthly_payment":
            try:
                clean_text = text.replace("£", "").replace(",", "").strip()
                monthly_payment = Decimal(clean_text)
                if monthly_payment < 0:
                    return TelegramReply(text="Payment must be positive. Please try again:")
                conv.set_data("monthly_payment", float(monthly_payment))
            except (ValueError, InvalidOperation):
                return TelegramReply(text="Please enter a valid payment amount:")
            conv.update_step("start_date")
            return TelegramReply(text="Start date (YYYY-MM-DD)?")
        
        # Step: start_date
        if conv.step == "start_date":
            try:
                parts = text.split("-")
                if len(parts) != 3:
                    return TelegramReply(text="Please use format YYYY-MM-DD:")
                start_date = Date(int(parts[0]), int(parts[1]), int(parts[2]))
                conv.set_data("start_date", start_date)
            except (ValueError, IndexError):
                return TelegramReply(text="Invalid date format. Please use YYYY-MM-DD:")
            conv.update_step("product_type")
            return TelegramReply(text="Product type (e.g. 'Fixed 2 year')? (or send 'skip')")
        
        # Step: product_type
        if conv.step == "product_type":
            if text.lower() != "skip":
                conv.set_data("product_type", text)
            conv.update_step("notes")
            return TelegramReply(text="Any notes? (or send 'skip')")
        
        # Step: notes
        if conv.step == "notes":
            if text.lower() != "skip":
                conv.set_data("notes", text)
            conv.update_step("confirm")
            
            # Calculate end_date from start_date and term_months
            start = conv.get_data("start_date")
            term = conv.get_data("term_months")
            end_date = Date(
                start.year + (start.month + term - 1) // 12,
                (start.month + term - 1) % 12 + 1,
                start.day
            )
            conv.set_data("end_date", end_date)
            
            # Build confirmation message
            lines = ["Please confirm the mortgage details:"]
            lines.append(f"Property ID: {conv.get_data('property_id')}")
            lines.append(f"Lender: {conv.get_data('lender')}")
            lines.append(f"Principal: £{conv.get_data('principal'):,.0f}")
            lines.append(f"Interest rate: {conv.get_data('interest_rate')}%")
            lines.append(f"Term: {conv.get_data('term_months')} months")
            lines.append(f"Monthly payment: £{conv.get_data('monthly_payment'):,.0f}")
            lines.append(f"Start date: {conv.get_data('start_date')}")
            lines.append(f"End date: {end_date}")
            if conv.get_data("product_type"):
                lines.append(f"Product type: {conv.get_data('product_type')}")
            if conv.get_data("notes"):
                lines.append(f"Notes: {conv.get_data('notes')}")
            lines.append("\nSend 'yes' to save or 'no' to cancel.")
            
            return TelegramReply(text="\n".join(lines))
        
        # Step: confirm
        if conv.step == "confirm":
            if text.lower() in ["yes", "y", "confirm"]:
                # Create mortgage
                mortgage_id = f"mort-{uuid.uuid4().hex[:8]}"
                mortgage = Mortgage(
                    id=mortgage_id,
                    property_id=conv.get_data("property_id"),
                    lender=conv.get_data("lender"),
                    principal=Decimal(str(conv.get_data("principal"))),
                    interest_rate=Decimal(str(conv.get_data("interest_rate"))),
                    term_months=conv.get_data("term_months"),
                    monthly_payment=Decimal(str(conv.get_data("monthly_payment"))),
                    start_date=conv.get_data("start_date"),
                    end_date=conv.get_data("end_date"),
                    product_type=conv.get_data("product_type"),
                    notes=conv.get_data("notes"),
                )
                
                if self._property_registry:
                    self._property_registry.add_mortgage(mortgage)
                
                self._conversation_manager.end_conversation(user_id)
                return TelegramReply(text=f"✅ Mortgage added successfully! ID: {mortgage_id}")
            else:
                self._conversation_manager.end_conversation(user_id)
                return TelegramReply(text="Mortgage registration cancelled.")
        
        return TelegramReply(text="Unknown conversation step. Please start over with /mortgage add")
    
    def _handle_tenant_add_conversation(
        self, user_id: str, text: str, conv: Any
    ) -> TelegramReply:
        """Handle multi-turn tenant add conversation."""
        if conv.step == "full_name":
            if not text.strip():
                return TelegramReply(text="Please provide the full name:")
            conv.set_data("full_name", text.strip())
            conv.update_step("email")
            return TelegramReply(text="Email address? (or send 'skip')")

        if conv.step == "email":
            if text.lower() != "skip":
                conv.set_data("email", text.strip())
            conv.update_step("phone")
            return TelegramReply(text="Phone number? (or send 'skip')")

        if conv.step == "phone":
            if text.lower() != "skip":
                conv.set_data("phone", text.strip())
            conv.update_step("lease_start")
            return TelegramReply(text="Lease start date (YYYY-MM-DD)?")

        if conv.step == "lease_start":
            try:
                conv.set_data("lease_start", self._parse_date(text))
            except ValueError:
                return TelegramReply(text="Please use YYYY-MM-DD format:")
            conv.update_step("lease_end")
            return TelegramReply(text="Lease end date (YYYY-MM-DD)?")

        if conv.step == "lease_end":
            try:
                conv.set_data("lease_end", self._parse_date(text))
            except ValueError:
                return TelegramReply(text="Please use YYYY-MM-DD format:")
            conv.update_step("monthly_rent")
            return TelegramReply(text="Monthly rent (£)? (or send 'skip')")

        if conv.step == "monthly_rent":
            if text.lower() != "skip":
                try:
                    value = Decimal(text.replace("£", "").replace(",", "").strip())
                    conv.set_data("monthly_rent", value)
                except (ValueError, InvalidOperation):
                    return TelegramReply(text="Please enter a valid rent amount:")
            conv.update_step("deposit")
            return TelegramReply(text="Deposit amount (£)? (or send 'skip')")

        if conv.step == "deposit":
            if text.lower() != "skip":
                try:
                    value = Decimal(text.replace("£", "").replace(",", "").strip())
                    conv.set_data("deposit", value)
                except (ValueError, InvalidOperation):
                    return TelegramReply(text="Please enter a valid deposit amount:")
            conv.update_step("notes")
            return TelegramReply(text="Notes? (or send 'skip')")

        if conv.step == "notes":
            if text.lower() != "skip":
                conv.set_data("notes", text.strip())
            conv.update_step("confirm")
            lines = ["Please confirm the tenancy details:"]
            lines.append(f"Property ID: {conv.get_data('property_id')}")
            lines.append(f"Full name: {conv.get_data('full_name')}")
            if conv.get_data("email"):
                lines.append(f"Email: {conv.get_data('email')}")
            if conv.get_data("phone"):
                lines.append(f"Phone: {conv.get_data('phone')}")
            lines.append(f"Lease start: {conv.get_data('lease_start')}")
            lines.append(f"Lease end: {conv.get_data('lease_end')}")
            if conv.get_data("monthly_rent") is not None:
                lines.append(f"Monthly rent: £{conv.get_data('monthly_rent'):,.2f}")
            if conv.get_data("deposit") is not None:
                lines.append(f"Deposit: £{conv.get_data('deposit'):,.2f}")
            if conv.get_data("notes"):
                lines.append(f"Notes: {conv.get_data('notes')}")
            lines.append("\nSend 'yes' to save or 'no' to cancel.")
            return TelegramReply(text="\n".join(lines))

        if conv.step == "confirm":
            if text.lower() in ["yes", "y", "confirm"]:
                tenancy = self._tenancy_service.create_tenancy(
                    property_id=conv.get_data("property_id"),
                    full_name=conv.get_data("full_name"),
                    email=conv.get_data("email"),
                    phone=conv.get_data("phone"),
                    lease_start=conv.get_data("lease_start"),
                    lease_end=conv.get_data("lease_end"),
                    monthly_rent=conv.get_data("monthly_rent"),
                    deposit=conv.get_data("deposit"),
                    notes=conv.get_data("notes"),
                )
                self._conversation_manager.end_conversation(user_id)
                return TelegramReply(text=f"✅ Tenant added successfully! ID: {tenancy.id}")
            self._conversation_manager.end_conversation(user_id)
            return TelegramReply(text="Tenant registration cancelled.")

        return TelegramReply(text="Unknown conversation step. Please start over with /tenant add")

    def memorize_text_message(self, chat_id: int, text: str) -> str | None:
        """Store a plain text message in memory. Returns record ID or None."""
        if self._text_memorization_service is None:
            return None
        return self._text_memorization_service.memorize_text(text=text, chat_id=chat_id)

    def transcribe_and_store_voice(self, chat_id: int, audio_file_path: str, file_id: str | None = None) -> str | None:
        """Transcribe a voice note and store it in memory. Returns transcription or None."""
        if self._llm_client is None:
            return None
        try:
            transcription = self._llm_client.transcribe_audio(audio_file_path)
            if self._text_memorization_service:
                self._text_memorization_service.memorize_voice_transcription(
                    transcription=transcription,
                    audio_file_id=file_id,
                    chat_id=chat_id,
                )
            return transcription
        except Exception:
            return None

    # --- NL Query Intent Handlers ---

    def _handle_compare_mortgages(self, parsed: ParsedNLQuery) -> TelegramReply:
        """Compare mortgage offers for a property within a date range."""
        if not parsed.property_address:
            return TelegramReply(
                text="I couldn't identify a property address in your question. "
                     "Please include the property address, e.g. 'compare mortgage offers for 133 Bowland Drive within last 2 months'"
            )
        
        # Query document registry for mortgage offers
        from datetime import datetime, timezone
        date_from = None
        date_to = None
        if parsed.date_from:
            date_from = datetime.combine(parsed.date_from, datetime.min.time(), tzinfo=timezone.utc)
        if parsed.date_to:
            date_to = datetime.combine(parsed.date_to, datetime.max.time(), tzinfo=timezone.utc)
        
        docs = []
        if self._document_registry:
            docs = self._document_registry.query(
                document_type="mortgage_offer",
                date_from=date_from,
                date_to=date_to,
                limit=20,
            )
            # Filter by property_address if set
            if parsed.property_address:
                docs = [d for d in docs if d.property_address and parsed.property_address.lower() in d.property_address.lower()]
        
        if not docs:
            return TelegramReply(
                text=f"No mortgage offers found for '{parsed.property_address}'"
                     + (f" between {parsed.date_from} and {parsed.date_to}" if parsed.date_from else "")
            )
        
        lines = [f"📊 Found {len(docs)} mortgage offer(s) for {parsed.property_address}:"]
        for doc in docs:
            lines.append(f"• {doc.title} ({doc.ingested_at.strftime('%Y-%m-%d')})")
            if doc.vendor:
                lines.append(f"  Lender: {doc.vendor}")
            if doc.amount:
                lines.append(f"  Amount: £{doc.amount:,.0f}")
            if doc.summary:
                lines.append(f"  Summary: {doc.summary[:120]}")
        
        return TelegramReply(text="\n".join(lines))

    def _handle_epc_expiry(self, parsed: ParsedNLQuery) -> TelegramReply:
        """Check EPC certificate expiry for a property."""
        if not parsed.property_address:
            return TelegramReply(
                text="I couldn't identify a property address. Please include it in your question."
            )
        
        # Query memory for EPC documents
        request = MemoryQueryInput(
            query=f"EPC certificate expiry {parsed.property_address}",
            property_address=parsed.property_address,
            document_type="epc_certificate",
            top_k=5,
        )
        matches = self._memory_store.query(request)
        
        if not matches:
            return TelegramReply(
                text=f"No EPC certificate found for {parsed.property_address}. "
                     "Upload the EPC certificate document to get expiry information."
            )
        
        # Use LLM to answer if available
        if self._llm_client:
            context = "\n".join([m.text for m in matches[:3]])
            try:
                answer = self._llm_client.answer_question(
                    question=parsed.raw_question,
                    context=context,
                )
                return TelegramReply(text=f"📋 EPC for {parsed.property_address}:\n\n{answer}")
            except Exception:
                pass
        
        # Fallback: return the matched text
        best_match = matches[0]
        return TelegramReply(
            text=f"📋 EPC information for {parsed.property_address}:\n"
                 f"{best_match.text[:300]}\n\n"
                 f"Source: {best_match.payload.source_uri}"
        )

    def _handle_mortgage_statements(self, parsed: ParsedNLQuery) -> TelegramReply:
        """List mortgage statements for a property within date range."""
        if not parsed.property_address:
            return TelegramReply(text="I couldn't identify a property address. Please include it.")
        
        from datetime import datetime, timezone
        date_from = None
        date_to = None
        if parsed.date_from:
            date_from = datetime.combine(parsed.date_from, datetime.min.time(), tzinfo=timezone.utc)
        if parsed.date_to:
            date_to = datetime.combine(parsed.date_to, datetime.max.time(), tzinfo=timezone.utc)
        
        docs = []
        if self._document_registry:
            docs = self._document_registry.query(
                document_type="bank_statement",
                date_from=date_from,
                date_to=date_to,
                limit=50,
            )
            if parsed.property_address:
                docs = [d for d in docs if d.property_address and parsed.property_address.lower() in d.property_address.lower()]
        
        if not docs:
            return TelegramReply(
                text=f"No mortgage statements found for {parsed.property_address}"
                     + (f" in the specified date range" if parsed.date_from else "")
            )
        
        lines = [f"📊 Mortgage statements for {parsed.property_address} ({len(docs)} found):"]
        for doc in docs:
            lines.append(f"• {doc.title} - {doc.ingested_at.strftime('%Y-%m-%d')}")
            if doc.amount:
                lines.append(f"  Amount: £{doc.amount:,.0f}")
        
        return TelegramReply(text="\n".join(lines))

    def _handle_tenancy_clause_check(self, parsed: ParsedNLQuery) -> TelegramReply:
        """Check if a tenancy agreement contains a specific clause."""
        if not parsed.property_address:
            return TelegramReply(text="I couldn't identify a property address. Please include it.")
        
        clause = parsed.clause_text or "no pet"
        
        # Query memory for tenancy agreement
        request = MemoryQueryInput(
            query=f"tenancy agreement {parsed.property_address} {clause}",
            property_address=parsed.property_address,
            document_type="tenancy_agreement",
            top_k=5,
        )
        matches = self._memory_store.query(request)
        
        if not matches:
            return TelegramReply(
                text=f"No tenancy agreement found for {parsed.property_address}."
            )
        
        # Use LLM to answer the clause question
        context = "\n".join([m.text for m in matches[:3]])
        if self._llm_client:
            try:
                answer = self._llm_client.answer_question(
                    question=f"Does the tenancy agreement for {parsed.property_address} contain a '{clause}' clause?",
                    context=context,
                )
                return TelegramReply(text=f"📜 Tenancy clause check for {parsed.property_address}:\n\n{answer}")
            except Exception:
                pass
        
        # Fallback: search for clause in text
        clause_lower = clause.lower()
        for m in matches:
            if clause_lower in m.text.lower():
                return TelegramReply(
                    text=f"📜 Yes, the tenancy agreement for {parsed.property_address} mentions '{clause}'.\n\n"
                         f"Source: {m.payload.source_uri}"
                )
        
        return TelegramReply(
            text=f"📜 No mention of '{clause}' found in the tenancy agreement for {parsed.property_address}.\n"
                 f"Source: {matches[0].payload.source_uri}"
        )

    def _handle_bulk_document_links(self, parsed: ParsedNLQuery) -> TelegramReply:
        """Return links for all documents matching type and date range."""
        from datetime import datetime, timezone
        date_from = None
        date_to = None
        if parsed.date_from:
            date_from = datetime.combine(parsed.date_from, datetime.min.time(), tzinfo=timezone.utc)
        if parsed.date_to:
            date_to = datetime.combine(parsed.date_to, datetime.max.time(), tzinfo=timezone.utc)
        
        docs = []
        if self._document_registry:
            docs = self._document_registry.query(
                document_type=parsed.document_type,
                date_from=date_from,
                date_to=date_to,
                limit=100,
            )
        
        if not docs:
            return TelegramReply(
                text="No documents found matching your criteria."
            )
        
        lines = [f"📎 Found {len(docs)} document(s):"]
        for doc in docs:
            link = doc.source_uri
            if doc.archived_file_path:
                link = doc.archived_file_path
            lines.append(f"• {doc.title} ({doc.document_type}) - {doc.ingested_at.strftime('%Y-%m-%d')}")
            lines.append(f"  Link: {link}")
        
        return TelegramReply(text="\n".join(lines))

    def _handle_transaction_matching(self, parsed: ParsedNLQuery) -> TelegramReply:
        """Match a transaction amount to stored invoices."""
        if parsed.transaction_amount is None:
            return TelegramReply(text="I couldn't identify a transaction amount. Please specify an amount (e.g. £180).")
        
        target_amount = parsed.transaction_amount
        # Search for invoices in memory
        query_text = f"invoice amount {target_amount}"
        if parsed.transaction_date:
            query_text += f" date {parsed.transaction_date.isoformat()}"
        
        request = MemoryQueryInput(
            query=query_text,
            date_from=parsed.transaction_date,
            top_k=10,
        )
        matches = self._memory_store.query(request)
        
        if not matches:
            return TelegramReply(
                text=f"No matching invoices found for £{target_amount:,.2f}"
                     + (f" on {parsed.transaction_date}" if parsed.transaction_date else "")
            )
        
        # Filter matches by amount proximity
        relevant = []
        for m in matches:
            if m.payload.amount is not None:
                diff = abs(m.payload.amount - target_amount)
                if diff < max(target_amount * 0.1, 5.0):  # Within 10% or £5
                    relevant.append(m)
        
        if not relevant:
            relevant = matches[:3]
        
        lines = [f"💰 Found {len(relevant)} potential invoice match(es) for £{target_amount:,.2f}:"]
        for m in relevant:
            amount_str = f"£{m.payload.amount:,.2f}" if m.payload.amount else "amount unknown"
            lines.append(f"• {m.text[:100]}")
            lines.append(f"  Amount: {amount_str}")
            lines.append(f"  Source: {m.payload.source_uri}")
        
        return TelegramReply(text="\n".join(lines))
