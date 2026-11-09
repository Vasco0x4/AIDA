"""bugbounty_loader — URL/ext-id parsing and normalization logic with the HTTP
fetch mocked at the httpx boundary."""
from __future__ import annotations

import csv
import hashlib
import io
import json

import pytest

import services.bugbounty_loader as bbl
from models.knowledge_entry import KnowledgeEntry
from services.bugbounty_loader import (_bounty_severity, _ext_id,
                                       ingest_hackerone_csv,
                                       ingest_pentesterland)


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_ext_id_is_stable_prefixed_sha1():
    a = _ext_id("https://example.com/writeup")
    assert a.startswith("bb-") and len(a) == 19
    assert a == "bb-" + hashlib.sha1(b"https://example.com/writeup").hexdigest()[:16]
    assert _ext_id("https://example.com/writeup") == a        # deterministic
    assert _ext_id("") == "bb-" + hashlib.sha1(b"").hexdigest()[:16]


def test_bounty_severity_bands():
    assert _bounty_severity("25000") == "CRITICAL"
    assert _bounty_severity("10,000") == "CRITICAL"   # thousands separator
    assert _bounty_severity("3000") == "HIGH"
    assert _bounty_severity("3500.50") == "HIGH"
    assert _bounty_severity("500") == "MEDIUM"
    assert _bounty_severity("1") == "LOW"
    assert _bounty_severity("0") is None
    assert _bounty_severity("0.0") is None
    assert _bounty_severity("") is None
    assert _bounty_severity("-") is None              # pentester.land's "no bounty"
    assert _bounty_severity("not-a-number") is None


# ── shared httpx fake ─────────────────────────────────────────────────────────

class Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text if text or payload is None else json.dumps(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class Client:
    resp = Resp()
    requests = []

    def __init__(self, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        Client.requests.append(url)
        if isinstance(Client.resp, Exception):
            raise Client.resp
        return Client.resp


def _write_csv(rows):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["title", "link", "program",
                                             "vuln_type", "upvotes", "bounty"])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ── ingest_pentesterland ──────────────────────────────────────────────────────

def _item(title="SSRF in avatar upload", url="https://example.com/w/1",
          bugs=("SSRF",), programs=("GitLab",), authors=("alice",),
          bounty="1000", pub="2024-01-01"):
    links = [{"Title": title, "Link": url},
             {"Title": "mirror", "Link": "https://mirror.example/w/1"}]
    return {"Links": links, "Bugs": list(bugs), "Programs": list(programs),
            "Authors": list(authors), "Bounty": bounty, "PublicationDate": pub}


async def test_ingest_pentesterland_happy_path_upsert_and_dedup(db, monkeypatch):
    monkeypatch.setattr(bbl.httpx, "AsyncClient", Client)
    Client.resp = Resp(payload={"data": [
        _item(),
        _item(),                                              # exact dup URL
        {"Links": []},                                        # no links → skip
        {"Links": [{"Title": "", "Link": "https://x/1"}]},    # no title → skip
        {"Links": [{"Title": "t", "Link": ""}]},              # no url → skip
        _item(title="XSS in search", url="https://example.com/w/2",
              bugs=(), programs=(), authors=(), bounty="-", pub=""),
    ]})

    out = await ingest_pentesterland(db)
    assert out == {"added": 2, "updated": 0, "total_seen": 6}

    row = db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == _ext_id("https://example.com/w/1")).one()
    assert row.source == "bugbounty"
    assert row.title == "SSRF in avatar upload"
    assert row.tags == "SSRF, GitLab"
    assert "Bug types: SSRF" in row.description
    assert "Programs/targets: GitLab" in row.description
    assert "By alice (2024-01-01)" in row.description
    assert ". Bounty: 1000" in row.description
    assert row.references == ["https://example.com/w/1",
                              "https://mirror.example/w/1"]

    # '-' bounty and empty fields degrade gracefully
    row2 = db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == _ext_id("https://example.com/w/2")).one()
    assert "Bug types: n/a" in row2.description
    assert "By unknown" in row2.description
    assert "Bounty" not in row2.description

    # Re-run updates existing rows instead of duplicating them.
    Client.resp = Resp(payload={"data": [_item(title="SSRF in avatar upload (updated)")]})
    out = await ingest_pentesterland(db)
    assert out["added"] == 0 and out["updated"] == 1
    db.expire_all()
    row = db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == _ext_id("https://example.com/w/1")).one()
    assert row.title.endswith("(updated)")
    assert db.query(KnowledgeEntry).filter(
        KnowledgeEntry.source == "bugbounty").count() == 2


