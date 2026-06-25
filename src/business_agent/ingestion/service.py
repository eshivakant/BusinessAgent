from __future__ import annotations

import uuid
import warnings
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from business_agent.ingestion.chunking import chunk_text
from business_agent.ingestion.parser import load_document_from_uri, ParsedDocument
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
        archive_dir: str | None = None,
        archive_enabled: bool = True,
    ) -> None:
        self._memory_store = memory_store
        self._summarizer = summarizer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_document_chars = max_document_chars
        self._allowed_local_dir = allowed_local_dir
        self._archive_dir = archive_dir
        self._archive_enabled = archive_enabled and archive_dir is not None

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
        
        # Archive the original document if enabled
        archived_file_path = None
        if self._archive_enabled:
            archived_file_path = self._archive_document(
                document_id=document_id,
                parsed_doc=parsed,
            )
        
        summary_payload = MemoryPayload(
            event_date=event_date,
            ingested_at=ingested_at,
            effective_date=effective_date,
            source_type=parsed.source_type,
            source_uri=source_uri,
            archived_file_path=archived_file_path,
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
                archived_file_path=archived_file_path,
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

    def _archive_document(self, document_id: str, parsed_doc: ParsedDocument) -> str | None:
        """Archive original document to disk and return relative path."""
        try:
            archive_path = Path(self._archive_dir) / document_id
            archive_path.mkdir(parents=True, exist_ok=True)
            
            # Determine filename with extension based on source type
            ext_map = {"txt": "txt", "pdf": "pdf", "docx": "docx"}
            ext = ext_map.get(parsed_doc.source_type, "bin")
            filename = f"original.{ext}"
            
            file_path = archive_path / filename
            
            # Re-fetch the original content from source to archive as-is
            parsed_uri = urlparse(parsed_doc.source_uri)
            if parsed_uri.scheme in {"http", "https"}:
                response = httpx.get(parsed_doc.source_uri, timeout=30.0, follow_redirects=True)
                response.raise_for_status()
                content = response.content
            else:
                path = Path(parsed_doc.source_uri).expanduser().resolve()
                content = path.read_bytes()
            
            file_path.write_bytes(content)
            
            # Return relative path from archive root
            return str(archive_path / filename)
        except Exception as e:
            # Log but don't fail ingestion; archival is non-critical
            warnings.warn(f"Failed to archive document {document_id}: {e}")
            return None

