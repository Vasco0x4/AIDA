"""
Integration tests for the per-assessment ASVS grid
(api/asvs_requirements.py + services/asvs_service.py).

Rows are seeded directly via the service (as assessment creation does); the
HTTP surface (catalog, listing with filters, single fetch, verdict PATCH with
status normalization and CVSS derivation, coverage summary) is exercised over
the real app.
"""
from __future__ import annotations

import pytest

from middleware.rate_limit import limiter
from models.assessment import Assessment
from models.asvs_requirement import AsvsRequirement
from services.asvs_service import load_catalog, seed_requirements


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def assessment(db) -> Assessment:
    a = Assessment(name="asvs-target", scope="app.example.com", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture()
def seeded(db, assessment) -> int:
    """Seed chapter V1 at level 1 (a small, deterministic slice)."""
    return seed_requirements(db, assessment, level=1, chapters=["V1"])


# --- catalog ------------------------------------------------------------------------

def test_catalog_endpoint(client, db, viewer_headers):
    r = client.get("/api/asvs/catalog", headers=viewer_headers)
    assert r.status_code == 200
    catalog = r.json()
    assert len(catalog) == len(load_catalog())
    first = catalog[0]
    for key in ("chapter_id", "section_id", "req_id", "level", "description"):
        assert key in first


# --- listing ------------------------------------------------------------------------

def test_list_requirements(client, db, admin_headers, assessment, seeded):
    r = client.get(f"/api/assessments/{assessment.id}/asvs",
                   headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == seeded
    assert all(req["status"] == "NOT_TESTED" for req in body)
    assert all(req["chapter_id"] == "V1" for req in body)
    assert all(req["level"] == 1 for req in body)
    # methodology metadata persisted on the assessment
    db.refresh(assessment)
    assert assessment.methodology == "asvs"
    assert assessment.asvs_level == 1


def test_list_requirements_unknown_assessment(client, db, admin_headers):
    assert client.get("/api/assessments/9876/asvs",
                      headers=admin_headers).status_code == 404


def test_list_filters(client, db, admin_headers, assessment, seeded):
    base = f"/api/assessments/{assessment.id}/asvs"
    # status filter is case-insensitive (upper-cased server-side)
    assert client.get(base, headers=admin_headers,
                      params={"status": "not_tested"}).json() != []
    assert client.get(base, headers=admin_headers,
                      params={"status": "PASS"}).json() == []
    # chapter + level filters
    assert client.get(base, headers=admin_headers,
                      params={"chapter": "v1"}).json() != []
    assert client.get(base, headers=admin_headers,
                      params={"chapter": "V2"}).json() == []
    assert client.get(base, headers=admin_headers,
                      params={"level": 1}).json() != []
    assert client.get(base, headers=admin_headers,
                      params={"level": 2}).json() == []


def test_get_single_requirement(client, db, admin_headers, assessment, seeded):
    req_id = db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == assessment.id).first()[0]
    r = client.get(f"/api/assessments/{assessment.id}/asvs/{req_id}",
                   headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["req_id"] == req_id
    assert client.get(f"/api/assessments/{assessment.id}/asvs/V9.9.9",
                      headers=admin_headers).status_code == 404


# --- verdicts (PATCH) ------------------------------------------------------------------

def test_patch_status_normalized_and_persisted(client, db, admin_headers,
                                               assessment, seeded):
    req_id = db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == assessment.id).first()[0]
    r = client.patch(f"/api/assessments/{assessment.id}/asvs/{req_id}",
                     headers=admin_headers,
                     json={"status": "pass", "analysis": "control verified",
                           "command_used": "curl -I https://app.example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PASS"      # lower-case input normalized
    assert body["analysis"] == "control verified"


def test_patch_invalid_status_rejected(client, db, admin_headers,
                                       assessment, seeded):
    req_id = db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == assessment.id).first()[0]
    r = client.patch(f"/api/assessments/{assessment.id}/asvs/{req_id}",
                     headers=admin_headers, json={"status": "MAYBE"})
    assert r.status_code == 400
    assert "status must be one of" in r.json()["detail"]


def test_patch_derives_cvss_from_vector(client, db, admin_headers,
                                        assessment, seeded):
    req_id = db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == assessment.id).first()[0]
    r = client.patch(f"/api/assessments/{assessment.id}/asvs/{req_id}",
                     headers=admin_headers,
                     json={"status": "FAIL",
                           "cvss_vector": "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/"
                                          "VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"})
    assert r.status_code == 200
    body = r.json()
    assert body["cvss_score"] == pytest.approx(9.3)
    assert body["severity"] == "CRITICAL"


def test_patch_unknown_requirement(client, db, admin_headers, assessment):
    assert client.patch(f"/api/assessments/{assessment.id}/asvs/V9.9.9",
                        headers=admin_headers,
                        json={"status": "PASS"}).status_code == 404


def test_patch_requires_auditor(client, db, viewer_headers, assessment, seeded):
    req_id = db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == assessment.id).first()[0]
    assert client.patch(f"/api/assessments/{assessment.id}/asvs/{req_id}",
                        headers=viewer_headers,
                        json={"status": "PASS"}).status_code == 403


# --- summary ---------------------------------------------------------------------------

def test_summary_coverage_math(client, db, admin_headers, assessment, seeded):
    base = f"/api/assessments/{assessment.id}/asvs"
    body = client.get(f"{base}/summary", headers=admin_headers).json()
    assert body["total"] == seeded
    assert body["tested"] == 0
    assert body["coverage_pct"] == 0.0
    assert body["by_status"]["NOT_TESTED"] == seeded
    assert body["asvs_version"] == "5.0.0"
    assert len(body["by_chapter"]) == 1

    # Record verdicts on two requirements
    req_ids = [row[0] for row in db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == assessment.id).limit(2).all()]
    for i, rid in enumerate(req_ids):
        client.patch(f"{base}/{rid}", headers=admin_headers,
                     json={"status": "PASS" if i == 0 else "NA"})

    body = client.get(f"{base}/summary", headers=admin_headers).json()
    assert body["tested"] == 2
    assert body["coverage_pct"] == round(2 / seeded * 100, 1)
    assert body["by_status"]["PASS"] == 1
    assert body["by_status"]["NA"] == 1
    assert body["by_chapter"][0]["tested"] == 2


def test_summary_unknown_assessment(client, db, admin_headers):
    assert client.get("/api/assessments/31337/asvs/summary",
                      headers=admin_headers).status_code == 404


# --- seeding service ---------------------------------------------------------------------

def test_seed_custom_requirement_list_expands_tokens(db):
    a = Assessment(name="asvs-custom", scope="x", status="active")
    db.add(a)
    db.commit()

    count = seed_requirements(db, a, req_ids=["V1.2.1", "V1.2"])
    seeded_ids = {row[0] for row in db.query(AsvsRequirement.req_id).filter(
        AsvsRequirement.assessment_id == a.id).all()}
    assert "V1.2.1" in seeded_ids
    assert count == len(seeded_ids)
    # section token V1.2 expands to every requirement in that section
    section_ids = {r["req_id"] for r in load_catalog()
                   if r["section_id"] == "V1.2"}
    assert section_ids <= seeded_ids
    db.refresh(a)
    assert a.asvs_level == max(
        r["level"] for r in load_catalog() if r["req_id"] in seeded_ids)


def test_seed_ignores_unknown_tokens(db):
    a = Assessment(name="asvs-unknown", scope="x", status="active")
    db.add(a)
    db.commit()
    count = seed_requirements(db, a, req_ids=["V99.9.9", "  "])
    assert count == 0
