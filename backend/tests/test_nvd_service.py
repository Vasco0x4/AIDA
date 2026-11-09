"""Hermetic tests for the NVD critical-CVE digest service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

import services.nvd_service as nvd_module
from models.nvd import NVDCVE, NVDDigestState
from services.nvd_service import NVD_API_URL, NVDService


NOW = datetime(2026, 11, 6, 12, 0, 0, tzinfo=timezone.utc)
CPE = "cpe:2.3:a:apache:http_server:2.4.49:*:*:*:*:*:*:*"


def vulnerability(cve_id="CVE-2026-0001", *, published="2026-11-06T10:30:00.000Z"):
    return {
        "cve": {
            "id": cve_id,
            "published": published,
            "lastModified": published,
            "descriptions": [
                {"lang": "es", "value": "descripción"},
                {"lang": "en", "value": "  Apache   allows remote code execution.  "},
            ],
            "metrics": {
                "cvssMetricV31": [
                    {
                        "type": "Primary",
                        "cvssData": {
                            "version": "3.1",
                            "baseScore": 9.8,
                            "baseSeverity": "CRITICAL",
                        },
                    }
                ]
            },
            "configurations": [
                {
                    "nodes": [
                        {
                            "cpeMatch": [
                                {"vulnerable": True, "criteria": CPE},
                                {"vulnerable": False, "criteria": "cpe:2.3:a:not:affected:*:*:*:*:*:*:*:*"},
                            ]
                        }
                    ]
                }
            ],
        }
    }


def payload(*items, total=None, start=0):
    return {
        "resultsPerPage": len(items),
        "startIndex": start,
        "totalResults": len(items) if total is None else total,
        "vulnerabilities": list(items),
    }


def service(db, handler, **overrides):
    options = {
        "transport": httpx.MockTransport(handler),
        "now": lambda: NOW,
        "sleep": lambda _seconds: None,
        "min_request_interval": 0,
    }
    options.update(overrides)
    return NVDService(db, **options)


def test_refresh_fetches_critical_24h_window_and_persists_digest(db):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload(vulnerability()))

    result = service(db, handler).refresh(force=True)

    assert len(requests) == 1
    request = requests[0]
    assert str(request.url).startswith(NVD_API_URL + "?")
    assert request.url.params["cvssV3Severity"] == "CRITICAL"
    assert request.url.params["pubStartDate"] == "2026-11-05T12:00:00.000Z"
    assert request.url.params["pubEndDate"] == "2026-11-06T12:00:00.000Z"
    assert request.url.params["startIndex"] == "0"

    assert result["status"] == "fresh"
    assert result["error"] is None
    assert result["item_count"] == 1
    item = result["items"][0]
    assert item == {
        "cve_id": "CVE-2026-0001",
        "cvss_score": 9.8,
        "cvss_severity": "CRITICAL",
        "cvss_version": "3.1",
        "published_at": datetime(2026, 11, 6, 10, 30, tzinfo=timezone.utc),
        "description": "Apache allows remote code execution.",
        "affected_products": [CPE],
        "nvd_url": "https://nvd.nist.gov/vuln/detail/CVE-2026-0001",
    }

    row = db.query(NVDCVE).one()
    assert row.cve_id == "CVE-2026-0001"
    state = db.query(NVDDigestState).one()
    assert state.last_success_at == NOW
    assert state.next_refresh_at == NOW + timedelta(hours=24)


def test_refresh_paginates_until_total_results_using_configured_limits(db):
    db.add(NVDDigestState(id=1, lookback_days=2, max_items=3))
    db.commit()
    requests = []

    def handler(request):
        requests.append(request)
        start = int(request.url.params["startIndex"])
        if start == 0:
            return httpx.Response(200, json=payload(
                vulnerability("CVE-2026-0001"), vulnerability("CVE-2026-0002"),
                total=3, start=0,
            ))
        if start == 2:
            return httpx.Response(200, json=payload(
                vulnerability("CVE-2026-0003"), total=3, start=2,
            ))
        raise AssertionError(f"unexpected startIndex {start}")

    result = service(db, handler).refresh(force=True)

    assert [r.url.params["startIndex"] for r in requests] == ["0", "2"]
    assert all(r.url.params["resultsPerPage"] == "3" for r in requests)
    assert requests[0].url.params["pubStartDate"] == "2026-11-04T12:00:00.000Z"
    assert result["item_count"] == 3
    assert [item["cve_id"] for item in result["items"]] == [
        "CVE-2026-0001", "CVE-2026-0002", "CVE-2026-0003",
    ]


def test_optional_cvss_v4_query_is_merged_and_deduplicated(db):
    db.add(NVDDigestState(id=1, include_cvss_v4=True))
    db.commit()
    requests = []

    def handler(request):
        requests.append(request)
        if "cvssV3Severity" in request.url.params:
            return httpx.Response(200, json=payload(vulnerability("CVE-2026-0001")))
        assert request.url.params["cvssV4Severity"] == "CRITICAL"
        return httpx.Response(200, json=payload(
            vulnerability("CVE-2026-0001"), vulnerability("CVE-2026-0002"),
        ))

    result = service(db, handler).refresh(force=True)

    assert len(requests) == 2
    assert result["item_count"] == 2
    assert {item["cve_id"] for item in result["items"]} == {
        "CVE-2026-0001", "CVE-2026-0002",
    }
    assert db.query(NVDCVE).count() == 2


def test_retry_is_bounded_exponential_and_honors_retry_after(db):
    attempts = []
    sleeps = []

    def handler(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        if len(attempts) == 2:
            return httpx.Response(503)
        return httpx.Response(200, json=payload(vulnerability()))

    result = service(
        db, handler, sleep=sleeps.append,
        max_retries=2, retry_base_delay=1, retry_max_delay=8,
    ).refresh(force=True)

    assert len(attempts) == 3
    assert sleeps == [7, 2]
    assert result["status"] == "fresh"


def test_failed_refresh_returns_persistent_stale_cache_with_explicit_freshness(db):
    clock = [NOW]
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=payload(vulnerability()))
        return httpx.Response(503)

    svc = service(db, handler, now=lambda: clock[0], max_retries=0)
    fresh = svc.refresh(force=True)
    clock[0] = NOW + timedelta(hours=2)
    failed = svc.refresh(force=True)

    assert fresh["status"] == "fresh"
    assert failed["status"] == "stale"
    assert failed["stale"] is True
    assert "HTTP 503" in failed["error"]
    assert failed["last_success_at"] == NOW
    assert failed["last_attempt_at"] == clock[0]
    assert failed["cache_age_seconds"] == 7200
    assert failed["next_refresh_at"] == clock[0] + timedelta(hours=1)
    assert [item["cve_id"] for item in failed["items"]] == ["CVE-2026-0001"]

    # A new service instance reads the same SQL cache and performs no request.
    cached = NVDService(db, now=lambda: clock[0]).get_digest()
    assert cached["status"] == "stale"
    assert cached["error"] == failed["error"]
    assert [item["cve_id"] for item in cached["items"]] == ["CVE-2026-0001"]


def test_refresh_if_due_uses_daily_schedule_and_force_bypasses_it(db):
    clock = [NOW]
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload(vulnerability()))

    svc = service(db, handler, now=lambda: clock[0])
    svc.refresh(force=True)

    clock[0] = NOW + timedelta(hours=23)
    skipped = svc.refresh_if_due()
    assert skipped["refreshed"] is False
    assert skipped["status"] == "fresh"
    assert len(calls) == 1

    clock[0] = NOW + timedelta(hours=24)
    due = svc.refresh_if_due()
    assert due["refreshed"] is True
    assert len(calls) == 2

    forced = svc.refresh(force=True)
    assert forced["refreshed"] is True
    assert len(calls) == 3


def test_http_policy_throttles_pages_sets_timeout_and_keeps_key_out_of_query(db, monkeypatch):
    monkeypatch.setenv("NVD_API_KEY", "super-secret-nvd-key")
    clock = [100.0]
    sleeps = []
    requests = []
    timeouts = []
    real_client = httpx.Client

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    def client_factory(**kwargs):
        timeouts.append(kwargs["timeout"])
        return real_client(**kwargs)

    monkeypatch.setattr(nvd_module.httpx, "Client", client_factory)

    def handler(request):
        requests.append(request)
        start = int(request.url.params["startIndex"])
        if start == 0:
            return httpx.Response(200, json=payload(
                vulnerability("CVE-2026-0001"), total=2, start=0,
            ))
        return httpx.Response(200, json=payload(
            vulnerability("CVE-2026-0002"), total=2, start=1,
        ))

    result = service(
        db, handler, timeout=12.5, min_request_interval=6,
        monotonic=lambda: clock[0], sleep=fake_sleep,
    ).refresh(force=True)

    assert result["item_count"] == 2
    assert sleeps == [6]
    assert timeouts == [12.5, 12.5]
    assert all(r.headers["apiKey"] == "super-secret-nvd-key" for r in requests)
    assert all("super-secret-nvd-key" not in str(r.url) for r in requests)


def test_schedule_update_persists_and_disables_automatic_refresh(db):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload())

    svc = service(db, handler)
    status = svc.update_schedule(
        enabled=False,
        refresh_interval_hours=12,
        lookback_days=7,
        max_items=25,
        include_cvss_v4=True,
    )

    assert status["enabled"] is False
    assert status["refresh_interval_hours"] == 12
    assert status["lookback_days"] == 7
    assert status["max_items"] == 25
    assert status["include_cvss_v4"] is True
    assert status["next_refresh_at"] is None
    assert "items" not in status

    skipped = svc.refresh_if_due()
    assert skipped["refreshed"] is False
    assert calls == []

    # Manual force remains available even when the automatic schedule is off.
    forced = svc.refresh(force=True)
    assert forced["refreshed"] is True
    assert forced["next_refresh_at"] is None
    assert len(calls) == 2  # CVSS v3 + optional v4
    assert db.query(NVDDigestState).one().max_items == 25
