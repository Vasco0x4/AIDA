"""
Authentication API endpoints
"""
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
from models.otp import RecoveryCode
from models.user import User
from services.audit_service import record as audit
from services import otp_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=7)
    email: Optional[str] = None


class OTPSetupRequest(BaseModel):
    password: Optional[str] = Field(None, max_length=256)


class OTPConfirmRequest(BaseModel):
    password: Optional[str] = Field(None, max_length=256)
    code: str = Field(..., min_length=6, max_length=64)


class OTPVerifyRequest(BaseModel):
    challenge_id: str = Field(..., min_length=36, max_length=36)
    code: str = Field(..., min_length=6, max_length=64)


def _require_reauthentication(user: User, password: Optional[str]) -> None:
    """Require a local password, or a verified SSO session for OIDC-only users."""
    if user.auth_provider == "oidc":
        return
    if not password or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Current password is incorrect")


def _otp_error(error: otp_service.OTPError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("/setup-status")
def setup_status(db: Session = Depends(get_db)):
    """Public endpoint: returns whether the platform still needs initial setup.

    Used by the frontend on first paint to decide between the setup wizard
    and the regular login screen.
    """
    return {"setup_required": db.query(User).count() == 0}


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
    audit(db, action="platform.setup", request=request, actor=admin,
          resource_type="user", resource_id=admin.id)
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(admin),
    )


@router.post("/login", response_model=TokenResponse, response_model_exclude_none=True)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Authenticate a password, then require OTP separately when enrolled."""
    user = db.query(User).filter(User.username == data.username).first()

    if not user or not verify_password(data.password, user.hashed_password):
        audit(db, action="auth.login.failed", request=request,
              actor_id=user.id if user else None,
              actor_username=data.username, success=False,
              detail={"reason": "invalid credentials"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        audit(db, action="auth.login.failed", request=request, actor=user,
              success=False, detail={"reason": "account disabled"})
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    if user.otp_enabled:
        challenge = otp_service.create_challenge(db, user)
        audit(db, action="auth.login.otp_challenge", request=request, actor=user)
        return TokenResponse(
            user=UserResponse.model_validate(user),
            otp_required=True,
            otp_enabled=True,
            challenge_id=challenge.id,
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.username)
    audit(db, action="auth.login.success", request=request, actor=user)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserResponse.model_validate(current_user)


@router.post("/otp/verify", response_model=TokenResponse, response_model_exclude_none=True)
@limiter.limit("10/minute")
def verify_otp_login(request: Request, data: OTPVerifyRequest, db: Session = Depends(get_db)):
    """Exchange a bounded password-login challenge for a full session token."""
    try:
        user = otp_service.verify_challenge(db, data.challenge_id, data.code)
    except otp_service.OTPError as error:
        audit(db, action="auth.otp.failed", request=request, success=False,
              detail={"reason": error.detail})
        raise _otp_error(error) from error
    token = create_access_token(user.id, user.username)
    audit(db, action="auth.login.success", request=request, actor=user,
          detail={"second_factor": "otp"})
    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
        otp_enabled=True,
    )


@router.get("/otp/status")
def otp_status(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    remaining = db.query(RecoveryCode).filter(
        RecoveryCode.user_id == current_user.id, RecoveryCode.used_at.is_(None)
    ).count()
    return {"enabled": current_user.otp_enabled, "recovery_codes_remaining": remaining}


@router.post("/otp/setup")
@limiter.limit("5/minute")
def setup_otp(
    request: Request,
    data: OTPSetupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a pending secret; OTP remains disabled until code confirmation."""
    _require_reauthentication(current_user, data.password)
    try:
        secret, uri, qr_svg = otp_service.begin_enrollment(db, current_user)
    except otp_service.OTPError as error:
        raise _otp_error(error) from error
    audit(db, action="auth.otp.setup", request=request, actor=current_user)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": qr_svg, "enabled": False}


