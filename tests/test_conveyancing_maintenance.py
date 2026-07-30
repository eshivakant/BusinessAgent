from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from business_agent.conveyancing.service import ConveyancingService
from business_agent.maintenance.service import MaintenanceService
from business_agent.property.models import Property, PropertyStatus


@pytest.mark.unit
def test_conveyancing_stage_progression_and_overdue_logic() -> None:
    property_registry: Any = type("Registry", (), {"get_property": lambda self, property_id: Property(id=property_id, address="123 Test", purchase_date=None, purchase_price=None, current_value=None, status=PropertyStatus.OWNED)})()
    service = ConveyancingService(property_registry=property_registry)
    transaction = service.create_transaction("prop-1", "purchase")

    advanced = service.advance_stage(transaction.id, "solicitor_instructed")
    assert advanced.stage == "solicitor_instructed"

    overdue = service.list_overdue(now=date.today() + timedelta(days=8))
    assert overdue[0]["transaction_id"] == transaction.id


@pytest.mark.unit
def test_mortgage_offer_comparison_and_total_cost() -> None:
    property_registry: Any = type("Registry", (), {"get_property": lambda self, property_id: Property(id=property_id, address="123 Test", purchase_date=None, purchase_price=None, current_value=None, status=PropertyStatus.OWNED)})()
    service = ConveyancingService(property_registry=property_registry)
    transaction = service.create_transaction("prop-1", "purchase")

    # create through direct offer entries to avoid filesystem dependence
    from business_agent.conveyancing.models import MortgageOffer

    offer = MortgageOffer(
        id="offer-1",
        transaction_id=transaction.id,
        lender_name="Halifax",
        loan_amount=Decimal("200000"),
        initial_rate=Decimal("4.5"),
        monthly_payment=Decimal("1100"),
        arrangement_fee=Decimal("500"),
    )
    service._mortgage_offers[offer.id] = offer
    second_offer = MortgageOffer(
        id="offer-2",
        transaction_id=transaction.id,
        lender_name="NatWest",
        loan_amount=Decimal("200000"),
        initial_rate=Decimal("3.9"),
        monthly_payment=Decimal("1200"),
        arrangement_fee=Decimal("250"),
    )
    service._mortgage_offers[second_offer.id] = second_offer

    comparison = service.compare_mortgage_offers(transaction.id)
    assert len(comparison) == 2
    assert comparison[0]["recommended"] or comparison[1]["recommended"]


@pytest.mark.unit
def test_maintenance_quote_comparison_and_spend_rollup() -> None:
    property_registry: Any = type("Registry", (), {"get_property": lambda self, property_id: Property(id=property_id, address="123 Test", purchase_date=None, purchase_price=None, current_value=None, status=PropertyStatus.OWNED)})()
    service = MaintenanceService(property_registry=property_registry)
    job = service.create_job("prop-1", "Boiler fix", "Fix boiler")
    service._documents["doc-1"] = type("Doc", (), {"job_id": job.id, "contractor_name": "A", "amount": Decimal("100"), "vat_amount": Decimal("20"), "document_subtype": "quote", "id": "doc-1"})()
    service._documents["doc-2"] = type("Doc", (), {"job_id": job.id, "contractor_name": "B", "amount": Decimal("80"), "vat_amount": Decimal("10"), "document_subtype": "quote", "id": "doc-2"})()
    job.quote_amount = Decimal("100")
    job.invoice_amount = Decimal("120")
    service._jobs[job.id] = job

    comparison = service.compare_quotes(job.id)
    assert comparison[0]["recommended"] or comparison[1]["recommended"]
    spend = service.spend("prop-1", year=datetime.now().year)
    assert spend["total_spend"] == 120.0


