"""Assessment router + AssessmentService integration tests (hermetic: the
Exegol container workspace creation is stubbed at the service boundary)."""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.assessment_section import AssessmentSection
from models.card import Card
from models.command_history import CommandHistory
from models.folder import Folder
from models.recon_data import ReconData
from services.container_service import ContainerService
from services.scan_importer import ScanImporter, ScanImportError

NMAP_XML = b"""<?xml version="1.0"?>
<nmaprun scanner="nmap">
  <host>
    <status state="up"/>
    <address addr="10.0.0.5" addrtype="ipv4"/>
    <hostnames><hostname name="target.local" type="user"/></hostnames>
    <ports>
      <port protocol="tcp" portid="80"><state state="open"/>
        <service name="http" product="nginx" version="1.18.0"/></port>
      <port protocol="tcp" portid="22"><state state="open"/>
        <service name="ssh" product="OpenSSH" version="8.4"/></port>
      <port protocol="tcp" portid="8080"><state state="closed"/>
        <service name="http-proxy"/></port>
    </ports>
  </host>
</nmaprun>
"""


def make_assessment(db, name="Web Test", **kw):
    kw.setdefault("scope", "127.0.0.1")
    kw.setdefault("status", "active")
    a = Assessment(name=name, **kw)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture()
def fake_workspace(monkeypatch):
    """Workspace creation shells out to docker — stub it at the class boundary
    (used by AssessmentService.create_assessment and the container-change route)."""
    calls = []

    async def _create_workspace(self, assessment_name, db=None):
        calls.append(assessment_name)
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in assessment_name.replace(" ", "_"))
        return {"workspace_path": f"/workspace/{safe}",
                "container_name": self.current_container or "mock-container"}

    monkeypatch.setattr(ContainerService, "create_workspace", _create_workspace)
    return calls


# --- auth ----------------------------------------------------------------------

def test_routes_require_token(client, db):
    r = client.get("/api/assessments")
    assert r.status_code == 401
    r = client.post("/api/assessments", json={"name": "x"})
    assert r.status_code == 401
    r = client.put("/api/assessments/1", json={"status": "done"})
    assert r.status_code == 401
    r = client.delete("/api/assessments/1")
    assert r.status_code == 401
    r = client.get("/api/assessments/1/compliance")
    assert r.status_code == 401


def test_viewer_read_ok_write_forbidden(client, db, admin_headers, viewer_headers):
    assert client.get("/api/assessments", headers=viewer_headers).status_code == 200
    r = client.post("/api/assessments", headers=viewer_headers, json={"name": "Nope"})
    assert r.status_code == 403
    assert "auditor" in r.json()["detail"]
    r = client.delete("/api/assessments/1", headers=viewer_headers)
    assert r.status_code == 403


# --- list + filters ------------------------------------------------------------

