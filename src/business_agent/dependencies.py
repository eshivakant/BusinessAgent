from __future__ import annotations

from functools import lru_cache

from business_agent.config import get_settings
from business_agent.conveyancing.service import ConveyancingService
from business_agent.data.readonly_sql import ReadOnlySQLDataAccess
from business_agent.ingestion.registry import DocumentRegistry, InMemoryDocumentRegistry
from business_agent.ingestion.service import DocumentIngestionService
from business_agent.ingestion.summarizer import ExtractiveSummarizer
from business_agent.llm.client import LLMClient
from business_agent.maintenance.service import MaintenanceService
from business_agent.memory.embeddings import DeterministicEmbeddingService
from business_agent.memory.store import QdrantMemoryStore
from business_agent.memory.text_memorization import TextMemorizationService
from business_agent.orchestrator.conversation import ConversationStore, RedisConversationStore
from business_agent.orchestrator.service import BusinessOrchestrator
from business_agent.persistence.database import AppDatabase
from business_agent.persistence.registry import SqlAlchemyDocumentRegistry, SqlAlchemyPropertyRegistry
from business_agent.property.registry import InMemoryPropertyRegistry, PropertyRegistry
from business_agent.telegram.client import TelegramBotClient
from business_agent.telegram.ui_state import RedisTelegramUiStateStore, TelegramUiStateStore
from business_agent.tenancy.registry import InMemoryTenancyRegistry, TenancyRegistry
from business_agent.tenancy.service import TenancyService
from business_agent.worker.queue import RedisSubagentQueue


@lru_cache
def get_embedding_service() -> DeterministicEmbeddingService:
    settings = get_settings()
    return DeterministicEmbeddingService(vector_size=settings.qdrant_vector_size)


@lru_cache
def get_memory_store() -> QdrantMemoryStore:
    settings = get_settings()
    return QdrantMemoryStore(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        collection_name=settings.qdrant_collection,
        vector_size=settings.qdrant_vector_size,
        distance=settings.qdrant_distance,
        embedding_service=get_embedding_service(),
    )


@lru_cache
def get_llm_client() -> LLMClient | None:
    settings = get_settings()
    if not settings.llm_openrouter_api_key:
        return None
    return LLMClient(
        api_key=settings.llm_openrouter_api_key,
        base_url=settings.llm_openrouter_base_url,
        request_timeout=settings.llm_request_timeout,
    )


@lru_cache
def get_document_registry() -> DocumentRegistry:
    app_database = get_app_database()
    if app_database is not None:
        return SqlAlchemyDocumentRegistry(app_database)
    return InMemoryDocumentRegistry()


@lru_cache
def get_property_registry() -> PropertyRegistry:
    app_database = get_app_database()
    if app_database is not None:
        return SqlAlchemyPropertyRegistry(app_database)
    return InMemoryPropertyRegistry()


@lru_cache
def get_tenancy_registry() -> TenancyRegistry:
    app_database = get_app_database()
    if app_database is not None:
        from business_agent.persistence.registry import SqlAlchemyTenancyRegistry

        return SqlAlchemyTenancyRegistry(app_database)
    return InMemoryTenancyRegistry()


@lru_cache
def get_tenancy_service() -> TenancyService:
    settings = get_settings()
    return TenancyService(
        tenancy_registry=get_tenancy_registry(),
        property_registry=get_property_registry(),
        memory_store=get_memory_store(),
        summarizer=get_summarizer(),
        chunk_size=settings.ingestion_chunk_size,
        chunk_overlap=settings.ingestion_chunk_overlap,
        max_document_chars=settings.ingestion_max_document_chars,
        storage_dir=settings.tenant_docs_dir,
        template_dir=settings.agreement_templates_dir,
        generated_dir=settings.generated_agreements_dir,
        llm_client=get_llm_client(),
        allowed_local_dir=settings.ingestion_allowed_local_dir,
    )


@lru_cache
def get_conveyancing_service() -> ConveyancingService:
    settings = get_settings()
    return ConveyancingService(
        property_registry=get_property_registry(),
        memory_store=get_memory_store(),
        summarizer=get_summarizer(),
        chunk_size=settings.ingestion_chunk_size,
        chunk_overlap=settings.ingestion_chunk_overlap,
        max_document_chars=settings.ingestion_max_document_chars,
        storage_dir=settings.conveyancing_docs_dir,
        allowed_local_dir=settings.ingestion_allowed_local_dir,
    )


