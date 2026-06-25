from __future__ import annotations

import uuid
import warnings
from datetime import date, datetime, time, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from business_agent.ingestion.chunking import chunk_text
from business_agent.ingestion.compression import compress_pdf_images
from business_agent.ingestion.parser import load_document_from_uri, ParsedDocument
from business_agent.ingestion.registry import DocumentInfo, DocumentRegistry
from business_agent.ingestion.summarizer import Summarizer
from business_agent.llm.client import LLMClient
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
        llm_client: LLMClient | None = None,
        document_registry: DocumentRegistry | None = None,
        enable_metadata_extraction: bool = True,
    ) -> None:
        self._memory_store = memory_store
        self._summarizer = summarizer
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_document_chars = max_document_chars
        self._allowed_local_dir = allowed_local_dir
        self._archive_dir = archive_dir
        self._archive_enabled = archive_enabled and archive_dir is not None
        self._llm_client = llm_client
        self._document_registry = document_registry
        self._enable_metadata_extraction = enable_metadata_extraction and llm_client is not None

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

        # Handle image OCR if needed
        text = parsed.text
        if parsed.source_type in {"png", "jpg", "jpeg", "gif", "webp"} and self._llm_client:
            try:
                temp_path = Path("/tmp") / f"ocr_{uuid.uuid4().hex}.{parsed.source_type}"
                # For images, we need to fetch and save temporarily for OCR
                if parsed.source_uri.startswith("http"):
                    response = httpx.get(parsed.source_uri, timeout=30.0)
                    temp_path.write_bytes(response.content)
                else:
                    temp_path.write_bytes(Path(parsed.source_uri).read_bytes())

                text = self._llm_client.ocr_image(str(temp_path))
                temp_path.unlink(missing_ok=True)
            except Exception as e:
                warnings.warn(f"OCR failed for {source_uri}: {e}")
                text = f"[Image - OCR failed: {parsed.source_type}]"

        # Truncate text
        text = text[: self._max_document_chars]

        ingested_at = datetime.now(timezone.utc)
        effective_date = self._compute_effective_date(event_date, ingested_at)
        summary = self._summarizer.summarize(text)
        chunks = chunk_text(text, chunk_size=self._chunk_size, overlap=self._chunk_overlap)

        document_id = uuid.uuid4().hex
        summary_id = f"{document_id}:summary"

        # Archive the original document with compression if needed
        archived_file_path = None
        if self._archive_enabled:
            archived_file_path = self._archive_document(
                document_id=document_id,
                parsed_doc=parsed,
                source_uri=source_uri,
            )

        # Extract metadata if LLM available (use structured extraction for richer metadata)
        metadata = None
        if self._enable_metadata_extraction and self._llm_client:
            try:
                # Try structured metadata first (includes property_address, amount)
                extract_fn = getattr(self._llm_client, "extract_structured_metadata", None)
                if extract_fn is None:
                    extract_fn = getattr(self._llm_client, "extract_metadata", None)
                if extract_fn is not None:
                    metadata = extract_fn(text, source_uri)
            except Exception as e:
                warnings.warn(f"Metadata extraction failed for {source_uri}: {e}")

        # Register document if registry available
        if self._document_registry:
            doc_info = DocumentInfo(
                document_id=document_id,
                title=Path(source_uri).stem,
                document_type=metadata.document_type if metadata else "other",
                vendor=metadata.vendor if metadata else None,
                department=metadata.department if metadata else None,
                keywords=metadata.keywords if metadata else [],
                source_uri=source_uri,
                source_type=parsed.source_type,
                archived_file_path=archived_file_path,
                ingested_at=ingested_at,
                event_date=event_date,
                effective_date=effective_date,
                summary=summary,
                chunk_count=len(chunks),
                property_address=getattr(metadata, "property_address", None) if metadata else None,
                amount=getattr(metadata, "amount", None) if metadata else None,
            )
            self._document_registry.register(doc_info)

        # Extract property and amount from metadata for payload
        prop_address = getattr(metadata, "property_address", None) if metadata else None
        doc_type = getattr(metadata, "document_type", None) if metadata else None
        amount_val = getattr(metadata, "amount", None) if metadata else None

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
            property_address=prop_address,
            document_type=doc_type,
            amount=amount_val,
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
                property_address=prop_address,
                document_type=doc_type,
                amount=amount_val,
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

    def _archive_document(
        self, document_id: str, parsed_doc: ParsedDocument, source_uri: str = ""
    ) -> str | None:
        """Archive original document to disk with compression if needed."""
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

            # Compress PDF if large
            if parsed_doc.source_type == "pdf" and len(content) > 1024 * 1024:
                content = compress_pdf_images(content, max_image_size=1024 * 1024)

            file_path.write_bytes(content)

            # Return relative path from archive root
            return str(archive_path / filename)
        except Exception as e:
            # Log but don't fail ingestion; archival is non-critical
            warnings.warn(f"Failed to archive document {document_id}: {e}")
            return None

