"""api/reports.py — markdown + PDF download endpoints over the real TestClient
auth/RBAC stack; PDF generation is mocked at the service boundary."""
from __future__ import annotations

import io

from models.assessment import Assessment
from models.card import Card
from models.credential import Credential


def _seed(db):
    asn = Assessment(name="API Report Test", scope="t.example")
    db.add(asn)
    db.flush()
    db.add(Card(assessment_id=asn.id, card_type="finding", title="Finding one",
                severity="HIGH"))
    db.add(Credential(assessment_id=asn.id, credential_type="bearer_token",
                      name="Token", placeholder="TOKEN",
                      token="super-secret-token"))
    db.commit()
    db.refresh(asn)
    return asn


def _make_fake_pdf(monkeypatch, pdf_bytes=b"%PDF-report"):
    async def fake_pdf(db, assessment_id, include_secrets=False, template="default"):
        buf = io.BytesIO()
        buf.write(pdf_bytes)
        buf.seek(0)
        return buf

    monkeypatch.setattr("api.reports.generate_pdf_report", fake_pdf)


def test_markdown_report_requires_auth(client, db):
    asn = _seed(db)
    res = client.get(f"/api/assessments/{asn.id}/report/markdown")
    assert res.status_code == 401


def test_markdown_report_success_and_headers(client, db, admin_headers):
    asn = _seed(db)
    res = client.get(f"/api/assessments/{asn.id}/report/markdown",
                     headers=admin_headers)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/markdown")
    assert 'filename="AIDA_Report_API Report Test.md"' in res.headers["content-disposition"]
    assert "# Security Assessment Report — API Report Test" in res.text
    assert "super-secret-token" not in res.text  # masked by default
    assert "••••••••" in res.text


def test_markdown_report_include_secrets(client, db, admin_headers):
    asn = _seed(db)
    res = client.get(f"/api/assessments/{asn.id}/report/markdown",
                     params={"include_secrets": True}, headers=admin_headers)
    assert res.status_code == 200
    assert "`super-secret-token`" in res.text


def test_markdown_report_not_found(client, db, admin_headers):
    res = client.get("/api/assessments/999999/report/markdown", headers=admin_headers)
    assert res.status_code == 404


def test_markdown_report_bad_template(client, db, admin_headers):
    asn = _seed(db)
    res = client.get(f"/api/assessments/{asn.id}/report/markdown",
                     params={"template": "nope"}, headers=admin_headers)
    assert res.status_code == 400
    assert "template must be one of" in res.json()["detail"]


def test_markdown_report_generation_error(client, db, admin_headers, monkeypatch):
    asn = _seed(db)

    def boom(db, assessment_id, include_secrets=False, template="default"):
        raise RuntimeError("md exploded")

    monkeypatch.setattr("api.reports.generate_markdown_report", boom)
    res = client.get(f"/api/assessments/{asn.id}/report/markdown", headers=admin_headers)
    assert res.status_code == 500
    assert "md exploded" in res.json()["detail"]


def test_pdf_report_success(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    _make_fake_pdf(monkeypatch)
    res = client.get(f"/api/assessments/{asn.id}/report/pdf", headers=admin_headers)
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content == b"%PDF-report"
    assert 'filename="AIDA_Report_API Report Test.pdf"' in res.headers["content-disposition"]


def test_pdf_report_filename_suffixes(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    seen = {}

    async def fake_pdf(db, assessment_id, include_secrets=False, template="default"):
        seen["include_secrets"] = include_secrets
        seen["template"] = template
        buf = io.BytesIO(b"%PDF-x")
        buf.seek(0)
        return buf

    monkeypatch.setattr("api.reports.generate_pdf_report", fake_pdf)
    res = client.get(f"/api/assessments/{asn.id}/report/pdf",
                     params={"include_secrets": True, "template": "owasp"},
                     headers=admin_headers)
    assert res.status_code == 200
    assert seen == {"include_secrets": True, "template": "owasp"}
    assert 'filename="AIDA_Report_API Report Test_with_creds_owasp.pdf"' in res.headers[
        "content-disposition"]


def test_pdf_report_not_found(client, db, admin_headers, monkeypatch):
    _make_fake_pdf(monkeypatch)
    res = client.get("/api/assessments/999999/report/pdf", headers=admin_headers)
    assert res.status_code == 404


def test_pdf_report_bad_template(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    _make_fake_pdf(monkeypatch)
    res = client.get(f"/api/assessments/{asn.id}/report/pdf",
                     params={"template": "nope"}, headers=admin_headers)
    assert res.status_code == 400
    assert "template must be one of" in res.json()["detail"]
