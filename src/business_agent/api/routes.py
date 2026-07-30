from __future__ import annotations

import tempfile
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from business_agent.api.security import verify_internal_api_token
from business_agent.config import get_settings
from business_agent.data.readonly_sql import SQLReadRequest, SQLReadResponse
from business_agent.dependencies import (
    get_document_registry,
    get_orchestrator,
    get_property_registry,
    get_sql_reader,
    get_tenancy_service,
    get_telegram_client,
    get_telegram_ui_state,
)
from business_agent.ingestion.service import IngestionResult
from business_agent.memory.models import MemoryMatch, MemoryQueryInput
from business_agent.orchestrator.service import TelegramReply
from business_agent.telegram.ui import (
    ACT_COMPACT,
    ACT_DATE,
    ACT_DETAILS,
    ACT_FOLLOW,
    ACT_REFINE,
    ACT_SOURCES,
    MENU_DATA,
    MENU_INGEST,
    MENU_RESET,
    build_answer_actions_keyboard,
    build_callback_prompt,
    build_compact_view_keyboard,
    build_menu_keyboard,
    format_menu_prompt,
    map_menu_text_to_action,
    parse_callback_data,
)
from business_agent.telegram.ui_state import TelegramUiPayload

router = APIRouter()


def _serialize_tenancy(tenancy: Any) -> dict[str, Any]:
    return {
        "id": tenancy.id,
        "property_id": tenancy.property_id,
        "full_name": tenancy.full_name or tenancy.name,
        "email": tenancy.email,
        "phone": tenancy.phone,
        "lease_start": tenancy.lease_start.isoformat() if tenancy.lease_start else None,
        "lease_end": tenancy.lease_end.isoformat() if tenancy.lease_end else None,
        "monthly_rent": float(tenancy.monthly_rent) if tenancy.monthly_rent is not None else None,
        "deposit": float(tenancy.deposit) if tenancy.deposit is not None else None,
        "is_active": tenancy.is_active,
        "notes": tenancy.notes,
        "created_at": tenancy.created_at.isoformat() if tenancy.created_at else None,
        "updated_at": tenancy.updated_at.isoformat() if tenancy.updated_at else None,
    }


def _serialize_document(document: Any) -> dict[str, Any]:
    return {
        "id": document.id,
        "tenancy_id": document.tenancy_id,
        "filename": document.filename,
        "stored_path": document.stored_path,
        "document_type": document.document_type,
        "ingested_at": document.ingested_at.isoformat() if document.ingested_at else None,
        "extracted_fields": document.extracted_fields,
        "qdrant_ids": document.qdrant_ids,
        "summary": document.summary,
        "chunk_count": document.chunk_count,
    }


class MemoryQueryResponse(BaseModel):
    matches: list[MemoryMatch]


class DocumentIngestRequest(BaseModel):
    source_uri: str = Field(min_length=1)
    event_date: date | None = None
    async_mode: bool = True
    requester_id: int | None = None


class DocumentIngestResponse(BaseModel):
    status: str
    job_id: str | None = None
    result: IngestionResult | None = None


class TenancyCreateRequest(BaseModel):
    property_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    email: str | None = None
    phone: str | None = None
    lease_start: date | None = None
    lease_end: date | None = None
    monthly_rent: float | None = None
    deposit: float | None = None
    notes: str | None = None


