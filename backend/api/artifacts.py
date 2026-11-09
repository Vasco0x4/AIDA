"""
Artifact API — evidence files (screenshots, captures) linked to findings.

Upload is multipart; content is streamed back for the UI. Images embed into the
PDF report automatically (see report_service).
"""
from typing import List, Optional
import io

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from services.audit_service import record as audit
from models.artifact import Artifact
from models.assessment import Assessment
from models.card import Card

router = APIRouter(tags=["artifacts"])

MAX_ARTIFACT_BYTES = 15 * 1024 * 1024  # 15 MB


class ArtifactMeta(BaseModel):
    id: int
    assessment_id: int
    card_id: Optional[int]
    kind: str
    filename: str
    content_type: str
    caption: Optional[str]
    size_bytes: Optional[int]
    hash_self: Optional[str] = None

    class Config:
        from_attributes = True


@router.get("/assessments/{assessment_id}/artifacts/chain")
def verify_evidence_chain(assessment_id: int, db: Session = Depends(get_db)):
    """E3 tamper-evidence: walk the assessment's evidence hash chain and report
    whether every stored artifact still matches its recorded hash."""
    if not db.query(Assessment).filter(Assessment.id == assessment_id).first():
        raise HTTPException(status_code=404, detail="Assessment not found")
    from services.evidence_chain import verify_chain
    result = verify_chain(db, assessment_id)
    result["status"] = "intact" if result["ok"] else "BROKEN"
    return result


@router.get("/assessments/{assessment_id}/artifacts", response_model=List[ArtifactMeta])
def list_artifacts(assessment_id: int, card_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Artifact).filter(Artifact.assessment_id == assessment_id)
    if card_id is not None:
        q = q.filter(Artifact.card_id == card_id)
    return q.order_by(Artifact.created_at.desc()).all()


@router.post("/assessments/{assessment_id}/artifacts", response_model=ArtifactMeta, status_code=201)
async def upload_artifact(
    assessment_id: int,
    file: UploadFile = File(...),
    card_id: Optional[int] = Form(None),
    caption: Optional[str] = Form(None),
    kind: str = Form("screenshot"),
    db: Session = Depends(get_db),
):
    if not db.query(Assessment).filter(Assessment.id == assessment_id).first():
        raise HTTPException(status_code=404, detail="Assessment not found")
    if card_id is not None and not db.query(Card).filter(Card.id == card_id).first():
        raise HTTPException(status_code=404, detail="Card not found")

    data = await file.read()
    if len(data) > MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail="Artifact too large (max 15 MB)")
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")

    row = Artifact(
        assessment_id=assessment_id,
        card_id=card_id,
        kind=kind if kind in ("screenshot", "file") else "file",
        filename=file.filename or "artifact",
        content_type=file.content_type or "application/octet-stream",
        caption=caption,
        size_bytes=len(data),
        data=data,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    from services.evidence_store import mirror_artifact
    mirror_artifact(db, row)  # also write to disk (~/AIDA-dev/evidence)
    return row


@router.get("/artifacts/{artifact_id}/content")
def get_artifact_content(artifact_id: int, db: Session = Depends(get_db)):
    row = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return StreamingResponse(
        io.BytesIO(row.data),
        media_type=row.content_type,
        headers={"Content-Disposition": f'inline; filename="{row.filename}"'},
    )


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(artifact_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.query(Artifact).filter(Artifact.id == artifact_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Artifact not found")
    db.delete(row)
    db.commit()
    audit(db, action="artifact.deleted", request=request,
          resource_type="artifact", resource_id=artifact_id)