def test_list_empty(client, db, admin_headers):
    r = client.get("/api/assessments", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_list_with_filters(client, db, admin_headers):
    folder = Folder(name="FY")
    db.add(folder)
    db.commit()
    db.refresh(folder)
    make_assessment(db, "In Folder", folder_id=folder.id)
    make_assessment(db, "Orphan", status="completed")

    r = client.get("/api/assessments", headers=admin_headers,
                   params={"folder_id": str(folder.id)})
    assert [a["name"] for a in r.json()] == ["In Folder"]

    r = client.get("/api/assessments", headers=admin_headers, params={"folder_id": "null"})
    assert [a["name"] for a in r.json()] == ["Orphan"]

    # invalid folder_id is ignored, not an error
    r = client.get("/api/assessments", headers=admin_headers, params={"folder_id": "abc"})
    assert len(r.json()) == 2

    r = client.get("/api/assessments", headers=admin_headers, params={"status": "completed"})
    assert [a["name"] for a in r.json()] == ["Orphan"]

    r = client.get("/api/assessments", headers=admin_headers, params={"status": "bogus"})
    assert r.status_code == 400
    assert "Invalid status" in r.json()["detail"]

    # pagination
    r = client.get("/api/assessments", headers=admin_headers,
                   params={"skip": 1, "limit": 1})
    assert len(r.json()) == 1


# --- get single ----------------------------------------------------------------

def test_get_assessment_found_and_missing(client, db, admin_headers):
    a = make_assessment(db, "Solo", client_name="ACME")
    r = client.get(f"/api/assessments/{a.id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Solo"
    assert body["client_name"] == "ACME"
    assert body["status"] == "active"
    assert client.get("/api/assessments/999", headers=admin_headers).status_code == 404


# --- compliance (E4) -----------------------------------------------------------

def test_compliance_mapping(client, db, admin_headers):
    a = make_assessment(db, "Comp")
    db.add(Card(assessment_id=a.id, card_type="finding", title="SQL Injection in login",
                severity="CRITICAL", status="confirmed"))
    db.add(Card(assessment_id=a.id, card_type="finding", title="Nothing interesting",
                severity="INFO", status="confirmed"))
    db.add(Card(assessment_id=a.id, card_type="finding", title="Reflected XSS dismissed",
                severity="LOW", status="false_positive"))  # excluded
    db.commit()

    r = client.get(f"/api/assessments/{a.id}/compliance", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"owasp", "pci", "nist"}
    assert "A03:2021" in body["owasp"]["controls"]
    sql = body["owasp"]["controls"]["A03:2021"]["findings"]
    assert [f["title"] for f in sql] == ["SQL Injection in login"]
    # the unmatched finding is counted, the false positive is not loaded at all
    assert body["owasp"]["unmapped_findings"] == 1

    r = client.get(f"/api/assessments/{a.id}/compliance", headers=admin_headers,
                   params={"framework": "owasp"})
    assert r.status_code == 200
    assert set(r.json()) == {"owasp"}

    r = client.get(f"/api/assessments/{a.id}/compliance", headers=admin_headers,
                   params={"framework": "iso27001"})
    assert r.status_code == 400
    assert "Unknown framework" in r.json()["detail"]

    assert client.get("/api/assessments/42/compliance",
                      headers=admin_headers).status_code == 404


def test_compliance_manual_override(client, db, admin_headers):
    a = make_assessment(db, "Manual")
    db.add(Card(assessment_id=a.id, card_type="finding", title="Odd cache issue",
                severity="LOW", status="confirmed",
                compliance_refs={"owasp": ["A05:2021"]}))
    db.commit()
    body = client.get(f"/api/assessments/{a.id}/compliance", headers=admin_headers,
                      params={"framework": "owasp"}).json()
    assert list(body["owasp"]["controls"]) == ["A05:2021"]


# --- findings diff (E4) --------------------------------------------------------

def test_diff_findings(client, db, admin_headers):
    old = make_assessment(db, "Audit 2025")
    new = make_assessment(db, "Audit 2026")
    db.add(Card(assessment_id=old.id, card_type="finding", title="SQL Injection",
                target_service="api", severity="HIGH", status="confirmed"))
    db.add(Card(assessment_id=old.id, card_type="finding", title="Old TLS",
                target_service="vpn", severity="MEDIUM", status="confirmed"))
    db.add(Card(assessment_id=new.id, card_type="finding", title="SQL Injection",
                target_service="api", severity="CRITICAL", status="confirmed"))
    db.add(Card(assessment_id=new.id, card_type="finding", title="SSRF in import",
                target_service="web", severity="HIGH", status="confirmed"))
    db.commit()

    r = client.get(f"/api/assessments/{new.id}/diff/{old.id}", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"] == {"total_old": 2, "total_new": 2, "new": 1, "fixed": 1,
                               "persistent": 1, "severity_changed": 1}
    assert [f["title"] for f in body["new"]] == ["SSRF in import"]
    assert [f["title"] for f in body["fixed"]] == ["Old TLS"]
    assert body["persistent"][0]["old_severity"] == "HIGH"
    assert body["persistent"][0]["new_severity"] == "CRITICAL"
    assert body["old_assessment"]["name"] == "Audit 2025"

    assert client.get(f"/api/assessments/{new.id}/diff/999",
                      headers=admin_headers).status_code == 404
    assert client.get("/api/assessments/999/diff/1", headers=admin_headers).status_code == 404


# --- full dump -----------------------------------------------------------------

def test_get_assessment_full(client, db, admin_headers):
    a = make_assessment(db, "Full")
    db.add(AssessmentSection(assessment_id=a.id, section_type="recon",
                             section_number=1.0, title="Recon"))
    db.add(Card(assessment_id=a.id, card_type="finding", title="F1", severity="LOW"))
    db.add(ReconData(assessment_id=a.id, data_type="subdomain", name="app.target"))
    db.commit()

    r = client.get(f"/api/assessments/{a.id}/full", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["assessment"]["name"] == "Full"
    assert len(body["sections"]) == 1
    assert [c["title"] for c in body["cards"]] == ["F1"]
    assert [x["name"] for x in body["recon_data"]] == ["app.target"]
    assert client.get("/api/assessments/7/full", headers=admin_headers).status_code == 404


# --- create --------------------------------------------------------------------

def test_create_assessment_happy_path(client, db, admin_headers, fake_workspace):
    r = client.post("/api/assessments", headers=admin_headers, json={
        "name": "New Engagement", "client_name": "ACME", "scope": "acme.test",
        "category": "Website", "target_domains": ["acme.test"],
        "start_date": "2026-01-05", "environment": "production",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "New Engagement"
    assert body["status"] == "active"
    assert body["workspace_path"] == "/workspace/New_Engagement"
    assert fake_workspace == ["New Engagement"]
    rows = db.query(Assessment).all()
    from config import settings
    assert len(rows) == 1
    assert rows[0].container_name == settings.DEFAULT_CONTAINER_NAME


def test_create_assessment_duplicate_name(client, db, admin_headers, fake_workspace):
    make_assessment(db, "Dup")
    r = client.post("/api/assessments", headers=admin_headers, json={"name": "Dup"})
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"]
    # whitespace is trimmed before the uniqueness check
    r = client.post("/api/assessments", headers=admin_headers, json={"name": "  Dup  "})
    assert r.status_code == 400


@pytest.mark.parametrize("payload", [
    {}, {"name": ""}, {"name": "   "}, {"name": "bad!name"}, {"name": "-leading"},
])
def test_create_assessment_validation_422(client, db, admin_headers, payload):
    r = client.post("/api/assessments", headers=admin_headers, json=payload)
    assert r.status_code == 422


def test_create_assessment_asvs_methodology(client, db, admin_headers, fake_workspace):
    r = client.post("/api/assessments", headers=admin_headers, json={
        "name": "ASVS Audit", "methodology": "asvs", "asvs_level": 1,
        "asvs_chapters": ["V1"]})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["methodology"] == "asvs"
    assert body["asvs_level"] == 1
    assert body["asvs_version"] == "5.0.0"
    assert db.query(AssessmentSection).count() == 0  # sections untouched
    from models.asvs_requirement import AsvsRequirement
    seeded = db.query(AsvsRequirement).count()
    assert seeded > 0


# --- update --------------------------------------------------------------------

def test_update_assessment(client, db, admin_headers):
    a = make_assessment(db, "Before")
    r = client.put(f"/api/assessments/{a.id}", headers=admin_headers,
                   json={"status": "completed", "client_name": "Beta"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert body["client_name"] == "Beta"
    assert body["name"] == "Before"  # untouched field

    # dates and arrays must survive the WebSocket-event serialization
    r = client.put(f"/api/assessments/{a.id}", headers=admin_headers,
                   json={"start_date": "2026-02-03", "target_domains": ["a.test"],
                         "end_date": "2026-03-01"})
    assert r.status_code == 200
    assert r.json()["start_date"] == "2026-02-03"
    assert r.json()["target_domains"] == ["a.test"]

    assert client.put("/api/assessments/999", headers=admin_headers,
                      json={"status": "done"}).status_code == 404
    r = client.put(f"/api/assessments/{a.id}", headers=admin_headers, json={"name": "!!"})
    assert r.status_code == 422


def test_serialize_for_json_nested_structures():
    from datetime import date, datetime

    from api.assessments import serialize_for_json

    out = serialize_for_json({
        "d": date(2026, 1, 2),
        "dt": datetime(2026, 1, 2, 3, 4, 5),
        "nested": {"inner": date(2026, 1, 3), "keep": 1},
        "items": [{"x": date(2026, 1, 4)}, "raw"],
        "plain": "text",
    })
    assert out == {
        "d": "2026-01-02",
        "dt": "2026-01-02T03:04:05",
        "nested": {"inner": "2026-01-03", "keep": 1},
        "items": [{"x": "2026-01-04"}, "raw"],
        "plain": "text",
    }


# --- delete --------------------------------------------------------------------

def test_delete_assessment_cascades(client, db, admin_headers):
    a = make_assessment(db, "Doomed")
    db.add(Card(assessment_id=a.id, card_type="info", title="note"))
    db.commit()
    r = client.delete(f"/api/assessments/{a.id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.query(Assessment).count() == 0
    assert db.query(Card).count() == 0
    assert client.delete("/api/assessments/999", headers=admin_headers).status_code == 404


# --- duplicate -----------------------------------------------------------------

def _seed_full_assessment(db):
    a = make_assessment(db, "Original", client_name="ACME", scope="scope.test",
                        credentials="user:pass", category="API",
                        target_domains=["x.test"], ip_scopes=["10.0.0.0/8"])
    db.add(Card(assessment_id=a.id, card_type="finding", title="C1", severity="HIGH",
                status="confirmed", technical_analysis="analysis", proof="proof"))
    db.add(AssessmentSection(assessment_id=a.id, section_type="recon",
                             section_number=2.5, title="Recon", content="text"))
    db.add(ReconData(assessment_id=a.id, data_type="service", name="svc",
                     details={"host": "h"}))
    db.add(CommandHistory(assessment_id=a.id, command="nmap -sV", stdout="out",
                          returncode=0, success=True, phase="recon",
                          status="completed"))
    db.commit()
    return a


def test_duplicate_assessment_copies_related_data(client, db, admin_headers, fake_workspace):
    a = _seed_full_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/duplicate", headers=admin_headers, json={
        "include_cards": True, "include_sections": True,
        "include_recon": True, "include_commands": True})
    assert r.status_code == 201, r.text
    dup_id = r.json()["id"]
    assert r.json()["name"] == "Original (Copy)"
    assert r.json()["client_name"] == "ACME"
    assert r.json()["scope"] == "scope.test"
    assert db.query(Card).filter(Card.assessment_id == dup_id).count() == 1
    assert db.query(AssessmentSection).filter(
        AssessmentSection.assessment_id == dup_id).count() == 1
    assert db.query(ReconData).filter(ReconData.assessment_id == dup_id).count() == 1
    assert db.query(CommandHistory).filter(
        CommandHistory.assessment_id == dup_id).count() == 1


def test_duplicate_assessment_without_related_data(client, db, admin_headers, fake_workspace):
    a = _seed_full_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/duplicate", headers=admin_headers, json={})
    assert r.status_code == 201
    dup_id = r.json()["id"]
    assert db.query(Card).filter(Card.assessment_id == dup_id).count() == 0
    assert db.query(ReconData).filter(ReconData.assessment_id == dup_id).count() == 0


def test_duplicate_assessment_naming_and_errors(client, db, admin_headers, fake_workspace):
    a = _seed_full_assessment(db)
    folder = Folder(name="Keep")
    db.add(folder)
    db.commit()
    db.refresh(folder)
    a.folder_id = folder.id
    db.commit()

    r = client.post(f"/api/assessments/{a.id}/duplicate", headers=admin_headers, json={})
    assert r.json()["name"] == "Original (Copy)"
    assert r.json()["folder_id"] == folder.id

    # second copy gets a numbered suffix
    r = client.post(f"/api/assessments/{a.id}/duplicate", headers=admin_headers, json={})
    assert r.json()["name"] == "Original (Copy 2)"

    # explicit name
    r = client.post(f"/api/assessments/{a.id}/duplicate", headers=admin_headers,
                    json={"name": "Renamed"})
    assert r.status_code == 201
    assert r.json()["name"] == "Renamed"

    # explicit name that already exists
    r = client.post(f"/api/assessments/{a.id}/duplicate", headers=admin_headers,
                    json={"name": "Original"})
    assert r.status_code == 400

    assert client.post("/api/assessments/999/duplicate", headers=admin_headers,
                       json={}).status_code == 404


# --- move to folder ------------------------------------------------------------

def test_move_assessment(client, db, admin_headers):
    a = make_assessment(db, "Mover")
    folder = Folder(name="Dest")
    db.add(folder)
    db.commit()
    db.refresh(folder)

    r = client.post(f"/api/assessments/{a.id}/move", headers=admin_headers,
                    json={"folder_id": folder.id})
    assert r.status_code == 200
    assert r.json()["folder_id"] == folder.id

    # back to no folder
    r = client.post(f"/api/assessments/{a.id}/move", headers=admin_headers,
                    json={"folder_id": None})
    assert r.status_code == 200
    assert r.json()["folder_id"] is None

    r = client.post(f"/api/assessments/{a.id}/move", headers=admin_headers,
                    json={"folder_id": 4242})
    assert r.status_code == 404
    assert "Folder" in r.json()["detail"]

    # non-integer folder_id is rejected as 422, not an unhandled DB error (500)
    for bad in ("not-a-number", [1], 3.5, True):
        r = client.post(f"/api/assessments/{a.id}/move", headers=admin_headers,
                        json={"folder_id": bad})
        assert r.status_code == 422, bad
        assert "folder_id must be an integer" in r.json()["detail"]

    # omitting folder_id entirely un-files the assessment
    r = client.post(f"/api/assessments/{a.id}/move", headers=admin_headers, json={})
    assert r.status_code == 200
    assert r.json()["folder_id"] is None

    assert client.post("/api/assessments/999/move", headers=admin_headers,
                       json={"folder_id": None}).status_code == 404


# --- parse-scans ---------------------------------------------------------------

def test_parse_scans_nmap(client, db, admin_headers):
    a = make_assessment(db, "Scan")
    r = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                    files=[("files", ("scan.xml", NMAP_XML, "text/xml"))])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["stats"]["services"] == 2  # closed port skipped
    svc = body["items"]["services"][0]
    assert svc["details"]["port"] == 80
    assert svc["is_duplicate"] is False
    assert body["files"][0]["scan_type"] == "nmap"
    assert client.post("/api/assessments/999/parse-scans", headers=admin_headers,
                       files=[("files", ("scan.xml", NMAP_XML, "text/xml"))
                              ]).status_code == 404


def test_parse_scans_unknown_format_reports_error(client, db, admin_headers):
    a = make_assessment(db, "Scan2")
    r = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                    files=[("files", ("notes.txt", b"hello world", "text/plain"))])
    assert r.status_code == 200
    body = r.json()
    assert body["files"][0]["success"] is False
    assert "Unknown scan format" in body["files"][0]["error"]
    assert body["stats"]["total"] == 0


def test_parse_scans_too_large(client, db, admin_headers):
    a = make_assessment(db, "Big")
    big = b"x" * (25 * 1024 * 1024 + 1)
    r = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                    files=[("files", ("huge.xml", big, "text/xml"))])
    assert r.status_code == 413


def test_parse_scans_importer_error_mapping(client, db, admin_headers, monkeypatch):
    a = make_assessment(db, "Err")
    from api import assessments as api_assessments

    def _boom(self, files):
        raise ScanImportError("bad stuff")

    monkeypatch.setattr(ScanImporter, "parse_files", _boom)
    r = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                    files=[("files", ("scan.xml", NMAP_XML, "text/xml"))])
    assert r.status_code == 400
    assert "bad stuff" in r.json()["detail"]

    def _kaboom(self, files):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(ScanImporter, "parse_files", _kaboom)
    r = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                    files=[("files", ("scan.xml", NMAP_XML, "text/xml"))])
    assert r.status_code == 500
    assert api_assessments.logger is not None  # module import sanity


# --- import-scans --------------------------------------------------------------

def test_import_scans_roundtrip(client, db, admin_headers):
    a = make_assessment(db, "Import")
    parsed = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                         files=[("files", ("scan.xml", NMAP_XML, "text/xml"))]).json()
    items = parsed["items"]

    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"item_ids": [], "items": items})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["stats"]["services"] == 2
    assert db.query(ReconData).filter(
        ReconData.assessment_id == a.id, ReconData.data_type == "service").count() == 2

    # re-parsing now flags both services as duplicates: unselected import
    # excludes them, explicit selection reports them as skipped
    reparsed = client.post(f"/api/assessments/{a.id}/parse-scans", headers=admin_headers,
                           files=[("files", ("scan.xml", NMAP_XML, "text/xml"))]).json()
    assert reparsed["stats"]["duplicates"] == 2
    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"item_ids": [], "items": reparsed["items"]})
    assert r.json()["stats"] == {"services": 0, "endpoints": 0, "findings": 0,
                                 "skipped_duplicates": 0}
    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"item_ids": [s["id"] for s in reparsed["items"]["services"]],
                          "items": reparsed["items"]})
    assert r.json()["stats"] == {"services": 0, "endpoints": 0, "findings": 0,
                                 "skipped_duplicates": 2}

    # selective import by id
    one = items["services"][0]["id"]
    db.query(ReconData).filter(ReconData.assessment_id == a.id).delete()
    db.commit()
    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"item_ids": [one], "items": items})
    assert r.json()["stats"]["services"] == 1

    assert client.post("/api/assessments/999/import-scans", headers=admin_headers,
                       json={"items": {}}).status_code == 404


