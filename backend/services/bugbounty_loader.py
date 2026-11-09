"""
Bug-bounty reports knowledge base.

Ingests PUBLIC disclosed bug-bounty writeups (pentester.land's curated
writeups.json — thousands of real reports with title, vuln types, programs,
authors, links) into the knowledge layer as source="bugbounty". The autonomous
agent can then search_knowledge() for real disclosed techniques on a given vuln
class / target tech and GROUND its approach in what actually worked — instead of
inventing techniques when it's stuck.

This is a reference/index layer (title + vuln types + programs + link), not a
copy of the reports; it tells the agent such a technique exists and where the
public writeup is.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from models.knowledge_entry import KnowledgeEntry
from utils.logger import get_logger

logger = get_logger(__name__)

PENTESTERLAND_URL = "https://pentester.land/writeups.json"
HACKERONE_CSV_URL = "https://raw.githubusercontent.com/reddelexc/hackerone-reports/master/data.csv"


def _ext_id(link: str) -> str:
    return "bb-" + hashlib.sha1((link or "").encode("utf-8")).hexdigest()[:16]


async def ingest_pentesterland(db: Session, limit: Optional[int] = None) -> dict:
    """Fetch pentester.land writeups.json and upsert into knowledge_entries."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(PENTESTERLAND_URL)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not fetch writeups: {e}")
    if resp.status_code != 200:
        raise RuntimeError(f"writeups.json returned {resp.status_code}")

    try:
        body = resp.json()
    except ValueError:
        raise RuntimeError("writeups.json returned a non-JSON response")
    items = body.get("data") if isinstance(body, dict) else body
    if not isinstance(items, list):
        raise RuntimeError("Unexpected writeups.json shape")
    if limit:
        items = items[:limit]

    added = updated = 0
    seen = set()  # dedup within this run (autoflush=False → repeat inserts otherwise)
    for it in items:
        links = it.get("Links") or []
        if not links:
            continue
        title = (links[0].get("Title") or "").strip()
        url = (links[0].get("Link") or "").strip()
        if not title or not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        bugs = it.get("Bugs") or []
        programs = it.get("Programs") or []
        authors = it.get("Authors") or []
        bounty = it.get("Bounty") or ""
        pub = it.get("PublicationDate") or ""

        tags = ", ".join([*bugs, *programs])[:400]
        summary = (
            f"Bug types: {', '.join(bugs) or 'n/a'}. "
            f"Programs/targets: {', '.join(programs) or 'n/a'}. "
            f"By {', '.join(authors) or 'unknown'}"
            + (f" ({pub})" if pub else "")
            + (f". Bounty: {bounty}" if bounty and bounty != "-" else "")
        )
        refs = [link.get("Link") for link in links if link.get("Link")]

        ext = _ext_id(url)
        row = db.query(KnowledgeEntry).filter(
            KnowledgeEntry.ext_id == ext, KnowledgeEntry.source == "bugbounty").first()
        if row:
            row.title = title[:400]
            row.description = summary[:2000]
            row.content = summary[:2000]
            row.tags = tags
            row.references = refs
            updated += 1
        else:
            db.add(KnowledgeEntry(
                source="bugbounty", ext_id=ext, title=title[:400],
                description=summary[:2000], content=summary[:2000],
                tags=tags, references=refs))
            added += 1
        # Commit in batches to avoid a giant transaction.
        if (added + updated) % 500 == 0:
            db.commit()

    db.commit()
    logger.info("Ingested bug-bounty writeups", added=added, updated=updated)
    return {"added": added, "updated": updated, "total_seen": len(items)}


def _bounty_severity(bounty: str) -> Optional[str]:
    """Rough severity band from bounty amount (signal for ranking)."""
    try:
        b = float(str(bounty).replace(",", "") or 0)
    except ValueError:
        return None
    if b >= 10000:
        return "CRITICAL"
    if b >= 3000:
        return "HIGH"
    if b >= 500:
        return "MEDIUM"
    if b > 0:
        return "LOW"
    return None


async def ingest_hackerone_csv(db: Session, limit: Optional[int] = None) -> dict:
    """Ingest reddelexc/hackerone-reports data.csv — disclosed HackerOne reports
    with program, vuln_type, upvotes and REAL bounty amounts."""
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            resp = await client.get(HACKERONE_CSV_URL)
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not fetch HackerOne data.csv: {e}")
    if resp.status_code != 200:
        raise RuntimeError(f"data.csv returned {resp.status_code}")

    reader = csv.DictReader(io.StringIO(resp.text))
    added = updated = 0
    n = 0
    seen = set()
    for row in reader:
        title = (row.get("title") or "").strip()
        link = (row.get("link") or "").strip()
        if not title or not link:
            continue
        if not link.startswith("http"):
            link = "https://" + link
        program = (row.get("program") or "").strip()
        vuln = (row.get("vuln_type") or "").strip()
        upvotes = (row.get("upvotes") or "").strip()
        bounty = (row.get("bounty") or "").strip()

        m = re.search(r"/reports/(\d+)", link)
        ext = "h1-" + (m.group(1) if m else hashlib.sha1(link.encode()).hexdigest()[:12])
        if ext in seen:
            continue
        seen.add(ext)
        tags = ", ".join(t for t in [vuln, program] if t)[:400]
        summary = (f"HackerOne report. Program: {program or 'n/a'}. "
                   f"Vuln type: {vuln or 'n/a'}. Upvotes: {upvotes or '0'}"
                   + (f". Bounty: ${bounty}" if bounty and bounty not in ('0', '0.0', '') else ""))

        row_obj = db.query(KnowledgeEntry).filter(
            KnowledgeEntry.ext_id == ext, KnowledgeEntry.source == "h1report").first()
        if row_obj:
            row_obj.title = title[:400]
            row_obj.description = summary[:2000]
            row_obj.content = summary[:2000]
            row_obj.tags = tags
            row_obj.references = [link]
            row_obj.severity = _bounty_severity(bounty)
            updated += 1
        else:
            db.add(KnowledgeEntry(
                source="h1report", ext_id=ext, title=title[:400],
                description=summary[:2000], content=summary[:2000], tags=tags,
                references=[link], severity=_bounty_severity(bounty)))
            added += 1
        n += 1
        if limit and n >= limit:
            break
        if (added + updated) % 500 == 0:
            db.commit()

    db.commit()
    logger.info("Ingested HackerOne reports", added=added, updated=updated)
    return {"added": added, "updated": updated, "total_seen": n}
