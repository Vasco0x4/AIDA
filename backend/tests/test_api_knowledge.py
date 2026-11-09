"""
Integration tests for the knowledge base (api/knowledge.py +
services/knowledge_service.py): search (Postgres FTS + filters), stats,
gzip export/import round-trip, playbook seeding, and the NVD / bug-bounty
ingest endpoints with all outbound HTTP mocked (hermetic).
"""
from __future__ import annotations

import gzip
import json
import types
from typing import Any

import pytest

from middleware.rate_limit import limiter
from models.knowledge_entry import KnowledgeEntry
from services.knowledge_service import KnowledgeService


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def entries(db):
    rows = [
        KnowledgeEntry(source="nvd", ext_id="CVE-2024-0001",
                       title="SQL injection in Foo CMS",
                       description="Foo CMS before 2.1 allows SQL injection",
                       severity="CRITICAL", cvss_score=9.8, cwe="CWE-89",
                       references=["https://example.com/advisory"], tags="sqli,web"),
        KnowledgeEntry(source="nvd", ext_id="CVE-2024-0002",
                       title="Reflected XSS in Bar portal",
                       description="Bar portal reflects user input",
                       severity="MEDIUM", cvss_score=5.4, cwe="CWE-79",
                       tags="xss,web"),
        KnowledgeEntry(source="playbook", ext_id="PB-TEST",
                       title="Web recon playbook", content="run subfinder",
                       severity="INFO", tags="recon,web"),
    ]
    db.add_all(rows)
    db.commit()
    return rows


# --- search & read -----------------------------------------------------------------

def test_stats(client, db, admin_headers, entries):
    r = client.get("/api/knowledge/stats", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body == {"total": 3, "by_source": {"nvd": 2, "playbook": 1}}


def test_search_by_keyword_fts(client, db, viewer_headers, entries):
    r = client.get("/api/knowledge", headers=viewer_headers,
                   params={"q": "SQL injection"})
    assert r.status_code == 200
    results = r.json()
    assert [e["ext_id"] for e in results] == ["CVE-2024-0001"]
    assert results[0]["cvss_score"] == 9.8
    assert results[0]["references"] == ["https://example.com/advisory"]


def test_search_with_source_filter(client, db, admin_headers, entries):
    r = client.get("/api/knowledge", headers=admin_headers,
                   params={"q": "web", "source": "playbook"})
    assert r.json()[0]["source"] == "playbook"
    only = client.get("/api/knowledge", headers=admin_headers,
                      params={"source": "playbook"})
    assert {e["source"] for e in only.json()} == {"playbook"}


def test_search_no_query_orders_by_score(client, db, admin_headers, entries):
    r = client.get("/api/knowledge", headers=admin_headers, params={"limit": 2})
    body = r.json()
    assert len(body) == 2
    assert body[0]["cvss_score"] >= body[1]["cvss_score"]


def test_get_entry_and_404(client, db, admin_headers, entries):
    r = client.get(f"/api/knowledge/{entries[0].id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["title"] == "SQL injection in Foo CMS"
    assert client.get("/api/knowledge/99999",
                      headers=admin_headers).status_code == 404


# --- export / import ------------------------------------------------------------------

def test_export_gzip_roundtrip(client, db, admin_headers, entries):
    r = client.get("/api/knowledge/export", headers=admin_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/gzip")
    assert "aida_knowledge_all.jsonl.gz" in r.headers["content-disposition"]
    lines = [json.loads(x) for x in gzip.decompress(r.content).decode().splitlines()]
    assert len(lines) == 3
    assert {row["ext_id"] for row in lines} >= {"CVE-2024-0001", "PB-TEST"}

    # Source filter narrows the export
    r = client.get("/api/knowledge/export", headers=admin_headers,
                   params={"source": "playbook"})
    lines = [json.loads(x) for x in gzip.decompress(r.content).decode().splitlines()]
    assert len(lines) == 1 and lines[0]["source"] == "playbook"


def test_import_gzipped_upsert(client, db, admin_headers, entries):
    export = client.get("/api/knowledge/export", headers=admin_headers).content

    # Fresh-ish state: wipe and re-import the export
    for e in db.query(KnowledgeEntry).all():
        db.delete(e)
    db.commit()

    r = client.post("/api/knowledge/import", headers=admin_headers,
                    files={"file": ("kb.jsonl.gz", export, "application/gzip")})
    assert r.status_code == 200
    assert r.json() == {"added": 3, "updated": 0}

    # Re-import the same data → everything updates instead
    r = client.post("/api/knowledge/import", headers=admin_headers,
                    files={"file": ("kb.jsonl.gz", export, "application/gzip")})
    assert r.json() == {"added": 0, "updated": 3}


def test_import_plain_jsonl_with_junk(client, db, admin_headers):
    payload = (b'{"source": "manual", "ext_id": "M-1", "title": "Note one"}\n'
               b'\n'
               b'not json at all\n'
               b'{"source": "manual", "title": "No ext id"}\n')
    r = client.post("/api/knowledge/import", headers=admin_headers,
                    files={"file": ("kb.jsonl", payload, "text/plain")})
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 2  # junk lines skipped, no-ext_id row still added
    assert db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == "M-1").one().title == "Note one"


def test_import_bad_gzip(client, db, admin_headers):
    r = client.post("/api/knowledge/import", headers=admin_headers,
                    files={"file": ("bad.gz", b"\x1f\x8b" + b"broken" * 10,
                                    "application/gzip")})
    assert r.status_code == 422


def test_import_admin_only(client, db, viewer_headers):
    assert client.post("/api/knowledge/import", headers=viewer_headers,
                       files={"file": ("x.jsonl", b"{}", "text/plain")}).status_code == 403


# --- seed playbooks --------------------------------------------------------------------

def test_seed_playbooks_idempotent(client, db, admin_headers):
    r = client.post("/api/knowledge/seed-playbooks", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["added"] == 5
    r = client.post("/api/knowledge/seed-playbooks", headers=admin_headers)
    assert r.json()["added"] == 0
    sources = {row[0] for row in db.query(KnowledgeEntry.source).all()}
    assert "playbook" in sources
    assert db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == "PB-AUTH").count() == 1


# --- NVD ingest (mocked HTTP) -----------------------------------------------------------

def _fake_httpx(monkeypatch, status_code=200, body=None):
    class _Client:
        def __init__(self, *a: Any, **k: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a: Any):
            return False

        async def get(self, url: str, params: dict | None = None):
            return types.SimpleNamespace(status_code=status_code,
                                         json=lambda: body or {})

    import services.knowledge_service as ks
    monkeypatch.setattr(ks.httpx, "AsyncClient", _Client)


def _nvd_body():
    return {
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2024-7777",
                    "descriptions": [{"lang": "en", "value": "SSRF in Gadget"}],
                    "metrics": {"cvssMetricV31": [
                        {"cvssData": {"baseScore": 8.6,
                                      "baseSeverity": "HIGH"}}]},
                    "weaknesses": [{"description": [{"value": "CWE-918"}]}],
                    "references": [{"url": "https://nvd.example/CVE-2024-7777"}],
                }
            },
            {"cve": {"id": "", "descriptions": []}},  # skipped: no id
        ]
    }


