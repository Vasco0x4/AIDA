"""knowledge_service, asvs_service, branding — DB-backed reference layers.

FTS queries run against the real test Postgres (no index needed); NVD/feed
ingestion is mocked at the httpx boundary.
"""
from __future__ import annotations

import json

import pytest

import services.knowledge_service as ks_mod
from models.asvs_requirement import AsvsRequirement
from models.assessment import Assessment
from models.knowledge_entry import KnowledgeEntry
from models.platform_settings import PlatformSettings
from services.asvs_service import (_resolve_tokens, compute_summary,
                                   load_catalog, seed_requirements)
from services.branding import (clear_logo, get_branding, save_logo,
                               update_branding)
from services.knowledge_service import KnowledgeService


# ── knowledge_service ─────────────────────────────────────────────────────────

def _entry(db, **kw):
    defaults = dict(source="nvd", ext_id="X-1", title="default title",
                    description="desc", content="body")
    defaults.update(kw)
    row = KnowledgeEntry(**defaults)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_seed_playbooks_idempotent(db):
    svc = KnowledgeService(db)
    assert svc.seed_playbooks() == 5
    assert svc.seed_playbooks() == 0
    pb = db.query(KnowledgeEntry).filter(KnowledgeEntry.ext_id == "PB-AUTH").first()
    assert pb.source == "playbook"
    assert pb.cwe == "CWE-287"


def test_search_no_query_orders_by_cvss(db):
    _entry(db, ext_id="low", title="low sev", cvss_score=2.0)
    _entry(db, ext_id="high", title="high sev", cvss_score=9.8)
    rows = KnowledgeService(db).search(query=None)
    assert [r.ext_id for r in rows] == ["high", "low"]


def test_search_fts_matches_title(db):
    _entry(db, ext_id="a", title="SQL injection in login form", description="x")
    _entry(db, ext_id="b", title="Cross-site scripting", description="y")
    rows = KnowledgeService(db).search(query="SQL injection")
    assert [r.ext_id for r in rows] == ["a"]


def test_search_source_filter(db):
    _entry(db, ext_id="n1", source="nvd", title="openssl bug openssl")
    _entry(db, ext_id="s1", source="skill", title="openssl skill openssl")
    rows = KnowledgeService(db).search(query="openssl", source="skill")
    assert {r.ext_id for r in rows} == {"s1"}


def test_search_keyword_fallback_ranks_title_over_description(db):
    # No row contains BOTH tokens → FTS (AND semantics) finds nothing and the
    # ILIKE keyword fallback ranks: title match beats description-only match.
    _entry(db, ext_id="CVE-9999-1111", title="unrelated words",
           description="unrelated", content="unrelated")
    _entry(db, ext_id="zzz", title="ghostcat processor",
           description="unrelated", content="unrelated")
    _entry(db, ext_id="yyy", title="unrelated", description="ghostcat mention",
           content="unrelated")
    rows = KnowledgeService(db).search(query="ghostcat zzqnotaword")
    assert rows, "keyword fallback should find candidates"
    exts = [r.ext_id for r in rows]
    assert exts.index("zzz") < exts.index("yyy")  # title beats description


def test_search_keyword_fallback_single_token_fallback(db):
    # Query with no alphanumeric tokens longer than 1 char → uses raw query.
    _entry(db, ext_id="sym", title="a % b")
    rows = KnowledgeService(db).search(query="%")
    assert [r.ext_id for r in rows] == ["sym"]


class _Resp:
    def __init__(self, status_code=200, payload=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _Client:
    resp = _Resp()

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None):
        self.last = (url, params)
        return _Client.resp


async def test_ingest_nvd_parses_cve_metadata(db, monkeypatch):
    body = {"vulnerabilities": [{
        "cve": {
            "id": "CVE-2024-0001",
            "descriptions": [{"lang": "fr", "value": "non"}, {"lang": "en", "value": "RCE in libx"}],
            "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 9.8, "baseSeverity": "CRITICAL"}}]},
            "weaknesses": [{"description": [{"value": "CWE-78"}]}],
            "references": [{"url": f"https://r{i}.example"} for i in range(15)],
        }}]}
    monkeypatch.setattr(ks_mod.httpx, "AsyncClient", _Client)
    _Client.resp = _Resp(payload=body)
    added = await KnowledgeService(db).ingest_nvd("libx")
    assert added == 1
    row = db.query(KnowledgeEntry).filter(KnowledgeEntry.ext_id == "CVE-2024-0001").one()
    assert row.source == "nvd"
    assert row.description == "RCE in libx"
    assert row.cvss_score == 9.8 and row.severity == "CRITICAL"
    assert row.cwe == "CWE-78"
    assert len(row.references) == 10  # capped
    assert row.tags == "libx"

    # Second ingest of the same CVE is a no-op.
    assert await KnowledgeService(db).ingest_nvd("libx") == 0