@pytest.mark.unit
def test_compliance_reminders_are_deduplicated() -> None:
    property_registry: Any = type("Registry", (), {"get_property": lambda self, property_id: Property(id=property_id, address="123 Test", purchase_date=None, purchase_price=None, current_value=None, status=PropertyStatus.OWNED)})()
    service = MaintenanceService(property_registry=property_registry)
    certificate = service.add_certificate("prop-1", "gas_safety", expiry_date=date.today() + timedelta(days=30))
    reminders = service.reminders_for_certificate(certificate, now=date.today())
    assert reminders
    service.mark_reminder_sent(certificate.id, reminders[0])
    assert service.reminders_for_certificate(certificate, now=date.today()) == []


@pytest.mark.e2e
def test_orchestrator_dispatches_conveyancing_and_maintenance_commands(fast_e2e_harness: Any) -> None:
    property = Property(
        id="prop-1",
        address="123 Example",
        purchase_date=date(2024, 1, 1),
        purchase_price=Decimal("250000"),
        current_value=Decimal("300000"),
        status=PropertyStatus.OWNED,
    )
    fast_e2e_harness.property_registry.add_property(property)

    reply = fast_e2e_harness.orchestrator.handle_telegram_message(1, "/conveyancing new purchase prop-1")
    assert "Created" in reply
    reply = fast_e2e_harness.orchestrator.handle_telegram_message(1, "/maintenance new prop-1")
    assert "Created job" in reply


@pytest.mark.e2e
def test_api_conveyancing_and_maintenance_flow(fast_e2e_harness: Any, tmp_path: Path) -> None:
    property = Property(
        id="prop-2",
        address="456 Example",
        purchase_date=date(2024, 1, 1),
        purchase_price=Decimal("250000"),
        current_value=Decimal("300000"),
        status=PropertyStatus.OWNED,
    )
    fast_e2e_harness.property_registry.add_property(property)

    response = fast_e2e_harness.client.post(
        "/api/conveyancing",
        json={"property_id": "prop-2", "transaction_type": "purchase"},
        headers={"X-API-Token": ""},
    )
    assert response.status_code == 200
    transaction_id = response.json()["id"]

    patch_response = fast_e2e_harness.client.patch(
        f"/api/conveyancing/{transaction_id}",
        json={"stage": "solicitor_instructed"},
        headers={"X-API-Token": ""},
    )
    assert patch_response.status_code == 200

    offer_path = tmp_path / "offer.txt"
    offer_path.write_text("Lender Name: Halifax\nLoan Amount: £200,000\nInitial Rate: 4.5%\nMonthly Payment: £1,100\nArrangement Fee: £500\nOffer Expiry: 2027-01-01")
    upload_response = fast_e2e_harness.client.post(
        f"/api/conveyancing/{transaction_id}/documents",
        files={"file": ("offer.txt", offer_path.read_bytes(), "text/plain")},
        data={"document_subtype": "mortgage_offer"},
        headers={"X-API-Token": ""},
    )
    assert upload_response.status_code == 200

    compare_response = fast_e2e_harness.client.get(
        f"/api/conveyancing/{transaction_id}/mortgage-offers/compare",
        headers={"X-API-Token": ""},
    )
    assert compare_response.status_code == 200
    assert compare_response.json()["items"]

    maintenance_response = fast_e2e_harness.client.post(
        "/api/maintenance",
        json={"property_id": "prop-2", "title": "Leak", "description": "Leak under sink"},
        headers={"X-API-Token": ""},
    )
    assert maintenance_response.status_code == 200
    job_id = maintenance_response.json()["id"]

    quote_path = tmp_path / "quote.txt"
    quote_path.write_text("Contractor: Acme\nAmount: £100\nVAT: £20")
    quote_response = fast_e2e_harness.client.post(
        f"/api/maintenance/{job_id}/documents",
        files={"file": ("quote.txt", quote_path.read_bytes(), "text/plain")},
        data={"document_subtype": "quote"},
        headers={"X-API-Token": ""},
    )
    assert quote_response.status_code == 200

    spend_response = fast_e2e_harness.client.get(
        "/api/maintenance/spend?property_id=prop-2",
        headers={"X-API-Token": ""},
    )
    assert spend_response.status_code == 200
    assert spend_response.json()["property_id"] == "prop-2"
