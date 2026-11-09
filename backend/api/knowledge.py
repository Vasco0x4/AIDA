"""
Knowledge base API — offensive-security reference (CVEs, advisories, playbooks).
"""
import gzip
import io
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from services.audit_service import record as audit
from database import get_db
from models.knowledge_entry import KnowledgeEntry
from services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class KnowledgeResponse(BaseModel):
    id: int
    source: str
    ext_id: Optional[str]
    title: str
    description: Optional[str]
    content: Optional[str]
    severity: Optional[str]
    cvss_score: Optional[float]
    cwe: Optional[str]
    references: list = []
    tags: Optional[str]

    class Config:
        from_attributes = True


class IngestRequest(BaseModel):
    keyword: str
    limit: int = 15


@router.get("/stats")
def knowledge_stats(db: Session = Depends(get_db)):
    """Counts per knowledge source (for the Settings UI)."""
    from sqlalchemy import func
    rows = (db.query(KnowledgeEntry.source, func.count(KnowledgeEntry.id))
            .group_by(KnowledgeEntry.source).all())
    by_source = {s: c for s, c in rows}
    return {"total": sum(by_source.values()), "by_source": by_source}


@router.get("", response_model=List[KnowledgeResponse])
def search_knowledge(q: Optional[str] = None, source: Optional[str] = None,
                     limit: int = 20, db: Session = Depends(get_db)):
    return KnowledgeService(db).search(query=q, source=source, limit=limit)


@router.get("/{entry_id:int}", response_model=KnowledgeResponse)
def get_entry(entry_id: int, db: Session = Depends(get_db)):
    row = db.query(KnowledgeEntry).filter(KnowledgeEntry.id == entry_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    return row


@router.post("/ingest/nvd")
async def ingest_nvd(body: IngestRequest, request: Request,
                    db: Session = Depends(get_db)):
    """Pull CVE metadata from the public NVD API by keyword."""
    try:
        added = await KnowledgeService(db).ingest_nvd(body.keyword, body.limit)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    audit(db, action="knowledge.ingest_nvd", request=request,
          detail={"keyword": body.keyword, "added": added})
    return {"ingested": added, "keyword": body.keyword}


_EXPORT_FIELDS = ("source", "ext_id", "title", "description", "content",
                  "severity", "cvss_score", "cwe", "references", "tags")


@router.get("/export")
def export_knowledge(source: Optional[str] = None, db: Session = Depends(get_db)):
    """Export the knowledge base as a compact gzipped JSONL file (portable/backup;
    much smaller than a DB dump — seed another instance offline with /import)."""
    q = db.query(KnowledgeEntry)
    if source:
        q = q.filter(KnowledgeEntry.source == source)

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        for e in q.yield_per(1000):
            row = {f: getattr(e, f) for f in _EXPORT_FIELDS}
            gz.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
    buf.seek(0)
    name = f"aida_knowledge_{source or 'all'}.jsonl.gz"
    return StreamingResponse(buf, media_type="application/gzip",
                             headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/import")
async def import_knowledge(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import a knowledge JSONL(.gz) export (upsert by source+ext_id)."""
    data = await file.read()
    if data[:2] == b"\x1f\x8b":  # gzip magic
        try:
            data = gzip.decompress(data)
        except Exception:
            raise HTTPException(status_code=422, detail="Bad gzip file")
    added = updated = 0
    for line in data.decode("utf-8", "ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        ext, src = r.get("ext_id"), r.get("source")
        row = None
        if ext:
            row = db.query(KnowledgeEntry).filter(
                KnowledgeEntry.ext_id == ext, KnowledgeEntry.source == src).first()
        if row:
            updated += 1
        else:
            row = KnowledgeEntry(source=src, ext_id=ext)
            db.add(row)
            added += 1
        for f in ("title", "description", "content", "severity", "cvss_score",
                  "cwe", "references", "tags"):
            if f in r:
                setattr(row, f, r[f])
        if (added + updated) % 1000 == 0:
            db.commit()
    db.commit()
    return {"added": added, "updated": updated}


@router.post("/seed-playbooks")
def seed_playbooks(db: Session = Depends(get_db)):
    added = KnowledgeService(db).seed_playbooks()
    return {"added": added}


class BugBountyIngest(BaseModel):
    limit: Optional[int] = None  # None = all (~6.4k)


@router.post("/ingest/bugbounty")
async def ingest_bugbounty(body: BugBountyIngest, db: Session = Depends(get_db)):
    """Ingest public disclosed bug-bounty reports from BOTH pentester.land
    (writeups) and reddelexc/hackerone-reports (H1 reports w/ bounty), so the
    agent can ground its approach in real reports."""
    from services.bugbounty_loader import ingest_pentesterland, ingest_hackerone_csv
    out = {}
    try:
        out["pentesterland"] = await ingest_pentesterland(db, limit=body.limit)
    except RuntimeError as e:
        out["pentesterland"] = {"error": str(e)}
    try:
        out["hackerone"] = await ingest_hackerone_csv(db, limit=body.limit)
    except RuntimeError as e:
        out["hackerone"] = {"error": str(e)}
    if all(isinstance(v, dict) and v.get("error") for v in out.values()):
        raise HTTPException(status_code=502, detail="; ".join(v["error"] for v in out.values()))
    return out
