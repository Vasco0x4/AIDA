"""
Subdomain Takeover API — enumerate a domain's subdomains and check each against
the can-i-take-over-xyz fingerprint set.

Scans run in the BACKGROUND and are PERSISTED (survive restarts): POST returns a
scan_id, progress + results stream over WebSocket (takeover_progress/done) and
are written to the DB. History is listable/deletable, and each result asset can
carry an operator note.
"""
import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, SessionLocal
from models import Assessment
from models.takeover_scan import TakeoverScan, TakeoverResult
from services.audit_service import record as audit
from services.takeover_service import TakeoverService, load_fingerprints
from websocket.manager import manager
from websocket.events import create_event, EventType
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/takeover", tags=["takeover"])

# Keep strong refs to fire-and-forget scan tasks so they aren't GC'd mid-run.
_scan_tasks: set = set()


# --------------------------------------------------------------- schemas
class ScanRequest(BaseModel):
    domain: str
    subdomains: Optional[List[str]] = None
    assessment_id: Optional[int] = None


class NoteBody(BaseModel):
    note: Optional[str] = None


def _scan_dict(s: TakeoverScan) -> dict:
    return {
        "scan_id": s.id, "domain": s.domain, "status": s.status,
        "wildcard": s.wildcard, "checked": s.checked, "total": s.total,
        "summary": {"vulnerable": s.vulnerable, "edge_case": s.edge_case,
                    "not_vulnerable": s.not_vulnerable},
        "error": s.error,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "finished_at": s.finished_at.isoformat() if s.finished_at else None,
    }


def _result_dict(r: TakeoverResult) -> dict:
    return {
        "id": r.id, "subdomain": r.subdomain, "verdict": r.verdict,
        "service": r.service, "confidence": r.confidence,
        "cname_target": r.cname_target, "dns_status": r.dns_status,
        "evidence": r.evidence, "fingerprint": r.fingerprint,
        "documentation": r.documentation, "note": r.note,
    }


# --------------------------------------------------------------- fingerprints
@router.get("/fingerprints")
def list_fingerprints():
    fps = load_fingerprints()
    return [{
        "service": f.service, "status": f.status, "vulnerable": f.vulnerable,
        "nxdomain": f.nxdomain, "cnames": f.cnames,
        "fingerprint": f.raw_fp, "documentation": f.documentation,
    } for f in fps]


# --------------------------------------------------------------- scan history
@router.get("/scans")
def list_scans(limit: int = 50, db: Session = Depends(get_db)):
    rows = (db.query(TakeoverScan).order_by(TakeoverScan.id.desc())
            .limit(min(limit, 200)).all())
    return [_scan_dict(s) for s in rows]


