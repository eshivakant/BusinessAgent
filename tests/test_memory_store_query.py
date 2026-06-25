from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from typing import Any, Sequence

import pytest

from business_agent.memory.models import MemoryPayload, MemoryQueryInput, MemoryRecord
from business_agent.memory.store import QdrantMemoryStore


class FakeEmbeddingService:
    vector_size = 3

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [[0.25, 0.5, 0.75] for _ in texts]


class FakeQdrantClient:
    def __init__(self) -> None:
        self.search_kwargs: dict[str, Any] = {}
        self.upsert_kwargs: dict[str, Any] = {}
        self.collection_exists_value = True
        self.create_collection_kwargs: dict[str, Any] = {}

    def collection_exists(self, collection_name: str) -> bool:
        del collection_name
        return self.collection_exists_value

    def create_collection(self, **_: Any) -> None:
        self.create_collection_kwargs = _

    def search(self, **kwargs: Any) -> list[SimpleNamespace]:
        self.search_kwargs = kwargs
        return [
            SimpleNamespace(
                id="doc-1",
                score=0.91,
                payload={
                    "text": "Revenue increased in Q1.",
                    "event_date": "2026-01-15",
                    "ingested_at": "2026-01-16T11:22:33Z",
                    "effective_date": "2026-01-15T00:00:00Z",
                    "source_type": "pdf",
                    "source_uri": "file:///data/docs/q1-report.pdf",
                    "record_type": "chunk",
                    "chunk_index": 0,
                    "chunk_count": 4,
                    "summary": "Q1 revenue increased.",
                },
            )
        ]

    def upsert(self, **kwargs: Any) -> None:
        self.upsert_kwargs = kwargs


def _sample_record() -> MemoryRecord:
    payload = MemoryPayload(
        event_date=date(2026, 1, 15),
        ingested_at="2026-01-16T11:22:33Z",
        effective_date="2026-01-15T00:00:00Z",
        source_type="pdf",
        source_uri="file:///data/docs/q1-report.pdf",
        record_type="chunk",
        chunk_index=0,
        chunk_count=1,
        summary="Q1 revenue increased.",
    )
    return MemoryRecord(id="doc-1", text="Revenue increased in Q1.", payload=payload)


def test_memory_query_passes_filter_and_maps_response() -> None:
    fake_client = FakeQdrantClient()
    store = QdrantMemoryStore(
        url="http://unused",
        api_key=None,
        collection_name="test-memory",
        vector_size=3,
        distance="Cosine",
        embedding_service=FakeEmbeddingService(),
        client=fake_client,
    )

    request = MemoryQueryInput(
        query="What happened in January?",
        top_k=3,
        date_from=date(2026, 1, 1),
    )
    matches = store.query(request)

    assert fake_client.search_kwargs["limit"] == 3
    assert fake_client.search_kwargs["query_filter"] is not None
    assert matches[0].id == "doc-1"
    assert matches[0].payload.source_uri == "file:///data/docs/q1-report.pdf"
    assert matches[0].payload.event_date == date(2026, 1, 15)


def test_upsert_builds_qdrant_points_with_payload_text() -> None:
    fake_client = FakeQdrantClient()
    fake_client.collection_exists_value = False
    store = QdrantMemoryStore(
        url="http://unused",
        api_key=None,
        collection_name="test-memory",
        vector_size=3,
        distance="Cosine",
        embedding_service=FakeEmbeddingService(),
        client=fake_client,
    )
    record = _sample_record()

    store.upsert([record])

    assert fake_client.create_collection_kwargs["collection_name"] == "test-memory"
    points = fake_client.upsert_kwargs["points"]
    assert len(points) == 1
    assert points[0].id == "doc-1"
    assert points[0].payload["source_uri"] == "file:///data/docs/q1-report.pdf"
    assert points[0].payload["text"] == "Revenue increased in Q1."
    assert points[0].payload["event_date"] == "2026-01-15"


def test_invalid_qdrant_distance_raises() -> None:
    fake_client = FakeQdrantClient()
    fake_client.collection_exists_value = False
    store = QdrantMemoryStore(
        url="http://unused",
        api_key=None,
        collection_name="test-memory",
        vector_size=3,
        distance="InvalidDistance",
        embedding_service=FakeEmbeddingService(),
        client=fake_client,
    )

    with pytest.raises(ValueError, match="Unsupported Qdrant distance"):
        store.ensure_collection()
