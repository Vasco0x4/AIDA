"""
REST endpoints for managing MCP HTTP API keys.

Users manage their own keys. Admins can list / revoke any user's keys
via ``?owner_user_id=`` — enforced inline rather than via a separate
admin router so ownership logic stays co-located with the resource.
"""
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from auth import generate_api_key, get_current_user
from database import get_db
from models.api_key import ApiKey
from models.assessment import Assessment
from models.user import User

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    # "agent" keys are minted by `aida run` for per-assessment agent
    # containers; see verify_mcp_api_key for how they're gated.
    scope: Literal["mcp", "agent"] = "mcp"
    # Binds the key to one assessment: its MCP client can't load, list or
    # touch any other. Required for agent keys.
    assessment_id: Optional[int] = None

    @model_validator(mode="after")
    def _agent_keys_are_bound(self):
        if self.scope == "agent" and self.assessment_id is None:
            raise ValueError("agent keys need an assessment_id")
        return self


class ApiKeySummary(BaseModel):
    id: int
    name: str
    key_prefix: str
    owner_user_id: int
    scope: str
    assessment_id: Optional[int] = None
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
        assessment_id=key.assessment_id,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mint a new key owned by the current user. Returns the plaintext once."""
    if payload.assessment_id is not None and (
        db.query(Assessment.id).filter(Assessment.id == payload.assessment_id).first() is None
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assessment not found",
        )
    full, prefix, hashed = generate_api_key()
    row = ApiKey(
        name=payload.name.strip(),
        key_prefix=prefix,
        key_hash=hashed,
        owner_user_id=current_user.id,
        scope=payload.scope,
        assessment_id=payload.assessment_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return ApiKeyCreateResponse(
        **_to_summary(row).model_dump(),
        full_key=full,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: int,
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
    return None
