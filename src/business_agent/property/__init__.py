"""Property management domain for buy-to-let business."""

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
from business_agent.property.registry import InMemoryPropertyRegistry, PropertyRegistry

__all__ = [
    "Property",
    "PropertyStatus",
    "Mortgage",
    "Tenant",
    "Contact",
    "ContactType",
    "MaintenanceRequest",
    "MaintenanceStatus",
    "PropertyRegistry",
    "InMemoryPropertyRegistry",
]
