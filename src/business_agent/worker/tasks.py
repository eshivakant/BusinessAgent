from __future__ import annotations

from datetime import date
from typing import Any

from business_agent.dependencies import get_ingestion_service, get_memory_store


def ingest_document_task(
    source_uri: str,
    event_date: str | None = None,
    requester_id: int | None = None,
) -> dict[str, Any]:
    parsed_event_date = date.fromisoformat(event_date) if event_date else None

    memory_store = get_memory_store()
    memory_store.ensure_collection()

    ingestion_service = get_ingestion_service()
    result = ingestion_service.ingest_from_uri(
        source_uri=source_uri,
        event_date=parsed_event_date,
        requester_id=requester_id,
    )
    return result.model_dump(mode="json")

