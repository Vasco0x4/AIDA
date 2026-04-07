"""
Authentication API endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from database import get_db
from models.user import User
from auth import (
    UserCreate, UserLogin, UserResponse, TokenResponse,
    ChangePasswordRequest, AdminUserCreate, AdminUserUpdate,
    hash_password, verify_password, create_access_token,
    get_current_user, require_admin,
)
from middleware.rate_limit import limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


    # Public registration removed — admin creates accounts via POST /auth/users


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate and receive JWT token."""
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    token = create_access_token(user.id, user.username)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    if current_user is None:
        return UserResponse(id=0, username="admin", email=None, is_active=True)
    return UserResponse.model_validate(current_user)


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    """Check if authentication is required (any users exist)."""
    user_count = db.query(User).count()
    return {
        "auth_required": user_count > 0,
        "user_count": user_count,
    }


# --- Password Management ---

@router.put("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change own password."""
    if current_user is None:
        raise HTTPException(status_code=400, detail="No users exist yet")

    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


# --- Admin: User Management ---

@router.get("/users", response_model=List[UserResponse])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all users (admin only)."""
    return db.query(User).order_by(User.id).all()


@router.post("/users", response_model=UserResponse)
def create_user(
    data: AdminUserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user (admin only)."""
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username already exists")

    if data.email and db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: AdminUserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update user role or active status (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent admin from demoting themselves
    if admin and user.id == admin.id and data.role and data.role != "admin":
        raise HTTPException(status_code=400, detail="Cannot demote yourself")

    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        # Prevent admin from deactivating themselves
        if admin and user.id == admin.id and not data.is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        user.is_active = data.is_active

    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Delete a user (admin only). Cannot delete yourself."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if admin and user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    db.delete(user)
    db.commit()
    return {"message": f"User '{user.username}' deleted"}


@router.put("/users/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Reset a user's password to their username (admin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(user.username)
    db.commit()
    return {"message": f"Password for '{user.username}' reset to username"}