async def test_ingest_nvd_error_paths(db, monkeypatch):
    monkeypatch.setattr(ks_mod.httpx, "AsyncClient", _Client)

    _Client.resp = _Resp(status_code=403, text="rate limited")
    with pytest.raises(RuntimeError, match="returned 403"):
        await KnowledgeService(db).ingest_nvd("x")

    class _ErrClient(_Client):
        async def get(self, url, params=None):
            raise ks_mod.httpx.ConnectError("no route")

    monkeypatch.setattr(ks_mod.httpx, "AsyncClient", _ErrClient)
    with pytest.raises(RuntimeError, match="NVD request failed"):
        await KnowledgeService(db).ingest_nvd("x")

    monkeypatch.setattr(ks_mod.httpx, "AsyncClient", _Client)
    _Client.resp = _Resp(text="<html>")
    with pytest.raises(RuntimeError, match="non-JSON"):
        await KnowledgeService(db).ingest_nvd("x")


# ── asvs_service ──────────────────────────────────────────────────────────────

def test_load_catalog_bundled():
    catalog = load_catalog()
    assert catalog, "bundled ASVS catalog must load"
    req = catalog[0]
    for field in ("chapter_id", "section_id", "req_id", "level", "description"):
        assert field in req


def test_resolve_tokens_req_section_chapter():
    catalog = [
        {"req_id": "V1.1.1", "section_id": "V1.1", "chapter_id": "V1"},
        {"req_id": "V1.1.2", "section_id": "V1.1", "chapter_id": "V1"},
        {"req_id": "V1.2.3", "section_id": "V1.2", "chapter_id": "V1"},
        {"req_id": "V2.1.1", "section_id": "V2.1", "chapter_id": "V2"},
    ]
    assert _resolve_tokens(["V1.1.1"], catalog) == {"V1.1.1"}
    assert _resolve_tokens(["v1.1"], catalog) == {"V1.1.1", "V1.1.2"}  # section, lowercased
    assert _resolve_tokens(["V2"], catalog) == {"V2.1.1"}             # whole chapter
    assert _resolve_tokens(["V9.9.9", "  ", None], catalog) == set()  # unknown ignored


