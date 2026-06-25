from datetime import date

import pytest

from business_agent.orchestrator.commands import (
    parse_ask_command,
    parse_data_command,
    parse_ingest_command,
    parse_question_with_optional_dates,
)


def test_parse_ask_command_with_dates() -> None:
    command = parse_ask_command("/ask from=2026-01-01 to=2026-01-31 revenue trend")
    assert command.question == "revenue trend"
    assert command.date_from == date(2026, 1, 1)
    assert command.date_to == date(2026, 1, 31)


def test_parse_question_with_optional_dates_requires_question() -> None:
    with pytest.raises(ValueError, match="Question is required"):
        parse_question_with_optional_dates("from=2026-01-01")


def test_parse_ingest_command_with_event_date() -> None:
    command = parse_ingest_command("/ingest /data/docs/report.pdf event_date=2026-02-05")
    assert command.source_uri == "/data/docs/report.pdf"
    assert command.event_date == date(2026, 2, 5)


def test_parse_ingest_command_rejects_unknown_option() -> None:
    with pytest.raises(ValueError, match="Unsupported ingest option"):
        parse_ingest_command("/ingest /data/docs/report.pdf foo=bar")


def test_parse_data_command_parses_filters_and_caps_limit() -> None:
    command = parse_data_command(
        "/data table=orders columns=id,total filters=status:paid,region:uk limit=2000",
        default_limit=50,
        max_limit=100,
    )
    assert command.table == "orders"
    assert command.columns == ["id", "total"]
    assert command.filters == {"status": "paid", "region": "uk"}
    assert command.limit == 100
