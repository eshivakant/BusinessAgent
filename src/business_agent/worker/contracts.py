from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Protocol


class SubagentTaskType(str, Enum):
    DOCUMENT_INGESTION = "document_ingestion"


@dataclass(frozen=True)
class DocumentIngestionTask:
    source_uri: str
    event_date: date | None = None
    requester_id: int | None = None


class SubagentTaskQueue(Protocol):
    def enqueue_document_ingestion(self, task: DocumentIngestionTask) -> str:
        ...

