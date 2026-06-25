from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol, Sequence


class EmbeddingService(Protocol):
    vector_size: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        ...


class DeterministicEmbeddingService:
    """Deterministic hashed embeddings for local/dev scaffolding."""

    def __init__(self, vector_size: int = 256) -> None:
        self.vector_size = vector_size

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.vector_size
        tokens = re.findall(r"\w+", text.lower())

        for token in tokens:
            digest = hashlib.blake2s(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:4], byteorder="big") % self.vector_size
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            vector[0] = 1.0
            return vector

        return [value / norm for value in vector]