@lru_cache
def get_maintenance_service() -> MaintenanceService:
    settings = get_settings()
    return MaintenanceService(
        property_registry=get_property_registry(),
        memory_store=get_memory_store(),
        summarizer=get_summarizer(),
        chunk_size=settings.ingestion_chunk_size,
        chunk_overlap=settings.ingestion_chunk_overlap,
        max_document_chars=settings.ingestion_max_document_chars,
        storage_dir=settings.maintenance_docs_dir,
        allowed_local_dir=settings.ingestion_allowed_local_dir,
    )


@lru_cache
def get_summarizer() -> ExtractiveSummarizer:
    settings = get_settings()
    return ExtractiveSummarizer(max_sentences=settings.ingestion_summary_sentences)


@lru_cache
def get_ingestion_service() -> DocumentIngestionService:
    settings = get_settings()
    return DocumentIngestionService(
        memory_store=get_memory_store(),
        summarizer=get_summarizer(),
        chunk_size=settings.ingestion_chunk_size,
        chunk_overlap=settings.ingestion_chunk_overlap,
        max_document_chars=settings.ingestion_max_document_chars,
        allowed_local_dir=settings.ingestion_allowed_local_dir,
        archive_dir=settings.ingestion_archive_dir,
        archive_enabled=settings.ingestion_archive_enabled,
        llm_client=get_llm_client(),
        document_registry=get_document_registry(),
        enable_metadata_extraction=settings.ingestion_enable_metadata_extraction,
    )


@lru_cache
def get_task_queue() -> RedisSubagentQueue:
    settings = get_settings()
    return RedisSubagentQueue(redis_url=settings.redis_url, queue_name=settings.rq_queue_name)


@lru_cache
def get_conversation_store() -> ConversationStore | None:
    settings = get_settings()
    if not settings.conversation_enabled:
        return None
    return RedisConversationStore(
        redis_url=settings.redis_url,
        window_messages=settings.conversation_window_messages,
        summary_max_chars=settings.conversation_summary_max_chars,
        context_max_chars=settings.conversation_context_max_chars,
        ttl_seconds=settings.conversation_ttl_seconds,
    )


@lru_cache
def get_telegram_ui_state() -> TelegramUiStateStore:
    settings = get_settings()
    return RedisTelegramUiStateStore(
        redis_url=settings.redis_url,
        ttl_seconds=settings.telegram_ui_state_ttl_seconds,
    )


@lru_cache
def get_sql_reader() -> ReadOnlySQLDataAccess | None:
    settings = get_settings()
    if not settings.sql_database_url:
        return None
    return ReadOnlySQLDataAccess(
        database_url=settings.sql_database_url,
        allowed_tables=settings.allowed_sql_tables,
        default_limit=settings.sql_query_limit_default,
        max_limit=settings.sql_query_limit_max,
    )


@lru_cache
def get_orchestrator() -> BusinessOrchestrator:
    return BusinessOrchestrator(
        memory_store=get_memory_store(),
        task_queue=get_task_queue(),
        ingestion_service=get_ingestion_service(),
        conversation_store=get_conversation_store(),
        sql_reader=get_sql_reader(),
        document_registry=get_document_registry(),
        property_registry=get_property_registry(),
        tenancy_service=get_tenancy_service(),
        conveyancing_service=get_conveyancing_service(),
        maintenance_service=get_maintenance_service(),
        llm_client=get_llm_client(),
        text_memorization_service=get_text_memorization_service(),
    )


@lru_cache
def get_telegram_client() -> TelegramBotClient:
    settings = get_settings()
    return TelegramBotClient(token=settings.telegram_bot_token, api_base=settings.telegram_api_base)


@lru_cache
def get_text_memorization_service() -> TextMemorizationService:
    return TextMemorizationService(memory_store=get_memory_store())


@lru_cache
def get_app_database() -> AppDatabase | None:
    settings = get_settings()
    if not settings.app_database_url:
        return None
    database = AppDatabase(settings.app_database_url)
    database.ensure_schema()
    return database
