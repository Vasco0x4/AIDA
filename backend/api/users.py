"""
User management API endpoints (admin only).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import (
    ROLE_PATTERN, UserCreate, UserResponse, hash_password, require_admin,
)
from database import get_db
from models.user import User
from services.audit_service import record as audit
from services import otp_service

router = APIRouter(prefix="/users", tags=["Users"])


class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = Field(None, pattern=ROLE_PATTERN)


class PasswordResetRequest(BaseModel):
    new_password: str = Field(..., min_length=7)


def _admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "admin", User.is_active == True).count()


@router.get("", response_model=List[UserResponse])
def list_users(db: Session = Depends(get_db)):
    return [UserResponse.model_validate(u) for u in db.query(User).order_by(User.id).all()]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreate, request: Request, current_user: User = Depends(require_admin),
                db: Session = Depends(get_db)):
    """Create a new user. The created account is forced to change its password
    on first login.
    """
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already exists")
    if data.email and db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
        is_active=True,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, action="user.created", request=request, actor=current_user,
          resource_type="user", resource_id=user.id, detail={"role": user.role})
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    # Block self-demotion / self-deactivation if it would leave zero admins.
    if user.id == current_user.id:
        if data.role is not None and data.role != "admin":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot demote yourself")
        if data.is_active is False:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot deactivate yourself")

    # Block demoting / deactivating the last active admin.
    if user.role == "admin" and user.is_active:
        will_lose_admin = (
            (data.role is not None and data.role != "admin")
            or (data.is_active is False)
        )
        if will_lose_admin and _admin_count(db) <= 1:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Cannot remove the last active admin",
            )

    if data.email is not None:
        # Reject an email already used by another user. Without this the DB
        # unique constraint would surface as an unhandled 500 (create_user
        # performs the same check).
        if data.email and db.query(User).filter(
            User.email == data.email, User.id != user_id
        ).first():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
        user.email = data.email
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.role is not None:
        user.role = data.role

    db.commit()
    db.refresh(user)
    audit(db, action="user.updated", request=request, actor=current_user,
          resource_type="user", resource_id=user.id,
          detail={"email": data.email, "is_active": data.is_active, "role": data.role})
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
def reset_password(
    user_id: int,
    data: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    user.hashed_password = hash_password(data.new_password)
    user.must_change_password = True
    # A password reset grants a local login path but deliberately preserves the
    # user's enrolled OTP. Lost authenticators use the separate reset-otp flow.
    user.auth_provider = "local"
    otp_service.invalidate_challenges(db, user.id)
    db.commit()
    db.refresh(user)
    audit(db, action="user.password_reset", request=request, actor=current_user,
          resource_type="user", resource_id=user.id)
    return UserResponse.model_validate(user)


@router.post("/{user_id}/reset-otp", response_model=UserResponse)
def reset_user_otp(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Account recovery for a lost authenticator; no OTP secret is disclosed."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    otp_service.reset_otp(db, user)
    db.refresh(user)
    audit(db, action="user.otp_reset", request=request, actor=current_user,
          resource_type="user", resource_id=user.id)
    return UserResponse.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if user.id == current_user.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete yourself")

    if user.role == "admin" and user.is_active and _admin_count(db) <= 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot delete the last active admin",
        )

    username_snapshot = user.username  # snapshot before delete detaches the row
    db.delete(user)
    db.commit()
    audit(db, action="user.deleted", request=request, actor=current_user,
          resource_type="user", resource_id=user_id, detail={"username": username_snapshot})
    return None
