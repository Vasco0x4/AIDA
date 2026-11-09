"""Card (finding/observation/info) router integration tests."""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.card import Card


def make_assessment(db, name="A"):
    a = Assessment(name=name, scope="127.0.0.1", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def make_card(db, assessment_id, title="Finding X", card_type="finding", **kw):
    kw.setdefault("severity", "HIGH")
    kw.setdefault("status", "confirmed")
    c = Card(assessment_id=assessment_id, card_type=card_type, title=title, **kw)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


# --- auth ----------------------------------------------------------------------

def test_cards_require_token_and_role(client, db):
    assert client.get("/api/assessments/1/cards").status_code == 401
    assert client.get("/api/findings").status_code == 401

    a = make_assessment(db)
    assert client.get(f"/api/assessments/{a.id}/cards",
                      headers=None or {}).status_code == 401


def test_viewer_read_ok_write_forbidden(client, db, viewer_headers):
    a = make_assessment(db)
    assert client.get(f"/api/assessments/{a.id}/cards",
                      headers=viewer_headers).status_code == 200
    r = client.post(f"/api/assessments/{a.id}/cards", headers=viewer_headers,
                    json={"card_type": "finding", "title": "T"})
    assert r.status_code == 403
    r = client.delete(f"/api/assessments/{a.id}/cards/1", headers=viewer_headers)
    assert r.status_code == 403


# --- global findings dashboard -------------------------------------------------

def test_list_all_findings_only_findings(client, db, admin_headers):
    a1 = make_assessment(db, "One")
    a2 = make_assessment(db, "Two")
    make_card(db, a1.id, title="F1", card_type="finding")
    make_card(db, a2.id, title="O1", card_type="observation")
    make_card(db, a2.id, title="F2", card_type="finding")

    r = client.get("/api/findings", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert sorted(f["title"] for f in body) == ["F1", "F2"]  # newest first, but
    # rows created in the same transaction can share a timestamp, so only the
    # membership/type filtering is asserted here
    assert all(f["card_type"] == "finding" for f in body)
    by_title = {f["title"]: f["assessment_name"] for f in body}
    assert by_title["F1"] == "One"
    assert by_title["F2"] == "Two"


def test_list_all_findings_empty(client, db, admin_headers):
    r = client.get("/api/findings", headers=admin_headers)
    assert r.status_code == 200
    assert r.json() == []


# --- per-assessment CRUD -------------------------------------------------------

def test_list_cards_requires_assessment(client, db, admin_headers):
    assert client.get("/api/assessments/9/cards",
                      headers=admin_headers).status_code == 404


def test_list_cards_with_type_filter_and_order(client, db, admin_headers):
    a = make_assessment(db)
    make_card(db, a.id, title="Obs", card_type="observation", section_number="2")
    make_card(db, a.id, title="F1", card_type="finding", section_number="3.1")
    make_card(db, a.id, title="Info", card_type="info", section_number="1")

    r = client.get(f"/api/assessments/{a.id}/cards", headers=admin_headers)
    assert r.status_code == 200
    assert [c["title"] for c in r.json()] == ["Info", "Obs", "F1"]  # by section

    r = client.get(f"/api/assessments/{a.id}/cards", headers=admin_headers,
                   params={"card_type": "finding"})
    assert [c["title"] for c in r.json()] == ["F1"]


def test_get_card_scoped_to_assessment(client, db, admin_headers):
    a1 = make_assessment(db, "Owner")
    a2 = make_assessment(db, "Other")
    card = make_card(db, a1.id, title="Scoped")

    assert client.get(f"/api/assessments/{a1.id}/cards/{card.id}",
                      headers=admin_headers).status_code == 200
    # same card id under a different assessment id → 404 (scoping)
    r = client.get(f"/api/assessments/{a2.id}/cards/{card.id}",
                   headers=admin_headers)
    assert r.status_code == 404
    assert client.get(f"/api/assessments/{a1.id}/cards/999",
                      headers=admin_headers).status_code == 404


def test_create_card_happy_path(client, db, admin_headers):
    a = make_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/cards", headers=admin_headers, json={
        "card_type": "finding", "title": "RCE via deserialization",
        "severity": "CRITICAL", "status": "potential", "target_service": "api",
        "cvss_vector": "CVSS:4.0/AV:N/AC:L", "cvss_score": 9.1,
        "technical_analysis": "analysis", "proof": "proof", "notes": "n",
        "compliance_refs": {"owasp": ["A08:2021"]},
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] > 0
    assert body["assessment_id"] == a.id
    assert body["severity"] == "CRITICAL"
    assert body["compliance_refs"] == {"owasp": ["A08:2021"]}
    assert db.query(Card).count() == 1


def test_create_card_invalid_type_and_missing_assessment(client, db, admin_headers):
    a = make_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/cards", headers=admin_headers,
                    json={"card_type": "vulnerability", "title": "T"})
    assert r.status_code == 400
    assert "card_type must be one of" in r.json()["detail"]

    r = client.post("/api/assessments/42/cards", headers=admin_headers,
                    json={"card_type": "finding", "title": "T"})
    assert r.status_code == 404

    r = client.post(f"/api/assessments/{a.id}/cards", headers=admin_headers,
                    json={"card_type": "finding"})
    assert r.status_code == 422


def test_update_card_partial_put_and_patch(client, db, admin_headers):
    a = make_assessment(db)
    card = make_card(db, a.id, title="Before", severity="LOW", status="untested",
                     notes="keep me")

    r = client.put(f"/api/assessments/{a.id}/cards/{card.id}", headers=admin_headers,
                   json={"severity": "HIGH"})
    assert r.status_code == 200
    body = r.json()
    assert body["severity"] == "HIGH"
    assert body["title"] == "Before"      # untouched
    assert body["notes"] == "keep me"     # partial update does not reset fields

    r = client.patch(f"/api/assessments/{a.id}/cards/{card.id}", headers=admin_headers,
                     json={"status": "confirmed"})
    assert r.status_code == 200
    assert r.json()["status"] == "confirmed"

    # invalid card_type on update too
    r = client.put(f"/api/assessments/{a.id}/cards/{card.id}", headers=admin_headers,
                   json={"card_type": "weird"})
    assert r.status_code == 400

    assert client.put(f"/api/assessments/{a.id}/cards/999", headers=admin_headers,
                      json={"title": "x"}).status_code == 404


def test_update_card_scoped_to_assessment(client, db, admin_headers):
    a1 = make_assessment(db, "Owner")
    a2 = make_assessment(db, "Other")
    card = make_card(db, a1.id, title="Scoped")
    r = client.put(f"/api/assessments/{a2.id}/cards/{card.id}", headers=admin_headers,
                   json={"title": "Hijack"})
    assert r.status_code == 404


def test_delete_card(client, db, admin_headers):
    a = make_assessment(db)
    card = make_card(db, a.id, title="Doomed")
    r = client.delete(f"/api/assessments/{a.id}/cards/{card.id}",
                      headers=admin_headers)
    assert r.status_code == 204
    assert db.query(Card).count() == 0
    assert client.delete(f"/api/assessments/{a.id}/cards/{card.id}",
                         headers=admin_headers).status_code == 404


@pytest.mark.parametrize("payload,missing", [
    ({"card_type": "finding"}, "title"),
    ({"title": "T"}, "card_type"),
])
def test_create_card_validation_422(client, db, admin_headers, payload, missing):
    a = make_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/cards", headers=admin_headers,
                    json=payload)
    assert r.status_code == 422
