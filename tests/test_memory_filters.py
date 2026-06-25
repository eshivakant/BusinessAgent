from datetime import date, datetime, timezone

from business_agent.memory.filters import build_memory_filter
from business_agent.memory.models import MemoryQueryInput


def test_build_memory_filter_with_date_range_and_source() -> None:
    query = MemoryQueryInput(
        query="sales trend",
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        source_type="pdf",
    )

    query_filter = build_memory_filter(query)
    assert query_filter is not None
    assert query_filter.must is not None

    source_condition = next(
        condition for condition in query_filter.must if getattr(condition, "key", None) == "source_type"
    )
    date_condition = next(
        condition for condition in query_filter.must if getattr(condition, "key", None) == "effective_date"
    )

    assert source_condition.match.value == "pdf"
    assert date_condition.range.gte == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert date_condition.range.lte == datetime(2026, 1, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)


def test_build_memory_filter_returns_none_without_filters() -> None:
    query = MemoryQueryInput(query="forecast")
    assert build_memory_filter(query) is None


def test_build_memory_filter_with_source_uri_only() -> None:
    query = MemoryQueryInput(query="forecast", source_uri="file:///data/docs/report.pdf")
    query_filter = build_memory_filter(query)

    assert query_filter is not None
    assert query_filter.must is not None
    assert len(query_filter.must) == 1
    assert query_filter.must[0].key == "source_uri"
    assert query_filter.must[0].match.value == "file:///data/docs/report.pdf"


def test_build_memory_filter_with_from_only_date() -> None:
    query = MemoryQueryInput(query="forecast", date_from=date(2026, 2, 1))
    query_filter = build_memory_filter(query)

    assert query_filter is not None
    date_condition = next(
        condition for condition in query_filter.must if getattr(condition, "key", None) == "effective_date"
    )
    assert date_condition.range.gte == datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert date_condition.range.lte is None
