"""
Coarse-grained RBAC enforced for EVERY /api route in one place (E2).

Role hierarchy: admin ⊃ auditor ⊃ viewer
  - viewer : read-only (GET/HEAD/OPTIONS anywhere)
  - auditor: everything operational (create tasks, run scans, record findings…)
  - admin  : + user management, AI-model credentials, API keys, platform
             settings, runner control, bulk knowledge ingestion

The JWT is decoded and the user re-loaded from the DB on every request (so a
demotion takes effect immediately, not at token expiry); the resolved user is
stashed on ``request.state`` and reused by ``auth.get_current_user`` to avoid
a second DB hit. Fine-grained per-object rules are NOT this middleware's job.

Write-admin exceptions live in ``_WRITE_ADMIN`` so they're auditable in one
glance. Every denial is written to the audit trail.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN

from auth import decode_token
from database import SessionLocal
from models.user import User
from utils.logger import get_logger

logger = get_logger(__name__)

ROLE_RANK = {"viewer": 0, "auditor": 1, "admin": 2}

# Path prefixes (no trailing slash) where EVERY method requires admin.
_ADMIN_PREFIXES = (
    "/api/users",
    "/api/ai-models",
    "/api/api-keys",
    "/api/audit",
    "/api/sso",
)

# Method+prefix rules requiring admin only for writes (auditors can read).
_WRITE_ADMIN = (
    ("PUT", "/api/tasks/runner"),
    ("POST", "/api/tasks/runner/"),
    ("POST", "/api/knowledge/ingest/"),
    ("POST", "/api/knowledge/import"),
    ("POST", "/api/knowledge/seed-playbooks"),
    ("PUT", "/api/system/settings/"),
    ("DELETE", "/api/system/settings/"),
    ("POST", "/api/command-settings/"),
    # NOTE: no trailing slash — the main settings route is PUT /api/command-settings
    # (a slashed prefix would NOT match it; sub-routes still match via startswith).
    ("PUT", "/api/command-settings"),
    ("DELETE", "/api/command-settings/"),
    # E4: report branding defines the org's client-facing identity
    ("PUT", "/api/branding"),
    ("POST", "/api/branding/"),
    ("DELETE", "/api/branding/"),
    ("DELETE", "/api/knowledge/"),
)

# Paths that skip RBAC entirely (they are public or auth themselves.
# NOTE: matched by prefix, keep them as tight as the router structure allows).
_PUBLIC_PREFIXES = (
    "/health",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/",
    "/api/ws",
    "/mcp",
)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _required_role(method: str, path: str) -> str:
    if any(path == p or path.startswith(p + "/") for p in _ADMIN_PREFIXES):
        return "admin"
    for m, prefix in _WRITE_ADMIN:
        if method == m and (path == prefix or path.startswith(prefix)):
            return "admin"
    return "viewer" if method in _SAFE_METHODS else "auditor"


class RBACMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = urlsplit(request.url.path).path
        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        authz = request.headers.get("authorization", "")
        token = authz[7:] if authz.lower().startswith("bearer ") else None
        payload = decode_token(token) if token else None
        if payload is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=HTTP_401_UNAUTHORIZED)

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == int(payload["sub"])).first()
        except (KeyError, ValueError):
            user = None
        finally:
            db.close()

        if user is None or not user.is_active:
            return JSONResponse({"detail": "User not found or inactive"}, status_code=HTTP_401_UNAUTHORIZED)

        # Hand the resolved user to the auth dependency (avoids a second load).
        request.state.user = user

        needed = _required_role(request.method, path)
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[needed]:
            db = SessionLocal()
            try:
                from services.audit_service import record
                record(db, action="rbac.denied", request=request, actor=user,
                       resource_type="path", resource_id=path,
                       detail={"method": request.method, "required_role": needed},
                       success=False)
            finally:
                db.close()
            return JSONResponse(
                {"detail": f"Requires {needed} role (you are {user.role})"},
                status_code=HTTP_403_FORBIDDEN,
            )

        return await call_next(request)
