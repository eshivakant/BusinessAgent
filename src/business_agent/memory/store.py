from __future__ import annotations

from typing import Any, Protocol, Sequence

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from business_agent.memory.embeddings import EmbeddingService
from business_agent.memory.filters import build_memory_filter
from business_agent.memory.models import MemoryMatch, MemoryPayload, MemoryQueryInput, MemoryRecord


class MemoryStore(Protocol):
    def ensure_collection(self) -> None:
        ...

    def upsert(self, records: Sequence[MemoryRecord]) -> None:
        ...

    def query(self, request: MemoryQueryInput) -> list[MemoryMatch]:
        ...


class QdrantMemoryStore:
    def __init__(
        self,
        url: str,
        collection_name: str,
        vector_size: int,
        distance: str,
        embedding_service: EmbeddingService,
        api_key: str | None = None,
        client: QdrantClient | None = None,
    ) -> None:
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._distance = distance
        self._embedding_service = embedding_service
        self._client = client or QdrantClient(url=url, api_key=api_key)

    def ensure_collection(self) -> None:
        if self._client.collection_exists(collection_name=self._collection_name):
            return
        self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=qmodels.VectorParams(
                size=self._vector_size,
                distance=self._to_qdrant_distance(self._distance),
            ),
        )

    def upsert(self, records: Sequence[MemoryRecord]) -> None:
        if not records:
            return

        self.ensure_collection()
        vectors = self._embedding_service.embed([record.text for record in records])
        points = []
        for record, vector in zip(records, vectors, strict=True):
            payload = record.payload.model_dump(mode="json")
            payload["text"] = record.text
            points.append(
                qmodels.PointStruct(
                    id=record.id,
                    vector=vector,
                    payload=payload,
                )
            )
        self._client.upsert(collection_name=self._collection_name, points=points, wait=True)

    def query(self, request: MemoryQueryInput) -> list[MemoryMatch]:
        self.ensure_collection()
        vector = self._embedding_service.embed([request.query])[0]
        query_filter = build_memory_filter(request)
        hits = self._client.search(
            collection_name=self._collection_name,
            query_vector=vector,
            query_filter=query_filter,
            with_payload=True,
            limit=request.top_k,
        )
        return [self._map_hit(hit) for hit in hits]

    def _to_qdrant_distance(self, distance: str) -> qmodels.Distance:
        mapping = {
            "Cosine": qmodels.Distance.COSINE,
            "Dot": qmodels.Distance.DOT,
            "Euclid": qmodels.Distance.EUCLID,
            "Manhattan": qmodels.Distance.MANHATTAN,
        }
        if distance not in mapping:
            raise ValueError(f"Unsupported Qdrant distance: {distance}")
        return mapping[distance]

    def _map_hit(self, hit: Any) -> MemoryMatch:
        payload_data = dict(hit.payload or {})
        text = str(payload_data.pop("text", ""))
        payload = MemoryPayload.model_validate(payload_data)
        return MemoryMatch(id=str(hit.id), score=float(hit.score), text=text, payload=payload)

