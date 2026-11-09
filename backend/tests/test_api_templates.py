"""
Integration tests for assessment templates (api/templates.py +
services/template_service.py): the static catalog served to the
create-assessment UI.
"""
from __future__ import annotations

from services.template_service import TEMPLATES, get_all_templates, get_template


def test_list_templates(client, db, viewer_headers):
    r = client.get("/api/templates", headers=viewer_headers)
    assert r.status_code == 200
    body = r.json()
    ids = {t["id"] for t in body}
    assert {"web_app", "api", "infrastructure", "mobile", "active_directory",
            "owasp_asvs", "blank"} <= ids
    # Summaries expose metadata but not the full phase bodies
    web = next(t for t in body if t["id"] == "web_app")
    assert web["name"] == "Web Application"
    assert web["methodology"] == "standard"
    assert "nmap" in web["suggested_tools"]
    assert "phases" not in web


def test_get_template_detail(client, db, viewer_headers):
    r = client.get("/api/templates/web_app", headers=viewer_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "web_app"
    assert len(body["phases"]) == 6
    assert body["phases"][0]["number"] == "1.0"
    assert "Reconnaissance" in body["phases"][0]["title"]


def test_get_template_asvs_has_no_phases(client, db, viewer_headers):
    r = client.get("/api/templates/owasp_asvs", headers=viewer_headers)
    assert r.status_code == 200
    assert r.json()["phases"] == []
    assert r.json()["methodology"] == "asvs"


def test_get_template_unknown_404(client, db, viewer_headers):
    assert client.get("/api/templates/nope",
                      headers=viewer_headers).status_code == 404


def test_templates_require_auth(client, db):
    assert client.get("/api/templates").status_code == 401


def test_service_catalog_shape():
    summary = get_all_templates()
    assert len(summary) == len(TEMPLATES)
    full = get_template("api")
    assert full["category"] == "API"
    assert get_template("missing") is None
