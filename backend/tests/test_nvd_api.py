"""API integration tests for the cached NVD digest (no live network)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from models.nvd import NVDCVE, NVDDigestState
from models.audit_log import AuditLog
from services.nvd_service import NVDService


NOW = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture()
def client(api_app):
    """Wire the owned router without modifying the shared application module."""
    from api.nvd import router
    from auth import get_current_user
    from config import settings

    if not any(getattr(route, "path", None) == "/api/nvd/digest"
               for route in api_app.routes):
        api_app.include_router(
            router,
            prefix=settings.API_V1_PREFIX,
            dependencies=[Depends(get_current_user)],
        )
    return TestClient(api_app, raise_server_exceptions=False)


@pytest.fixture()
def auditor_headers(db):
    from auth import create_access_token
    from conftest import make_user

    user = make_user(db, username="auditor", role="auditor")
    return {"Authorization": f"Bearer {create_access_token(user.id, user.username)}"}


def cached_digest(db) -> None:
    db.add(NVDDigestState(
        id=1,
        window_start=NOW - timedelta(days=1),
        window_end=NOW,
        last_attempt_at=NOW,
        last_success_at=NOW,
        next_refresh_at=datetime(2999, 1, 1, tzinfo=timezone.utc),
        item_count=1,
    ))
    db.add(NVDCVE(
        cve_id="CVE-2026-0001",
        cvss_score=9.8,
        cvss_severity="CRITICAL",
        cvss_version="3.1",
        published_at=NOW - timedelta(hours=1),
        last_modified_at=NOW - timedelta(hours=1),
        description="Critical cached vulnerability",
        affected_products=["cpe:2.3:a:example:product:*:*:*:*:*:*:*:*"],
        nvd_url="https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
        last_seen_at=NOW,
    ))
    db.commit()


def test_get_digest_returns_cached_items_without_network(client, db, admin_headers, monkeypatch):
    cached_digest(db)

    def no_network(**_kwargs):
        raise AssertionError("digest reads must use the SQL cache")

    monkeypatch.setattr("services.nvd_service.httpx.Client", no_network)
    response = client.get("/api/nvd/digest", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "fresh"
    assert body["refreshed"] is False
    assert body["item_count"] == 1
    assert body["items"][0]["cve_id"] == "CVE-2026-0001"
    assert body["items"][0]["published_at"] == "2026-11-06T11:00:00Z"


def test_get_status_omits_items(client, db, admin_headers):
    cached_digest(db)

    response = client.get("/api/nvd/status", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "fresh"
    assert body["item_count"] == 1
    assert body["refresh_interval_hours"] == 24
    assert body["lookback_days"] == 1
    assert "items" not in body


def test_manual_refresh_forces_fetch_while_schedule_is_disabled(
    client, db, admin_headers, monkeypatch,
):
    db.add(NVDDigestState(id=1, enabled=False, refresh_interval_hours=12))
    db.commit()
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={
            "totalResults": 0,
            "vulnerabilities": [],
        })

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        kwargs["transport"] = transport
        return real_client(**kwargs)

    monkeypatch.setattr("services.nvd_service.httpx.Client", client_factory)
    response = client.post("/api/nvd/refresh", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["refreshed"] is True
    assert body["status"] == "fresh"
    assert body["next_refresh_at"] is None
    assert len(requests) == 1
    assert requests[0].url.params["cvssV3Severity"] == "CRITICAL"
    assert db.query(NVDDigestState).one().last_success_at is not None


def test_manual_refresh_requires_admin(
    client, db, auditor_headers, monkeypatch,
):
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={
        "totalResults": 0,
        "vulnerabilities": [],
    }))
    def client_factory(**kwargs):
        kwargs["transport"] = transport
        return real_client(**kwargs)

    monkeypatch.setattr("services.nvd_service.httpx.Client", client_factory)

    response = client.post("/api/nvd/refresh", headers=auditor_headers)

    assert response.status_code == 403


def test_update_schedule_persists_validated_fields_and_writes_audit(
    client, db, admin_headers,
):
    changes = {
        "enabled": False,
        "refresh_interval_hours": 12,
        "lookback_days": 7,
        "max_items": 25,
        "include_cvss_v4": True,
    }

    response = client.put("/api/nvd/schedule", headers=admin_headers, json=changes)

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["refresh_interval_hours"] == 12
    assert body["lookback_days"] == 7
    assert body["max_items"] == 25
    assert body["include_cvss_v4"] is True
    assert body["next_refresh_at"] is None
    assert "items" not in body

    state = db.query(NVDDigestState).one()
    assert state.lookback_days == 7
    entry = db.query(AuditLog).filter(
        AuditLog.action == "nvd.schedule.updated",
    ).one()
    assert entry.actor_username == "admin"
    assert entry.resource_type == "nvd_digest_state"
    assert entry.resource_id == "1"
    assert entry.detail["fields"] == sorted(changes)


@pytest.mark.parametrize("payload", [
    {"refresh_interval_hours": 0},
    {"refresh_interval_hours": 721},
    {"lookback_days": 0},
    {"lookback_days": 121},
    {"max_items": 0},
    {"max_items": 5001},
    {"refresh_interval_hours": "often"},
    {"refresh_interval_hours": None},
    {"unexpected": True},
])
def test_update_schedule_rejects_invalid_input(
    client, db, admin_headers, payload,
):
    response = client.put("/api/nvd/schedule", headers=admin_headers, json=payload)

    assert response.status_code == 422
    assert db.query(NVDDigestState).count() == 0
    assert db.query(AuditLog).filter(
        AuditLog.action == "nvd.schedule.updated",
    ).count() == 0


def test_refresh_failure_returns_stale_cache_without_secrets_or_disabled_schedule(
    client, db, admin_headers, monkeypatch,
):
    cached_digest(db)
    state = db.query(NVDDigestState).one()
    state.enabled = False
    db.commit()
    secret = "super-secret-nvd-key"
    monkeypatch.setenv("NVD_API_KEY", secret)
    monkeypatch.setattr("services.nvd_service.time.sleep", lambda _seconds: None)
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503)

    real_client = httpx.Client
    transport = httpx.MockTransport(handler)

    def client_factory(**kwargs):
        kwargs["transport"] = transport
        return real_client(**kwargs)

    monkeypatch.setattr("services.nvd_service.httpx.Client", client_factory)
    response = client.post("/api/nvd/refresh", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "stale"
    assert body["stale"] is True
    assert body["refreshed"] is True
    assert "HTTP 503" in body["error"]
    assert body["items"][0]["cve_id"] == "CVE-2026-0001"
    assert body["next_refresh_at"] is None
    assert len(requests) == 4
    assert secret not in response.text


def test_nvd_key_is_encrypted_and_never_returned(client, db, admin_headers, monkeypatch):
    monkeypatch.delenv("NVD_API_KEY", raising=False)
    from models.platform_settings import PlatformSettings
    from utils.crypto import decrypt_secret

    secret = "nvd-key-from-secret-store"
    response = client.put("/api/nvd/key", headers=admin_headers, json={"api_key": secret})
    assert response.status_code == 200
    assert response.json()["api_key_configured"] is True
    assert response.json()["api_key_source"] == "encrypted"
    assert secret not in response.text

    stored = db.query(PlatformSettings).filter_by(key="nvd_api_key").one()
    assert stored.value != secret
    assert decrypt_secret(stored.value) == secret
    assert NVDService(db).api_key == secret

    status = client.get("/api/nvd/status", headers=admin_headers)
    assert status.json()["api_key_configured"] is True
    assert secret not in status.text

    deleted = client.delete("/api/nvd/key", headers=admin_headers)
    assert deleted.status_code == 200
    assert deleted.json()["api_key_configured"] is False
    assert db.query(PlatformSettings).filter_by(key="nvd_api_key").count() == 0


def test_nvd_key_requires_admin_and_valid_input(client, auditor_headers, admin_headers):
    assert client.put("/api/nvd/key", headers=auditor_headers,
                      json={"api_key": "not-authorized"}).status_code == 403
    assert client.delete("/api/nvd/key", headers=auditor_headers).status_code == 403
    assert client.put("/api/nvd/key", headers=admin_headers,
                      json={"api_key": ""}).status_code == 422
