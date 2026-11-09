"""
Audit-trail service: one helper everything else calls.

`record()` is BEST-EFFORT by design — an audit write must never break the
request it is auditing (it logs a warning and moves on). Details are
PII/secret-redacted before storage (utils/redact).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from models.audit_log import AuditLog
from models.user import User
from utils.logger import get_logger
from utils.redact import redact_obj

logger = get_logger(__name__)

MAX_DETAIL = 4000  # chars of JSON — keep rows lean


def _client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def record(
    db: Session,
    *,
    action: str,
    request: Optional[Request] = None,
    actor: Optional[User] = None,
    actor_id: Optional[int] = None,
    actor_username: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
    detail: Optional[dict] = None,
    success: bool = True,
) -> None:
    """Append an audit entry. Never raises."""
    # The RBAC middleware stashes the resolved user on request.state — reuse
    # it when the caller didn't pass an explicit actor.
    if actor is None and request is not None:
        actor = getattr(request.state, "user", None)
    try:
        safe_detail = redact_obj(detail or {})
        row = AuditLog(
            actor_id=(actor.id if actor else actor_id),
            actor_username=(actor.username if actor else actor_username),
            action=action[:100],
            resource_type=resource_type,
            resource_id=str(resource_id)[:64] if resource_id is not None else None,
            ip=_client_ip(request),
            user_agent=(request.headers.get("user-agent", "")[:255] if request else None),
            detail=safe_detail,
            success=success,
        )
        db.add(row)
        db.commit()
    except Exception as e:  # pragma: no cover — safety net
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning("audit record failed", action=action, error=str(e))


def query(
    db: Session,
    *,
    actor_id: Optional[int] = None,
    action_prefix: Optional[str] = None,
    resource_type: Optional[str] = None,
    success: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Filtered, newest-first audit query + total count."""
    q = db.query(AuditLog)
    if actor_id is not None:
        q = q.filter(AuditLog.actor_id == actor_id)
    if action_prefix:
        q = q.filter(AuditLog.action.like(f"{action_prefix}%"))
    if resource_type:
        q = q.filter(AuditLog.resource_type == resource_type)
    if success is not None:
        q = q.filter(AuditLog.success == success)
    total = q.count()
    rows = q.order_by(AuditLog.id.desc()).offset(offset).limit(min(limit, 500)).all()
    return rows, total
