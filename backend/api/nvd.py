"""Authenticated API for the cached NVD critical-CVE digest."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from auth import require_admin
from database import get_db
from models.user import User
from services.audit_service import record as audit
from services.nvd_service import NVDService

router = APIRouter(prefix="/nvd", tags=["nvd"])


class NVDScheduleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    refresh_interval_hours: int | None = Field(default=None, ge=1, le=720)
    lookback_days: int | None = Field(default=None, ge=1, le=120)
    max_items: int | None = Field(default=None, ge=1, le=5000)
    include_cvss_v4: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("NVD schedule fields cannot be null")
        return self


class NVDKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str = Field(min_length=1, max_length=512)


@router.get("/digest")
def get_digest(db: Session = Depends(get_db)) -> dict:
    return NVDService(db).get_digest()


@router.get("/status")
def get_status(db: Session = Depends(get_db)) -> dict:
    return NVDService(db).get_status()


@router.post("/refresh")
def manual_refresh(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    return NVDService(db).refresh(force=True)


@router.put("/schedule")
def update_schedule(
    body: NVDScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    changes = body.model_dump(exclude_unset=True)
    result = NVDService(db).update_schedule(**changes)
    audit(
        db,
        action="nvd.schedule.updated",
        request=request,
        resource_type="nvd_digest_state",
        resource_id=1,
        detail={"fields": sorted(changes)},
    )
    return result


@router.put("/key")
def update_api_key(
    body: NVDKeyUpdate,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    result = NVDService(db).set_api_key(body.api_key)
    audit(db, action="nvd.key.updated", request=request,
          resource_type="nvd_digest_state", resource_id=1,
          detail={"storage": "encrypted"})
    return result


@router.delete("/key")
def clear_api_key(
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict:
    result = NVDService(db).clear_api_key()
    audit(db, action="nvd.key.cleared", request=request,
          resource_type="nvd_digest_state", resource_id=1)
    return result
