from __future__ import annotations

from datetime import date, datetime, time, timezone

from qdrant_client.http import models as qmodels

from business_agent.memory.models import MemoryQueryInput


def _to_utc_datetime(input_date: date, end_of_day: bool) -> datetime:
    time_part = time.max if end_of_day else time.min
    return datetime.combine(input_date, time_part, tzinfo=timezone.utc)


def build_memory_filter(query: MemoryQueryInput) -> qmodels.Filter | None:
    must_conditions: list[qmodels.Condition] = []

    if query.source_type:
        must_conditions.append(
            qmodels.FieldCondition(
                key="source_type",
                match=qmodels.MatchValue(value=query.source_type),
            )
        )

    if query.source_uri:
        must_conditions.append(
            qmodels.FieldCondition(
                key="source_uri",
                match=qmodels.MatchValue(value=query.source_uri),
            )
        )

    if query.date_from or query.date_to:
        must_conditions.append(
            qmodels.FieldCondition(
                key="effective_date",
                range=qmodels.DatetimeRange(
                    gte=_to_utc_datetime(query.date_from, end_of_day=False) if query.date_from else None,
                    lte=_to_utc_datetime(query.date_to, end_of_day=True) if query.date_to else None,
                ),
            )
        )

    if not must_conditions:
        return None
    return qmodels.Filter(must=must_conditions)
