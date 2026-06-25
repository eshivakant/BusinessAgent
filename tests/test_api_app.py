from __future__ import annotations

from fastapi.testclient import TestClient

from business_agent.api import app as app_module


def test_create_app_startup_ensures_memory_collection(monkeypatch) -> None:
    state = {"called": False}

    class FakeMemoryStore:
        def ensure_collection(self) -> None:
            state["called"] = True

    monkeypatch.setattr(app_module, "get_memory_store", lambda: FakeMemoryStore())

    app = app_module.create_app()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
    assert state["called"] is True
