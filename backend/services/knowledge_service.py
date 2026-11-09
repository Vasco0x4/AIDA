"""
Knowledge service — offensive-security reference layer.

- search(): query stored CVEs / advisories / playbooks.
- ingest_nvd(): pull CVE metadata from the public NVD 2.0 API by keyword.
- seed_playbooks(): install built-in methodology playbooks (idempotent).

Reference knowledge only (descriptions, CVSS, CWE, references, how-to-test) —
not a store of weaponized exploit code.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.knowledge_entry import KnowledgeEntry
from utils.logger import get_logger

logger = get_logger(__name__)

NVD_API = "https://services.nvd.nist.gov/rest/json/cves/2.0"


# Built-in methodology playbooks — give the agent a baseline even offline.
_PLAYBOOKS = [
    {
        "ext_id": "PB-WEB-RECON",
        "title": "Web application reconnaissance",
        "severity": "INFO", "cwe": None, "tags": "recon,web,enumeration",
        "content": (
            "1. Enumerate subdomains (subfinder, dnsx). 2. Port/service scan in-scope hosts "
            "(nmap -sV). 3. Fingerprint tech (httpx, whatweb). 4. Content discovery (ffuf, katana) "
            "with a sensible wordlist. 5. Map auth flows and API endpoints. Record every asset via "
            "record_recon. Stay strictly in scope."
        ),
    },
    {
        "ext_id": "PB-AUTH",
        "title": "Authentication & session testing",
        "severity": "HIGH", "cwe": "CWE-287", "tags": "auth,session,access-control",
        "content": (
            "Check: credential stuffing surface, weak password policy, missing rate limiting, "
            "JWT alg/none & signature issues, session fixation, insecure cookie flags, IDOR on "
            "user-scoped objects, privilege escalation between roles. Never brute-force where the "
            "scope excludes it."
        ),
    },
    {
        "ext_id": "PB-INJECTION",
        "title": "Injection testing (SQLi / command / template)",
        "severity": "CRITICAL", "cwe": "CWE-89", "tags": "injection,sqli,rce",
        "content": (
            "Probe inputs for SQLi (error-based, boolean, time-based; sqlmap for confirmation), "
            "OS command injection (CWE-78), SSTI, and NoSQL injection. Confirm with a benign PoC "
            "(e.g. arithmetic/time delay) — do not exfiltrate real data or run destructive payloads."
        ),
    },
    {
        "ext_id": "PB-SSRF",
        "title": "SSRF & request-forgery testing",
        "severity": "HIGH", "cwe": "CWE-918", "tags": "ssrf,web",
        "content": (
            "Identify features that fetch URLs (webhooks, importers, preview, PDF/render). Test for "
            "SSRF to internal ranges and cloud metadata endpoints. Demonstrate impact with a benign "
            "callback/OAST hit; avoid pivoting into out-of-scope internal systems."
        ),
    },
    {
        "ext_id": "PB-XSS",
        "title": "Cross-site scripting (XSS) testing",
        "severity": "MEDIUM", "cwe": "CWE-79", "tags": "xss,web",
        "content": (
            "Test reflected, stored, and DOM XSS. Confirm execution context (HTML/attr/JS/URL) and "
            "encoding gaps. PoC with a harmless marker (alert/console/DNS callback), capture a "
            "screenshot as evidence, and record the finding with the exact payload."
        ),
    },
]


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db

    # Must match the expression of knowledge_fts_idx in database._ensure_columns.
    FTS_EXPR = ("to_tsvector('english', coalesce(title,'') || ' ' || "
                "coalesce(tags,'') || ' ' || coalesce(description,''))")

    def search(self, query: Optional[str] = None, source: Optional[str] = None,
               limit: int = 20) -> list[KnowledgeEntry]:
        q = self.db.query(KnowledgeEntry)
        if source:
            q = q.filter(KnowledgeEntry.source == source)
        if not query:
            return (q.order_by(KnowledgeEntry.cvss_score.desc().nullslast(),
                               KnowledgeEntry.created_at.desc())
                    .limit(min(limit, 100)).all())

        # 1) Primary: Postgres full-text search (GIN-indexed, ts_rank ordering).
        fts = self._search_fts(query, source, limit)
        if fts:
            return fts
        # 2) Fallback: keyword-overlap over ILIKE candidates (short/odd queries).
        return self._search_keyword(query, source, limit)

    def _search_fts(self, query: str, source: Optional[str], limit: int) -> list:
        from sqlalchemy import text
        lim = min(limit, 100)
        src_clause = "AND source = :src" if source else ""
        sql = text(
            f"SELECT id FROM knowledge_entries "
            f"WHERE {self.FTS_EXPR} @@ websearch_to_tsquery('english', :q) {src_clause} "
            f"ORDER BY ts_rank({self.FTS_EXPR}, websearch_to_tsquery('english', :q)) DESC "
            f"LIMIT :lim")
        params = {"q": query, "lim": lim}
        if source:
            params["src"] = source
        try:
            ids = [r[0] for r in self.db.execute(sql, params).fetchall()]
        except Exception:
            # Roll back so a failed FTS statement doesn't poison the session and
            # break the ILIKE keyword fallback (and every later query).
            try:
                self.db.rollback()
            except Exception:
                pass
            return []
        if not ids:
            return []
        rows = {e.id: e for e in self.db.query(KnowledgeEntry)
                .filter(KnowledgeEntry.id.in_(ids)).all()}
        return [rows[i] for i in ids if i in rows]

    def _search_keyword(self, query: str, source: Optional[str], limit: int) -> list:
        q = self.db.query(KnowledgeEntry)
        if source:
            q = q.filter(KnowledgeEntry.source == source)
        # Fetch candidates matching ANY query token, then rank in Python by
        # keyword overlap (title/ext_id/tags weighted highest). This is far
        # better than raw ILIKE ordering without needing an embedding model.
        tokens = [t for t in re.split(r"[^a-z0-9]+", query.lower()) if len(t) > 1]
        if not tokens:
            tokens = [query.lower()]
        # Tiered fetch (the KB can be 20k+ rows): first the SPECIFIC matches
        # (query token in title/tags/ext_id/cwe), then fill with body matches.
        strong_conds, weak_conds = [], []
        for t in tokens:
            like = f"%{t}%"
            strong_conds += [KnowledgeEntry.title.ilike(like),
                             KnowledgeEntry.tags.ilike(like),
                             KnowledgeEntry.ext_id.ilike(like),
                             KnowledgeEntry.cwe.ilike(like)]
            weak_conds += [KnowledgeEntry.description.ilike(like),
                           KnowledgeEntry.content.ilike(like)]
        strong = q.filter(or_(*strong_conds)).limit(400).all()
        candidates = list(strong)
        if len(strong) < 400:
            seen = {e.id for e in strong}
            weak = self.db.query(KnowledgeEntry)
            if source:
                weak = weak.filter(KnowledgeEntry.source == source)
            for e in weak.filter(or_(*weak_conds)).limit(200).all():
                if e.id not in seen:
                    candidates.append(e)

        def score(e):
            title = (e.title or "").lower()
            ext = (e.ext_id or "").lower()
            tags = (e.tags or "").lower()
            desc = (e.description or "").lower()
            body = (e.content or "").lower()
            s = 0.0
            for t in tokens:
                if t in ext:
                    s += 6
                if t in title:
                    s += 5
                if t in tags:
                    s += 3
                if t in desc:
                    s += 2
                if t in body:
                    s += 1
            # Small boost for exact phrase in title/ext.
            if query.lower() in title or query.lower() in ext:
                s += 4
            if e.cvss_score:
                s += min(e.cvss_score, 10) / 10.0
            return s

        candidates.sort(key=score, reverse=True)
        return candidates[:min(limit, 100)]

    def seed_playbooks(self) -> int:
        """Install built-in playbooks if missing (idempotent by ext_id)."""
        added = 0
        for pb in _PLAYBOOKS:
            exists = self.db.query(KnowledgeEntry).filter(
                KnowledgeEntry.ext_id == pb["ext_id"]).first()
            if exists:
                continue
            self.db.add(KnowledgeEntry(
                source="playbook", ext_id=pb["ext_id"], title=pb["title"],
                description=pb["content"][:300], content=pb["content"],
                severity=pb["severity"], cwe=pb["cwe"], tags=pb["tags"],
                references=[],
            ))
            added += 1
        if added:
            self.db.commit()
        return added

    async def ingest_nvd(self, keyword: str, limit: int = 15) -> int:
        """Fetch CVE metadata from the public NVD 2.0 API and store it."""
        params = {"keywordSearch": keyword, "resultsPerPage": min(limit, 50)}
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(NVD_API, params=params)
        except httpx.HTTPError as e:
            raise RuntimeError(f"NVD request failed: {e}")
        if resp.status_code != 200:
            raise RuntimeError(f"NVD API returned {resp.status_code}")
        try:
            body = resp.json()
        except ValueError:
            raise RuntimeError("NVD returned a non-JSON response (rate-limited?)")

        vulns = body.get("vulnerabilities", [])
        added = 0
        for v in vulns:
            cve = v.get("cve", {})
            cve_id = cve.get("id")
            if not cve_id:
                continue
            if self.db.query(KnowledgeEntry).filter(KnowledgeEntry.ext_id == cve_id).first():
                continue

            descs = cve.get("descriptions", [])
            desc = next((d["value"] for d in descs if d.get("lang") == "en"), "")

            score, sev = None, None
            metrics = cve.get("metrics", {})
            for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
                if metrics.get(key):
                    data = metrics[key][0].get("cvssData", {})
                    score = data.get("baseScore")
                    sev = data.get("baseSeverity") or metrics[key][0].get("baseSeverity")
                    break

            cwe = None
            for w in cve.get("weaknesses", []):
                for d in w.get("description", []):
                    if d.get("value", "").startswith("CWE-"):
                        cwe = d["value"]
                        break
                if cwe:
                    break

            refs = [r.get("url") for r in cve.get("references", []) if r.get("url")][:10]

            self.db.add(KnowledgeEntry(
                source="nvd", ext_id=cve_id, title=cve_id,
                description=desc, severity=sev, cvss_score=score, cwe=cwe,
                references=refs, tags=keyword.lower(),
            ))
            added += 1
        if added:
            self.db.commit()
        return added
