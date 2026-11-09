"""CRUD for reusable, bounded Scan Profiles."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models.scan_profile import ScanProfile
from services.audit_service import record as audit

router = APIRouter(prefix="/scan-profiles", tags=["scan-profiles"])


class ProfileBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(pattern="^(safe_web_baseline|autonomous)$")
    description: Optional[str] = None
    rate_limit_seconds: int = Field(60, ge=1, le=3600)
    max_pages: int = Field(8, ge=1, le=25)
    max_response_bytes: int = Field(1_000_000, ge=1024, le=2_000_000)
    timeout_seconds: int = Field(5, ge=1, le=15)
    max_concurrency: int = Field(1, ge=1, le=1)
    enabled: bool = True


class ProfileCreate(ProfileBase):
    pass


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    kind: Optional[str] = Field(None, pattern="^(safe_web_baseline|autonomous)$")
    description: Optional[str] = None
    rate_limit_seconds: Optional[int] = Field(None, ge=1, le=3600)
    max_pages: Optional[int] = Field(None, ge=1, le=25)
    max_response_bytes: Optional[int] = Field(None, ge=1024, le=2_000_000)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=15)
    max_concurrency: Optional[int] = Field(None, ge=1, le=1)
    enabled: Optional[bool] = None


class ProfileResponse(ProfileBase):
    id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.get("", response_model=List[ProfileResponse])
def list_profiles(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                  db: Session = Depends(get_db)):
    return db.query(ScanProfile).order_by(ScanProfile.name).offset(skip).limit(limit).all()


@router.post("", response_model=ProfileResponse, status_code=201)
def create_profile(body: ProfileCreate, request: Request, db: Session = Depends(get_db)):
    if db.query(ScanProfile).filter(func.lower(ScanProfile.name) == body.name.strip().lower()).first():
        raise HTTPException(409, "A Scan Profile with this name already exists")
    row = ScanProfile(**{**body.model_dump(), "name": body.name.strip()})
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, action="scan_profile.created", request=request,
          resource_type="scan_profile", resource_id=row.id, detail={"name": row.name, "kind": row.kind})
    return row


@router.put("/{profile_id}", response_model=ProfileResponse)
def update_profile(profile_id: int, body: ProfileUpdate, request: Request,
                   db: Session = Depends(get_db)):
    row = db.get(ScanProfile, profile_id)
    if row is None:
        raise HTTPException(404, "Scan Profile not found")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("name"):
        fields["name"] = fields["name"].strip()
        duplicate = db.query(ScanProfile).filter(
            func.lower(ScanProfile.name) == fields["name"].lower(),
            ScanProfile.id != profile_id).first()
        if duplicate:
            raise HTTPException(409, "A Scan Profile with this name already exists")
    for key, value in fields.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    audit(db, action="scan_profile.updated", request=request,
          resource_type="scan_profile", resource_id=profile_id, detail={"fields": sorted(fields)})
    return row


@router.delete("/{profile_id}", status_code=204)
def delete_profile(profile_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.get(ScanProfile, profile_id)
    if row is None:
        raise HTTPException(404, "Scan Profile not found")
    db.delete(row)
    db.commit()
    audit(db, action="scan_profile.deleted", request=request,
          resource_type="scan_profile", resource_id=profile_id)
    return None
