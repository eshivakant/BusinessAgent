from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from business_agent.api.security import verify_internal_api_token
from business_agent.config import get_settings
from business_agent.data.readonly_sql import SQLReadRequest, SQLReadResponse
from business_agent.dependencies import (
    get_orchestrator,
    get_sql_reader,
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


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
    if not isinstance(chat, dict) or not isinstance(text, str):
        return {"ok": True, "ignored": True}

    chat_id = chat.get("id")
    if not isinstance(chat_id, int):
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
