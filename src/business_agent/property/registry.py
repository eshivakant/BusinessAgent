"""Property registry for storing and querying property portfolio."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from business_agent.property.models import (
    Contact,
    ContactType,
    MaintenanceRequest,
    MaintenanceStatus,
    Mortgage,
    Property,
    PropertyStatus,
    Tenant,
)


class PropertyRegistry(Protocol):
    """Protocol for property storage backend."""

    # Property operations
    def add_property(self, prop: Property) -> None:
        """Add a property to the registry."""
        ...

    def get_property(self, property_id: str) -> Property | None:
        """Get property by ID."""
        ...

    def list_properties(self, status: PropertyStatus | None = None) -> list[Property]:
        """List all properties, optionally filtered by status."""
        ...

    def update_property(self, prop: Property) -> None:
        """Update an existing property."""
        ...

    def delete_property(self, property_id: str) -> bool:
        """Delete a property. Returns True if found and deleted."""
        ...

    # Mortgage operations
    def add_mortgage(self, mortgage: Mortgage) -> None:
        """Add a mortgage to the registry."""
        ...

    def get_mortgage(self, mortgage_id: str) -> Mortgage | None:
        """Get mortgage by ID."""
        ...

    def list_mortgages(self, property_id: str | None = None) -> list[Mortgage]:
        """List mortgages, optionally filtered by property."""
        ...

    def list_expiring_mortgages(self, months: int = 6) -> list[Mortgage]:
        """List mortgages expiring within specified months."""
        ...

    def update_mortgage(self, mortgage: Mortgage) -> None:
        """Update an existing mortgage."""
        ...

    # Tenant operations
    def add_tenant(self, tenant: Tenant) -> None:
        """Add a tenant to the registry."""
        ...

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        """Get tenant by ID."""
        ...

    def list_tenants(self, property_id: str | None = None, active_only: bool = True) -> list[Tenant]:
        """List tenants, optionally filtered by property and active status."""
        ...

    def update_tenant(self, tenant: Tenant) -> None:
        """Update an existing tenant."""
        ...

    # Contact operations
    def add_contact(self, contact: Contact) -> None:
        """Add a contact to the registry."""
        ...

    def get_contact(self, contact_id: str) -> Contact | None:
        """Get contact by ID."""
        ...

    def list_contacts(self, contact_type: ContactType | None = None) -> list[Contact]:
        """List contacts, optionally filtered by type."""
        ...

    def update_contact(self, contact: Contact) -> None:
        """Update an existing contact."""
        ...

    # Maintenance operations
    def add_maintenance_request(self, request: MaintenanceRequest) -> None:
        """Add a maintenance request."""
        ...

    def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        """Get maintenance request by ID."""
        ...

    def list_maintenance_requests(
        self,
        property_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]:
        """List maintenance requests with optional filters."""
        ...

    def update_maintenance_request(self, request: MaintenanceRequest) -> None:
        """Update an existing maintenance request."""
        ...


class InMemoryPropertyRegistry:
    """In-memory implementation of PropertyRegistry."""

    def __init__(self):
        self._properties: dict[str, Property] = {}
        self._mortgages: dict[str, Mortgage] = {}
        self._tenants: dict[str, Tenant] = {}
        self._contacts: dict[str, Contact] = {}
        self._maintenance: dict[str, MaintenanceRequest] = {}

    # Property operations
    def add_property(self, prop: Property) -> None:
        self._properties[prop.id] = prop

    def get_property(self, property_id: str) -> Property | None:
        return self._properties.get(property_id)

    def list_properties(self, status: PropertyStatus | None = None) -> list[Property]:
        props = list(self._properties.values())
        if status:
            props = [p for p in props if p.status == status]
        return sorted(props, key=lambda p: p.created_at, reverse=True)

    def update_property(self, prop: Property) -> None:
        if prop.id in self._properties:
            self._properties[prop.id] = prop

    def delete_property(self, property_id: str) -> bool:
        if property_id in self._properties:
            del self._properties[property_id]
            return True
        return False

    # Mortgage operations
    def add_mortgage(self, mortgage: Mortgage) -> None:
        self._mortgages[mortgage.id] = mortgage

    def get_mortgage(self, mortgage_id: str) -> Mortgage | None:
        return self._mortgages.get(mortgage_id)

    def list_mortgages(self, property_id: str | None = None) -> list[Mortgage]:
        mortgages = list(self._mortgages.values())
        if property_id:
            mortgages = [m for m in mortgages if m.property_id == property_id]
        return sorted(mortgages, key=lambda m: m.created_at, reverse=True)

    def list_expiring_mortgages(self, months: int = 6) -> list[Mortgage]:
        return [m for m in self._mortgages.values() if m.is_expiring_soon(months)]

    def update_mortgage(self, mortgage: Mortgage) -> None:
        if mortgage.id in self._mortgages:
            self._mortgages[mortgage.id] = mortgage

    # Tenant operations
    def add_tenant(self, tenant: Tenant) -> None:
        self._tenants[tenant.id] = tenant

    def get_tenant(self, tenant_id: str) -> Tenant | None:
        return self._tenants.get(tenant_id)

    def list_tenants(self, property_id: str | None = None, active_only: bool = True) -> list[Tenant]:
        tenants = list(self._tenants.values())
        if property_id:
            tenants = [t for t in tenants if t.property_id == property_id]
        if active_only:
            tenants = [t for t in tenants if t.is_active]
        return sorted(tenants, key=lambda t: t.created_at, reverse=True)

    def update_tenant(self, tenant: Tenant) -> None:
        if tenant.id in self._tenants:
            self._tenants[tenant.id] = tenant

    # Contact operations
    def add_contact(self, contact: Contact) -> None:
        self._contacts[contact.id] = contact

    def get_contact(self, contact_id: str) -> Contact | None:
        return self._contacts.get(contact_id)

    def list_contacts(self, contact_type: ContactType | None = None) -> list[Contact]:
        contacts = list(self._contacts.values())
        if contact_type:
            contacts = [c for c in contacts if c.contact_type == contact_type]
        return sorted(contacts, key=lambda c: c.name)

    def update_contact(self, contact: Contact) -> None:
        if contact.id in self._contacts:
            self._contacts[contact.id] = contact

    # Maintenance operations
    def add_maintenance_request(self, request: MaintenanceRequest) -> None:
        self._maintenance[request.id] = request

    def get_maintenance_request(self, request_id: str) -> MaintenanceRequest | None:
        return self._maintenance.get(request_id)

    def list_maintenance_requests(
        self,
        property_id: str | None = None,
        status: MaintenanceStatus | None = None,
    ) -> list[MaintenanceRequest]:
        requests = list(self._maintenance.values())
        if property_id:
            requests = [r for r in requests if r.property_id == property_id]
        if status:
            requests = [r for r in requests if r.status == status]
        return sorted(requests, key=lambda r: r.reported_date, reverse=True)

    def update_maintenance_request(self, request: MaintenanceRequest) -> None:
        if request.id in self._maintenance:
            self._maintenance[request.id] = request
