from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from pydantic import BaseModel

from business_agent.ingestion.chunking import chunk_text
from business_agent.ingestion.parser import load_document_from_uri
from business_agent.ingestion.summarizer import Summarizer
from business_agent.memory.models import MemoryPayload, MemoryRecord
from business_agent.memory.store import MemoryStore


class IngestionResult(BaseModel):
    document_id: str
    source_uri: str
    source_type: str
    summary_id: str
    chunk_count: int
    records_written: int


class DocumentIngestionService:
    def __init__(
        self,
        memory_store: MemoryStore,
        summarizer: Summarizer,
        chunk_size: int,
        chunk_overlap: int,
        max_document_chars: int,
        allowed_local_dir: str,
    ) -> None:
        self._memory_store = memory_store
        self._summarizer = summarizer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_document_chars = max_document_chars
        self._allowed_local_dir = allowed_local_dir

    def ingest_from_uri(
        self,
        source_uri: str,
        event_date: date | None = None,
        requester_id: int | None = None,
    ) -> IngestionResult:
        parsed = load_document_from_uri(
            source_uri=source_uri,
            allowed_local_dir=self._allowed_local_dir,
        )

        text = parsed.text[: self._max_document_chars]
        ingested_at = datetime.now(timezone.utc)
        effective_date = self._compute_effective_date(event_date, ingested_at)
        summary = self._summarizer.summarize(text)
        chunks = chunk_text(text, chunk_size=self._chunk_size, overlap=self._chunk_overlap)

        document_id = uuid.uuid4().hex
        summary_id = f"{document_id}:summary"
        summary_payload = MemoryPayload(
            event_date=event_date,
            ingested_at=ingested_at,
            effective_date=effective_date,
            source_type=parsed.source_type,
            source_uri=source_uri,
            record_type="summary",
            chunk_index=None,
            chunk_count=len(chunks),
            summary=summary,
        )

        records = [MemoryRecord(id=summary_id, text=summary or text[:1000], payload=summary_payload)]

        for index, chunk in enumerate(chunks):
            payload = MemoryPayload(
                event_date=event_date,
                ingested_at=ingested_at,
                effective_date=effective_date,
                source_type=parsed.source_type,
                source_uri=source_uri,
                record_type="chunk",
                chunk_index=index,
                chunk_count=len(chunks),
                summary=summary,
            )
            records.append(MemoryRecord(id=f"{document_id}:chunk:{index}", text=chunk, payload=payload))

        self._memory_store.upsert(records)
        return IngestionResult(
            document_id=document_id,
            source_uri=source_uri,
            source_type=parsed.source_type,
            summary_id=summary_id,
            chunk_count=len(chunks),
            records_written=len(records),
        )

    def _compute_effective_date(self, event_date: date | None, ingested_at: datetime) -> datetime:
        if event_date is None:
            return ingested_at
        return datetime.combine(event_date, time.min, tzinfo=timezone.utc)

