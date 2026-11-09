"""
E4 compliance-registry tests (OWASP / PCI DSS / NIST CSF mapping + manual
override) and the outbound-webhook notification channel (the Jira bridge):
JSON payload shape and the HMAC-SHA256 signature header.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace

import pytest

from models.assessment import Assessment
from models.card import Card
from services.compliance_registry import FRAMEWORKS, classify_finding, map_assessment
from services.notification_service import NotificationService


# --- classifier ---------------------------------------------------------------

def _finding(db, assessment_id, title, analysis="", severity="HIGH",
             compliance_refs=None):
    row = Card(assessment_id=assessment_id, card_type="finding", title=title,
               severity=severity, status="confirmed",
                   target_service="https://app.example.com",
                   technical_analysis=analysis, compliance_refs=compliance_refs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_sqli_maps_to_injection_and_pci(db):
    asmt = Assessment(name="compliance-t1")
    db.add(asmt)
    db.commit()
    _finding(db, asmt.id, "SQL Injection in /search",
             analysis="union-select exfiltrates records from the database")

    refs = classify_finding(db.query(Card).one())
    assert "A03:2021" in [i["code"] for i in refs["owasp"]]
    assert "6.5.1" in [i["code"] for i in refs["pci"]]


def test_manual_refs_override_auto_classification(db):
    asmt = Assessment(name="compliance-t2")
    db.add(asmt)
    db.commit()
    row = _finding(db, asmt.id, "Odd business flow", analysis="",
                   compliance_refs={"owasp": ["A04:2021"], "pci": ["6.5.1"]})

    refs = classify_finding(row)
    assert [i["code"] for i in refs["owasp"]] == ["A04:2021"]
    assert [i["code"] for i in refs["pci"]] == ["6.5.1"]
    # Frameworks without a manual override fall back to auto (here: nothing).
    assert "nist" not in refs


def test_unmapped_finding_stays_unmapped(db):
    asmt = Assessment(name="compliance-t3")
    db.add(asmt)
    db.commit()
    row = _finding(db, asmt.id, "Something entirely unrelated to any control",
                   analysis="prose without framework keywords")

    assert classify_finding(row) == {}  # errs toward unmapped, never invents


def test_map_assessment_all_frameworks_and_counts(db):
    asmt = Assessment(name="compliance-t4")
    db.add(asmt)
    db.commit()
    _finding(db, asmt.id, "Reflected XSS in search",
             analysis="cross-site scripting in the q parameter")
    _finding(db, asmt.id, "IDOR on /api/orders/1",
             analysis="unauthorized access to another tenant's order")
    _finding(db, asmt.id, "Prose finding with no keywords")
    # excluded from mapping entirely
    _finding(db, asmt.id, "XSS in /q2", analysis="cross-site scripting",
             compliance_refs=None)
    db.query(Card).filter(Card.title == "XSS in /q2").one().status = "false_positive"
    db.commit()

    out = map_assessment(db, asmt.id)

    assert set(out.keys()) == set(FRAMEWORKS.keys())
    owasp = out["owasp"]
    assert "A03:2021" in owasp["controls"]      # XSS
    assert "A01:2021" in owasp["controls"]      # IDOR
    assert owasp["mapped_findings"] == 2        # XSS + IDOR
    assert owasp["unmapped_findings"] == 1      # prose finding


def test_map_assessment_single_framework_and_unknown(db):
    asmt = Assessment(name="compliance-t5")
    db.add(asmt)
    db.commit()
    _finding(db, asmt.id, "Stored cross-site scripting in profile name")

    out = map_assessment(db, asmt.id, framework="owasp")
    assert list(out.keys()) == ["owasp"]
    assert "A03:2021" in out["owasp"]["controls"]

    with pytest.raises(ValueError):
        map_assessment(db, asmt.id, framework="iso27001")


# --- webhook channel (Jira bridge) ---------------------------------------------

class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.text = "ok"


class _FakeAsyncClient:
    """Records the POST; per-instance capture via the class-level list."""
    calls: list[dict] = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, content=None, headers=None, **kw):
        _FakeAsyncClient.calls.append(
            {"url": url, "content": content, "headers": dict(headers or {})})
        return _FakeResponse()


@pytest.fixture()
def fake_httpx(monkeypatch):
    import services.notification_service as ns
    _FakeAsyncClient.calls = []
    monkeypatch.setattr(ns, "httpx", SimpleNamespace(AsyncClient=_FakeAsyncClient))
    return _FakeAsyncClient


async def test_webhook_payload_and_hmac_signature(db, fake_httpx):
    cfg = {"url": "https://jira.example.com/hooks/aida",
           "secret": "s3cret-webhook-key"}
    await NotificationService(db)._send_webhook(cfg, "AIDA: HIGH finding on app")

    assert len(fake_httpx.calls) == 1
    call = fake_httpx.calls[0]
    assert call["url"] == cfg["url"]

    body = json.loads(call["content"])
    assert body["event"] == "notification"
    assert body["text"] == "AIDA: HIGH finding on app"
    assert body["timestamp"]

    expected = "sha256=" + hmac.new(cfg["secret"].encode(),
                                    call["content"], hashlib.sha256).hexdigest()
    assert call["headers"]["X-AIDA-Signature"] == expected
    assert call["headers"]["Content-Type"] == "application/json"


async def test_webhook_without_secret_has_no_signature(db, fake_httpx):
    await NotificationService(db)._send_webhook(
        {"url": "https://soar.example/hook"}, "msg")
    call = fake_httpx.calls[0]
    assert "X-AIDA-Signature" not in call["headers"]


async def test_webhook_requires_url(db, fake_httpx):
    with pytest.raises(ValueError):
        await NotificationService(db)._send_webhook({"url": ""}, "msg")
    assert fake_httpx.calls == []


async def test_webhook_error_status_raises(db, fake_httpx, monkeypatch):
    class _ErrClient(_FakeAsyncClient):
        async def post(self, *a, **kw):
            return _FakeResponse(status_code=502)

    import services.notification_service as ns
    monkeypatch.setattr(ns, "httpx", SimpleNamespace(AsyncClient=_ErrClient))
    with pytest.raises(RuntimeError):
        await NotificationService(db)._send_webhook(
            {"url": "https://jira.example/hook"}, "msg")