def test_ingest_nvd(client, db, admin_headers, monkeypatch):
    _fake_httpx(monkeypatch, body=_nvd_body())
    r = client.post("/api/knowledge/ingest/nvd", headers=admin_headers,
                    json={"keyword": "gadget", "limit": 5})
    assert r.status_code == 200
    assert r.json() == {"ingested": 1, "keyword": "gadget"}

    row = db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == "CVE-2024-7777").one()
    assert row.source == "nvd"
    assert row.cvss_score == 8.6
    assert row.severity == "HIGH"
    assert row.cwe == "CWE-918"
    assert row.tags == "gadget"

    # Second ingest of the same data → deduplicated
    _fake_httpx(monkeypatch, body=_nvd_body())
    r = client.post("/api/knowledge/ingest/nvd", headers=admin_headers,
                    json={"keyword": "gadget", "limit": 5})
    assert r.json()["ingested"] == 0


def test_ingest_nvd_upstream_error(client, db, admin_headers, monkeypatch):
    _fake_httpx(monkeypatch, status_code=503, body={})
    r = client.post("/api/knowledge/ingest/nvd", headers=admin_headers,
                    json={"keyword": "gadget"})
    assert r.status_code == 502


def test_ingest_nvd_admin_only(client, db, viewer_headers):
    assert client.post("/api/knowledge/ingest/nvd", headers=viewer_headers,
                       json={"keyword": "x"}).status_code == 403


# --- bug bounty ingest (mocked loaders) ----------------------------------------------------

def test_ingest_bugbounty_merges_sources(client, db, admin_headers, monkeypatch):
    import services.bugbounty_loader as loader

    async def fake_pl(db, limit=None):
        return {"added": 3, "updated": 0}

    async def fake_h1(db, limit=None):
        return {"added": 1, "updated": 2}

    monkeypatch.setattr(loader, "ingest_pentesterland", fake_pl)
    monkeypatch.setattr(loader, "ingest_hackerone_csv", fake_h1)
    r = client.post("/api/knowledge/ingest/bugbounty", headers=admin_headers,
                    json={"limit": 5})
    assert r.status_code == 200
    assert r.json() == {"pentesterland": {"added": 3, "updated": 0},
                        "hackerone": {"added": 1, "updated": 2}}


