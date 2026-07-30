from __future__ import annotations

import re

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from business_agent.config import get_settings
from business_agent.persistence.database import AppDatabase

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quoted_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsupported PostgreSQL identifier: {value}")
    return f'"{value}"'


def ensure_postgres_database(admin_url: str, app_database_url: str) -> None:
    target_url = make_url(app_database_url)
    if target_url.get_backend_name() != "postgresql":
        raise ValueError("APP_DATABASE_URL must use a PostgreSQL driver for bootstrap")
    if not target_url.database:
        raise ValueError("APP_DATABASE_URL must include a database name")
    if not target_url.username:
        raise ValueError("APP_DATABASE_URL must include a username")
    if target_url.password is None:
        raise ValueError("APP_DATABASE_URL must include a password for bootstrap")

    role_name = _quoted_identifier(target_url.username)
    database_name = _quoted_identifier(target_url.database)

    engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            role_exists = connection.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :name"),
                {"name": target_url.username},
            ).scalar()
            if role_exists is None:
                connection.execute(
                    text(f"CREATE ROLE {role_name} LOGIN PASSWORD :password"),
                    {"password": target_url.password},
                )

            database_exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target_url.database},
            ).scalar()
            if database_exists is None:
                connection.execute(text(f"CREATE DATABASE {database_name} OWNER {role_name}"))
    finally:
        engine.dispose()


def main() -> None:
    settings = get_settings()
    if not settings.app_database_url:
        raise RuntimeError("APP_DATABASE_URL must be set to bootstrap app persistence")

    if settings.app_database_admin_url:
        ensure_postgres_database(
            admin_url=settings.app_database_admin_url,
            app_database_url=settings.app_database_url,
        )

    AppDatabase(settings.app_database_url).ensure_schema()


if __name__ == "__main__":
    main()
