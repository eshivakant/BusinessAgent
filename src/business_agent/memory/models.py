from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator


class MemoryPayload(BaseModel):
    event_date: date | None = None
    ingested_at: datetime
    effective_date: datetime
    source_type: str
    source_uri: str
    archived_file_path: str | None = None
    record_type: str
    chunk_index: int | None = None
    chunk_count: int | None = None
    summary: str | None = None
    property_address: str | None = None
    property_id: str | None = None
    document_type: str | None = None
    amount: float | None = None


class MemoryRecord(BaseModel):
    id: str
    text: str
    payload: MemoryPayload


class MemoryMatch(BaseModel):
    id: str
    score: float
    text: str
    payload: MemoryPayload


class MemoryQueryInput(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    date_from: date | None = None
    date_to: date | None = None
    source_type: str | None = None
    source_uri: str | None = None
    property_address: str | None = None
    property_id: str | None = None
    document_type: str | None = None
    record_type: str | None = None

    @model_validator(mode="after")
    def validate_dates(self) -> "MemoryQueryInput":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be less than or equal to date_to")
        return self

