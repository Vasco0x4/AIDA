"""
Credentials API — /api/assessments/{id}/credentials + /api/credentials/{id}.

Full CRUD through the API, uniqueness of placeholders per assessment, type
filtering/stats, and by-placeholder lookup. Also pins the storage contract:
secrets round-trip byte-for-byte through create → read (the platform stores
credential values as-is — plaintext — which the command-substitution endpoints
rely on; see report notes).
"""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.credential import Credential


@pytest.fixture()
def assessment(db):
    a = Assessment(name="cred-assessment", scope="example.com")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _cred(db, assessment, placeholder, ctype="bearer_token", **kw):
    row = Credential(
        assessment_id=assessment.id, credential_type=ctype,
        name=kw.pop("name", f"cred-{placeholder}"), placeholder=placeholder,
        token=kw.pop("token", "tok"), username=kw.pop("username", None),
        password=kw.pop("password", None),
        cookie_value=kw.pop("cookie_value", None))
    db.add(row)
    db.commit()
    return row


# ------------------------------------------------------------------ list
def test_list_requires_auth(client, assessment):
    r = client.get(f"/api/assessments/{assessment.id}/credentials")
    assert r.status_code == 401


def test_list_unknown_assessment_404(client, admin_headers):
    assert client.get("/api/assessments/987/credentials",
                      headers=admin_headers).status_code == 404


