"""Submission-report router integration tests.

The LLM call is stubbed at the service boundary (api.submission.generate_submission)
and the evidence disk mirror is redirected to a tmp dir; PDF rendering uses the
real (local, hermetic) WeasyPrint pipeline."""
from __future__ import annotations

import base64

import pytest

from models.artifact import Artifact
from models.assessment import Assessment
from models.card import Card

from api.submission import _figures_for_card, _safe_filename

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg"
    "YGBgAAAABQABh6FO1AAAAABJRU5ErkJggg==")


def make_world(db):
    a = Assessment(name="Sub", scope="127.0.0.1", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    card = Card(assessment_id=a.id, card_type="finding", title="SSRF in webhook",
                severity="HIGH", status="confirmed", target_service="api")
    db.add(card)
    db.commit()
    db.refresh(card)
    return a, card


@pytest.fixture()
def evidence_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    return tmp_path


# --- platforms -----------------------------------------------------------------

def test_list_platforms(client, db, admin_headers):
    r = client.get("/api/submission/platforms", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    ids = [p["id"] for p in body]
    assert "hackerone" in ids and "bugcrowd" in ids and "generic" in ids
    assert all(p["label"] == p["id"].capitalize() for p in body)


# --- render-pdf ----------------------------------------------------------------

def test_render_pdf_requires_token_and_body(client, db, admin_headers):
    assert client.post("/api/submission/render-pdf",
                       json={"markdown": "# x"}).status_code == 401
    r = client.post("/api/submission/render-pdf", headers=admin_headers,
                    json={"markdown": "   "})
    assert r.status_code == 422


def test_render_pdf_happy_path(client, db, admin_headers):
    r = client.post("/api/submission/render-pdf", headers=admin_headers, json={
        "markdown": "# Report\n\n**SQL injection** found.\n\n```\ncurl -X ' http://t\n```",
        "title": "Quarterly Audit", "filename": "My Report!! 2026",
    })
    assert r.status_code == 200, r.text
    assert r.content[:5] == b"%PDF-"
    assert r.headers["content-type"] == "application/pdf"
    assert "My-Report-2026.pdf" in r.headers["content-disposition"]


def test_render_pdf_filename_fallbacks(client, db, admin_headers):
    r = client.post("/api/submission/render-pdf", headers=admin_headers,
                    json={"markdown": "x", "filename": "///", "title": None})
    assert r.status_code == 200
    assert 'filename="report.pdf"' in r.headers["content-disposition"]

    r = client.post("/api/submission/render-pdf", headers=admin_headers,
                    json={"markdown": "x", "title": "Titre Ünïcode"})
    assert r.status_code == 200
    assert "Titre-n-code.pdf" in r.headers["content-disposition"]


def test_render_pdf_with_card_screenshots(client, db, admin_headers):
    a, card = make_world(db)
    db.add(Artifact(assessment_id=a.id, card_id=card.id, kind="screenshot",
                    filename="proof.png", content_type="image/png",
                    caption="Command output", size_bytes=len(PNG_1PX), data=PNG_1PX))
    db.commit()

    plain = client.post("/api/submission/render-pdf", headers=admin_headers,
                        json={"markdown": "# M", "title": "T"}).content
    with_figs = client.post("/api/submission/render-pdf", headers=admin_headers,
                            json={"markdown": "# M", "title": "T",
                                  "card_id": card.id}).content
    assert with_figs[:5] == b"%PDF-"
    assert len(with_figs) > len(plain)  # embedded evidence inflates the PDF


def test_render_pdf_failure_500(client, db, admin_headers, monkeypatch):
    def _boom(markdown_text, title=None, figures=None):
        raise RuntimeError("weasyprint exploded")

    monkeypatch.setattr("api.submission.markdown_to_pdf", _boom)
    r = client.post("/api/submission/render-pdf", headers=admin_headers,
                    json={"markdown": "# x"})
    assert r.status_code == 500
    assert "PDF render failed" in r.json()["detail"]


# --- figure selection helpers --------------------------------------------------

def test_figures_for_card_selection_rules(db):
    a, card = make_world(db)
    other = Card(assessment_id=a.id, card_type="finding", title="Other",
                 severity="LOW", status="confirmed")
    db.add(other)
    db.commit()
    db.refresh(other)

    assert _figures_for_card(db, None) == []
    assert _figures_for_card(db, other.id) == []  # no artifacts → nothing

    db.add_all([
        Artifact(assessment_id=a.id, card_id=card.id, kind="screenshot",
                 filename="ok.png", content_type="image/png",
                 size_bytes=len(PNG_1PX), data=PNG_1PX),
        Artifact(assessment_id=a.id, card_id=card.id, kind="file",
                 filename="notes.txt", content_type="text/plain",
                 size_bytes=4, data=b"text"),  # not an image → skipped
        Artifact(assessment_id=a.id, card_id=card.id, kind="screenshot",
                 filename="huge.png", content_type="image/png",
                 size_bytes=9 * 1024 * 1024, data=b"\x89PNG" + b"x" * (9 * 1024 * 1024)),
    ])
    db.commit()
    figs = _figures_for_card(db, card.id)
    assert len(figs) == 1  # only the small image
    assert figs[0]["caption"] == "ok.png"
    assert figs[0]["data_uri"].startswith("data:image/png;base64,")


def test_figures_for_card_caps_at_fifteen(db):
    a, card = make_world(db)
    for i in range(17):
        db.add(Artifact(assessment_id=a.id, card_id=card.id, kind="screenshot",
                        filename=f"s{i}.png", content_type="image/png",
                        size_bytes=len(PNG_1PX), data=PNG_1PX))
    db.commit()
    figs = _figures_for_card(db, card.id)
    assert len(figs) == 15  # _MAX_FIGURES cap: extras dropped, no error


def test_safe_filename():
    assert _safe_filename("a b/c:d", "fb") == "a-b-c-d"
    assert _safe_filename("", "fb") == "fb"
    assert _safe_filename("!!!", "fb") == "fb"
    assert _safe_filename("ok.txt", "fb") == "ok.txt"


# --- generate ------------------------------------------------------------------

def test_generate_auth_and_validation(client, db, admin_headers, viewer_headers):
    assert client.post("/api/submission/1", json={}).status_code == 401
    _a, card = make_world(db)
    r = client.post(f"/api/submission/{card.id}", headers=viewer_headers, json={})
    assert r.status_code == 403
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers)
    assert r.status_code == 422  # body required


def test_generate_card_not_found(client, db, admin_headers):
    r = client.post("/api/submission/999", headers=admin_headers, json={})
    assert r.status_code == 404
    assert "Finding not found" in r.json()["detail"]


def test_generate_without_ai_model_400(client, db, admin_headers):
    _a, card = make_world(db)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers, json={})
    assert r.status_code == 400
    assert "No AI model configured" in r.json()["detail"]