class TenancyUpdateRequest(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    lease_start: date | None = None
    lease_end: date | None = None
    monthly_rent: float | None = None
    deposit: float | None = None
    is_active: bool | None = None
    notes: str | None = None


class AgreementGenerateRequest(BaseModel):
    tenancy_id: str = Field(min_length=1)
    template_name: str | None = None
    values: dict[str, Any] | None = None
    missing_values: dict[str, Any] | None = None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/tenancies", dependencies=[Depends(verify_internal_api_token)])
def create_tenancy(payload: TenancyCreateRequest) -> dict[str, Any]:
    service = get_tenancy_service()
    tenancy = service.create_tenancy(
        property_id=payload.property_id,
        full_name=payload.full_name,
        email=payload.email,
        phone=payload.phone,
        lease_start=payload.lease_start,
        lease_end=payload.lease_end,
        monthly_rent=Decimal(str(payload.monthly_rent)) if payload.monthly_rent is not None else None,
        deposit=Decimal(str(payload.deposit)) if payload.deposit is not None else None,
        notes=payload.notes,
    )
    return _serialize_tenancy(tenancy)


@router.get("/api/tenancies", dependencies=[Depends(verify_internal_api_token)])
def list_tenancies(property_id: str | None = None, active_only: bool = True) -> dict[str, Any]:
    service = get_tenancy_service()
    tenancies = service.list_tenancies(property_id=property_id, active_only=active_only)
    return {
        "items": [_serialize_tenancy(tenancy) for tenancy in tenancies],
        "count": len(tenancies),
    }


@router.get("/api/tenancies/{tenancy_id}", dependencies=[Depends(verify_internal_api_token)])
def get_tenancy(tenancy_id: str) -> dict[str, Any]:
    service = get_tenancy_service()
    tenancy = service.get_tenancy(tenancy_id)
    if tenancy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenancy not found")
    return _serialize_tenancy(tenancy)


@router.patch("/api/tenancies/{tenancy_id}", dependencies=[Depends(verify_internal_api_token)])
def update_tenancy(tenancy_id: str, payload: TenancyUpdateRequest) -> dict[str, Any]:
    service = get_tenancy_service()
    updates: dict[str, Any] = {}
    for field_name in [
        "full_name",
        "email",
        "phone",
        "lease_start",
        "lease_end",
        "monthly_rent",
        "deposit",
        "is_active",
        "notes",
    ]:
        value = getattr(payload, field_name, None)
        if value is not None:
            if field_name in {"monthly_rent", "deposit"}:
                updates[field_name] = Decimal(str(value))
            else:
                updates[field_name] = value
    tenancy = service.update_tenancy(tenancy_id, updates)
    if tenancy is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenancy not found")
    return _serialize_tenancy(tenancy)


@router.post("/api/tenancies/{tenancy_id}/documents", dependencies=[Depends(verify_internal_api_token)])
async def upload_tenancy_document(
    tenancy_id: str,
    file: UploadFile,
    event_date: str | None = None,
) -> dict[str, Any]:
    service = get_tenancy_service()
    temp_dir = Path(tempfile.gettempdir())
    temp_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}_{file.filename or 'upload'}"
    temp_path = temp_dir / safe_name
    temp_path.write_bytes(await file.read())
    try:
        parsed_date = date.fromisoformat(event_date) if event_date else None
        document = service.store_document(
            tenancy_id,
            temp_path,
            filename=file.filename,
            event_date=parsed_date,
        )
    finally:
        temp_path.unlink(missing_ok=True)
    return _serialize_document(document)


@router.get("/api/tenancies/{tenancy_id}/documents", dependencies=[Depends(verify_internal_api_token)])
def list_tenancy_documents(tenancy_id: str) -> dict[str, Any]:
    service = get_tenancy_service()
    documents = service.list_documents(tenancy_id)
    return {
        "items": [_serialize_document(document) for document in documents],
        "count": len(documents),
    }


@router.post("/api/agreements/generate", dependencies=[Depends(verify_internal_api_token)])
def generate_agreement(payload: AgreementGenerateRequest) -> dict[str, Any]:
    service = get_tenancy_service()
    agreement, unresolved = service.generate_agreement(
        payload.tenancy_id,
        template_name=payload.template_name,
        values=payload.values,
        missing_values=payload.missing_values,
    )
    return {
        "agreement_id": agreement.id,
        "tenancy_id": agreement.tenancy_id,
        "template_name": agreement.template_name,
        "stored_path": agreement.stored_path,
        "pdf_path": agreement.pdf_path,
        "generated_at": agreement.generated_at.isoformat(),
        "unresolved_placeholders": unresolved,
    }