def test_ingest_bugbounty_all_failed_502(client, db, admin_headers, monkeypatch):
    import services.bugbounty_loader as loader

    async def boom(db, limit=None):
        raise RuntimeError("feed unreachable")

    monkeypatch.setattr(loader, "ingest_pentesterland", boom)
    monkeypatch.setattr(loader, "ingest_hackerone_csv", boom)
    r = client.post("/api/knowledge/ingest/bugbounty", headers=admin_headers,
                    json={})
    assert r.status_code == 502
    assert "feed unreachable" in r.json()["detail"]


# --- service-level search fallback -----------------------------------------------------------

def test_search_keyword_fallback_for_odd_queries(db, entries):
    # A query the FTS layer can't match falls back to token/ILIKE matching
    results = KnowledgeService(db).search(query="sqli", limit=10)
    assert any(e.ext_id == "CVE-2024-0001" for e in results)
    # Exact tag term ranks the tagged entry first
    results = KnowledgeService(db).search(query="xss", limit=10)
    assert results[0].ext_id == "CVE-2024-0002"


# --- service-level search internals -------------------------------------------------------

def test_fts_search_no_match_returns_empty(db, entries):
    svc = KnowledgeService(db)
    assert svc._search_fts("zzqqxxnotaword", None, 10) == []
    # FTS layer handles plain queries when the index matches
    hits = svc._search_fts("injection", None, 10)
    assert [e.ext_id for e in hits] == ["CVE-2024-0001"]


def test_keyword_fallback_ranks_by_token_weights(db, entries):
    svc = KnowledgeService(db)
    # Drive the ILIKE fallback directly: title + tag tokens weigh highest
    results = svc._search_keyword("sql injection foo", None, 10)
    assert results, "keyword fallback must find the SQLi entry"
    assert results[0].ext_id == "CVE-2024-0001"
    # Weak (description/body) matches fill in below strong ones
    results = svc._search_keyword("reflected", None, 10)
    assert [e.ext_id for e in results] == ["CVE-2024-0002"]


def test_keyword_fallback_handles_unsplittable_query(db, entries):
    svc = KnowledgeService(db)
    # A query with no usable tokens falls back to the raw string
    results = svc._search_keyword("!!", None, 10)
    assert isinstance(results, list)


def test_search_fts_sql_failure_rolls_back(db, entries, monkeypatch):
    svc = KnowledgeService(db)

    # Force the FTS statement itself to fail so the rollback branch runs
    original_execute = db.execute

    def failing_execute(stmt, *a, **k):
        if "websearch_to_tsquery" in str(getattr(stmt, "text", stmt)):
            raise RuntimeError("fts blew up")
        return original_execute(stmt, *a, **k)

    monkeypatch.setattr(db, "execute", failing_execute)
    results = svc.search(query="injection", limit=10)
    # Falls back to the keyword path instead of poisoning the session
    assert any(e.ext_id == "CVE-2024-0001" for e in results)


def test_ingest_nvd_metric_and_description_fallbacks(db, monkeypatch):
    async def run():
        body = {
            "vulnerabilities": [
                {"cve": {
                    "id": "CVE-2021-2222",
                    "descriptions": [{"lang": "fr", "value": "français"}],
                    "metrics": {"cvssMetricV2": [
                        {"cvssData": {"baseScore": 6.5}}]},
                    "weaknesses": [{"description": [{"value": "NVD-CWE-noinfo"},
                                                     {"value": "CWE-79"}]}],
                    "references": [],
                }},
            ]
        }
        _fake_httpx(monkeypatch, body=body)
        return await KnowledgeService(db).ingest_nvd("widgets", 5)

    import asyncio
    added = asyncio.run(run())
    assert added == 1
    row = db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == "CVE-2021-2222").one()
    # No English description → empty; CVSS V2 metrics used as fallback
    assert row.description == ""
    assert row.cvss_score == 6.5
    assert row.cwe == "CWE-79"  # first CWE- prefixed value wins


def test_ingest_nvd_non_json_response(db, monkeypatch):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None):
            def raise_json():
                raise ValueError("not json")
            return types.SimpleNamespace(status_code=200, json=raise_json)

    import services.knowledge_service as ks
    monkeypatch.setattr(ks.httpx, "AsyncClient", _Client)
    import asyncio
    with pytest.raises(RuntimeError, match="non-JSON"):
        asyncio.run(KnowledgeService(db).ingest_nvd("x"))
