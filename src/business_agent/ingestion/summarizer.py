from __future__ import annotations

import re
from typing import Protocol


class Summarizer(Protocol):
    def summarize(self, text: str) -> str:
        ...


class ExtractiveSummarizer:
    def __init__(self, max_sentences: int = 5) -> None:
        self._max_sentences = max_sentences

    def summarize(self, text: str) -> str:
        cleaned = " ".join(text.split())
        if not cleaned:
            return ""
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]
        if not sentences:
            return cleaned[:1000]
        summary = " ".join(sentences[: self._max_sentences])
        return summary[:2000]

