from __future__ import annotations

from business_agent import dependencies
from business_agent.ingestion.registry import InMemoryDocumentRegistry
from business_agent.persistence.database import AppDatabase
from business_agent.persistence.registry import SqlAlchemyDocumentRegistry, SqlAlchemyPropertyRegistry
from business_agent.property.registry import InMemoryPropertyRegistry


def _clear_dependency_caches() -> None:
    dependencies.get_settings.cache_clear()
    dependencies.get_app_database.cache_clear()
    dependencies.get_document_registry.cache_clear()
    dependencies.get_property_registry.cache_clear()


def test_dependencies_use_in_memory_registries_without_app_database(monkeypatch) -> None:
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    _clear_dependency_caches()

    document_registry = dependencies.get_document_registry()
    property_registry = dependencies.get_property_registry()

    assert isinstance(document_registry, InMemoryDocumentRegistry)
    assert isinstance(property_registry, InMemoryPropertyRegistry)

    _clear_dependency_caches()


def test_dependencies_use_sqlalchemy_registries_with_app_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_DATABASE_URL", f"sqlite:///{tmp_path / 'deps.db'}")
    _clear_dependency_caches()

    app_database = dependencies.get_app_database()
    document_registry = dependencies.get_document_registry()
    property_registry = dependencies.get_property_registry()

    assert isinstance(app_database, AppDatabase)
    assert isinstance(document_registry, SqlAlchemyDocumentRegistry)
    assert isinstance(property_registry, SqlAlchemyPropertyRegistry)

    _clear_dependency_caches()
