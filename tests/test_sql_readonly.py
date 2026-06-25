from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, text

from business_agent.data.readonly_sql import ReadOnlySQLDataAccess, SQLReadRequest


def _seed_orders_db(db_path: Path) -> str:
    db_url = f"sqlite+pysqlite:///{db_path}"
    engine = create_engine(db_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    total REAL NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO orders (id, status, total) VALUES
                    (1, 'paid', 100.0),
                    (2, 'pending', 55.5),
                    (3, 'paid', 240.0)
                """
            )
        )
    engine.dispose()
    return db_url


def test_sql_readonly_fetch_rows_with_filters_and_limit(tmp_path: Path) -> None:
    db_url = _seed_orders_db(tmp_path / "orders.db")
    reader = ReadOnlySQLDataAccess(
        database_url=db_url,
        allowed_tables={"orders"},
        default_limit=10,
        max_limit=100,
    )

    request = SQLReadRequest(
        table="orders",
        columns=["id", "status", "total"],
        filters={"status": "paid"},
        limit=5,
    )
    rows = reader.fetch_rows(request)

    assert len(rows) == 2
    assert {row["id"] for row in rows} == {1, 3}


def test_sql_readonly_limit_is_capped_to_max_limit(tmp_path: Path) -> None:
    db_url = _seed_orders_db(tmp_path / "orders.db")
    reader = ReadOnlySQLDataAccess(
        database_url=db_url,
        allowed_tables={"orders"},
        default_limit=10,
        max_limit=1,
    )

    request = SQLReadRequest(table="orders", columns=["id"], limit=999)
    rows = reader.fetch_rows(request)
    assert len(rows) == 1


def test_sql_readonly_rejects_table_not_in_allowlist(tmp_path: Path) -> None:
    db_url = _seed_orders_db(tmp_path / "orders.db")
    reader = ReadOnlySQLDataAccess(
        database_url=db_url,
        allowed_tables={"customers"},
    )

    request = SQLReadRequest(table="orders", columns=["id"])
    with pytest.raises(PermissionError, match="SQL_ALLOWED_TABLES"):
        reader.fetch_rows(request)


def test_sql_readonly_rejects_when_no_allowed_tables(tmp_path: Path) -> None:
    db_url = _seed_orders_db(tmp_path / "orders.db")
    reader = ReadOnlySQLDataAccess(database_url=db_url, allowed_tables=set())
    request = SQLReadRequest(table="orders", columns=["id"])

    with pytest.raises(PermissionError, match="No SQL tables are allowed"):
        reader.fetch_rows(request)


def test_sql_readonly_identifier_validation_blocks_invalid_names() -> None:
    with pytest.raises(ValidationError):
        SQLReadRequest(table="orders;DROP_TABLE", columns=["id"])

    with pytest.raises(ValidationError):
        SQLReadRequest(table="orders", columns=["id", "status;DELETE"])


def test_sql_readonly_filter_value_is_parameterized(tmp_path: Path) -> None:
    db_url = _seed_orders_db(tmp_path / "orders.db")
    reader = ReadOnlySQLDataAccess(
        database_url=db_url,
        allowed_tables={"orders"},
        default_limit=10,
        max_limit=10,
    )

    request = SQLReadRequest(
        table="orders",
        columns=["id", "status"],
        filters={"status": "paid' OR 1=1 --"},
    )
    rows = reader.fetch_rows(request)
    assert rows == []
