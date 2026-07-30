from __future__ import annotations

from typing import Protocol

from business_agent.property.models import Tenant
from business_agent.tenancy.models import GeneratedAgreement, TenantDocument


class TenancyRegistry(Protocol):
    def create_tenancy(self, tenancy: Tenant) -> None:
        ...

    def get_tenancy(self, tenancy_id: str) -> Tenant | None:
        ...

    def list_tenancies(self, property_id: str | None = None, active_only: bool = True) -> list[Tenant]:
        ...

    def update_tenancy(self, tenancy: Tenant) -> None:
        ...

    def add_document(self, document: TenantDocument) -> None:
        ...

    def list_documents(self, tenancy_id: str) -> list[TenantDocument]:
        ...

    def create_agreement(self, agreement: GeneratedAgreement) -> None:
        ...

    def get_agreement(self, agreement_id: str) -> GeneratedAgreement | None:
        ...


class InMemoryTenancyRegistry:
    def __init__(self) -> None:
        self._tenancies: dict[str, Tenant] = {}
        self._documents: dict[str, TenantDocument] = {}
        self._agreements: dict[str, GeneratedAgreement] = {}

    def create_tenancy(self, tenancy: Tenant) -> None:
        self._tenancies[tenancy.id] = tenancy

    def get_tenancy(self, tenancy_id: str) -> Tenant | None:
        return self._tenancies.get(tenancy_id)

    def list_tenancies(self, property_id: str | None = None, active_only: bool = True) -> list[Tenant]:
        tenancies = list(self._tenancies.values())
        if property_id:
            tenancies = [item for item in tenancies if item.property_id == property_id]
        if active_only:
            tenancies = [item for item in tenancies if item.is_active]
        return sorted(tenancies, key=lambda item: item.created_at, reverse=True)

    def update_tenancy(self, tenancy: Tenant) -> None:
        if tenancy.id in self._tenancies:
            self._tenancies[tenancy.id] = tenancy

    def add_document(self, document: TenantDocument) -> None:
        self._documents[document.id] = document

    def list_documents(self, tenancy_id: str) -> list[TenantDocument]:
        docs = [item for item in self._documents.values() if item.tenancy_id == tenancy_id]
        return sorted(docs, key=lambda item: item.ingested_at, reverse=True)

    def create_agreement(self, agreement: GeneratedAgreement) -> None:
        self._agreements[agreement.id] = agreement

    def get_agreement(self, agreement_id: str) -> GeneratedAgreement | None:
        return self._agreements.get(agreement_id)
