"""
Recon Data API — /api/assessments/{id}/recon.

CRUD + batch import + data_type normalization (free-form categories are
lowercased/snake_cased by the Pydantic validator) + the /types distinct listing.
"""
from __future__ import annotations

from models.assessment import Assessment
from models.recon_data import ReconData


def _assessment(db, name="recon-assess"):
    a = Assessment(name=name, scope="example.com")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _row(db, assessment, data_type="subdomain", name="x.example.com", **kw):
    row = ReconData(assessment_id=assessment.id, data_type=data_type, name=name,
                    details=kw.pop("details", None),
                    discovered_in_phase=kw.pop("discovered_in_phase", "recon"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------------ list
def test_recon_endpoints_require_auth(client, db):
    a = _assessment(db)
    assert client.get(f"/api/assessments/{a.id}/recon").status_code == 401
    assert client.get(f"/api/assessments/{a.id}/recon/types").status_code == 401


def test_list_unknown_assessment_404(client, admin_headers):
    assert client.get("/api/assessments/666/recon",
                      headers=admin_headers).status_code == 404


def test_list_orders_and_filters_by_type(client, db, admin_headers):
    a = _assessment(db)
    _row(db, a, "subdomain", "b.example.com")
    _row(db, a, "endpoint", "/api/v1/users")
    _row(db, a, "subdomain", "a.example.com")

    r = client.get(f"/api/assessments/{a.id}/recon", headers=admin_headers)
    assert r.status_code == 200
    assert [x["name"] for x in r.json()] == \
        ["b.example.com", "/api/v1/users", "a.example.com"]  # created_at asc

    r = client.get(f"/api/assessments/{a.id}/recon",
                   params={"data_type": "subdomain"}, headers=admin_headers)
    assert [x["name"] for x in r.json()] == ["b.example.com", "a.example.com"]


def test_types_distinct_sorted(client, db, admin_headers):
    a = _assessment(db)
    _row(db, a, "subdomain", "s1")
    _row(db, a, "endpoint", "e1")
    _row(db, a, "subdomain", "s2")
    r = client.get(f"/api/assessments/{a.id}/recon/types", headers=admin_headers)
    assert r.json() == ["endpoint", "subdomain"]


def test_types_unknown_assessment_404(client, admin_headers):
    assert client.get("/api/assessments/667/recon/types",
                      headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ create
def test_create_normalizes_data_type(client, db, admin_headers):
    a = _assessment(db)
    r = client.post(f"/api/assessments/{a.id}/recon", headers=admin_headers, json={
        "data_type": "Data Base-Table", "name": "users table",
        "details": {"engine": "postgres"}, "discovered_in_phase": "enum"})
    assert r.status_code == 201
    body = r.json()
    assert body["data_type"] == "data_base_table"
    assert body["details"] == {"engine": "postgres"}
    assert db.query(ReconData).one().data_type == "data_base_table"


def test_create_unknown_assessment_404(client, admin_headers):
    r = client.post("/api/assessments/668/recon", headers=admin_headers,
                    json={"data_type": "subdomain", "name": "x"})
    assert r.status_code == 404


def test_create_validation_422(client, db, admin_headers):
    a = _assessment(db)
    for bad in ({"name": "no type"},                # data_type required
                {"data_type": "subdomain"}):        # name required
        r = client.post(f"/api/assessments/{a.id}/recon",
                        headers=admin_headers, json=bad)
        assert r.status_code == 422, bad


# ------------------------------------------------------------------ batch
def test_batch_creates_entries_and_summary(client, db, admin_headers):
    a = _assessment(db)
    r = client.post(f"/api/assessments/{a.id}/recon/batch", headers=admin_headers,
                    json={"entries": [
                        {"data_type": "Subdomain", "name": "a.example.com"},
                        {"data_type": "technology", "name": "nginx",
                         "details": {"version": "1.25"}},
                        {"data_type": "subdomain", "name": "b.example.com"},
                    ]})
    assert r.status_code == 201
    body = r.json()
    assert body["created_count"] == 3
    assert body["summary"] == {"subdomain": 2, "technology": 1}
    assert len(body["entries"]) == 3
    assert db.query(ReconData).count() == 3


def test_batch_empty_entries_400(client, db, admin_headers):
    a = _assessment(db)
    r = client.post(f"/api/assessments/{a.id}/recon/batch",
                    headers=admin_headers, json={"entries": []})
    assert r.status_code == 400
    assert "No entries" in r.json()["detail"]


def test_batch_invalid_entry_400_and_nothing_persisted(client, db, admin_headers):
    a = _assessment(db)
    r = client.post(f"/api/assessments/{a.id}/recon/batch", headers=admin_headers,
                    json={"entries": [
                        {"data_type": "subdomain", "name": "ok.example.com"},
                        {"data_type": "subdomain"},   # missing name
                    ]})
    assert r.status_code == 400
    assert "Invalid entry" in r.json()["detail"]
    assert db.query(ReconData).count() == 0


def test_batch_unknown_assessment_404(client, admin_headers):
    r = client.post("/api/assessments/669/recon/batch", headers=admin_headers,
                    json={"entries": [{"data_type": "x", "name": "y"}]})
    assert r.status_code == 404


# ------------------------------------------------------------------ update
def test_patch_recon_partial(client, db, admin_headers):
    a = _assessment(db)
    row = _row(db, a, "endpoint", "/old")
    r = client.patch(f"/api/assessments/{a.id}/recon/{row.id}",
                     headers=admin_headers,
                     json={"name": "/new", "details": {"status": 301}})
    assert r.status_code == 200
    assert r.json()["name"] == "/new"
    assert r.json()["data_type"] == "endpoint"
    assert r.json()["details"] == {"status": 301}


def test_patch_recon_404_wrong_assessment_or_id(client, db, admin_headers):
    a = _assessment(db)
    other = _assessment(db, "recon-other")
    row = _row(db, a)
    assert client.patch(f"/api/assessments/{other.id}/recon/{row.id}",
                        headers=admin_headers,
                        json={"name": "x"}).status_code == 404
    assert client.patch(f"/api/assessments/{a.id}/recon/999",
                        headers=admin_headers,
                        json={"name": "x"}).status_code == 404


# ------------------------------------------------------------------ delete
def test_delete_recon(client, db, admin_headers):
    a = _assessment(db)
    row = _row(db, a)
    r = client.delete(f"/api/assessments/{a.id}/recon/{row.id}",
                      headers=admin_headers)
    assert r.status_code == 204
    assert db.query(ReconData).count() == 0
    assert client.delete(f"/api/assessments/{a.id}/recon/{row.id}",
                         headers=admin_headers).status_code == 404


def test_recon_write_requires_auditor(client, db, viewer_headers):
    a = _assessment(db)
    r = client.post(f"/api/assessments/{a.id}/recon", headers=viewer_headers,
                    json={"data_type": "subdomain", "name": "x"})
    assert r.status_code == 403
