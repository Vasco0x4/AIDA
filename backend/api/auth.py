"""
Authentication API endpoints
"""
import hmac
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import (
    PasswordChangeRequest, TokenResponse, UserLogin, UserResponse,
    create_access_token, create_api_token, get_current_user, hash_password, verify_password,
)
from database import get_db
from middleware.rate_limit import limiter
from models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


# --- First-admin setup code ------------------------------------------------
# The web UI is reachable from the LAN, so whoever loads it first could claim
# the admin account. Creating it therefore needs a one-time code that only
# the person who started AIDA has: start.sh generates it, passes it in
# AIDA_SETUP_CODE and prints it. When the backend is started some other way,
# it makes one up and prints it in its own logs.
_SETUP_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
_generated_setup_code: Optional[str] = None


def get_setup_code() -> str:
    global _generated_setup_code
    configured = os.getenv("AIDA_SETUP_CODE", "").strip()
    if configured:
        return configured
    if _generated_setup_code is None:
        raw = "".join(secrets.choice(_SETUP_CODE_ALPHABET) for _ in range(8))
        _generated_setup_code = f"{raw[:4]}-{raw[4:]}"
    return _generated_setup_code


def announce_setup_code(db: Session) -> None:
    """Print the setup code at startup while no account exists yet."""
    if db.query(User).count() == 0:
        print(f"[setup] No admin account yet. Setup code: {get_setup_code()}", flush=True)


def _normalize_setup_code(code: str) -> bytes:
    # Accept "abcd efgh", "ABCD-EFGH", ... — only letters and digits count.
    return "".join(ch for ch in code.upper() if ch.isalnum()).encode()


def _setup_code_matches(candidate: Optional[str]) -> bool:
    if not candidate:
        return False
    return hmac.compare_digest(
        _normalize_setup_code(candidate), _normalize_setup_code(get_setup_code())
    )


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=7)
    email: Optional[str] = None
    setup_code: Optional[str] = Field(None, max_length=64)


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """Public endpoint: returns whether the platform still needs initial setup.

    Used by the frontend on first paint to decide between the setup wizard
    and the regular login screen.
    """
    return {
        "setup_required": db.query(User).count() == 0,
        # Lets the wizard show the code field (older backends didn't need one).
        "setup_code_required": True,
    }


@router.post("/setup", response_model=TokenResponse)
@limiter.limit("3/minute")
def setup(request: Request, data: SetupRequest, db: Session = Depends(get_db)):
    """Create the initial admin account.

    Only callable while the database has zero users — once the first admin
    exists, this endpoint refuses every subsequent call. The created admin
    is fully ready (no forced password change, since the user just chose it).
    """
    if db.query(User).count() > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup already completed",
        )
    if not _setup_code_matches(data.setup_code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Wrong setup code. It was printed when AIDA started — run `aida status` to see it again.",
        )

    admin = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
        role="admin",
        is_active=True,
        must_change_password=False,
        last_login_at=datetime.now(timezone.utc),
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    token = create_access_token(admin.id, admin.username)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(admin),
    )


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

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.username)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse.model_validate(current_user)


@router.post("/api-token")
@limiter.limit("10/minute")
def issue_api_token(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Issue a long-lived API token (1 year) for CLI/MCP use.

    Requires an existing valid session. The returned token uses the same
    JWT format as access tokens and is validated by the standard auth
    dependency — no extra infrastructure needed.
    """
    token = create_api_token(current_user.id, current_user.username)
    return {"api_token": token}


@router.post("/change-password", response_model=UserResponse)
@limiter.limit("5/minute")
def change_password(
    request: Request,
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password.

    Required after login when `must_change_password` is true. The new password
    must differ from the current one.
    """
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    if data.current_password == data.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from the current one",
        )

    current_user.hashed_password = hash_password(data.new_password)
    current_user.must_change_password = False
    db.commit()
    db.refresh(current_user)

    return UserResponse.model_validate(current_user)