@router.post("/telegram/webhook")
async def telegram_webhook(
    update: dict[str, Any],
    x_telegram_secret: Annotated[
        str | None,
        Header(alias="X-Telegram-Bot-Api-Secret-Token"),
    ] = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.telegram_webhook_secret and x_telegram_secret != settings.telegram_webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Telegram webhook secret.",
        )

    callback_query = update.get("callback_query")
    if isinstance(callback_query, dict):
        return await _handle_callback_query(update=callback_query, token_enabled=bool(settings.telegram_bot_token))

    message = update.get("message")
    if not isinstance(message, dict):
        return {"ok": True, "ignored": True}

    chat = message.get("chat")
    text = message.get("text")
    if not isinstance(chat, dict):
        return {"ok": True, "ignored": True}

    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
        return {"ok": True, "ignored": True}

    # Handle voice messages
    voice = message.get("voice")
    if isinstance(voice, dict):
        return await _handle_voice_message(chat_id=chat_id, voice=voice, settings=settings)

    # Handle document uploads (files sent to the bot)
    document = message.get("document")
    if isinstance(document, dict):
        return await _handle_document_upload(chat_id=chat_id, document=document, settings=settings, caption=text)

    # Handle photo uploads
    photos = message.get("photo")
    if isinstance(photos, list) and len(photos) > 0:
        # Use the largest photo
        largest_photo = photos[-1]
        if isinstance(largest_photo, dict):
            return await _handle_photo_upload(chat_id=chat_id, photo=largest_photo, settings=settings, caption=text)

    if not isinstance(text, str):
        return {"ok": True, "ignored": True}

    normalized_text = text.strip()
    menu_action = map_menu_text_to_action(normalized_text)
    if menu_action in {MENU_INGEST, MENU_DATA}:
        reply = TelegramReply(text=format_menu_prompt(menu_action))
    elif menu_action == MENU_RESET:
        reply = _invoke_orchestrator_reply(chat_id=chat_id, message_text="/reset")
    elif menu_action is not None:
        reply = TelegramReply(text=format_menu_prompt(menu_action))
    else:
        reply = _invoke_orchestrator_reply(chat_id=chat_id, message_text=normalized_text)

    if settings.telegram_bot_token:
        reply_markup = _build_reply_markup(chat_id=chat_id, reply=reply)
        await get_telegram_client().send_message(
            chat_id=chat_id,
            text=reply.text,
            reply_markup=reply_markup,
        )
        return {"ok": True}

    return {"ok": True, "response_preview": reply.text}


async def _handle_voice_message(
    chat_id: int,
    voice: dict[str, Any],
    settings: Any,
) -> dict[str, Any]:
    """Handle a Telegram voice message: download, transcribe, store, and respond."""
    from business_agent.dependencies import get_llm_client, get_text_memorization_service
    
    file_id = voice.get("file_id")
    if not file_id:
        return {"ok": True, "error": "No file_id in voice message"}
    
    try:
        telegram_client = get_telegram_client()
        audio_data = await telegram_client.download_file(file_id)
        
        # Save to temp file
        import tempfile
        from pathlib import Path
        import uuid
        
        temp_dir = Path(tempfile.gettempdir())
        temp_path = temp_dir / f"voice_{uuid.uuid4().hex}.ogg"
        temp_path.write_bytes(audio_data)
        
        # Transcribe
        llm_client = get_llm_client()
        if llm_client:
            transcription = llm_client.transcribe_audio(str(temp_path))
        else:
            transcription = "[Voice note received but LLM not configured for transcription]"
        
        temp_path.unlink(missing_ok=True)
        
        # Store in memory
        memo_service = get_text_memorization_service()
        record_id = memo_service.memorize_voice_transcription(
            transcription=transcription,
            audio_file_id=file_id,
            chat_id=chat_id,
        )
        
        # Send confirmation
        reply_text = f"🎙️ Voice note transcribed and stored.\n\nTranscription:\n{transcription[:1000]}"
        if settings.telegram_bot_token:
            await telegram_client.send_message(chat_id=chat_id, text=reply_text)
            return {"ok": True}
        
        return {"ok": True, "response_preview": reply_text}
    except Exception as e:
        error_msg = f"❌ Failed to process voice note: {e}"
        if settings.telegram_bot_token:
            await get_telegram_client().send_message(chat_id=chat_id, text=error_msg)
        return {"ok": False, "error": str(e)}


