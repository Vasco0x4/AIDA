"""
SSO configuration API (admin only) — the Settings → SSO tab's backend.

Dedicated endpoint rather than raw platform-settings writes so that:
- the client secret is encrypted at rest and NEVER read back (only a
  ``has_secret`` flag is returned),
- the whole config round-trips as one typed payload,
- every change lands in the audit trail as a single event.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import ROLE_PATTERN, require_admin
from database import get_db
from models.user import User
from services import oidc_service
from services.audit_service import record as audit

router = APIRouter(prefix="/sso", tags=["SSO"])


class SSOConfigResponse(BaseModel):
    enabled: bool
    issuer: str
    client_id: str
    has_secret: bool
    default_role: str
    redirect_base: str


class SSOConfigUpdate(BaseModel):
    enabled: bool = False
    issuer: str = ""
    client_id: str = ""
    client_secret: Optional[str] = None  # None/empty = keep stored secret
    default_role: str = Field("viewer", pattern=ROLE_PATTERN)
    redirect_base: str = ""


@router.get("/config", response_model=SSOConfigResponse)
def get_sso_config(db: Session = Depends(get_db),
                   current_user: User = Depends(require_admin)):
    cfg = oidc_service.get_config(db)
    return SSOConfigResponse(
        enabled=cfg["enabled"],
        issuer=cfg["issuer"],
        client_id=cfg["client_id"],
        has_secret=bool(cfg["client_secret"]),
        default_role=cfg["default_role"],
        redirect_base=cfg["redirect_base"],
    )


@router.post("/config", response_model=SSOConfigResponse)
def save_sso_config(data: SSOConfigUpdate, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_admin)):
    # Enabling without a complete setup would 500 on every login attempt —
    # validate before persisting so the admin gets an actionable error.
    if data.enabled:
        missing = [label for label, value in (
            ("issuer", data.issuer), ("client_id", data.client_id)) if not value.strip()]
        if missing:
            raise HTTPException(
                422, f"Cannot enable SSO: missing {', '.join(missing)}")
        stored = oidc_service.get_config(db)
        if not (data.client_secret or "").strip() and not stored["client_secret"]:
            raise HTTPException(
                422, "Cannot enable SSO: client secret is not set")

    oidc_service.save_config(
        db,
        enabled=data.enabled,
        issuer=data.issuer,
        client_id=data.client_id,
        client_secret=(data.client_secret or "").strip() or None,
        default_role=data.default_role,
        redirect_base=data.redirect_base,
    )
    audit(db, action="sso.config_updated", request=request, actor=current_user,
          resource_type="settings", resource_id="oidc",
          detail={"enabled": data.enabled,
                  "default_role": data.default_role})
    return get_sso_config(db, current_user)
