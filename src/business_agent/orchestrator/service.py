from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from textwrap import shorten

from business_agent.config import get_settings
from business_agent.data.readonly_sql import ReadOnlySQLDataAccess, SQLReadRequest
from business_agent.ingestion.service import DocumentIngestionService, IngestionResult
from business_agent.memory.models import MemoryMatch, MemoryQueryInput
from business_agent.memory.store import MemoryStore
from business_agent.orchestrator.commands import (
    AskCommand,
    ListCommand,
    parse_ask_command,
    parse_data_command,
    parse_ingest_command,
    parse_list_command,
    parse_question_with_optional_dates,
)
from business_agent.orchestrator.conversation import ConversationStore
from business_agent.worker.contracts import DocumentIngestionTask, SubagentTaskQueue


HELP_TEXT = (
    "Commands:\n"
    "/ask [from=YYYY-MM-DD] [to=YYYY-MM-DD] <question>\n"
    "/ingest <source_uri> [event_date=YYYY-MM-DD]\n"
    "/list [type=<type>] [vendor=<vendor>] [date_from=YYYY-MM-DD] [date_to=YYYY-MM-DD] [limit=<n>]\n"
    "/data table=<name> columns=<c1,c2> filters=<key:value,...> limit=<n>\n"
    "/reset\n\n"
    "Tip: keep questions concise. Use date filters for precise retrieval."
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
    ) -> None:
        self._memory_store = memory_store
        self._task_queue = task_queue
        self._ingestion_service = ingestion_service
        self._conversation_store = conversation_store
        self._sql_reader = sql_reader
        self._settings = get_settings()

    def handle_telegram_message(self, chat_id: int, message_text: str) -> str:
        return self.handle_telegram_message_with_ui(chat_id=chat_id, message_text=message_text).text

    def handle_telegram_message_with_ui(self, chat_id: int, message_text: str) -> TelegramReply:
        text = message_text.strip()
        if not text:
            return TelegramReply(text="Send /help for available actions.")
        if text.startswith("/reset"):
            return self._handle_reset_command(chat_id)
        if text.startswith("/help"):
            return TelegramReply(text=HELP_TEXT)
        if text.startswith("/list"):
            return self._handle_list_command(text)
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
        try:
            command = parse_question_with_optional_dates(text)
        except ValueError:
            command = AskCommand(question=text)

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
