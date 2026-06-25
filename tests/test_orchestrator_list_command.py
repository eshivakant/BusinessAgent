"""Tests for /list command parsing and handling."""

from datetime import date, datetime, timezone

import pytest

from business_agent.orchestrator.commands import ListCommand, parse_list_command


def test_parse_list_command_empty():
    """Test parsing empty /list command uses defaults."""
    cmd = parse_list_command("/list")
    assert cmd.document_type is None
    assert cmd.vendor is None
    assert cmd.date_from is None
    assert cmd.date_to is None
    assert cmd.limit == 100


def test_parse_list_command_with_type():
    """Test parsing /list with document type."""
    cmd = parse_list_command("/list type=invoice")
    assert cmd.document_type == "invoice"


def test_parse_list_command_with_vendor():
    """Test parsing /list with vendor."""
    cmd = parse_list_command("/list vendor=acme")
    assert cmd.vendor == "acme"


def test_parse_list_command_with_dates():
    """Test parsing /list with date range."""
    cmd = parse_list_command("/list date_from=2025-01-01 date_to=2025-12-31")
    assert cmd.date_from == date(2025, 1, 1)
    assert cmd.date_to == date(2025, 12, 31)


def test_parse_list_command_with_limit():
    """Test parsing /list with custom limit."""
    cmd = parse_list_command("/list limit=50")
    assert cmd.limit == 50


def test_parse_list_command_combined():
    """Test parsing /list with multiple filters."""
    cmd = parse_list_command(
        "/list type=invoice vendor=acme date_from=2025-01-01 date_to=2025-12-31 limit=20"
    )
    assert cmd.document_type == "invoice"
    assert cmd.vendor == "acme"
    assert cmd.date_from == date(2025, 1, 1)
    assert cmd.date_to == date(2025, 12, 31)
    assert cmd.limit == 20


def test_parse_list_command_no_slash():
    """Test parsing /list command without leading slash."""
    cmd = parse_list_command("list type=invoice")
    assert cmd.document_type == "invoice"


def test_parse_list_command_invalid_date():
    """Test parsing /list with invalid date format."""
    with pytest.raises(ValueError):
        parse_list_command("/list date_from=2025/01/01")


def test_parse_list_command_invalid_limit():
    """Test parsing /list with invalid limit."""
    with pytest.raises(ValueError):
        parse_list_command("/list limit=notanumber")


def test_parse_list_command_date_range_error():
    """Test that from > to raises error."""
    with pytest.raises(ValueError, match="date_from must be before or equal to date_to"):
        parse_list_command("/list date_from=2025-12-31 date_to=2025-01-01")


def test_parse_list_command_unknown_option():
    """Test parsing /list with unknown option."""
    with pytest.raises(ValueError, match="Unsupported list option"):
        parse_list_command("/list unknown_key=value")


def test_parse_list_command_missing_equals():
    """Test parsing /list with malformed key=value."""
    with pytest.raises(ValueError, match="Expected key=value pair"):
        parse_list_command("/list type invoice")


def test_parse_list_command_whitespace():
    """Test parsing /list with extra whitespace."""
    cmd = parse_list_command("  /list  type=invoice  limit=10  ")
    assert cmd.document_type == "invoice"
    assert cmd.limit == 10
