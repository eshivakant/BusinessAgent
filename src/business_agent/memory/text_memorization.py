"""Service for memorizing arbitrary text messages and voice note transcriptions.

Stores text in the memory store with appropriate metadata for later retrieval.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, date
from typing import Any

from business_agent.memory.models import MemoryPayload, MemoryRecord
from business_agent.memory.store import MemoryStore


class TextMemorizationService:
    """Stores arbitrary text in memory for later retrieval."""

    def __init__(self, memory_store: MemoryStore) -> None:
        self._memory_store = memory_store

    def memorize_text(
        self,
        text: str,
        chat_id: int | None = None,
        source_type: str = "text_message",
    ) -> str:
        """Store a text message in memory.
        
        Args:
            text: The text content to memorize.
            chat_id: Telegram chat ID for context.
            source_type: Type of source (text_message, voice_transcription, etc.)
        
        Returns:
            The memory record ID.
        """
        record_id = f"memo-{uuid.uuid4().hex[:12]}"
        ingested_at = datetime.now(timezone.utc)
        
        payload = MemoryPayload(
            event_date=ingested_at.date(),
            ingested_at=ingested_at,
            effective_date=ingested_at,
            source_type=source_type,
            source_uri=f"telegram://chat/{chat_id}" if chat_id else "text://message",
            record_type="memorized_text",
            summary=text[:200] if len(text) > 200 else text,
        )
        
        record = MemoryRecord(
            id=record_id,
            text=text,
            payload=payload,
        )
        
        self._memory_store.upsert([record])
        return record_id

    def memorize_voice_transcription(
        self,
        transcription: str,
        audio_file_id: str | None = None,
        chat_id: int | None = None,
    ) -> str:
        """Store a voice note transcription in memory.
        
        Args:
            transcription: The transcribed text.
            audio_file_id: Telegram file_id of the original voice note.
            chat_id: Telegram chat ID for context.
        
        Returns:
            The memory record ID.
        """
        source_uri = f"telegram://voice/{audio_file_id}" if audio_file_id else "voice://message"
        return self.memorize_text(
            text=transcription,
            chat_id=chat_id,
            source_type="voice_note",
        )
