"""
Authentication module - JWT tokens, password hashing, dependencies
"""
import os
import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from models.user import User
from models.api_key import ApiKey
from models.platform_settings import PlatformSettings

# Configuration. SECRET_KEY must be present at module-import time. If the
# environment doesn't carry it (e.g. when this module is imported from a
# `docker compose exec` ad-hoc shell), invoke the bootstrap which loads or
# generates a persistent key. The bootstrap is idempotent and safe to call
# from any context.
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    from bootstrap_secrets import ensure_secret_key
    ensure_secret_key()
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY could not be loaded or generated")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Bearer token scheme
security = HTTPBearer(auto_error=False)


# --- Pydantic Schemas ---

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=7)
    email: Optional[str] = None
    role: str = Field("user", pattern="^(admin|user)$")


class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=7)


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    role: str
    must_change_password: bool

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# --- Core Functions ---

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_api_token(user_id: int, username: str) -> str:
    """Issue a long-lived token (1 year) for CLI/MCP use.

    Same JWT format as access tokens so the existing get_current_user
    dependency validates it without any changes.
    """
    expire = datetime.now(timezone.utc) + timedelta(days=365)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "type": "api",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# --- FastAPI Dependencies ---

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Dependency: extract and validate JWT, return User object."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency: ensure the authenticated user has the admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


# --- API key helpers (for the HTTP MCP transport) ---

API_KEY_PREFIX_LEN = 12  # "aida_sk_" + first 4 chars of random portion


def generate_api_key() -> Tuple[str, str, str]:
    """Mint a fresh API key.

    Returns ``(full_key, prefix, hash)``. ``full_key`` is shown to the
    user exactly once — only the prefix and bcrypt hash are persisted.
    """
    raw = secrets.token_urlsafe(32)
    full = f"aida_sk_{raw}"
    prefix = full[:API_KEY_PREFIX_LEN]
    hashed = pwd_context.hash(full)
    return full, prefix, hashed


def _get_platform_setting(db: Session, key: str, default: str) -> str:
    row = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
    return row.value if row else default


def _ip_matches_policy(client_host: Optional[str], policy: str) -> bool:
    """Return True if ``client_host`` is allowed under ``policy``."""
    if policy == "any":
        return True
    if not client_host:
        return False
    try:
        addr = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    if policy == "localhost":
        return addr.is_loopback
    if policy == "lan":
        # Loopback + RFC1918 + link-local.
        return addr.is_loopback or addr.is_private or addr.is_link_local
    return False


def _match_api_key(db: Session, token: str) -> Optional[ApiKey]:
    """Return the non-revoked key whose hash matches ``token``, if any."""
    if len(token) < API_KEY_PREFIX_LEN or not token.startswith("aida_sk_"):
        return None
    candidates = (
        db.query(ApiKey)
        .filter(ApiKey.key_prefix == token[:API_KEY_PREFIX_LEN], ApiKey.revoked_at.is_(None))
        .all()
    )
    for candidate in candidates:
        if pwd_context.verify(token, candidate.key_hash):
            return candidate
    return None


async def verify_mcp_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    api_key: Optional[str] = Query(None, alias="api_key"),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Dependency: validate a Bearer API key for ``/mcp``.

    Accepts the key as an ``Authorization: Bearer`` header or as an
    ``?api_key=`` query parameter (used by clients that cannot set headers,
    e.g. claude.ai remote connectors).

    - 503 if HTTP MCP is disabled in platform settings.
    - 403 if the client IP is not allowed under the configured network policy.
    - 401 on any other auth failure.

    Keys with scope "agent" (minted by `aida run` for per-assessment agent
    containers) bypass the feature flag and are always accepted from private
    addresses: the agent reaches the backend over a dedicated Docker bridge,
    so it never comes from loopback. The toggle and policy keep governing
    external MCP clients.
    """
    token = (credentials.credentials if credentials and credentials.credentials else None) or api_key
    key = _match_api_key(db, token) if token else None
    agent_key = key is not None and key.scope == "agent"

    if not agent_key and _get_platform_setting(db, "mcp_http_enabled", "false").lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HTTP MCP transport is disabled",
        )

    policy = _get_platform_setting(db, "mcp_http_network_policy", "localhost")
    if agent_key and policy == "localhost":
        policy = "lan"
    client_host = request.client.host if request.client else None
    if not _ip_matches_policy(client_host, policy):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Client {client_host} not permitted by network policy '{policy}'",
        )

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if len(token) < API_KEY_PREFIX_LEN or not token.startswith("aida_sk_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    key.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return key
