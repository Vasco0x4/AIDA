"""Folder router integration tests."""
from __future__ import annotations

from models.assessment import Assessment
from models.folder import Folder


def make_folder(db, name="Folder", **kw):
    f = Folder(name=name, **kw)
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def make_assessment(db, name="A", folder_id=None):
    a = Assessment(name=name, scope="127.0.0.1", status="active",
                   folder_id=folder_id)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# --- auth ----------------------------------------------------------------------

def test_folders_require_token(client, db):
    assert client.get("/api/folders").status_code == 401
    assert client.get("/api/folders/1").status_code == 401


def test_viewer_read_ok_write_forbidden(client, db, viewer_headers):
    assert client.get("/api/folders", headers=viewer_headers).status_code == 200
    r = client.post("/api/folders", headers=viewer_headers, json={"name": "F"})
    assert r.status_code == 403
    r = client.put("/api/folders/1", headers=viewer_headers, json={"name": "F"})
    assert r.status_code == 403
    r = client.delete("/api/folders/1", headers=viewer_headers)
    assert r.status_code == 403


# --- list / get ----------------------------------------------------------------

def test_list_folders_with_counts(client, db, admin_headers):
    f1 = make_folder(db, "Empty")
    f2 = make_folder(db, "Busy", description="desc", color="#ff0000")
    make_assessment(db, "A1", folder_id=f2.id)
    make_assessment(db, "A2", folder_id=f2.id)
    make_assessment(db, "A3")  # unfiled

    r = client.get("/api/folders", headers=admin_headers)
    assert r.status_code == 200
    body = {f["name"]: f for f in r.json()}
    assert body["Empty"]["assessment_count"] == 0
    assert body["Busy"]["assessment_count"] == 2
    assert body["Busy"]["description"] == "desc"
    assert body["Busy"]["color"] == "#ff0000"

    r = client.get(f"/api/folders/{f1.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Empty"
    assert client.get("/api/folders/999", headers=admin_headers).status_code == 404


# --- create --------------------------------------------------------------------

def test_create_folder(client, db, admin_headers):
    r = client.post("/api/folders", headers=admin_headers,
                    json={"name": "2026 Engagements", "description": "d"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["id"] > 0
    assert body["name"] == "2026 Engagements"
    assert body["color"] == "#06b6d4"  # default
    assert db.query(Folder).count() == 1


def test_create_folder_duplicate_name(client, db, admin_headers):
    make_folder(db, "Dup")
    r = client.post("/api/folders", headers=admin_headers, json={"name": "Dup"})
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"]


def test_create_folder_validation_422(client, db, admin_headers):
    r = client.post("/api/folders", headers=admin_headers, json={})
    assert r.status_code == 422
    r = client.post("/api/folders", headers=admin_headers,
                    json={"name": None})
    assert r.status_code == 422


# --- update --------------------------------------------------------------------

def test_update_folder(client, db, admin_headers):
    f = make_folder(db, "Before", description="d")
    r = client.put(f"/api/folders/{f.id}", headers=admin_headers,
                   json={"name": "After", "color": "#123456"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "After"
    assert body["color"] == "#123456"
    assert body["description"] == "d"  # untouched

    assert client.put("/api/folders/999", headers=admin_headers,
                      json={"name": "x"}).status_code == 404


# --- delete --------------------------------------------------------------------

def test_delete_folder_detaches_assessments(client, db, admin_headers):
    f = make_folder(db, "Doomed")
    a = make_assessment(db, "Kept", folder_id=f.id)
    r = client.delete(f"/api/folders/{f.id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.query(Folder).count() == 0
    db.refresh(a)
    assert a.folder_id is None  # assessment survives, unfiled

    assert client.delete("/api/folders/999", headers=admin_headers).status_code == 404


def test_list_folder_counts_use_constant_number_of_queries(client, db, admin_headers):
    """Regression: five folders must not cause one COUNT query per folder."""
    from sqlalchemy import event

    for index in range(5):
        folder = make_folder(db, f"Counted {index}")
        make_assessment(db, f"Assessment {index}", folder_id=folder.id)

    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        response = client.get("/api/folders", headers=admin_headers)
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)

    assert response.status_code == 200
    assert {row["assessment_count"] for row in response.json()} == {1}
    # One authentication SELECT plus one folders/counts SELECT.
    assert len(statements) <= 2, f"Expected <=2 SELECTs, got {len(statements)}"