def _asn(db, **kw):
    row = Assessment(name=kw.pop("name", "asvs-target"), scope="127.0.0.1", **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_seed_requirements_level_and_chapters(db):
    asn = _asn(db)
    n = seed_requirements(db, asn, level=1, chapters=["V1", "V2"])
    assert n > 0
    rows = db.query(AsvsRequirement).filter(
        AsvsRequirement.assessment_id == asn.id).all()
    assert all(r.level <= 1 for r in rows)
    assert {r.chapter_id for r in rows} <= {"V1", "V2"}
    assert asn.methodology == "asvs"
    assert asn.asvs_level == 1
    assert asn.asvs_version == "5.0.0"
    assert all(r.status == "NOT_TESTED" for r in rows)


def test_seed_requirements_custom_req_ids_take_precedence(db):
    asn = _asn(db)
    catalog = load_catalog()
    target = catalog[0]["req_id"]
    n = seed_requirements(db, asn, req_ids=[target.upper()], level=3)
    assert n == 1
    seeded = db.query(AsvsRequirement).filter(
        AsvsRequirement.assessment_id == asn.id).one()
    assert seeded.req_id == target
    # stored_level is the max level among the selected requirements
    assert asn.asvs_level == max(r["level"] for r in catalog if r["req_id"] == target)


def test_compute_summary_counts_and_coverage(db):
    asn = _asn(db, methodology="asvs")
    db.add_all([
        AsvsRequirement(assessment_id=asn.id, chapter_id="V1", chapter_name="Arch",
                        section_id="V1.1", req_id="V1.1.1", level=1, status="PASS"),
        AsvsRequirement(assessment_id=asn.id, chapter_id="V1", chapter_name="Arch",
                        section_id="V1.1", req_id="V1.1.2", level=1, status="FAIL"),
        AsvsRequirement(assessment_id=asn.id, chapter_id="V1", chapter_name="Arch",
                        section_id="V1.2", req_id="V1.2.1", level=1, status="NOT_TESTED"),
        AsvsRequirement(assessment_id=asn.id, chapter_id="V2", chapter_name="Auth",
                        section_id="V2.1", req_id="V2.1.1", level=1, status=None),
    ])
    db.commit()
    summary = compute_summary(db, asn)
    assert summary["total"] == 4
    assert summary["tested"] == 2
    assert summary["coverage_pct"] == 50.0
    assert summary["by_status"]["PASS"] == 1
    assert summary["by_status"]["FAIL"] == 1
    assert summary["by_status"]["NOT_TESTED"] == 2  # NULL counts as NOT_TESTED
    assert [c["chapter_id"] for c in summary["by_chapter"]] == ["V1", "V2"]
    assert summary["by_chapter"][0]["tested"] == 2

    empty = compute_summary(db, _asn(db, name="empty-asvs"))
    assert empty["total"] == 0 and empty["coverage_pct"] == 0.0


# ── branding ──────────────────────────────────────────────────────────────────

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPEG = b"\xff\xd8\xff" + b"0" * 16
SVG = b'   <?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'


def _set_setting(db, value):
    from sqlalchemy import delete
    db.execute(delete(PlatformSettings).where(PlatformSettings.key == "report_branding"))
    db.add(PlatformSettings(key="report_branding", value=value))
    db.commit()


def test_get_branding_defaults_and_merge(db):
    assert get_branding(db)["organization"] == "AIDA"
    _set_setting(db, json.dumps({"organization": "Acme Ltd",
                                 "primary_color": "#123456",
                                 "unknown_key": "ignored"}))
    b = get_branding(db)
    assert b["organization"] == "Acme Ltd"
    assert b["primary_color"] == "#123456"
    assert "unknown_key" not in b
    assert b["classification"] == "Confidential"  # default retained

    _set_setting(db, "not-json{")
    assert get_branding(db)["organization"] == "AIDA"  # corrupt row ignored

    _set_setting(db, json.dumps(["a", "list"]))
    assert get_branding(db)["organization"] == "AIDA"  # non-dict ignored


def test_update_branding_validation_and_persistence(db):
    with pytest.raises(ValueError, match="1-120"):
        update_branding(db, organization="")
    with pytest.raises(ValueError, match="1-120"):
        update_branding(db, organization="x" * 121)
    with pytest.raises(ValueError, match="1-60"):
        update_branding(db, classification="")
    with pytest.raises(ValueError, match="hex color"):
        update_branding(db, primary_color="red")

    out = update_branding(db, organization="  Acme ", tagline=" pen " + "t" * 300,
                          classification="Top Secret", primary_color="#AbCdEf")
    assert out["organization"] == "Acme"           # stripped
    assert len(out["tagline"]) <= 200              # tagline capped, not rejected
    assert out["classification"] == "Top Secret"
    assert out["primary_color"] == "#AbCdEf"
    # Persisted as JSON on the single settings row.
    assert get_branding(db) == out


def test_save_logo_validation_and_data_uri(db):
    with pytest.raises(ValueError, match="Empty"):
        save_logo(db, b"")
    with pytest.raises(ValueError, match="too large"):
        save_logo(db, b"x" * (300 * 1024 + 1))
    with pytest.raises(ValueError, match="Unsupported"):
        save_logo(db, b"MZ\x90\x00 executable")

    b = save_logo(db, PNG)
    assert b["logo_data_uri"].startswith("data:image/png;base64,")

    b = save_logo(db, JPEG)
    assert b["logo_data_uri"].startswith("data:image/jpeg;base64,")

    b = save_logo(db, SVG)  # leading whitespace tolerated
    assert b["logo_data_uri"].startswith("data:image/svg+xml;base64,")

    assert clear_logo(db)["logo_data_uri"] == ""
