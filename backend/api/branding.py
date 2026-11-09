"""
Report branding API (E4) — org identity on generated reports.

GET is open to any authenticated user (report preview needs it); writes are
admin-only (enforced by the RBAC middleware's _WRITE_ADMIN rules).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from database import get_db
from services.audit_service import record as audit
from services import branding as branding_svc
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/branding", tags=["branding"])


class BrandingUpdate(BaseModel):
    organization: Optional[str] = None
    tagline: Optional[str] = None
    classification: Optional[str] = None
    primary_color: Optional[str] = None


@router.get("")
async def get_branding(db: Session = Depends(get_db)):
    return branding_svc.get_branding(db)


@router.put("")
async def update_branding(body: BrandingUpdate, request: Request,
                          db: Session = Depends(get_db)):
    try:
        out = branding_svc.update_branding(
            db, organization=body.organization, tagline=body.tagline,
            classification=body.classification,
            primary_color=body.primary_color)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, action="branding.updated", request=request, detail={
        k: v for k, v in body.model_dump(exclude_unset=True).items()})
    return out


@router.post("/logo")
async def upload_logo(request: Request, file: UploadFile = File(...),
                      db: Session = Depends(get_db)):
    data = await file.read()
    try:
        out = branding_svc.save_logo(db, data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    audit(db, action="branding.logo_uploaded", request=request,
          detail={"filename": file.filename, "bytes": len(data)})
    return out


@router.delete("/logo")
async def delete_logo(request: Request, db: Session = Depends(get_db)):
    out = branding_svc.clear_logo(db)
    audit(db, action="branding.logo_cleared", request=request)
    return out
