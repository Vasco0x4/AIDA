"""
OIDC SSO (E2) — authorization-code flow with PKCE, enterprise-IdP style.

Flow: /auth/oidc/login → IdP authorize (state = HMAC-signed, PKCE S256)
      → IdP redirects to /auth/oidc/callback → code+state verified →
      token exchange → id_token verified against the IdP JWKS (issuer +
      audience + expiry) → JIT user provisioning → AIDA access token issued.

State carries its own HMAC (forgery-proof) and a 10-minute expiry, so the
callback needs no server-side session storage.
"""
from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional
from urllib.parse import urlencode, urlsplit

import httpx
from jose import jwk as jose_jwk
from jose import jwt as jose_jwt
from jose.exceptions import JOSEError
from sqlalchemy.orm import Session
from auth import SECRET_KEY, hash_password
from models.platform_settings import PlatformSettings
from models.user import User
from utils.crypto import decrypt_secret, encrypt_secret
from utils.logger import get_logger

logger = get_logger(__name__)

STATE_TTL = 600  # seconds
_DISCOVERY_TTL = 300
_discovery_cache: dict[str, tuple[float, dict]] = {}


class OIDCError(Exception):
    pass


# --- configuration -----------------------------------------------------------

def _setting(db: Session, key: str) -> Optional[str]:
    row = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
    return row.value if row else None


def get_config(db: Session) -> dict:
    secret = _setting(db, "oidc_client_secret")
    return {
        "enabled": (_setting(db, "oidc_enabled") or "").lower() == "true",
        "issuer": (_setting(db, "oidc_issuer_url") or "").strip().rstrip("/"),
        "client_id": _setting(db, "oidc_client_id") or "",
        "client_secret": decrypt_secret(secret) if secret else "",
        "default_role": _setting(db, "oidc_default_role") or "viewer",
        "redirect_base": (_setting(db, "oidc_redirect_base") or "").rstrip("/"),
        "scopes": "openid profile email",
    }


def save_config(db: Session, *, enabled: bool, issuer: str, client_id: str,
                client_secret: Optional[str], default_role: str, redirect_base: str) -> None:
    """Upsert the OIDC settings. Empty client_secret keeps the stored one
    (so the secret never has to round-trip through the UI)."""
    values = {
        "oidc_enabled": "true" if enabled else "false",
        "oidc_issuer_url": issuer.strip().rstrip("/"),
        "oidc_client_id": client_id.strip(),
        "oidc_default_role": default_role,
        "oidc_redirect_base": redirect_base.strip().rstrip("/"),
    }
    for key, value in values.items():
        row = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
        if row:
            row.value = value
        else:
            db.add(PlatformSettings(key=key, value=value,
                                    description=f"OIDC SSO ({key})"))
    if client_secret:  # only overwrite when a new secret is provided
        enc = encrypt_secret(client_secret.strip())
        row = db.query(PlatformSettings).filter(
            PlatformSettings.key == "oidc_client_secret").first()
        if row:
            row.value = enc
        else:
            db.add(PlatformSettings(key="oidc_client_secret", value=enc,
                                    description="OIDC SSO client secret (encrypted)"))
    db.commit()


def _require(cfg: dict) -> dict:
    if not (cfg["enabled"] and cfg["issuer"] and cfg["client_id"]):
        raise OIDCError("SSO is not configured")
    return cfg


# --- discovery / tokens --------------------------------------------------------

async def _discovery(issuer: str) -> dict:
    cached = _discovery_cache.get(issuer)
    if cached and time.monotonic() - cached[0] < _DISCOVERY_TTL:
        return cached[1]
    url = issuer + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(url)
    if resp.status_code != 200:
        raise OIDCError(f"Discovery failed ({resp.status_code}) for {url}")
    doc = resp.json()
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not doc.get(field):
            raise OIDCError(f"Discovery document missing {field}")
    _discovery_cache[issuer] = (time.monotonic(), doc)
    return doc


