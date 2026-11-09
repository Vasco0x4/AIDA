"""
Submission-ready report API.

Turns a finding (Card) into a polished, platform-formatted bug-bounty report
(HackerOne / Bugcrowd / generic), grounded by similar disclosed reports from the
knowledge base. Optionally persists the result as a PDF artifact on the finding
(also mirrored to disk under ~/AIDA-dev/evidence), and can render any report
Markdown to a downloadable PDF on demand.
"""
import io
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.card import Card
from models.artifact import Artifact
from services.submission_service import generate_submission, PLATFORM_HINTS
from services.pdf_render import markdown_to_pdf, image_data_uri
from services.evidence_store import mirror_artifact
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/submission", tags=["submission"])


class GenerateBody(BaseModel):
    platform: str = "hackerone"
    save: bool = False
    format: str = "pdf"          # saved-artifact format: "pdf" (default) or "md"


class RenderBody(BaseModel):
    markdown: str
    title: Optional[str] = None
    filename: Optional[str] = None
    card_id: Optional[int] = None   # embed this finding's screenshots into the PDF


def _safe_filename(name: str, fallback: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip("-")
    return name or fallback


# Bound how much imagery we embed so a finding with many/huge screenshots can't
# produce a runaway PDF or exhaust memory during render.
_MAX_FIGURES = 15
_MAX_FIGURE_BYTES = 8 * 1024 * 1024        # skip any single image larger than this
_MAX_FIGURES_TOTAL_BYTES = 40 * 1024 * 1024  # stop once embedded imagery hits this


def _figures_for_card(db: Session, card_id: Optional[int]) -> list:
    """Collect a finding's image artifacts as embeddable PDF figures — the
    screenshots a human would attach to the report as evidence."""
    if not card_id:
        return []
    rows = (db.query(Artifact)
            .filter(Artifact.card_id == card_id)
            .order_by(Artifact.id).all())
    figs, total = [], 0
    for a in rows:
        if not (a.content_type and a.content_type.startswith("image/") and a.data):
            continue
        size = len(a.data)
        if size > _MAX_FIGURE_BYTES:
            continue
        if total + size > _MAX_FIGURES_TOTAL_BYTES or len(figs) >= _MAX_FIGURES:
            break
        total += size
        figs.append({"caption": a.caption or a.filename,
                     "data_uri": image_data_uri(a.data, a.content_type)})
    return figs


@router.get("/platforms")
def list_platforms():
    return [{"id": k, "label": k.capitalize()} for k in PLATFORM_HINTS]


@router.post("/render-pdf")
def render_pdf(body: RenderBody, db: Session = Depends(get_db)):
    """Render already-generated report Markdown to a downloadable PDF (no LLM
    call) — used by the 'Download PDF' button on the current report. Embeds the
    finding's screenshots when card_id is given."""
    if not (body.markdown or "").strip():
        raise HTTPException(status_code=422, detail="markdown is required")
    try:
        figures = _figures_for_card(db, body.card_id)
        pdf = markdown_to_pdf(body.markdown, body.title or "Vulnerability Report", figures)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF render failed: {e}")
    fname = _safe_filename(body.filename or (body.title or "report"), "report") + ".pdf"
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/{card_id}")
async def generate(card_id: int, body: GenerateBody, db: Session = Depends(get_db)):
    platform = (body.platform or "hackerone").lower()
    if platform not in PLATFORM_HINTS:
        platform = "generic"
    try:
        result = await generate_submission(db, card_id, platform)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if body.save:
        card = db.query(Card).filter(Card.id == card_id).first()
        if not card:  # deleted between generation and save
            raise HTTPException(status_code=404, detail="Finding not found")
        report = result["report_markdown"] or ""
        fmt = (body.format or "pdf").lower()

        if fmt == "md":
            data = report.encode("utf-8")
            fname = f"submission-{platform}-card{card_id}.md"
            ctype = "text/markdown"
        else:  # default: PDF (with the finding's screenshots embedded as evidence)
            try:
                figures = _figures_for_card(db, card_id)
                # WeasyPrint is CPU-heavy + synchronous — run it off the event loop.
                data = await run_in_threadpool(
                    markdown_to_pdf, report, card.title if card else "Vulnerability Report", figures)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"PDF render failed: {e}")
            fname = f"submission-{platform}-card{card_id}.pdf"
            ctype = "application/pdf"

        art = Artifact(
            assessment_id=card.assessment_id, card_id=card_id, kind="file",
            filename=fname, content_type=ctype,
            caption=f"{platform.capitalize()} submission-ready report",
            size_bytes=len(data), data=data)
        db.add(art)
        db.commit()
        db.refresh(art)
        # Mirror to disk (~/AIDA-dev/evidence/<assessment>/), best-effort.
        rel = mirror_artifact(db, art)
        result["artifact_id"] = art.id
        result["format"] = fmt if fmt == "md" else "pdf"
        if rel:
            result["disk_path"] = rel

    return result
