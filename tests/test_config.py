from __future__ import annotations

from business_agent.config import Settings, get_settings


def test_settings_defaults_without_env_file() -> None:
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.app_port == 8080
    assert settings.qdrant_distance == "Cosine"
    assert settings.conversation_enabled is True
    assert settings.conversation_window_messages == 8
    assert settings.allowed_sql_tables == set()
    assert settings.app_database_url is None
    assert settings.app_database_admin_url is None


def test_allowed_sql_tables_parses_csv_and_strips() -> None:
    settings = Settings(_env_file=None, sql_allowed_tables=" orders, customers , ,orders ")
    assert settings.allowed_sql_tables == {"orders", "customers"}


def test_get_settings_respects_env_and_cache(monkeypatch) -> None:
    monkeypatch.setenv("APP_NETWORK_EXTERNAL", "false")
    monkeypatch.setenv("SQL_ALLOWED_TABLES", "orders,customers")
    monkeypatch.setenv("CONVERSATION_WINDOW_MESSAGES", "6")
    monkeypatch.setenv("APP_DATABASE_URL", "sqlite:///tmp/business-agent.db")
    monkeypatch.setenv("APP_DATABASE_ADMIN_URL", "postgresql+psycopg://postgres:secret@postgres:5432/postgres")
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.app_network_external is False
    assert settings.conversation_window_messages == 6
    assert settings.allowed_sql_tables == {"orders", "customers"}
    assert settings.app_database_url == "sqlite:///tmp/business-agent.db"
    assert settings.app_database_admin_url == "postgresql+psycopg://postgres:secret@postgres:5432/postgres"

    get_settings.cache_clear()