def test_import_scans_error_mapping(client, db, admin_headers, monkeypatch):
    a = make_assessment(db, "ImportErr")

    def _boom(self, item_ids, all_items):
        raise ScanImportError("nope")

    monkeypatch.setattr(ScanImporter, "import_items", _boom)
    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"items": {}})
    assert r.status_code == 400

    def _kaboom(self, item_ids, all_items):
        raise RuntimeError("db down")

    monkeypatch.setattr(ScanImporter, "import_items", _kaboom)
    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"items": {}})
    assert r.status_code == 500


def test_import_scans_validation_422(client, db, admin_headers):
    a = make_assessment(db, "Val")
    r = client.post(f"/api/assessments/{a.id}/import-scans", headers=admin_headers,
                    json={"item_ids": "nope"})
    assert r.status_code == 422


# --- change container ----------------------------------------------------------

def test_change_container_success(client, db, admin_headers, fake_workspace, monkeypatch):
    a = make_assessment(db, "Cont", container_name="old", workspace_path="/workspace/old")

    async def _discover(self, force_refresh=False):
        return [{"name": "exegol-b", "status": "running"}]

    monkeypatch.setattr(ContainerService, "discover_containers", _discover)

    r = client.put(f"/api/assessments/{a.id}/container", headers=admin_headers,
                   json={"container_name": "exegol-b"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old_container"] == "old"
    assert body["new_container"] == "exegol-b"
    db.refresh(a)
    assert a.container_name == "exegol-b"
    assert a.workspace_path == "/workspace/Cont"


def test_change_container_not_found_errors(client, db, admin_headers, monkeypatch):
    a = make_assessment(db, "Cont2")

    async def _discover(self, force_refresh=False):
        return [{"name": "exegol-a", "status": "running"}]

    monkeypatch.setattr(ContainerService, "discover_containers", _discover)

    assert client.put("/api/assessments/999/container", headers=admin_headers,
                      json={"container_name": "exegol-a"}).status_code == 404

    r = client.put(f"/api/assessments/{a.id}/container", headers=admin_headers,
                   json={"container_name": "ghost"})
    assert r.status_code == 400
    assert "ghost" in r.json()["detail"]

    async def _kaboom(self, force_refresh=False):
        raise RuntimeError("docker socket gone")

    monkeypatch.setattr(ContainerService, "discover_containers", _kaboom)
    r = client.put(f"/api/assessments/{a.id}/container", headers=admin_headers,
                   json={"container_name": "exegol-a"})
    assert r.status_code == 500
