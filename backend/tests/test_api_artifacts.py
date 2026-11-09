"""Artifact (evidence files) router integration tests.

The disk mirror under /evidence is redirected to a per-test tmp dir so nothing
touches the host evidence mount; the DB copy and hash chain stay fully real."""
from __future__ import annotations

from models.artifact import Artifact
from models.assessment import Assessment
from models.audit_log import AuditLog
from models.card import Card


def make_assessment(db, name="A"):
    a = Assessment(name=name, scope="127.0.0.1", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def make_card(db, assessment_id, title="F"):
    c = Card(assessment_id=assessment_id, card_type="finding", title=title,
             severity="HIGH", status="confirmed")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def upload(client, headers, assessment_id, data=b"PNGDATA", filename="shot.png",
           ctype="image/png", **form):
    return client.post(
        f"/api/assessments/{assessment_id}/artifacts", headers=headers,
        files={"file": (filename, data, ctype)}, data=form)


# --- auth ----------------------------------------------------------------------

def test_artifacts_require_token_and_role(client, db):
    assert client.get("/api/assessments/1/artifacts").status_code == 401
    assert client.get("/api/assessments/1/artifacts/chain").status_code == 401


def test_viewer_read_ok_write_forbidden(client, db, viewer_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    a = make_assessment(db)
    assert client.get(f"/api/assessments/{a.id}/artifacts",
                      headers=viewer_headers).status_code == 200
    assert client.get(f"/api/assessments/{a.id}/artifacts/chain",
                      headers=viewer_headers).status_code == 200
    r = upload(client, viewer_headers, a.id)
    assert r.status_code == 403
    r = client.delete("/api/artifacts/1", headers=viewer_headers)
    assert r.status_code == 403


# --- upload --------------------------------------------------------------------

def test_upload_and_list_artifacts(client, db, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    a = make_assessment(db)
    card = make_card(db, a.id)

    r = upload(client, admin_headers, a.id, data=b"image-bytes",
               caption="Login page", kind="screenshot", card_id=str(card.id))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["assessment_id"] == a.id
    assert body["card_id"] == card.id
    assert body["kind"] == "screenshot"
    assert body["filename"] == "shot.png"
    assert body["content_type"] == "image/png"
    assert body["size_bytes"] == len(b"image-bytes")
    assert body["hash_self"]  # chained at upload

    r = upload(client, admin_headers, a.id, data=b"raw", filename="notes.txt",
               ctype="text/plain", kind="weird-kind")
    assert r.status_code == 201
    assert r.json()["kind"] == "file"  # unknown kinds normalize to "file"
    assert r.json()["card_id"] is None

    rows = db.query(Artifact).all()
    assert len(rows) == 2
    # mirrored to the redirected evidence dir
    mirrored = list(tmp_path.rglob("*shot.png"))
    assert len(mirrored) == 1

    r = client.get(f"/api/assessments/{a.id}/artifacts", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get(f"/api/assessments/{a.id}/artifacts", headers=admin_headers,
                   params={"card_id": card.id})
    assert [x["filename"] for x in r.json()] == ["shot.png"]


def test_upload_not_found_and_size_limits(client, db, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    assert upload(client, admin_headers, 999).status_code == 404

    a = make_assessment(db)
    assert upload(client, admin_headers, a.id, card_id="999").status_code == 404

    r = upload(client, admin_headers, a.id, data=b"")
    assert r.status_code == 422

    big = b"x" * (15 * 1024 * 1024 + 1)
    r = upload(client, admin_headers, a.id, data=big)
    assert r.status_code == 413
    assert db.query(Artifact).count() == 0


# --- content -------------------------------------------------------------------

def test_artifact_content_streaming(client, db, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    a = make_assessment(db)
    art_id = upload(client, admin_headers, a.id, data=b"BYTES-1234",
                    filename="cap.png", ctype="image/png").json()["id"]

    r = client.get(f"/api/artifacts/{art_id}/content", headers=admin_headers)
    assert r.status_code == 200
    assert r.content == b"BYTES-1234"
    assert r.headers["content-type"].startswith("image/png")
    assert "cap.png" in r.headers["content-disposition"]
    assert client.get("/api/artifacts/999/content",
                      headers=admin_headers).status_code == 404


# --- delete --------------------------------------------------------------------

def test_delete_artifact_writes_audit(client, db, admin_headers, tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    a = make_assessment(db)
    art_id = upload(client, admin_headers, a.id).json()["id"]

    r = client.delete(f"/api/artifacts/{art_id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.query(Artifact).count() == 0
    logs = db.query(AuditLog).filter(AuditLog.action == "artifact.deleted").all()
    assert len(logs) == 1
    assert logs[0].resource_id == str(art_id)

    assert client.delete(f"/api/artifacts/{art_id}",
                         headers=admin_headers).status_code == 404


# --- evidence hash chain (E3) --------------------------------------------------

def test_evidence_chain_verify_intact_and_tampered(client, db, admin_headers,
                                                   tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence_store.EVIDENCE_DIR", str(tmp_path))
    a = make_assessment(db)

    assert client.get("/api/assessments/999/artifacts/chain",
                      headers=admin_headers).status_code == 404

    r = client.get(f"/api/assessments/{a.id}/artifacts/chain", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "chained": 0, "legacy": 0, "broken_at": None,
                        "status": "intact"}

    first = upload(client, admin_headers, a.id, data=b"one").json()
    second = upload(client, admin_headers, a.id, data=b"two").json()

    r = client.get(f"/api/assessments/{a.id}/artifacts/chain", headers=admin_headers)
    body = r.json()
    assert body["status"] == "intact"
    assert body["chained"] == 2
    assert body["legacy"] == 0
    second_row = db.query(Artifact).filter(Artifact.id == second["id"]).first()
    assert second_row.hash_prev == first["hash_self"]

    # tamper with the second artifact's bytes behind the API's back
    row = db.query(Artifact).filter(Artifact.id == second["id"]).first()
    row.data = b"tampered"
    db.commit()

    body = client.get(f"/api/assessments/{a.id}/artifacts/chain",
                      headers=admin_headers).json()
    assert body["status"] == "BROKEN"
    assert body["ok"] is False
    assert body["broken_at"] == second["id"]

    # legacy artifacts (NULL hash) are skipped, not reported broken
    db.add(Artifact(assessment_id=a.id, kind="file", filename="legacy.bin",
                    content_type="application/octet-stream", data=b"old"))
    db.commit()
    body = client.get(f"/api/assessments/{a.id}/artifacts/chain",
                      headers=admin_headers).json()
    assert body["legacy"] == 1