@router.get("/scans/{scan_id}")
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    s = db.query(TakeoverScan).filter(TakeoverScan.id == scan_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan not found")
    order = {"VULNERABLE": 0, "EDGE_CASE": 1, "NOT_VULNERABLE": 2}
    results = sorted((db.query(TakeoverResult)
                      .filter(TakeoverResult.scan_id == scan_id).all()),
                     key=lambda r: order.get(r.verdict, 9))
    d = _scan_dict(s)
    d["results"] = [_result_dict(r) for r in results]
    return d


@router.delete("/scans/{scan_id}", status_code=204)
def delete_scan(scan_id: int, request: Request, db: Session = Depends(get_db)):
    s = db.query(TakeoverScan).filter(TakeoverScan.id == scan_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Scan not found")
    db.delete(s)  # cascades to results
    db.commit()
    audit(db, action="takeover.scan_deleted", request=request,
          resource_type="takeover_scan", resource_id=scan_id)


@router.patch("/results/{result_id}")
def set_result_note(result_id: int, body: NoteBody, db: Session = Depends(get_db)):
    r = db.query(TakeoverResult).filter(TakeoverResult.id == result_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Result not found")
    r.note = body.note
    db.commit()
    return _result_dict(r)


@router.delete("/results/{result_id}", status_code=204)
def delete_result(result_id: int, db: Session = Depends(get_db)):
    r = db.query(TakeoverResult).filter(TakeoverResult.id == result_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Result not found")
    db.delete(r)
    db.commit()


# --------------------------------------------------------------- start scan
@router.post("/scan")
async def start_scan(body: ScanRequest, db: Session = Depends(get_db)):
    domain = (body.domain or "").strip()
    if not domain:
        raise HTTPException(status_code=422, detail="domain is required")
    scan = TakeoverScan(domain=domain, status="running")
    db.add(scan)
    db.commit()
    db.refresh(scan)
    task = asyncio.create_task(_run_scan(scan.id, domain, body.subdomains, body.assessment_id))
    _scan_tasks.add(task)
    task.add_done_callback(_scan_tasks.discard)
    return {"scan_id": scan.id, "status": "running"}


async def _run_scan(scan_id: int, domain: str, subdomains, assessment_id):
    db = SessionLocal()
    lock = asyncio.Lock()
    # In-memory counters (source of truth); DB writes are throttled + self-healing.
    state = {"checked": 0, "total": 0, "vulnerable": 0, "edge_case": 0,
             "not_vulnerable": 0, "wildcard": False}
    status, error, results = "error", None, []

    def _clean(s):  # strip NUL bytes that would break a Postgres text insert
        return s.replace("\x00", "") if isinstance(s, str) else s

    async def on_progress(ev):
        r = ev.get("result")
        state["checked"], state["total"] = ev["checked"], ev["total"]
        if r:
            key = {"VULNERABLE": "vulnerable", "EDGE_CASE": "edge_case",
                   "NOT_VULNERABLE": "not_vulnerable"}.get(r["verdict"])
            if key:
                state[key] += 1
        # Persist only on a result or every 25 checks (throttle) — self-healing.
        if r or ev["checked"] % 25 == 0 or ev["checked"] == ev["total"]:
            async with lock:
                try:
                    scan = db.query(TakeoverScan).filter(TakeoverScan.id == scan_id).first()
                    if scan:
                        scan.checked, scan.total = state["checked"], state["total"]
                        scan.vulnerable, scan.edge_case, scan.not_vulnerable = (
                            state["vulnerable"], state["edge_case"], state["not_vulnerable"])
                        if r:
                            db.add(TakeoverResult(
                                scan_id=scan_id, subdomain=_clean(r["subdomain"]), verdict=r["verdict"],
                                service=r.get("service"), confidence=r.get("confidence"),
                                cname_target=_clean(r.get("cname_target")), dns_status=r.get("dns_status"),
                                evidence=_clean(r.get("evidence")), fingerprint=_clean(r.get("fingerprint")),
                                documentation=r.get("documentation")))
                        db.commit()
                except Exception:
                    db.rollback()  # don't poison the session for other coroutines
                    logger.warning("takeover progress persist failed", scan_id=scan_id)
        if r or ev["checked"] % 10 == 0 or ev["checked"] == ev["total"]:
            await manager.broadcast(create_event(EventType.TAKEOVER_PROGRESS, {
                "scan_id": scan_id, "checked": state["checked"], "total": state["total"],
                "result": r, "summary": {k: state[k] for k in ("vulnerable", "edge_case", "not_vulnerable")}}))

    try:
        result = await TakeoverService().scan(domain, subdomains=subdomains, on_progress=on_progress)
        results = result["results"]
        state["wildcard"] = result["wildcard"]
        state["total"] = result["subdomains_checked"]
        status, error = "done", None
    except Exception as e:
        logger.exception("takeover scan failed", scan_id=scan_id)
        status, error = "error", str(e)
    finally:
        # Bulletproof teardown: always finalize the scan row + broadcast DONE.
        try:
            db.rollback()
            scan = db.query(TakeoverScan).filter(TakeoverScan.id == scan_id).first()
            if scan:
                scan.status = status
                scan.error = error
                scan.wildcard = state["wildcard"]
                scan.checked, scan.total = state["checked"], state["total"]
                scan.vulnerable, scan.edge_case, scan.not_vulnerable = (
                    state["vulnerable"], state["edge_case"], state["not_vulnerable"])
                from sqlalchemy import func as _f
                scan.finished_at = _f.now()
                db.commit()
            if status == "done" and assessment_id and results:
                _record_findings(db, assessment_id, results)
        except Exception:
            logger.exception("takeover finalize failed", scan_id=scan_id)
        finally:
            try:
                db.close()
            except Exception:
                pass
            try:
                await manager.broadcast(create_event(EventType.TAKEOVER_DONE, {
                    "scan_id": scan_id, "status": status,
                    "checked": state["checked"], "total": state["total"],
                    "wildcard": state["wildcard"], "error": error,
                    "summary": {k: state[k] for k in ("vulnerable", "edge_case", "not_vulnerable")}}))
            except Exception:
                pass


def _record_findings(db: Session, assessment_id: int, results: list) -> int:
    if not db.query(Assessment).filter(Assessment.id == assessment_id).first():
        return 0
    from models.card import Card
    from models.recon_data import ReconData
    added = 0
    for r in results:
        db.add(ReconData(
            assessment_id=assessment_id, data_type="subdomain", name=r["subdomain"],
            details={"takeover_verdict": r["verdict"], "service": r["service"],
                     "cname": r.get("cname_target")}, discovered_in_phase="takeover"))
        if r["verdict"] in ("VULNERABLE", "EDGE_CASE"):
            db.add(Card(
                assessment_id=assessment_id, card_type="finding",
                title=f"Subdomain takeover ({r['service']}): {r['subdomain']}",
                severity="HIGH" if r["verdict"] == "VULNERABLE" else "MEDIUM",
                status="potential" if r["verdict"] == "VULNERABLE" else "untested",
                target_service=r["service"],
                technical_analysis=(f"`{r['subdomain']}` points to **{r['service']}** "
                                    f"(CNAME → `{r.get('cname_target')}`), appears unclaimed. "
                                    f"Verdict **{r['verdict']}** ({r['confidence']}). {r['evidence']}."),
                proof=(f"DNS: {r['dns_status']}, CNAME chain: {', '.join(r['cname_chain']) or '-'}\n"
                       f"Matched fingerprint: {r['fingerprint']}\n"
                       f"Reference: {r.get('documentation') or 'can-i-take-over-xyz'}")))
            added += 1
    db.commit()
    return added
