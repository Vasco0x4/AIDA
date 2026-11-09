"""
Audit-trail API (admin only — enforced by RBAC middleware on /api/audit*).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from services.audit_service import query as audit_query

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntry(BaseModel):
    id: int
    created_at: str
    actor_id: Optional[int] = None
    actor_username: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    detail: dict = {}
    success: bool = True


class AuditListResponse(BaseModel):
    items: list[AuditEntry]
    total: int


@router.get("", response_model=AuditListResponse)
def list_audit(
    actor_id: Optional[int] = None,
    action: Optional[str] = Query(None, description="Action prefix, e.g. 'auth.'"),
    resource_type: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows, total = audit_query(
        db, actor_id=actor_id, action_prefix=action,
        resource_type=resource_type, success=success,
        limit=limit, offset=offset,
    )
    items = [
        AuditEntry(
            id=r.id,
            created_at=r.created_at.isoformat() if r.created_at else None,
            actor_id=r.actor_id, actor_username=r.actor_username,
            action=r.action, resource_type=r.resource_type, resource_id=r.resource_id,
            ip=r.ip, user_agent=r.user_agent,
            detail=(r.detail or {}), success=r.success,
        )
        for r in rows
    ]
    return AuditListResponse(items=items, total=total)
