"""
REST endpoints for managing MCP HTTP API keys.

Users manage their own keys. Admins can list / revoke any user's keys
via ``?owner_user_id=`` — enforced inline rather than via a separate
admin router so ownership logic stays co-located with the resource.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import generate_api_key, get_current_user
from database import get_db
from services.audit_service import record as audit
from models.api_key import ApiKey
from models.user import User

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeySummary(BaseModel):
    id: int
    name: str
    key_prefix: str
    owner_user_id: int
    scope: str
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]
    revoked_at: Optional[datetime]

    class Config:
        from_attributes = True


class ApiKeyCreateResponse(ApiKeySummary):
    full_key: str = Field(..., description="Shown once — store it securely")


def _to_summary(key: ApiKey) -> ApiKeySummary:
    return ApiKeySummary(
        id=key.id,
        name=key.name,
        key_prefix=key.key_prefix,
        owner_user_id=key.owner_user_id,
        scope=key.scope,
        created_at=key.created_at,
        last_used_at=key.last_used_at,
        revoked_at=key.revoked_at,
    )


@router.get("", response_model=List[ApiKeySummary])
def list_api_keys(
    owner_user_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List the current user's API keys. Admins may filter by owner."""
    query = db.query(ApiKey)
    if owner_user_id is not None:
        if current_user.role != "admin" and owner_user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can list other users' keys",
            )
        query = query.filter(ApiKey.owner_user_id == owner_user_id)
    else:
        query = query.filter(ApiKey.owner_user_id == current_user.id)

    rows = query.order_by(ApiKey.created_at.desc()).all()
    return [_to_summary(r) for r in rows]


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mint a new key owned by the current user. Returns the plaintext once."""
    full, prefix, hashed = generate_api_key()
    row = ApiKey(
        name=payload.name.strip(),
        key_prefix=prefix,
        key_hash=hashed,
        owner_user_id=current_user.id,
        scope="mcp",
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    audit(db, action="api_key.created", request=request, actor=current_user,
          resource_type="api_key", resource_id=row.id, detail={"name": row.name})
    return ApiKeyCreateResponse(
        **_to_summary(row).model_dump(),
        full_key=full,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Soft-revoke a key. Admins can revoke any user's key."""
    row = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    if current_user.role != "admin" and row.owner_user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot revoke a key you do not own",
        )
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
    audit(db, action="api_key.revoked", request=request, actor=current_user,
          resource_type="api_key", resource_id=key_id, detail={"name": row.name})
    return None
