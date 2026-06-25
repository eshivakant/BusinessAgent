from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


QdrantDistance = Literal["Cosine", "Dot", "Euclid", "Manhattan"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_env: str = "development"
    app_log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8080
    internal_api_token: str | None = None

    telegram_bot_token: str = ""
    telegram_webhook_secret: str | None = None
    telegram_api_base: str = "https://api.telegram.org"
    telegram_webhook_path: str = "/telegram/webhook"

    redis_url: str = "redis://redis:6379/0"
    rq_queue_name: str = "business-agent"
    conversation_enabled: bool = True
    conversation_window_messages: int = 8
    conversation_summary_max_chars: int = 1200
    conversation_context_max_chars: int = 2500
    conversation_ttl_seconds: int = 604800
    telegram_ui_state_ttl_seconds: int = 86400

    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "business_agent_memory"
    qdrant_vector_size: int = 256
    qdrant_distance: QdrantDistance = "Cosine"

    ingestion_allowed_local_dir: str = "/data/docs"
    ingestion_archive_dir: str = "/data/archive"
    ingestion_archive_enabled: bool = True
    ingestion_chunk_size: int = 1200
    ingestion_chunk_overlap: int = 200
    ingestion_summary_sentences: int = 5
    ingestion_max_document_chars: int = 200000

    sql_database_url: str | None = None
    sql_allowed_tables: str = ""
    sql_query_limit_default: int = 100
    sql_query_limit_max: int = 1000

    app_network_external: bool = True
    external_docker_network: str = "app-network"
    traefik_enable: bool = False
    traefik_host: str = "business-agent.example.com"

    @property
    def allowed_sql_tables(self) -> set[str]:
        if not self.sql_allowed_tables.strip():
            return set()
        return {item.strip() for item in self.sql_allowed_tables.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
