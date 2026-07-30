from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from business_agent.memory.models import MemoryPayload, MemoryQueryInput, MemoryRecord
from business_agent.property.models import MaintenanceRequest, MaintenanceStatus, Mortgage, PropertyStatus, Tenant


@pytest.mark.e2e
def test_telegram_ask_reset_and_follow_up_flow(fast_e2e_harness) -> None:
    harness = fast_e2e_harness
    harness.memory_store.upsert(
        [
            MemoryRecord(
                id="memo-1",
                text="The tenancy agreement for 133 Bowland Drive has a no pet clause.",
                payload=MemoryPayload(
                    event_date=date(2026, 1, 10),
                    ingested_at=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
                    effective_date=datetime(2026, 1, 10, 0, 0, tzinfo=timezone.utc),
                    source_type="txt",
                    source_uri="/tmp/lease.txt",
                    archived_file_path=None,
                    record_type="memorized_text",
                    summary="pet clause",
                ),
            )
        ]
    )

    ask_update = {
        "message": {
            "chat": {"id": 101},
            "text": "/ask from=2026-01-01 to=2026-01-31 lease clause for 133 Bowland Drive",
        }
    }
    response = harness.client.post("/telegram/webhook", json=ask_update)
    assert response.status_code == 200
    assert response.json()["ok"] is True

    follow_up = {"message": {"chat": {"id": 101}, "text": "What about the pet clause?"}}
    response = harness.client.post("/telegram/webhook", json=follow_up)
    assert response.status_code == 200
    assert response.json()["ok"] is True

    reset_update = {"message": {"chat": {"id": 101}, "text": "/reset"}}
    response = harness.client.post("/telegram/webhook", json=reset_update)
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert harness.conversation_store.history[101] == []


@pytest.mark.e2e
def test_document_ingest_flow_persists_summary_and_chunks_and_exposes_api_query(fast_e2e_harness, tmp_path) -> None:
    harness = fast_e2e_harness
    docs_dir = Path(harness.settings.ingestion_allowed_local_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    document_path = docs_dir / "lease.txt"
    document_path.write_text("The tenancy agreement for 133 Bowland Drive has a no pet clause.", encoding="utf-8")

    result = harness.orchestrator.ingest_document_now(
        source_uri=str(document_path),
        event_date=date(2026, 1, 15),
        requester_id=202,
    )

    assert result.chunk_count >= 1
    assert result.records_written >= 2

    api_response = harness.client.post(
        "/api/memory/query",
        json={"query": "pet clause", "date_from": "2026-01-01", "date_to": "2026-01-31", "top_k": 5},
    )
    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["matches"]


@pytest.mark.e2e
def test_date_range_retrieval_uses_effective_dates_for_boundaries(fast_e2e_harness) -> None:
    harness = fast_e2e_harness
    harness.memory_store.upsert(
        [
            MemoryRecord(
                id="before",
                text="older record",
                payload=MemoryPayload(
                    event_date=date(2025, 12, 31),
                    ingested_at=datetime(2025, 12, 31, 10, 0, tzinfo=timezone.utc),
                    effective_date=datetime(2025, 12, 31, 0, 0, tzinfo=timezone.utc),
                    source_type="txt",
                    source_uri="/tmp/older.txt",
                    archived_file_path=None,
                    record_type="chunk",
                    summary="older",
                ),
            ),
            MemoryRecord(
                id="inside",
                text="matching record",
                payload=MemoryPayload(
                    event_date=date(2026, 1, 15),
                    ingested_at=datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc),
                    effective_date=datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc),
                    source_type="txt",
                    source_uri="/tmp/inside.txt",
                    archived_file_path=None,
                    record_type="chunk",
                    summary="inside",
                ),
            ),
            MemoryRecord(
                id="after",
                text="later record",
                payload=MemoryPayload(
                    event_date=date(2026, 2, 1),
                    ingested_at=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
                    effective_date=datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc),
                    source_type="txt",
                    source_uri="/tmp/later.txt",
                    archived_file_path=None,
                    record_type="chunk",
                    summary="later",
                ),
            ),
        ]
    )

    matches = harness.orchestrator.query_memory(
        request=MemoryQueryInput(
            query="record",
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            top_k=10,
        )
    )
    assert len(matches) == 1
    assert matches[0].id == "inside"