@router.post("/otp/enable")
@limiter.limit("10/minute")
def enable_otp(
    request: Request,
    data: OTPConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_reauthentication(current_user, data.password)
    try:
        codes = otp_service.confirm_enrollment(db, current_user, data.code)
    except otp_service.OTPError as error:
        raise _otp_error(error) from error
    audit(db, action="auth.otp.enabled", request=request, actor=current_user)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/otp/recovery-codes")
@limiter.limit("5/minute")
def regenerate_recovery_codes(
    request: Request,
    data: OTPConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_reauthentication(current_user, data.password)
    if not current_user.otp_enabled:
        raise HTTPException(status_code=409, detail="OTP is not enabled")
    try:
        if otp_service.verify_second_factor(db, current_user, data.code) is None:
            db.rollback()
            raise otp_service.OTPError("Invalid authenticator or recovery code")
        codes = otp_service.replace_recovery_codes(db, current_user)
        db.commit()
    except otp_service.OTPError as error:
        raise _otp_error(error) from error
    audit(db, action="auth.otp.recovery_regenerated", request=request, actor=current_user)
    return {"recovery_codes": codes}


@router.post("/otp/disable")
@limiter.limit("5/minute")
def disable_otp(
    request: Request,
    data: OTPConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_reauthentication(current_user, data.password)
    if not current_user.otp_enabled:
        return {"enabled": False}
    try:
        if otp_service.verify_second_factor(db, current_user, data.code) is None:
            db.rollback()
            raise otp_service.OTPError("Invalid authenticator or recovery code")
        otp_service.reset_otp(db, current_user)
    except otp_service.OTPError as error:
        raise _otp_error(error) from error
    audit(db, action="auth.otp.disabled", request=request, actor=current_user)
    return {"enabled": False}


@router.post("/api-token")
@limiter.limit("10/minute")
def issue_api_token(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Issue a long-lived API token (1 year) for CLI/MCP use.

    Requires an existing valid session. The returned token uses the same
    JWT format as access tokens and is validated by the standard auth
    dependency — no extra infrastructure needed.
    """
    token = create_api_token(current_user.id, current_user.username)
    audit(db, action="auth.api_token.issued", request=request, actor=current_user)
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
    otp_service.invalidate_challenges(db, current_user.id)
    db.commit()
    db.refresh(current_user)
    audit(db, action="auth.password_changed", request=request, actor=current_user)

    return UserResponse.model_validate(current_user)


# --- OIDC SSO (E2) --------------------------------------------------------------

from fastapi.responses import RedirectResponse  # noqa: E402

import services.oidc_service as oidc  # noqa: E402


def _base_url(request: Request) -> str:
    return f"{request.base_url.scheme}://{request.base_url.netloc}"


def _sso_error(cfg: dict, request: Request, message: str) -> RedirectResponse:
    from urllib.parse import quote
    target = f"{oidc.frontend_redirect(cfg, _base_url(request))}/sso#error={quote(message)}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/oidc/status")
def oidc_status(db: Session = Depends(get_db)):
    """Public: is SSO configured? (the login screen shows the button only then)"""
    cfg = oidc.get_config(db)
    return {
        "enabled": cfg["enabled"] and bool(cfg["issuer"]) and bool(cfg["client_id"]),
        "provider": oidc.provider_label(cfg["issuer"]) if cfg["issuer"] else None,
    }


@router.get("/oidc/login")
async def oidc_login(request: Request, db: Session = Depends(get_db)):
    cfg = oidc.get_config(db)
    redirect_uri = f"{_base_url(request)}/api/auth/oidc/callback"
    try:
        url, _state, _verifier = await oidc.build_authorization_url(cfg, redirect_uri)
    except oidc.OIDCError as e:
        return _sso_error(cfg, request, str(e))
    return RedirectResponse(url=url, status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    cfg = oidc.get_config(db)
    params = request.query_params
    if params.get("error"):
        return _sso_error(cfg, request, params.get("error_description") or params.get("error"))
    code = params.get("code")
    state = params.get("state")
    if not code or not state:
        return _sso_error(cfg, request, "Missing code/state in callback")

    payload = oidc.load_state(state)
    if payload is None:
        return _sso_error(cfg, request, "Invalid or expired SSO state")
    verifier = payload.get("v", "")

    try:
        redirect_uri = f"{_base_url(request)}/api/auth/oidc/callback"
        tokens = await oidc.exchange_code(cfg, code, redirect_uri, verifier)
        claims = await oidc.verify_id_token(cfg, tokens["id_token"], tokens.get("access_token"))
        user = oidc.provision_user(db, claims, cfg["default_role"])
    except oidc.OIDCError as e:
        audit(db, action="auth.sso.failed", request=request,
              success=False, detail={"error": str(e)})
        return _sso_error(cfg, request, str(e))

    if user.otp_enabled:
        challenge = otp_service.create_challenge(db, user)
        audit(db, action="auth.sso.otp_challenge", request=request, actor=user,
              detail={"provider": oidc.provider_label(cfg["issuer"])})
        target = f"{oidc.frontend_redirect(cfg, _base_url(request))}/sso#challenge={challenge.id}"
        return RedirectResponse(url=target, status_code=302)

    token = create_access_token(user.id, user.username)
    audit(db, action="auth.sso.login", request=request, actor=user,
          detail={"provider": oidc.provider_label(cfg["issuer"])})
    target = f"{oidc.frontend_redirect(cfg, _base_url(request))}/sso#token={token}"
    return RedirectResponse(url=target, status_code=302)
