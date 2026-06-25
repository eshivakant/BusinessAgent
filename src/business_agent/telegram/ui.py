from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MENU_ASK = "menu:ask"
MENU_INGEST = "menu:ingest"
MENU_DATA = "menu:data"
MENU_RESET = "menu:reset"

ACT_REFINE = "act:refine"
ACT_DATE = "act:date"
ACT_SOURCES = "act:sources"
ACT_DETAILS = "act:details"
ACT_FOLLOW = "act:follow"
ACT_COMPACT = "act:compact"

MENU_BUTTON_LABELS = {
    "Ask question": MENU_ASK,
    "Upload document": MENU_INGEST,
    "Query data": MENU_DATA,
    "Reset context": MENU_RESET,
}


@dataclass(frozen=True)
class ParsedCallback:
    action: str
    token: str | None = None


def build_menu_keyboard() -> dict[str, list[list[dict[str, str]]]]:
    return {
        "inline_keyboard": [
            [
                {"text": "Ask question", "callback_data": MENU_ASK},
                {"text": "Upload document", "callback_data": MENU_INGEST},
            ],
            [
                {"text": "Query data", "callback_data": MENU_DATA},
                {"text": "Reset context", "callback_data": MENU_RESET},
            ],
        ]
    }


def build_answer_actions_keyboard(token: str) -> dict[str, list[list[dict[str, str]]]]:
    keyboard = build_menu_keyboard()["inline_keyboard"]
    keyboard.extend(
        [
            [
                {"text": "Refine", "callback_data": f"{ACT_REFINE}:{token}"},
                {"text": "Date filter", "callback_data": f"{ACT_DATE}:{token}"},
            ],
            [
                {"text": "Show sources", "callback_data": f"{ACT_SOURCES}:{token}"},
                {"text": "More details", "callback_data": f"{ACT_DETAILS}:{token}"},
            ],
            [
                {"text": "Follow-up", "callback_data": f"{ACT_FOLLOW}:{token}"},
            ],
        ]
    )
    return {"inline_keyboard": keyboard}


def build_compact_view_keyboard(token: str) -> dict[str, list[list[dict[str, str]]]]:
    keyboard = build_menu_keyboard()["inline_keyboard"]
    keyboard.extend(
        [
            [
                {"text": "Back to compact", "callback_data": f"{ACT_COMPACT}:{token}"},
            ],
            [
                {"text": "Show sources", "callback_data": f"{ACT_SOURCES}:{token}"},
                {"text": "More details", "callback_data": f"{ACT_DETAILS}:{token}"},
            ],
        ]
    )
    return {"inline_keyboard": keyboard}


def parse_callback_data(data: str) -> ParsedCallback | None:
    if data in {MENU_ASK, MENU_INGEST, MENU_DATA, MENU_RESET}:
        return ParsedCallback(action=data, token=None)
    if data.count(":") < 2:
        return None
    action, token = data.rsplit(":", maxsplit=1)
    if action not in {ACT_REFINE, ACT_DATE, ACT_SOURCES, ACT_DETAILS, ACT_FOLLOW, ACT_COMPACT}:
        return None
    return ParsedCallback(action=action, token=token)


def map_menu_text_to_action(text: str) -> str | None:
    normalized = " ".join(text.split())
    return MENU_BUTTON_LABELS.get(normalized)


def format_menu_prompt(action: str) -> str:
    if action == MENU_ASK:
        return (
            "Ask your question directly, or use:\n"
            "/ask from=YYYY-MM-DD to=YYYY-MM-DD <question>"
        )
    if action == MENU_INGEST:
        return (
            "Queue a document for ingestion:\n"
            "/ingest /data/docs/report.pdf event_date=2026-01-15\n"
            "Status updates will be returned after queueing."
        )
    if action == MENU_DATA:
        return (
            "Run read-only SQL query:\n"
            "/data table=orders columns=id,total filters=status:paid limit=20"
        )
    if action == MENU_RESET:
        return "Use /reset to clear conversation context for this chat."
    return "Use /help for available actions."


def action_requires_cached_payload(action: str) -> bool:
    return action in {ACT_REFINE, ACT_DATE, ACT_SOURCES, ACT_DETAILS, ACT_FOLLOW, ACT_COMPACT}


def build_callback_prompt(action: str, question_text: str | None) -> str:
    if action == ACT_REFINE:
        seed = question_text or "your question"
        return (
            f"Refine this question:\n\"{seed}\"\n\n"
            "Tip: be specific with entity + metric + time range."
        )
    if action == ACT_DATE:
        seed = question_text or "<your question>"
        return (
            "Add a date range using:\n"
            f"/ask from=2026-01-01 to=2026-01-31 {seed}"
        )
    if action == ACT_FOLLOW:
        return "Send your follow-up in one message. I will use recent context automatically."
    return "Action complete."


def build_response_preview(text: str) -> dict[str, Any]:
    return {"text": text}

