"""
Subdomain Takeover API — /api/takeover.

Fingerprint catalog listing, persisted scan history (CRUD + result ordering and
operator notes), scan start (TakeoverService.scan stubbed — the background
worker never touches docker/DNS), and the finding-recorder helper.
"""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.card import Card
from models.recon_data import ReconData
from models.takeover_scan import TakeoverResult, TakeoverScan


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    from slowapi import Limiter
    import main as main_mod
    monkeypatch.setattr(main_mod.app.state, "limiter",
                        Limiter(key_func=lambda r: "test", storage_uri="memory://"))


@pytest.fixture(autouse=True)
def _scan_sessions(monkeypatch, runtime_sessions):
    """_run_scan opens its own sessions via the module-global SessionLocal —
    point it at the test DB so a racing background write can't hit dev data."""
    import api.takeover as tk
    monkeypatch.setattr(tk, "SessionLocal", runtime_sessions)


def _scan(db, domain="example.com", status="done", **kw):
    row = TakeoverScan(domain=domain, status=status,
                       checked=kw.pop("checked", 3), total=kw.pop("total", 3),
                       vulnerable=kw.pop("vulnerable", 1),
                       edge_case=kw.pop("edge_case", 0),
                       not_vulnerable=kw.pop("not_vulnerable", 2), **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _result(db, scan, subdomain, verdict="NOT_VULNERABLE", **kw):
    row = TakeoverResult(scan_id=scan.id, subdomain=subdomain, verdict=verdict,
                         service=kw.pop("service", "Heroku"),
                         confidence=kw.pop("confidence", "high"),
                         cname_target=kw.pop("cname_target", "svc.herokuapp.com"),
                         dns_status=kw.pop("dns_status", "NOERROR"),
                         evidence=kw.pop("evidence", "no such app"),
                         fingerprint=kw.pop("fingerprint", "No such app"),
                         documentation=kw.pop("documentation", "https://doc"),
                         note=kw.pop("note", None))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------------ fingerprints
def test_fingerprints_catalog(client, admin_headers):
    r = client.get("/api/takeover/fingerprints", headers=admin_headers)
    assert r.status_code == 200
    fps = r.json()
    assert len(fps) > 50  # the bundled can-i-take-over-xyz dataset
    services = {f["service"] for f in fps}
    assert any("Heroku" in s for s in services)
    assert all({"service", "status", "vulnerable", "cnames",
                "fingerprint"} <= set(f) for f in fps[:10])


def test_fingerprints_requires_auth(client):
    assert client.get("/api/takeover/fingerprints").status_code == 401


# ------------------------------------------------------------------ history
def test_list_scans_newest_first_with_limit(client, db, admin_headers):
    _scan(db, "first.com")
    _scan(db, "second.com")
    r = client.get("/api/takeover/scans", headers=admin_headers)
    assert [s["domain"] for s in r.json()] == ["second.com", "first.com"]

    r = client.get("/api/takeover/scans", params={"limit": 1},
                   headers=admin_headers)
    assert [s["domain"] for s in r.json()] == ["second.com"]


def test_get_scan_orders_results_by_severity(client, db, admin_headers):
    s = _scan(db)
    nv = _result(db, s, "safe.example.com")
    edge = _result(db, s, "edge.example.com", "EDGE_CASE")
    vuln = _result(db, s, "pwn.example.com", "VULNERABLE")
    r = client.get(f"/api/takeover/scans/{s.id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {"vulnerable": 1, "edge_case": 0,
                               "not_vulnerable": 2}
    assert [x["id"] for x in body["results"]] == [vuln.id, edge.id, nv.id]


def test_get_scan_404(client, admin_headers):
    assert client.get("/api/takeover/scans/66",
                      headers=admin_headers).status_code == 404


def test_delete_scan_cascades_results(client, db, admin_headers):
    s = _scan(db)
    _result(db, s, "x.example.com")
    assert client.delete(f"/api/takeover/scans/{s.id}",
                         headers=admin_headers).status_code == 204
    assert db.query(TakeoverScan).count() == 0
    assert db.query(TakeoverResult).count() == 0
    assert client.delete(f"/api/takeover/scans/{s.id}",
                         headers=admin_headers).status_code == 404


def test_delete_scan_audited(client, db, admin_headers):
    from models.audit_log import AuditLog
    s = _scan(db)
    client.delete(f"/api/takeover/scans/{s.id}", headers=admin_headers)
    row = db.query(AuditLog).filter(
        AuditLog.action == "takeover.scan_deleted").one()
    assert row.resource_id == str(s.id)


# ------------------------------------------------------------------ results
def test_set_result_note(client, db, admin_headers):
    s = _scan(db)
    res = _result(db, s, "noted.example.com")
    r = client.patch(f"/api/takeover/results/{res.id}", headers=admin_headers,
                     json={"note": "claimed by us, ignore"})
    assert r.status_code == 200
    assert r.json()["note"] == "claimed by us, ignore"
    # clearing works too
    r = client.patch(f"/api/takeover/results/{res.id}", headers=admin_headers,
                     json={"note": None})
    assert r.json()["note"] is None


def test_set_result_note_404(client, admin_headers):
    assert client.patch("/api/takeover/results/99", headers=admin_headers,
                        json={"note": "x"}).status_code == 404


def test_delete_result(client, db, admin_headers):
    s = _scan(db)
    res = _result(db, s, "gone.example.com")
    assert client.delete(f"/api/takeover/results/{res.id}",
                         headers=admin_headers).status_code == 204
    assert db.query(TakeoverResult).count() == 0
    assert client.delete(f"/api/takeover/results/{res.id}",
                         headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ start scan
def test_start_scan_creates_running_row(client, db, admin_headers, monkeypatch):
    from services.takeover_service import TakeoverService
    started = []

    async def _stalled_scan(self, domain, subdomains=None, on_progress=None):
        started.append((domain, subdomains))
        import asyncio
        await asyncio.Event().wait()  # never completes inside the test portal

    monkeypatch.setattr(TakeoverService, "scan", _stalled_scan)
    r = client.post("/api/takeover/scan", headers=admin_headers,
                    json={"domain": "example.com",
                          "subdomains": ["a.example.com"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "running"
    row = db.query(TakeoverScan).filter(TakeoverScan.id == body["scan_id"]).one()
    assert row.domain == "example.com"
    assert row.status in ("running", "error")  # cancelled bg task may finalize
    assert started == [("example.com", ["a.example.com"])]


def test_start_scan_requires_domain_422(client, admin_headers):
    assert client.post("/api/takeover/scan", headers=admin_headers,
                       json={"domain": "  "}).status_code == 422
    assert client.post("/api/takeover/scan",
                       headers=admin_headers).status_code == 422


def test_scan_write_requires_auditor(client, viewer_headers):
    assert client.post("/api/takeover/scan", headers=viewer_headers,
                       json={"domain": "example.com"}).status_code == 403


# ------------------------------------------------------------------ findings
def test_record_findings_creates_recon_and_cards(db):
    from api.takeover import _record_findings
    a = Assessment(name="tk-assess", scope="example.com")
    db.add(a)
    db.commit()
    results = [
        {"subdomain": "v.example.com", "verdict": "VULNERABLE", "service": "Heroku",
         "confidence": "high", "cname_target": "x.herokuapp.com",
         "dns_status": "NOERROR", "evidence": "no such app",
         "fingerprint": "No such app", "documentation": "doc",
         "cname_chain": ["x.herokuapp.com"]},
        {"subdomain": "s.example.com", "verdict": "NOT_VULNERABLE",
         "service": "GitHub", "confidence": "high",
         "cname_target": "gh.io", "dns_status": "NOERROR",
         "evidence": "ok", "fingerprint": "fp", "documentation": "doc",
         "cname_chain": []},
    ]
    added = _record_findings(db, a.id, results)
    assert added == 1  # only the VULNERABLE one becomes a finding card
    recon = db.query(ReconData).all()
    assert {r.name for r in recon} == {"v.example.com", "s.example.com"}
    assert all(r.data_type == "subdomain" for r in recon)
    card = db.query(Card).one()
    assert card.severity == "HIGH"
    assert card.status == "potential"
    assert "v.example.com" in card.title


def test_record_findings_unknown_assessment_is_noop(db):
    from api.takeover import _record_findings
    assert _record_findings(db, 4242, [{"subdomain": "x", "verdict": "VULNERABLE",
                                        "service": "s", "confidence": "c",
                                        "cname_target": None, "dns_status": "",
                                        "evidence": "", "fingerprint": "",
                                        "documentation": None,
                                        "cname_chain": []}]) == 0
    assert db.query(ReconData).count() == 0


# ------------------------------------------------------------------ _run_scan
async def test_run_scan_finalizes_done_and_records_findings(
        db, runtime_sessions, monkeypatch):
    from api import takeover as tk
    from models.task import Task  # noqa: F401 — import graph warm-up
    from services.takeover_service import TakeoverService
    a = Assessment(name="runscan-assess", scope="example.com")
    db.add(a)
    db.commit()
    scan = _scan(db, "example.com", status="running", checked=0, total=0,
                 vulnerable=0, edge_case=0, not_vulnerable=0)

    progress = []

    async def _fake(self, domain, subdomains=None, on_progress=None):
        assert domain == "example.com"
        await on_progress({"checked": 1, "total": 2, "result": {
            "subdomain": "v.example.com", "verdict": "VULNERABLE",
            "service": "Heroku", "confidence": "high",
            "cname_target": "x.herokuapp.com", "dns_status": "NOERROR",
            "evidence": "e", "fingerprint": "f", "documentation": "d"}})
        await on_progress({"checked": 2, "total": 2, "result": {
            "subdomain": "s.example.com", "verdict": "NOT_VULNERABLE",
            "service": "Agora", "confidence": "high",
            "cname_target": None, "dns_status": "NOERROR",
            "evidence": "e", "fingerprint": "f"}})
        progress.append("done")
        return {"wildcard": True, "subdomains_checked": 2,
                "results": [
                    {"subdomain": "v.example.com", "verdict": "VULNERABLE",
                     "service": "Heroku", "confidence": "high",
                     "cname_target": "x.herokuapp.com", "dns_status": "NOERROR",
                     "evidence": "e", "fingerprint": "f", "documentation": "d",
                     "cname_chain": ["x.herokuapp.com"]},
                    {"subdomain": "s.example.com", "verdict": "NOT_VULNERABLE",
                     "service": "Agora", "confidence": "high",
                     "cname_target": None, "dns_status": "NOERROR",
                     "evidence": "e", "fingerprint": "f",
                     "cname_chain": []}]}

    monkeypatch.setattr(TakeoverService, "scan", _fake)
    await tk._run_scan(scan.id, "example.com", None, a.id)

    s = runtime_sessions()
    try:
        row = s.query(TakeoverScan).filter(TakeoverScan.id == scan.id).one()
        assert row.status == "done"
        assert row.wildcard is True
        assert (row.checked, row.total) == (2, 2)
        assert row.vulnerable == 1 and row.not_vulnerable == 1
        assert row.finished_at is not None
        results = s.query(TakeoverResult).filter(
            TakeoverResult.scan_id == scan.id).all()
        assert {r.subdomain for r in results} == {"v.example.com",
                                                  "s.example.com"}
        # findings were recorded for the assessment (1 card + 2 recon rows)
        assert s.query(Card).count() == 1
        assert s.query(ReconData).count() == 2
    finally:
        s.close()
    assert progress == ["done"]


async def test_run_scan_error_path(db, runtime_sessions, monkeypatch):
    from api import takeover as tk
    from services.takeover_service import TakeoverService
    scan = _scan(db, "broken.example", status="running")

    async def _boom(self, domain, subdomains=None, on_progress=None):
        raise RuntimeError("dns exploded")

    monkeypatch.setattr(TakeoverService, "scan", _boom)
    await tk._run_scan(scan.id, "broken.example", None, None)

    s = runtime_sessions()
    try:
        row = s.query(TakeoverScan).filter(TakeoverScan.id == scan.id).one()
        assert row.status == "error"
        assert "dns exploded" in row.error
        assert s.query(TakeoverResult).count() == 0
    finally:
        s.close()


async def test_run_scan_strips_nul_bytes_from_results(db, runtime_sessions,
                                                      monkeypatch):
    from api import takeover as tk
    from services.takeover_service import TakeoverService
    scan = _scan(db, "nul.example", status="running")

    async def _fake(self, domain, subdomains=None, on_progress=None):
        await on_progress({"checked": 1, "total": 1, "result": {
            "subdomain": "a\x00.example", "verdict": "EDGE_CASE",
            "service": "Fastly", "confidence": "firm",
            "cname_target": "t\x00.fastly.net", "dns_status": "NOERROR",
            "evidence": "ev\x00", "fingerprint": "fp\x00"}})
        return {"wildcard": False, "subdomains_checked": 1, "results": []}

    monkeypatch.setattr(TakeoverService, "scan", _fake)
    await tk._run_scan(scan.id, "nul.example", None, None)

    s = runtime_sessions()
    try:
        res = s.query(TakeoverResult).one()
        assert "\x00" not in res.subdomain
        assert "\x00" not in (res.cname_target or "")
        assert "\x00" not in (res.evidence or "")
    finally:
        s.close()