async def build_authorization_url(cfg: dict, redirect_uri: str) -> tuple[str, str, str]:
    """Returns (authorize_url, state, verifier)."""
    cfg = _require(cfg)
    doc = await _discovery(cfg["issuer"])
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = _sign_state({"v": verifier, "e": int(time.time()) + STATE_TTL})
    params = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "scope": cfg["scopes"],
        "state": state,
        "nonce": secrets.token_urlsafe(16),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return f"{doc['authorization_endpoint']}?{urlencode(params)}", state, verifier


async def exchange_code(cfg: dict, code: str, redirect_uri: str, verifier: str) -> dict:
    cfg = _require(cfg)
    doc = await _discovery(cfg["issuer"])
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            doc["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "code_verifier": verifier,
            },
            headers={"Accept": "application/json"},
        )
    if resp.status_code != 200:
        raise OIDCError(f"Token exchange failed: {resp.status_code} {resp.text[:200]}")
    return resp.json()


async def verify_id_token(cfg: dict, id_token: str, access_token: Optional[str] = None) -> dict:
    """Verify signature (JWKS), issuer, audience and expiry. Returns claims."""
    cfg = _require(cfg)
    doc = await _discovery(cfg["issuer"])
    header = jose_jwt.get_unverified_header(id_token)
    kid = header.get("kid")
    alg = header.get("alg", "RS256")
    if alg not in ("RS256", "RS384", "RS512", "ES256"):
        raise OIDCError(f"Unsupported id_token algorithm {alg}")
    async with httpx.AsyncClient(timeout=15) as client:
        jwks = (await client.get(doc["jwks_uri"])).json()
    key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
    if key_data is None:
        raise OIDCError("id_token signing key not found in JWKS")
    key = jose_jwk.construct(key_data, algorithm=alg)
    try:
        claims = jose_jwt.decode(
            id_token, key=key, algorithms=[alg],
            audience=cfg["client_id"], issuer=cfg["issuer"],
            access_token=access_token,
        )
    except JOSEError as e:
        raise OIDCError(f"id_token verification failed: {e}") from e
    return claims


# --- signed state ---------------------------------------------------------------

def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _sign_state(payload: dict) -> str:
    body = _b64u(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64u(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def load_state(state: str) -> Optional[dict]:
    try:
        body, sig = state.split(".", 1)
        expect = _b64u(hmac.new(SECRET_KEY.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        if int(payload.get("e", 0)) < time.time():
            return None
        return payload
    except Exception:
        return None


# --- provisioning ----------------------------------------------------------------

def provision_user(db: Session, claims: dict, default_role: str) -> User:
    """Find-or-create the local account for verified IdP claims.

    Existing accounts keep their local role (promotions happen explicitly in
    Users admin) — SSO can log in but never self-escalate."""
    username = (claims.get("preferred_username")
                or (claims.get("email") or "").split("@")[0]
                or "").strip()
    if not username or len(username) > 50:
        raise OIDCError("IdP claims carry no usable username")
    email = claims.get("email")

    user = db.query(User).filter(User.username == username).first()
    if user is None and email:
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            # link by email: keep the existing account
            pass
    if user is None:
        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),  # unusable pwd
            role=default_role if default_role in ("admin", "auditor", "viewer") else "viewer",
            is_active=True,
            must_change_password=False,
            auth_provider="oidc",
        )
        db.add(user)
    if not user.is_active:
        db.rollback()
        raise OIDCError("Account is disabled")
    if not user.otp_enabled:
        user.last_login_at = _dt.datetime.now(_dt.timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def frontend_redirect(cfg: dict, fallback_origin: str) -> str:
    """Where to send the browser after the callback (SPA token pickup)."""
    if cfg["redirect_base"]:
        return cfg["redirect_base"]
    return fallback_origin.rstrip("/")


def provider_label(issuer: str) -> str:
    try:
        return urlsplit(issuer).netloc or issuer
    except Exception:  # pragma: no cover
        return issuer