def test_list_with_type_filter_and_stats(client, db, admin_headers, assessment):
    _cred(db, assessment, "{{A}}", "bearer_token")
    _cred(db, assessment, "{{B}}", "bearer_token")
    _cred(db, assessment, "{{C}}", "cookie", cookie_value="sid=1")

    r = client.get(f"/api/assessments/{assessment.id}/credentials",
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["by_type"] == {"bearer_token": 2, "cookie": 1}

    r = client.get(f"/api/assessments/{assessment.id}/credentials",
                   params={"credential_type": "cookie"}, headers=admin_headers)
    assert [c["placeholder"] for c in r.json()["credentials"]] == ["{{C}}"]


def test_list_scoped_to_assessment(client, db, admin_headers, assessment):
    other = Assessment(name="other-assess")
    db.add(other)
    db.commit()
    _cred(db, assessment, "{{MINE}}")
    _cred(db, other, "{{OTHERS}}")
    r = client.get(f"/api/assessments/{assessment.id}/credentials",
                   headers=admin_headers)
    assert [c["placeholder"] for c in r.json()["credentials"]] == ["{{MINE}}"]


# ------------------------------------------------------------------ create
def test_create_credential_roundtrip(client, db, admin_headers, assessment):
    payload = {
        "credential_type": "basic_auth", "name": "admin login",
        "placeholder": "{{ADMIN_CREDS}}", "username": "adm",
        "password": "s3cr3t-pass", "service": "Web", "target": "example.com",
    }
    r = client.post(f"/api/assessments/{assessment.id}/credentials",
                    headers=admin_headers, json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0 and body["assessment_id"] == assessment.id
    assert body["discovered_by"] == "manual"

    # Round-trip: stored values come back unchanged (relied upon by the
    # {{PLACEHOLDER}} substitution endpoints).
    got = client.get(f"/api/credentials/{body['id']}",
                     headers=admin_headers).json()
    assert got["username"] == "adm" and got["password"] == "s3cr3t-pass"

    row = db.query(Credential).one()
    assert row.password == "s3cr3t-pass"


def test_create_credential_unknown_assessment_404(client, admin_headers):
    r = client.post("/api/assessments/321/credentials", headers=admin_headers,
                    json={"credential_type": "cookie", "name": "x",
                          "placeholder": "{{P}}", "cookie_value": "c"})
    assert r.status_code == 404


def test_create_credential_duplicate_placeholder_409(
        client, db, admin_headers, assessment):
    _cred(db, assessment, "{{DUP}}")
    r = client.post(f"/api/assessments/{assessment.id}/credentials",
                    headers=admin_headers,
                    json={"credential_type": "api_key", "name": "again",
                          "placeholder": "{{DUP}}", "token": "t"})
    assert r.status_code == 409
    assert "{{DUP}}" in r.json()["detail"]
    # Same placeholder on a DIFFERENT assessment is fine.
    other = Assessment(name="second-assess")
    db.add(other)
    db.commit()
    r = client.post(f"/api/assessments/{other.id}/credentials",
                    headers=admin_headers,
                    json={"credential_type": "api_key", "name": "again",
                          "placeholder": "{{DUP}}", "token": "t"})
    assert r.status_code == 201


def test_create_credential_validation_422(client, admin_headers, assessment):
    for bad in ({"name": "no type", "placeholder": "{{X}}"},        # type required
                {"credential_type": "cookie", "placeholder": "{{X}}"}):  # name required
        r = client.post(f"/api/assessments/{assessment.id}/credentials",
                        headers=admin_headers, json=bad)
        assert r.status_code == 422, bad


# ------------------------------------------------------------------ read
def test_get_credential_404(client, admin_headers):
    assert client.get("/api/credentials/777",
                      headers=admin_headers).status_code == 404


def test_get_by_placeholder(client, db, admin_headers, assessment):
    _cred(db, assessment, "{{LOOKUP}}", token="found-me")
    r = client.get(f"/api/assessments/{assessment.id}/credentials"
                   f"/by-placeholder/{{{{LOOKUP}}}}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["token"] == "found-me"
    r = client.get(f"/api/assessments/{assessment.id}/credentials"
                   f"/by-placeholder/{{{{MISSING}}}}", headers=admin_headers)
    assert r.status_code == 404


# ------------------------------------------------------------------ update
def test_update_credential_partial(client, db, admin_headers, assessment):
    row = _cred(db, assessment, "{{UPD}}", token="old")
    r = client.patch(f"/api/credentials/{row.id}", headers=admin_headers,
                     json={"token": "new", "notes": "rotated"})
    assert r.status_code == 200
    assert r.json()["token"] == "new"
    assert r.json()["notes"] == "rotated"
    assert r.json()["name"] == "cred-{{UPD}}"  # untouched


def test_update_credential_placeholder_conflict_409(
        client, db, admin_headers, assessment):
    _cred(db, assessment, "{{ONE}}")
    two = _cred(db, assessment, "{{TWO}}")
    r = client.patch(f"/api/credentials/{two.id}", headers=admin_headers,
                     json={"placeholder": "{{ONE}}"})
    assert r.status_code == 409
    # ...and renaming to a FREE placeholder works.
    r = client.patch(f"/api/credentials/{two.id}", headers=admin_headers,
                     json={"placeholder": "{{TWO_RENAMED}}"})
    assert r.status_code == 200
    assert r.json()["placeholder"] == "{{TWO_RENAMED}}"


def test_update_credential_404(client, admin_headers):
    assert client.patch("/api/credentials/555", headers=admin_headers,
                        json={"token": "x"}).status_code == 404


# ------------------------------------------------------------------ delete
def test_delete_credential(client, db, admin_headers, assessment):
    row = _cred(db, assessment, "{{DEL}}")
    r = client.delete(f"/api/credentials/{row.id}", headers=admin_headers)
    assert r.status_code == 204
    assert db.query(Credential).count() == 0
    assert client.delete(f"/api/credentials/{row.id}",
                         headers=admin_headers).status_code == 404


def test_credentials_write_requires_auditor(client, db, viewer_headers, assessment):
    r = client.post(f"/api/assessments/{assessment.id}/credentials",
                    headers=viewer_headers,
                    json={"credential_type": "cookie", "name": "v",
                          "placeholder": "{{V}}", "cookie_value": "c"})
    assert r.status_code == 403