@pytest.mark.e2e
def test_property_flow_and_portfolio_summary_are_consistent(fast_e2e_harness) -> None:
    harness = fast_e2e_harness

    create_property_response = harness.client.post(
        "/api/properties",
        json={
            "id": "prop-001",
            "address": "133 Bowland Drive",
            "status": "owned",
            "purchase_price": 300000,
            "current_value": 320000,
            "bedrooms": 3,
            "bathrooms": 2,
            "postcode": "SW1A 1AA",
            "notes": "Newly added property",
        },
    )
    assert create_property_response.status_code == 201

    list_properties_response = harness.client.get("/api/properties")
    assert list_properties_response.status_code == 200
    properties = list_properties_response.json()
    assert any(item["id"] == "prop-001" for item in properties)

    property_reply = harness.orchestrator.handle_telegram_message_with_ui(chat_id=301, message_text="/property show prop-001")
    assert "133 Bowland Drive" in property_reply.text

    mortgage = Mortgage(
        id="mort-001",
        property_id="prop-001",
        lender="Metro Bank",
        principal=250000,
        interest_rate=4.5,
        term_months=300,
        start_date=date(2020, 1, 1),
        monthly_payment=1200,
        end_date=date(2026, 8, 1),
    )
    harness.property_registry.add_mortgage(mortgage)

    tenant = Tenant(
        id="tenant-001",
        property_id="prop-001",
        name="Alicia Smith",
        email="alicia@example.com",
        phone="07700000000",
        lease_start=date(2025, 1, 1),
        lease_end=date(2027, 1, 1),
        monthly_rent=1500,
        deposit=3000,
    )
    harness.property_registry.add_tenant(tenant)
    maintenance = MaintenanceRequest(
        id="maint-001",
        property_id="prop-001",
        reported_date=date(2026, 1, 10),
        description="Boiler replacement",
        status=MaintenanceStatus.REPORTED,
    )
    harness.property_registry.add_maintenance_request(maintenance)

    expiring_response = harness.client.get("/api/mortgages/expiring?months=6")
    assert expiring_response.status_code == 200
    assert len(expiring_response.json()) == 1

    portfolio_response = harness.client.get("/api/portfolio/summary")
    assert portfolio_response.status_code == 200
    summary = portfolio_response.json()
    assert summary["total_properties"] == 1
    assert summary["owned_count"] == 1
    assert summary["under_offer_count"] == 0
    assert summary["total_monthly_rent"] == 1500.0
    assert summary["active_tenants"] == 1
    assert summary["open_maintenance_count"] == 1
    assert summary["expiring_mortgages_count"] == 1


@pytest.mark.e2e
def test_sql_read_only_api_returns_rows_and_rejects_unsafe_table(fast_e2e_harness) -> None:
    harness = fast_e2e_harness

    response = harness.client.post(
        "/api/sql/read",
        json={"table": "properties", "columns": ["id", "address"], "filters": {"status": "owned"}, "limit": 5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["address"] == "133 Bowland Drive"

    unsafe_response = harness.client.post(
        "/api/sql/read",
        json={"table": "drop_table", "columns": ["id"], "filters": {}, "limit": 5},
    )
    assert unsafe_response.status_code == 403
    assert "Table not allowed" in unsafe_response.json()["detail"]


@pytest.mark.e2e
def test_telegram_webhook_rejects_invalid_secret(fast_e2e_harness) -> None:
    harness = fast_e2e_harness
    harness.settings.telegram_webhook_secret = "super-secret"

    response = harness.client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 500}, "text": "hello"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Telegram webhook secret."
