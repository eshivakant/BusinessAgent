from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from business_agent.persistence.bootstrap import ensure_postgres_database


def test_bootstrap_rejects_non_postgres_urls() -> None:
    with pytest.raises(ValueError, match="PostgreSQL driver"):
        ensure_postgres_database(
            admin_url="postgresql+psycopg://admin:secret@postgres:5432/postgres",
            app_database_url="sqlite:///tmp/test.db",
        )


def test_bootstrap_rejects_invalid_identifiers() -> None:
    with pytest.raises(ValueError, match="Unsupported PostgreSQL identifier"):
        ensure_postgres_database(
            admin_url="postgresql+psycopg://admin:secret@postgres:5432/postgres",
            app_database_url="postgresql+psycopg://bad-user:secret@postgres:5432/business_agent",
        )


def test_bootstrap_creates_role_and_database_when_missing() -> None:
    mock_connection = MagicMock()
    mock_connection.execute.side_effect = [
        MagicMock(scalar=MagicMock(return_value=None)),
        MagicMock(),
        MagicMock(scalar=MagicMock(return_value=None)),
        MagicMock(),
    ]
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_connection

    with patch("business_agent.persistence.bootstrap.create_engine", return_value=mock_engine):
        ensure_postgres_database(
            admin_url="postgresql+psycopg://admin:secret@postgres:5432/postgres",
            app_database_url="postgresql+psycopg://business_agent:appsecret@postgres:5432/business_agent",
        )

    statements = [args[0].text for args, _ in mock_connection.execute.call_args_list]
    assert statements[0] == "SELECT 1 FROM pg_roles WHERE rolname = :name"
    assert 'CREATE ROLE "business_agent" LOGIN PASSWORD :password' in statements[1]
    assert statements[2] == "SELECT 1 FROM pg_database WHERE datname = :name"
    assert 'CREATE DATABASE "business_agent" OWNER "business_agent"' in statements[3]


def test_bootstrap_skips_creation_when_role_and_database_exist() -> None:
    mock_connection = MagicMock()
    mock_connection.execute.side_effect = [
        MagicMock(scalar=MagicMock(return_value=1)),
        MagicMock(scalar=MagicMock(return_value=1)),
    ]
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_connection

    with patch("business_agent.persistence.bootstrap.create_engine", return_value=mock_engine):
        ensure_postgres_database(
            admin_url="postgresql+psycopg://admin:secret@postgres:5432/postgres",
            app_database_url="postgresql+psycopg://business_agent:appsecret@postgres:5432/business_agent",
        )

    statements = [args[0].text for args, _ in mock_connection.execute.call_args_list]
    assert statements == [
        "SELECT 1 FROM pg_roles WHERE rolname = :name",
        "SELECT 1 FROM pg_database WHERE datname = :name",
    ]
