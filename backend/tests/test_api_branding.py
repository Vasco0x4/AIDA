"""
Integration tests for report branding (api/branding.py + services/branding.py).

GET is open to every authenticated user (report preview); writes are
admin-only via the RBAC middleware. Logo upload constraints (format sniffing,
300KB cap) and field validation are exercised against the service rules.
"""
from __future__ import annotations

import pytest

from middleware.rate_limit import limiter
from models.audit_log import AuditLog
from models.platform_settings import PlatformSettings
from services import branding as branding_svc


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 64
SVG_BYTES = b'<svg xmlns="http://www.w3.org/2000/svg" width="10"/>'


# --- read -------------------------------------------------------------------------

def test_get_default_branding(client, db, viewer_headers):
    r = client.get("/api/branding", headers=viewer_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["organization"] == "AIDA"
    assert body["classification"] == "Confidential"
    assert body["primary_color"] == "#0b3d91"
    assert body["logo_data_uri"] == ""


def test_get_branding_requires_auth(client, db):
    assert client.get("/api/branding").status_code == 401


# --- update -----------------------------------------------------------------------

def test_update_branding_admin_only(client, db, viewer_headers):
    assert client.put("/api/branding", headers=viewer_headers,
                      json={"organization": "Evil"}).status_code == 403


def test_update_branding_roundtrip(client, db, admin_headers, viewer_headers):
    r = client.put("/api/branding", headers=admin_headers, json={
        "organization": "ACME Security",
        "tagline": "We break things",
        "classification": "Top Secret",
        "primary_color": "#ff8800",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["organization"] == "ACME Security"
    assert body["classification"] == "Top Secret"
    assert body["primary_color"] == "#ff8800"

    # Visible to a plain viewer afterwards (report preview path)
    got = client.get("/api/branding", headers=viewer_headers).json()
    assert got["tagline"] == "We break things"

    row = (db.query(AuditLog).filter(AuditLog.action == "branding.updated")
           .order_by(AuditLog.id.desc()).first())
    assert row is not None
    assert row.detail["organization"] == "ACME Security"


@pytest.mark.parametrize("payload", [
    {"organization": ""},                      # empty after strip
    {"organization": "x" * 121},               # too long
    {"classification": ""},                    # empty after strip
    {"classification": "x" * 61},              # too long
    {"primary_color": "red"},                  # not hex
    {"primary_color": "#12345"},               # wrong length
    {"primary_color": "#12345g"},              # bad char
])
def test_update_branding_validation(client, db, admin_headers, payload):
    r = client.put("/api/branding", headers=admin_headers, json=payload)
    assert r.status_code == 400, payload


def test_update_branding_partial_keeps_other_fields(client, db, admin_headers):
    client.put("/api/branding", headers=admin_headers,
               json={"organization": "First Org"})
    r = client.put("/api/branding", headers=admin_headers,
                   json={"classification": "Internal"})
    assert r.status_code == 200
    assert r.json()["organization"] == "First Org"
    assert r.json()["classification"] == "Internal"


# --- logo -------------------------------------------------------------------------

def test_upload_png_logo(client, db, admin_headers):
    r = client.post("/api/branding/logo", headers=admin_headers,
                    files={"file": ("logo.png", PNG_BYTES, "image/png")})
    assert r.status_code == 200
    uri = r.json()["logo_data_uri"]
    assert uri.startswith("data:image/png;base64,")
    import base64
    assert base64.b64decode(uri.split(",", 1)[1]) == PNG_BYTES


def test_upload_jpeg_and_svg_logos(client, db, admin_headers):
    r = client.post("/api/branding/logo", headers=admin_headers,
                    files={"file": ("x.jpg", JPEG_BYTES, "image/jpeg")})
    assert r.json()["logo_data_uri"].startswith("data:image/jpeg;base64,")
    r = client.post("/api/branding/logo", headers=admin_headers,
                    files={"file": ("x.svg", SVG_BYTES, "image/svg+xml")})
    assert r.json()["logo_data_uri"].startswith("data:image/svg+xml;base64,")


def test_upload_logo_rejects_unsupported_format(client, db, admin_headers):
    r = client.post("/api/branding/logo", headers=admin_headers,
                    files={"file": ("evil.exe", b"MZ\x90\x00" + b"0" * 32,
                                    "application/octet-stream")})
    assert r.status_code == 400
    assert "Unsupported logo format" in r.json()["detail"]


def test_upload_logo_rejects_empty(client, db, admin_headers):
    r = client.post("/api/branding/logo", headers=admin_headers,
                    files={"file": ("empty.png", b"", "image/png")})
    assert r.status_code == 400


def test_upload_logo_rejects_oversize(client, db, admin_headers):
    big = PNG_BYTES + b"0" * (300 * 1024 + 1)
    r = client.post("/api/branding/logo", headers=admin_headers,
                    files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 400
    assert "too large" in r.json()["detail"]


def test_upload_logo_admin_only(client, db, viewer_headers):
    r = client.post("/api/branding/logo", headers=viewer_headers,
                    files={"file": ("x.png", PNG_BYTES, "image/png")})
    assert r.status_code == 403


def test_delete_logo(client, db, admin_headers):
    client.post("/api/branding/logo", headers=admin_headers,
                files={"file": ("logo.png", PNG_BYTES, "image/png")})
    r = client.delete("/api/branding/logo", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["logo_data_uri"] == ""
    assert (db.query(AuditLog).filter(AuditLog.action == "branding.logo_cleared")
            .order_by(AuditLog.id.desc()).first() is not None)


def test_delete_logo_admin_only(client, db, viewer_headers):
    assert client.delete("/api/branding/logo",
                         headers=viewer_headers).status_code == 403


# --- service-level edge cases --------------------------------------------------------

def test_branding_survives_corrupt_stored_json(db):
    db.add(PlatformSettings(key="report_branding", value="{not json"))
    db.commit()
    out = branding_svc.get_branding(db)
    assert out == branding_svc.DEFAULT_BRANDING  # falls back to defaults


def test_tagline_is_trimmed_and_capped(db):
    out = branding_svc.update_branding(db, tagline="  " + "t" * 250 + "  ")
    assert out["tagline"] == "t" * 200