@pytest.fixture()
def fake_generate(monkeypatch):
    calls = {}

    async def _fake(db, card_id, platform="hackerone"):
        calls["card_id"] = card_id
        calls["platform"] = platform
        return {"card_id": card_id, "platform": platform,
                "report_markdown": "# Fake Report\n\nGenerated content.",
                "precedents": [{"title": "p1", "url": "https://x.test/1"}]}

    monkeypatch.setattr("api.submission.generate_submission", _fake)
    return calls


def test_generate_happy_no_save(client, db, admin_headers, fake_generate):
    _a, card = make_world(db)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers,
                    json={"platform": "HACKERONE"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["platform"] == "hackerone"
    assert "# Fake Report" in body["report_markdown"]
    assert fake_generate["card_id"] == card.id
    assert fake_generate["platform"] == "hackerone"  # normalized (lowered)
    assert db.query(Artifact).count() == 0  # save=False → nothing persisted


def test_generate_unknown_platform_falls_back_to_generic(client, db, admin_headers,
                                                         fake_generate):
    _a, card = make_world(db)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers,
                    json={"platform": "intigriti"})
    assert r.status_code == 200
    assert fake_generate["platform"] == "generic"


def test_generate_save_as_markdown_artifact(client, db, admin_headers, fake_generate,
                                            evidence_tmp):
    a, card = make_world(db)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers,
                    json={"platform": "bugcrowd", "save": True, "format": "md"})
    assert r.status_code == 200, r.text
    body = r.json()
    art = db.query(Artifact).first()
    assert art is not None
    assert art.assessment_id == a.id
    assert art.card_id == card.id
    assert art.filename == f"submission-bugcrowd-card{card.id}.md"
    assert art.content_type == "text/markdown"
    assert b"Fake Report" in bytes(art.data)
    assert body["artifact_id"] == art.id
    assert body["format"] == "md"
    assert body["disk_path"]
    mirrored = list(evidence_tmp.rglob(f"*{art.id:04d}*"))
    assert len(mirrored) == 1


def test_generate_save_as_pdf_artifact(client, db, admin_headers, fake_generate,
                                       evidence_tmp):
    _a, card = make_world(db)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers,
                    json={"platform": "hackerone", "save": True})
    assert r.status_code == 200, r.text
    body = r.json()
    art = db.query(Artifact).first()
    assert art.filename.endswith(".pdf")
    assert art.content_type == "application/pdf"
    assert bytes(art.data)[:5] == b"%PDF-"
    assert body["format"] == "pdf"
    assert art.hash_self  # chained via the mirror hook


def test_generate_save_but_card_deleted(client, db, admin_headers, fake_generate):
    a, card = make_world(db)
    db.delete(card)
    db.commit()
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers,
                    json={"save": True})
    assert r.status_code == 404
    assert "Finding not found" in r.json()["detail"]
    assert db.query(Artifact).count() == 0


def test_generate_error_mapping(client, db, admin_headers, monkeypatch):
    _a, card = make_world(db)

    async def _runtime(db, card_id, platform="hackerone"):
        raise RuntimeError("Model error: timeout")

    monkeypatch.setattr("api.submission.generate_submission", _runtime)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers, json={})
    assert r.status_code == 400

    async def _value(db, card_id, platform="hackerone"):
        raise ValueError("Finding not found")

    monkeypatch.setattr("api.submission.generate_submission", _value)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers, json={})
    assert r.status_code == 404


def test_generate_save_pdf_render_failure(client, db, admin_headers, fake_generate,
                                          monkeypatch):
    _a, card = make_world(db)

    def _boom(markdown_text, title=None, figures=None):
        raise RuntimeError("no fonts")

    monkeypatch.setattr("api.submission.markdown_to_pdf", _boom)
    r = client.post(f"/api/submission/{card.id}", headers=admin_headers,
                    json={"save": True})
    assert r.status_code == 500
    assert "PDF render failed" in r.json()["detail"]