async def _handle_document_upload(
    chat_id: int,
    document: dict[str, Any],
    settings: Any,
    caption: str | None = None,
) -> dict[str, Any]:
    """Handle a document file uploaded to the bot."""
    from business_agent.dependencies import get_telegram_client
    
    file_id = document.get("file_id")
    file_name = document.get("file_name", "unknown")
    mime_type = document.get("mime_type", "application/octet-stream")
    
    if not file_id:
        return {"ok": True, "error": "No file_id in document"}
    
    try:
        telegram_client = get_telegram_client()
        file_data = await telegram_client.download_file(file_id)
        
        # Save to ingestion directory
        from pathlib import Path
        import uuid
        
        # Use the ingestion allowed dir
        ingest_dir = Path(settings.ingestion_allowed_local_dir)
        ingest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{file_name}"
        file_path = ingest_dir / safe_name
        file_path.write_bytes(file_data)
        
        # Trigger ingestion
        source_uri = str(file_path)
        orchestrator = get_orchestrator()
        
        # Use caption as event_date hint if it looks like a date
        event_date = None
        if caption:
            from datetime import date as date_cls
            try:
                parts = caption.strip().split("-")
                if len(parts) == 3:
                    event_date = date_cls(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        
        result = orchestrator.ingest_document_now(
            source_uri=source_uri,
            event_date=event_date,
            requester_id=chat_id,
        )
        
        reply_text = f"📄 Document ingested: {file_name}\nID: {result.document_id}\nChunks: {result.chunk_count}"
        if settings.telegram_bot_token:
            await telegram_client.send_message(chat_id=chat_id, text=reply_text)
            return {"ok": True}
        
        return {"ok": True, "response_preview": reply_text}
    except Exception as e:
        error_msg = f"❌ Failed to process document: {e}"
        if settings.telegram_bot_token:
            await get_telegram_client().send_message(chat_id=chat_id, text=error_msg)
        return {"ok": False, "error": str(e)}


async def _handle_photo_upload(
    chat_id: int,
    photo: dict[str, Any],
    settings: Any,
    caption: str | None = None,
) -> dict[str, Any]:
    """Handle a photo uploaded to the bot (OCR + ingestion)."""
    from business_agent.dependencies import get_telegram_client
    
    file_id = photo.get("file_id")
    if not file_id:
        return {"ok": True, "error": "No file_id in photo"}
    
    try:
        telegram_client = get_telegram_client()
        file_data = await telegram_client.download_file(file_id)
        
        # Save to ingestion directory
        from pathlib import Path
        import uuid
        
        ingest_dir = Path(settings.ingestion_allowed_local_dir)
        ingest_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_photo.jpg"
        file_path = ingest_dir / safe_name
        file_path.write_bytes(file_data)
        
        # Trigger ingestion (the ingestion service will handle OCR)
        source_uri = str(file_path)
        orchestrator = get_orchestrator()
        
        event_date = None
        if caption:
            from datetime import date as date_cls
            try:
                parts = caption.strip().split("-")
                if len(parts) == 3:
                    event_date = date_cls(int(parts[0]), int(parts[1]), int(parts[2]))
            except (ValueError, IndexError):
                pass
        
        result = orchestrator.ingest_document_now(
            source_uri=source_uri,
            event_date=event_date,
            requester_id=chat_id,
        )
        
        reply_text = f"🖼️ Photo ingested and OCR processed.\nID: {result.document_id}\nChunks: {result.chunk_count}"
        if settings.telegram_bot_token:
            await telegram_client.send_message(chat_id=chat_id, text=reply_text)
            return {"ok": True}
        
        return {"ok": True, "response_preview": reply_text}
    except Exception as e:
        error_msg = f"❌ Failed to process photo: {e}"
        if settings.telegram_bot_token:
            await get_telegram_client().send_message(chat_id=chat_id, text=error_msg)
        return {"ok": False, "error": str(e)}


@router.post(
    "/api/memory/query",
    response_model=MemoryQueryResponse,
    dependencies=[Depends(verify_internal_api_token)],
)
def query_memory(request: MemoryQueryInput) -> MemoryQueryResponse:
    matches = get_orchestrator().query_memory(request)
    return MemoryQueryResponse(matches=matches)


@router.post(
    "/api/documents/ingest",
    response_model=DocumentIngestResponse,
    dependencies=[Depends(verify_internal_api_token)],
)
def ingest_document(request: DocumentIngestRequest) -> DocumentIngestResponse:
    orchestrator = get_orchestrator()

    if request.async_mode:
        job_id = orchestrator.enqueue_document_ingestion(
            source_uri=request.source_uri,
            event_date=request.event_date,
            requester_id=request.requester_id,
        )
        return DocumentIngestResponse(status="queued", job_id=job_id)

    result = orchestrator.ingest_document_now(
        source_uri=request.source_uri,
        event_date=request.event_date,
        requester_id=request.requester_id,
    )
    return DocumentIngestResponse(status="completed", result=result)


@router.post(
    "/api/sql/read",
    response_model=SQLReadResponse,
    dependencies=[Depends(verify_internal_api_token)],
)
def read_sql(request: SQLReadRequest) -> SQLReadResponse:
    sql_reader = get_sql_reader()
    if sql_reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SQL access is not configured.",
        )
    try:
        rows = sql_reader.fetch_rows(request)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return SQLReadResponse(rows=rows, row_count=len(rows))


