"""Assessment sections (phases) router integration tests."""
from __future__ import annotations

from decimal import Decimal

from models.assessment import Assessment
from models.assessment_section import AssessmentSection


def make_assessment(db, name="A"):
    a = Assessment(name=name, scope="127.0.0.1", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def make_section(db, assessment_id, section_type="recon", number=1.0, **kw):
    s = AssessmentSection(assessment_id=assessment_id, section_type=section_type,
                          section_number=Decimal(str(number)), **kw)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# --- auth ----------------------------------------------------------------------

def test_sections_require_token_and_role(client, db):
    assert client.get("/api/assessments/1/sections").status_code == 401


def test_viewer_read_ok_write_forbidden(client, db, viewer_headers):
    a = make_assessment(db)
    assert client.get(f"/api/assessments/{a.id}/sections",
                      headers=viewer_headers).status_code == 200
    r = client.post(f"/api/assessments/{a.id}/sections", headers=viewer_headers,
                    json={"section_type": "recon", "section_number": 1.0})
    assert r.status_code == 403
    r = client.delete(f"/api/assessments/{a.id}/sections/1", headers=viewer_headers)
    assert r.status_code == 403


# --- list ----------------------------------------------------------------------

def test_list_sections_ordered_missing_assessment(client, db, admin_headers):
    assert client.get("/api/assessments/3/sections",
                      headers=admin_headers).status_code == 404

    a = make_assessment(db)
    make_section(db, a.id, "phase_1", 2.0, title="Phase 1")
    make_section(db, a.id, "recon", 1.0, title="Recon")
    make_section(db, a.id, "phase_2", 2.5, title="Phase 2")

    r = client.get(f"/api/assessments/{a.id}/sections", headers=admin_headers)
    assert r.status_code == 200
    assert [s["title"] for s in r.json()] == ["Recon", "Phase 1", "Phase 2"]


# --- create / upsert -----------------------------------------------------------

def test_create_section(client, db, admin_headers):
    a = make_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/sections", headers=admin_headers,
                    json={"section_type": "phase_1", "section_number": 2.0,
                          "title": "Exploitation", "content": "steps..."})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["assessment_id"] == a.id
    assert body["title"] == "Exploitation"
    assert float(body["section_number"]) == 2.0
    assert db.query(AssessmentSection).count() == 1


def test_create_section_upserts_same_type_and_number(client, db, admin_headers):
    a = make_assessment(db)
    make_section(db, a.id, "recon", 1.0, title="Old", content="old content")

    # same (type, number) → update in place, no new row
    r = client.post(f"/api/assessments/{a.id}/sections", headers=admin_headers,
                    json={"section_type": "recon", "section_number": 1.0,
                          "title": "New"})
    assert r.status_code == 201
    assert r.json()["title"] == "New"
    assert db.query(AssessmentSection).count() == 1

    # partial upsert must not blank the fields the client omitted
    r = client.post(f"/api/assessments/{a.id}/sections", headers=admin_headers,
                    json={"section_type": "recon", "section_number": 1.0,
                          "content": "added later"})
    assert r.status_code == 201
    body = r.json()
    assert body["content"] == "added later"
    assert body["title"] == "New"

    # different number → new row
    r = client.post(f"/api/assessments/{a.id}/sections", headers=admin_headers,
                    json={"section_type": "recon", "section_number": 1.1})
    assert db.query(AssessmentSection).count() == 2


def test_create_section_missing_assessment_and_validation(client, db, admin_headers):
    assert client.post("/api/assessments/8/sections", headers=admin_headers,
                       json={"section_type": "recon", "section_number": 1.0}
                       ).status_code == 404

    a = make_assessment(db)
    r = client.post(f"/api/assessments/{a.id}/sections", headers=admin_headers,
                    json={"section_type": "recon"})
    assert r.status_code == 422
    r = client.post(f"/api/assessments/{a.id}/sections", headers=admin_headers,
                    json={"section_number": 1.0})
    assert r.status_code == 422


# --- update --------------------------------------------------------------------

def test_update_section(client, db, admin_headers):
    a = make_assessment(db)
    s = make_section(db, a.id, "recon", 1.0, title="Old", content="c")

    r = client.put(f"/api/assessments/{a.id}/sections/{s.id}", headers=admin_headers,
                   json={"title": "Updated"})
    assert r.status_code == 200
    assert r.json()["title"] == "Updated"
    assert r.json()["content"] == "c"

    assert client.put(f"/api/assessments/{a.id}/sections/999", headers=admin_headers,
                      json={"title": "x"}).status_code == 404

    # section of another assessment is invisible
    b = make_assessment(db, "B")
    assert client.put(f"/api/assessments/{b.id}/sections/{s.id}",
                      headers=admin_headers,
                      json={"title": "x"}).status_code == 404


# --- delete --------------------------------------------------------------------

def test_delete_section(client, db, admin_headers):
    a = make_assessment(db)
    s = make_section(db, a.id, "recon", 1.0)
    r = client.delete(f"/api/assessments/{a.id}/sections/{s.id}",
                      headers=admin_headers)
    assert r.status_code == 204
    assert db.query(AssessmentSection).count() == 0
    assert client.delete(f"/api/assessments/{a.id}/sections/{s.id}",
                         headers=admin_headers).status_code == 404
