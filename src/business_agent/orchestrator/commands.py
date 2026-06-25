from __future__ import annotations

import shlex
import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class AskCommand:
    question: str
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class IngestCommand:
    source_uri: str
    event_date: date | None = None


@dataclass(frozen=True)
class DataCommand:
    table: str
    columns: list[str]
    filters: dict[str, str | int | float | bool]
    limit: int


@dataclass(frozen=True)
class ListCommand:
    document_type: str | None = None
    vendor: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 100


def parse_ask_command(raw_text: str) -> AskCommand:
    text = raw_text.strip()
    if text.startswith("/ask"):
        text = text[4:].strip()
    if text.startswith("/knowledge"):
        text = text[10:].strip()
    return parse_question_with_optional_dates(text)


def parse_question_with_optional_dates(text: str) -> AskCommand:
    tokens = shlex.split(text)
    date_from = None
    date_to = None
    question_tokens: list[str] = []

    for token in tokens:
        if token.startswith("from="):
            date_from = date.fromisoformat(token.split("=", 1)[1])
            continue
        if token.startswith("to="):
            date_to = date.fromisoformat(token.split("=", 1)[1])
            continue
        question_tokens.append(token)

    question = " ".join(question_tokens).strip()
    if not question:
        raise ValueError("Question is required. Example: /ask from=2026-01-01 What happened?")
    if date_from and date_to and date_from > date_to:
        raise ValueError("from date must be before or equal to to date")

    return AskCommand(question=question, date_from=date_from, date_to=date_to)


def parse_ingest_command(raw_text: str) -> IngestCommand:
    text = raw_text.strip()
    if text.startswith("/ingest"):
        text = text[7:].strip()
    tokens = shlex.split(text)
    if not tokens:
        raise ValueError("Document source URI is required. Example: /ingest /data/docs/report.pdf")

    source_uri = tokens[0]
    event_date = None
    for token in tokens[1:]:
        if token.startswith("event_date="):
            event_date = date.fromisoformat(token.split("=", 1)[1])
            continue
        raise ValueError(f"Unsupported ingest option: {token}")

    return IngestCommand(source_uri=source_uri, event_date=event_date)


def parse_data_command(raw_text: str, default_limit: int, max_limit: int) -> DataCommand:
    text = raw_text.strip()
    if text.startswith("/data"):
        text = text[5:].strip()
    tokens = shlex.split(text)
    if not tokens:
        raise ValueError(
            "Data command is empty. Example: /data table=orders columns=id,total filters=status:open limit=20"
        )

    arguments: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"Expected key=value pair, got: {token}")
        key, value = token.split("=", 1)
        arguments[key.strip().lower()] = value.strip()

    table = arguments.get("table")
    columns = arguments.get("columns")
    if not table or not columns:
        raise ValueError("table and columns are required in /data command")

    filters: dict[str, str | int | float | bool] = {}
    filters_token = arguments.get("filters", "")
    if filters_token:
        for part in filters_token.split(","):
            if ":" not in part:
                raise ValueError(f"Invalid filter expression: {part}")
            key, value = part.split(":", 1)
            filters[key.strip()] = _coerce_filter_value(value.strip())

    limit_text = arguments.get("limit")
    limit = default_limit if not limit_text else int(limit_text)
    if limit < 1:
        raise ValueError("limit must be positive")
    if limit > max_limit:
        limit = max_limit

    return DataCommand(
        table=table,
        columns=[column_name.strip() for column_name in columns.split(",") if column_name.strip()],
        filters=filters,
        limit=limit,
    )


def _coerce_filter_value(raw_value: str) -> str | int | float | bool:
    lowered = raw_value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", raw_value):
        return int(raw_value)
    if re.fullmatch(r"-?\d+\.\d+", raw_value):
        return float(raw_value)
    return raw_value


def parse_list_command(raw_text: str) -> ListCommand:
    """Parse /list command for document filtering.
    
    Example: /list type=invoice vendor=acme date_from=2025-01-01 date_to=2025-12-31 limit=50
    Also accepts: list type=invoice ... (without slash)
    """
    text = raw_text.strip()
    if text.startswith("/list"):
        text = text[5:].strip()
    elif text.startswith("list"):
        text = text[4:].strip()
    
    tokens = shlex.split(text)
    document_type = None
    vendor = None
    date_from = None
    date_to = None
    limit = 100
    
    for token in tokens:
        if "=" not in token:
            raise ValueError(f"Expected key=value pair, got: {token}")
        key, value = token.split("=", 1)
        key = key.strip().lower()
        value = value.strip()
        
        if key == "type":
            document_type = value
        elif key == "vendor":
            vendor = value
        elif key == "date_from":
            date_from = date.fromisoformat(value)
        elif key == "date_to":
            date_to = date.fromisoformat(value)
        elif key == "limit":
            limit = int(value)
        else:
            raise ValueError(f"Unsupported list option: {key}")
    
    if date_from and date_to and date_from > date_to:
        raise ValueError("date_from must be before or equal to date_to")
    
    return ListCommand(
        document_type=document_type,
        vendor=vendor,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