async def _handle_callback_query(update: dict[str, Any], token_enabled: bool) -> dict[str, Any]:
    callback_id = update.get("id")
    data = update.get("data")
    message = update.get("message")
    if not isinstance(callback_id, str) or not isinstance(data, str) or not isinstance(message, dict):
        return {"ok": True, "ignored": True}

    chat = message.get("chat")
    message_id = message.get("message_id")
    if not isinstance(chat, dict) or not isinstance(chat.get("id"), int):
        return {"ok": True, "ignored": True}

    chat_id = chat["id"]
    parsed = parse_callback_data(data)
    if parsed is None:
        if token_enabled:
            await get_telegram_client().answer_callback_query(callback_query_id=callback_id, text="Unknown action.")
        return {"ok": True, "ignored": True}

    if token_enabled:
        await get_telegram_client().answer_callback_query(callback_query_id=callback_id)

    if parsed.action in {MENU_INGEST, MENU_DATA, MENU_RESET, "menu:ask"}:
        if parsed.action == MENU_RESET:
            response_text = _invoke_orchestrator_reply(chat_id=chat_id, message_text="/reset").text
        else:
            response_text = format_menu_prompt(parsed.action)
        if token_enabled:
            await _send_or_edit(
                chat_id=chat_id,
                message_id=message_id,
                text=response_text,
                reply_markup=build_menu_keyboard(),
            )
        return {"ok": True, "response_preview": response_text}

    token = parsed.token
    if not token:
        if token_enabled:
            await get_telegram_client().send_message(
                chat_id=chat_id,
                text="This action is missing context. Ask a new question first.",
                reply_markup=build_menu_keyboard(),
            )
        return {"ok": True, "ignored": True}

    payload = get_telegram_ui_state().load(chat_id=chat_id, token=token)
    if payload is None:
        expired_text = "Action expired. Ask the question again to refresh actions."
        if token_enabled:
            await _send_or_edit(
                chat_id=chat_id,
                message_id=message_id,
                text=expired_text,
                reply_markup=build_menu_keyboard(),
            )
        return {"ok": True, "response_preview": expired_text}

    if parsed.action == ACT_COMPACT:
        text = payload.compact_text
        markup = build_answer_actions_keyboard(token)
        if token_enabled:
            await _send_or_edit(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
        return {"ok": True, "response_preview": text}

    if parsed.action == ACT_SOURCES:
        text = payload.sources_text or "No source list is available for this response."
        markup = build_compact_view_keyboard(token)
        if token_enabled:
            await _send_or_edit(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
        return {"ok": True, "response_preview": text}

    if parsed.action == ACT_DETAILS:
        text = payload.detailed_text or "No additional details are available."
        markup = build_compact_view_keyboard(token)
        if token_enabled:
            await _send_or_edit(chat_id=chat_id, message_id=message_id, text=text, reply_markup=markup)
        return {"ok": True, "response_preview": text}

    if parsed.action in {ACT_REFINE, ACT_DATE, ACT_FOLLOW}:
        text = build_callback_prompt(parsed.action, payload.question_text)
        if token_enabled:
            await get_telegram_client().send_message(chat_id=chat_id, text=text, reply_markup=build_menu_keyboard())
        return {"ok": True, "response_preview": text}

    return {"ok": True, "ignored": True}


def _invoke_orchestrator_reply(chat_id: int, message_text: str) -> TelegramReply:
    orchestrator = get_orchestrator()
    if hasattr(orchestrator, "handle_telegram_message_with_ui"):
        return orchestrator.handle_telegram_message_with_ui(chat_id=chat_id, message_text=message_text)
    return TelegramReply(text=orchestrator.handle_telegram_message(chat_id=chat_id, message_text=message_text))


def _build_reply_markup(chat_id: int, reply: TelegramReply) -> dict[str, Any]:
    if not reply.show_actions:
        return build_menu_keyboard()

    payload = TelegramUiPayload(
        compact_text=reply.text,
        detailed_text=reply.detailed_text,
        sources_text=reply.sources_text,
        question_text=reply.question_text,
    )
    token = get_telegram_ui_state().store(chat_id=chat_id, payload=payload)
    return build_answer_actions_keyboard(token)


async def _send_or_edit(chat_id: int, message_id: Any, text: str, reply_markup: dict[str, Any]) -> None:
    if isinstance(message_id, int):
        await get_telegram_client().edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )
        return
    await get_telegram_client().send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# Document API endpoints


class DocumentListResponse(BaseModel):
    """Response for document list query."""
    count: int
    documents: list[dict[str, Any]]


class DocumentInfoResponse(BaseModel):
    """Response for single document info."""
    document_id: str
    title: str
    document_type: str
    vendor: str | None
    department: str | None
    keywords: list[str]
    summary: str
    chunk_count: int
    ingested_at: str
    event_date: str | None
    archive_link: str | None


@router.get("/api/documents/list", response_model=DocumentListResponse)
def list_documents(
    document_type: str | None = None,
    vendor: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 100,
    _: None = Depends(verify_internal_api_token),
) -> DocumentListResponse:
    """List documents with optional filters."""
    from business_agent.dependencies import get_document_registry
    from datetime import datetime
    
    registry = get_document_registry()
    if registry is None:
        return DocumentListResponse(count=0, documents=[])
    
    # Parse date filters
    from_date = datetime.fromisoformat(date_from) if date_from else None
    to_date = datetime.fromisoformat(date_to) if date_to else None
    
    # Query registry
    docs = registry.query(
        document_type=document_type,
        vendor=vendor,
        date_from=from_date,
        date_to=to_date,
        limit=limit,
    )
    
    settings = get_settings()
    documents = []
    for doc in docs:
        archive_link = None
        if doc.archived_file_path and settings.app_base_url:
            archive_link = f"{settings.app_base_url}/api/documents/{doc.document_id}/download"
        
        documents.append({
            "document_id": doc.document_id,
            "title": doc.title,
            "document_type": doc.document_type,
            "vendor": doc.vendor,
            "department": doc.department,
            "keywords": doc.keywords,
            "ingested_at": doc.ingested_at.isoformat(),
            "event_date": doc.event_date.isoformat() if doc.event_date else None,
            "archive_link": archive_link,
        })
    
    return DocumentListResponse(count=len(documents), documents=documents)


@router.get("/api/documents/{document_id}", response_model=DocumentInfoResponse)
def get_document(
    document_id: str,
    _: None = Depends(verify_internal_api_token),
) -> DocumentInfoResponse:
    """Get document metadata and summary."""
    
    from business_agent.dependencies import get_document_registry
    
    registry = get_document_registry()
    if registry is None:
        raise HTTPException(status_code=404, detail="Document registry not available")
    
    doc = registry.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    
    settings = get_settings()
    archive_link = None
    if doc.archived_file_path and settings.app_base_url:
        archive_link = f"{settings.app_base_url}/api/documents/{document_id}/download"
    
    return DocumentInfoResponse(
        document_id=doc.document_id,
        title=doc.title,
        document_type=doc.document_type,
        vendor=doc.vendor,
        department=doc.department,
        keywords=doc.keywords,
        summary=doc.summary,
        chunk_count=doc.chunk_count,
        ingested_at=doc.ingested_at.isoformat(),
        event_date=doc.event_date.isoformat() if doc.event_date else None,
        archive_link=archive_link,
    )


@router.get("/api/documents/{document_id}/download")
def download_document(
    document_id: str,
    _: None = Depends(verify_internal_api_token),
):
    """Download original archived document."""
    from business_agent.dependencies import get_document_registry
    from fastapi.responses import FileResponse
    from pathlib import Path
    
    registry = get_document_registry()
    if registry is None:
        raise HTTPException(status_code=404, detail="Document registry not available")
    
    doc = registry.get(document_id)
    if doc is None or doc.archived_file_path is None:
        raise HTTPException(status_code=404, detail="Document or archive not found")
    
    file_path = Path(doc.archived_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Archive file not found on disk")
    
    return FileResponse(
        path=file_path,
        filename=f"{document_id}.{doc.source_type}",
        media_type="application/octet-stream",
    )


# Property Management APIs

class PropertyCreateRequest(BaseModel):
    """Request to create a new property."""
    id: str = Field(min_length=1)
    address: str = Field(min_length=1)
    purchase_date: date | None = None
    purchase_price: float | None = None
    current_value: float | None = None
    status: str = "viewing"  # Default to viewing
    bedrooms: int | None = None
    bathrooms: int | None = None
    square_feet: int | None = None
    postcode: str | None = None
    notes: str | None = None


class PropertyResponse(BaseModel):
    """Property response model."""
    id: str
    address: str
    purchase_date: date | None
    purchase_price: float | None
    current_value: float | None
    status: str
    bedrooms: int | None
    bathrooms: int | None
    square_feet: int | None
    postcode: str | None
    notes: str | None


class MortgageResponse(BaseModel):
    """Mortgage response model."""
    id: str
    property_id: str
    lender: str
    principal: float
    interest_rate: float
    term_months: int
    monthly_payment: float
    end_date: date | None
    months_until_expiry: int | None


class PortfolioSummaryResponse(BaseModel):
    """Portfolio summary response."""
    total_properties: int
    owned_count: int
    under_offer_count: int
    viewing_count: int
    total_monthly_rent: float
    active_tenants: int
    open_maintenance_count: int
    expiring_mortgages_count: int


@router.get("/api/properties", response_model=list[PropertyResponse])
def list_properties(
    property_status: str | None = None,
    _: None = Depends(verify_internal_api_token),
) -> list[PropertyResponse]:
    """List all properties, optionally filtered by status."""
    from business_agent.property.models import PropertyStatus
    from decimal import Decimal
    
    registry = get_property_registry()
    
    status_filter = None
    if property_status:
        try:
            status_filter = PropertyStatus(property_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {property_status}. Valid: owned, under_offer, viewing, sold, pending_purchase"
            )
    
    properties = registry.list_properties(status=status_filter)
    
    return [
        PropertyResponse(
            id=p.id,
            address=p.address,
            purchase_date=p.purchase_date,
            purchase_price=float(p.purchase_price) if p.purchase_price else None,
            current_value=float(p.current_value) if p.current_value else None,
            status=p.status.value,
            bedrooms=p.bedrooms,
            bathrooms=p.bathrooms,
            square_feet=p.square_feet,
            postcode=p.postcode,
            notes=p.notes,
        )
        for p in properties
    ]


@router.post("/api/properties", response_model=PropertyResponse, status_code=201)
def create_property(
    request: PropertyCreateRequest,
    _: None = Depends(verify_internal_api_token),
) -> PropertyResponse:
    """Create a new property."""
    from business_agent.property.models import Property, PropertyStatus
    from decimal import Decimal
    
    registry = get_property_registry()
    
    # Check if property already exists
    if registry.get_property(request.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Property with ID {request.id} already exists"
        )
    
    # Validate status
    try:
        property_status = PropertyStatus(request.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status: {request.status}"
        )
    
    # Create property
    prop = Property(
        id=request.id,
        address=request.address,
        purchase_date=request.purchase_date,
        purchase_price=Decimal(str(request.purchase_price)) if request.purchase_price else None,
        current_value=Decimal(str(request.current_value)) if request.current_value else None,
        status=property_status,
        bedrooms=request.bedrooms,
        bathrooms=request.bathrooms,
        square_feet=request.square_feet,
        postcode=request.postcode,
        notes=request.notes,
    )
    
    registry.add_property(prop)
    
    return PropertyResponse(
        id=prop.id,
        address=prop.address,
        purchase_date=prop.purchase_date,
        purchase_price=float(prop.purchase_price) if prop.purchase_price else None,
        current_value=float(prop.current_value) if prop.current_value else None,
        status=prop.status.value,
        bedrooms=prop.bedrooms,
        bathrooms=prop.bathrooms,
        square_feet=prop.square_feet,
        postcode=prop.postcode,
        notes=prop.notes,
    )


@router.get("/api/mortgages/expiring", response_model=list[MortgageResponse])
def list_expiring_mortgages(
    months: int = 6,
    _: None = Depends(verify_internal_api_token),
) -> list[MortgageResponse]:
    """List mortgages expiring within specified months."""
    registry = get_property_registry()
    
    if months < 1 or months > 120:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="months must be between 1 and 120"
        )
    
    expiring = registry.list_expiring_mortgages(months=months)
    
    return [
        MortgageResponse(
            id=m.id,
            property_id=m.property_id,
            lender=m.lender,
            principal=float(m.principal),
            interest_rate=float(m.interest_rate),
            term_months=m.term_months,
            monthly_payment=float(m.monthly_payment),
            end_date=m.end_date,
            months_until_expiry=m.months_until_expiry(),
        )
        for m in expiring
    ]


@router.get("/api/portfolio/summary", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(
    expiring_window_months: int = 6,
    _: None = Depends(verify_internal_api_token),
) -> PortfolioSummaryResponse:
    """Get portfolio summary with key metrics."""
    from business_agent.property.models import PropertyStatus, MaintenanceStatus
    from decimal import Decimal
    
    registry = get_property_registry()
    
    # Get all properties
    all_properties = registry.list_properties()
    owned = [p for p in all_properties if p.status == PropertyStatus.OWNED]
    under_offer = [p for p in all_properties if p.status == PropertyStatus.UNDER_OFFER]
    viewing = [p for p in all_properties if p.status == PropertyStatus.VIEWING]
    
    # Calculate total monthly rent from active tenants
    all_tenants = registry.list_tenants(active_only=True)
    total_rent = sum(t.monthly_rent for t in all_tenants)
    
    # Count open maintenance requests
    all_maintenance = registry.list_maintenance_requests()
    open_maintenance = [
        m for m in all_maintenance 
        if m.status in (MaintenanceStatus.REPORTED, MaintenanceStatus.QUOTED, MaintenanceStatus.APPROVED, MaintenanceStatus.IN_PROGRESS)
    ]
    
    # Count expiring mortgages
    expiring_mortgages = registry.list_expiring_mortgages(months=expiring_window_months)
    
    return PortfolioSummaryResponse(
        total_properties=len(all_properties),
        owned_count=len(owned),
        under_offer_count=len(under_offer),
        viewing_count=len(viewing),
        total_monthly_rent=float(total_rent),
        active_tenants=len(all_tenants),
        open_maintenance_count=len(open_maintenance),
        expiring_mortgages_count=len(expiring_mortgages),
    )