async def test_ingest_pentesterland_limit_and_list_body(db, monkeypatch):
    monkeypatch.setattr(bbl.httpx, "AsyncClient", Client)
    Client.resp = Resp(payload=[_item(url=f"https://example.com/w/{i}")
                                for i in range(5)])  # bare list body
    out = await ingest_pentesterland(db, limit=3)
    assert out == {"added": 3, "updated": 0, "total_seen": 3}


async def test_ingest_pentesterland_error_paths(db, monkeypatch):
    monkeypatch.setattr(bbl.httpx, "AsyncClient", Client)

    Client.resp = bbl.httpx.ConnectError("no route to host")
    with pytest.raises(RuntimeError, match="Could not fetch writeups"):
        await ingest_pentesterland(db)

    Client.resp = Resp(status_code=404, text="gone")
    with pytest.raises(RuntimeError, match="returned 404"):
        await ingest_pentesterland(db)

    Client.resp = Resp(text="<html>not json</html>")
    with pytest.raises(RuntimeError, match="non-JSON"):
        await ingest_pentesterland(db)

    Client.resp = Resp(payload={"unexpected": "shape"})
    with pytest.raises(RuntimeError, match="Unexpected writeups.json shape"):
        await ingest_pentesterland(db)


# ── ingest_hackerone_csv ──────────────────────────────────────────────────────

async def test_ingest_hackerone_csv_parsing_and_dedup(db, monkeypatch):
    monkeypatch.setattr(bbl.httpx, "AsyncClient", Client)
    Client.resp = Resp(text=_write_csv([
        {"title": "RCE via deserialization", "link": "hackerone.com/reports/456",
         "program": "GitLab", "vuln_type": "RCE", "upvotes": "42", "bounty": "4000"},
        {"title": "dup of 456", "link": "https://hackerone.com/reports/456",
         "program": "X", "vuln_type": "Y", "upvotes": "1", "bounty": "1"},
        {"title": "Blog writeup, no report id",
         "link": "https://blog.example/post", "program": "Shop",
         "vuln_type": "IDOR", "upvotes": "7", "bounty": "0"},
        {"title": "", "link": "https://hackerone.com/reports/999"},   # no title → skip
        {"title": "no link", "link": ""},                             # no link → skip
    ]))

    out = await ingest_hackerone_csv(db)
    assert out == {"added": 2, "updated": 0, "total_seen": 2}

    row = db.query(KnowledgeEntry).filter(KnowledgeEntry.ext_id == "h1-456").one()
    assert row.source == "h1report"
    assert row.severity == "HIGH"                     # $4000 band
    assert row.references == ["https://hackerone.com/reports/456"]  # scheme added
    assert "Program: GitLab" in row.description and "Upvotes: 42" in row.description
    assert "Bounty: $4000" in row.description
    assert row.tags == "RCE, GitLab"

    # No /reports/<id> → sha1 fallback ext id
    fallback = "h1-" + hashlib.sha1(b"https://blog.example/post").hexdigest()[:12]
    row2 = db.query(KnowledgeEntry).filter(KnowledgeEntry.ext_id == fallback).one()
    assert row2.severity is None
    assert "Bounty" not in row2.description           # bounty '0' omitted

    # Re-run updates rather than duplicates.
    Client.resp = Resp(text=_write_csv([
        {"title": "RCE via deserialization (updated)",
         "link": "https://hackerone.com/reports/456", "program": "GitLab",
         "vuln_type": "RCE", "upvotes": "50", "bounty": "20000"}]))
    out = await ingest_hackerone_csv(db)
    assert out["added"] == 0 and out["updated"] == 1
    db.expire_all()
    assert db.query(KnowledgeEntry).filter(
        KnowledgeEntry.ext_id == "h1-456").one().severity == "CRITICAL"


async def test_ingest_hackerone_csv_limit(db, monkeypatch):
    monkeypatch.setattr(bbl.httpx, "AsyncClient", Client)
    Client.resp = Resp(text=_write_csv([
        {"title": f"t{i}", "link": f"https://hackerone.com/reports/{100 + i}",
         "program": "P", "vuln_type": "V", "upvotes": "1", "bounty": "100"}
        for i in range(4)]))
    out = await ingest_hackerone_csv(db, limit=2)
    assert out["added"] == 2 and out["total_seen"] == 2


async def test_ingest_hackerone_csv_error_paths(db, monkeypatch):
    monkeypatch.setattr(bbl.httpx, "AsyncClient", Client)
    Client.resp = bbl.httpx.ReadTimeout("slow")
    with pytest.raises(RuntimeError, match="Could not fetch HackerOne"):
        await ingest_hackerone_csv(db)
    Client.resp = Resp(status_code=503, text="unavailable")
    with pytest.raises(RuntimeError, match="data.csv returned 503"):
        await ingest_hackerone_csv(db)
