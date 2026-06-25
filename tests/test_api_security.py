from __future__ import annotations

import pytest
from fastapi import HTTPException

from business_agent.api import security


def test_verify_internal_api_token_allows_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: type("S", (), {"internal_api_token": None})())
    security.verify_internal_api_token(x_api_token=None)


def test_verify_internal_api_token_rejects_invalid(monkeypatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: type("S", (), {"internal_api_token": "secret"})())
    with pytest.raises(HTTPException) as exc_info:
        security.verify_internal_api_token(x_api_token="wrong")
    assert exc_info.value.status_code == 401


def test_verify_internal_api_token_accepts_valid(monkeypatch) -> None:
    monkeypatch.setattr(security, "get_settings", lambda: type("S", (), {"internal_api_token": "secret"})())
    security.verify_internal_api_token(x_api_token="secret")
