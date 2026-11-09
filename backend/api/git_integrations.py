"""Administrator-managed Git connections. No credentials in responses or audits."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session
from auth import require_admin
from database import get_db
from models.git_connection import GitConnection, GitRepository
from models.appsec import AppSecProject, AppSecScan
from services.git_provider import GitProvider, GitError, origin_url, seal
from services.audit_service import record as audit


class SafeValidationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe(request):
            try:
                return await handler(request)
            except RequestValidationError:
                # FastAPI's default errors may echo input, including an invalid token.
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": "Check the connection fields and repository ID. Tokens must be strings; provider must be github or gitlab."
                    },
                )
            except GitError as exc:
                return JSONResponse(status_code=422, content={"detail": str(exc)})

        return safe


router = APIRouter(
    prefix="/appsec/integrations",
    tags=["Git integrations"],
    dependencies=[Depends(require_admin)],
    route_class=SafeValidationRoute,
)


class ConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: str = Field(pattern="^(github|gitlab)$")
    origin: str = Field(max_length=255)
    token: SecretStr
    allow_private_network: bool = False


class Rotate(BaseModel):
    token: SecretStr


class Grant(BaseModel):
    allowed: bool


def connection(db, ident, enabled=True, lock=False):
    query = db.query(GitConnection).filter_by(id=ident)
    if lock:
        query = query.with_for_update().populate_existing()
    row = query.first()
    if not row:
        raise HTTPException(404, "Git connection not found")
    if enabled and not row.enabled:
        raise HTTPException(409, "Connection is disconnected. Replace its token to reconnect.")
    return row


def public(row):
    return {
        key: getattr(row, key)
        for key in ("id", "name", "provider", "origin", "allow_private_network", "enabled", "account", "checked_at")
    }


def cancel_projects(db, ids):
    if ids:
        db.query(AppSecScan).filter(
            AppSecScan.project_id.in_(ids),
            AppSecScan.source == "repository",
            AppSecScan.status.in_(["queued", "running"]),
        ).update(
            {
                "status": "cancelled",
                "archive": None,
                "completed_at": datetime.utcnow(),
                "error": "Repository permission or Git connection was revoked.",
            },
            synchronize_session=False,
        )


@router.get("")
def connections(db: Session = Depends(get_db)):
    return [public(row) for row in db.query(GitConnection).order_by(GitConnection.id.desc()).all()]


@router.post("", status_code=201)
def create(body: ConnectionCreate, request: Request, db: Session = Depends(get_db)):
    if not body.name.strip():
        raise HTTPException(422, "Connection name is required")
    encrypted = seal(body.token.get_secret_value())
    row = GitConnection(
        name=body.name.strip(),
        provider=body.provider,
        origin=origin_url(body.origin),
        token_encrypted=encrypted,
        allow_private_network=body.allow_private_network,
        enabled=True,
    )
    row.account = GitProvider(row).check()
    row.checked_at = datetime.utcnow()
    db.execute(text("SELECT pg_advisory_xact_lock(41494443)"))
    if db.query(GitConnection).count() >= 50:
        raise HTTPException(409, "Connection limit reached (50)")
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, action="appsec.git.connected", request=request, resource_type="git_connection", resource_id=row.id)
    return public(row)


@router.post("/{ident}/check")
def check(ident: int, request: Request, db: Session = Depends(get_db)):
    row = connection(db, ident)
    account = GitProvider(row).check()
    row = connection(db, ident, lock=True)
    row.account = account
    row.checked_at = datetime.utcnow()
    db.commit()
    audit(db, action="appsec.git.checked", request=request, resource_type="git_connection", resource_id=ident)
    return public(row)


@router.put("/{ident}/token")
def rotate(ident: int, body: Rotate, request: Request, db: Session = Depends(get_db)):
    row = connection(db, ident, enabled=False, lock=True)
    encrypted = seal(body.token.get_secret_value())
    candidate = GitConnection(
        provider=row.provider,
        origin=row.origin,
        token_encrypted=encrypted,
        allow_private_network=row.allow_private_network,
    )
    account = GitProvider(candidate).check()
    row.token_encrypted = encrypted
    row.enabled = True
    row.account = account
    row.checked_at = datetime.utcnow()
    db.commit()
    audit(db, action="appsec.git.token_replaced", request=request, resource_type="git_connection", resource_id=ident)
    return public(row)


@router.delete("/{ident}")
def disconnect(ident: int, request: Request, db: Session = Depends(get_db)):
    row = connection(db, ident, enabled=False, lock=True)
    grants = db.query(GitRepository).filter_by(connection_id=ident).all()
    cancel_projects(db, [g.project_id for g in grants])
    for grant in grants:
        grant.allowed = False
    row.token_encrypted = ""
    row.enabled = False
    db.commit()
    audit(db, action="appsec.git.disconnected", request=request, resource_type="git_connection", resource_id=ident)
    return public(row)


@router.get("/{ident}/repositories")
def repositories(ident: int, page: int = Query(1, ge=1, le=1000), db: Session = Depends(get_db)):
    row = connection(db, ident)
    items = GitProvider(row).repositories(page)
    grants = {g.provider_id: g for g in db.query(GitRepository).filter_by(connection_id=ident)}
    for item in items:
        grant = grants.get(item["provider_id"])
        item.update(allowed=bool(grant and grant.allowed), project_id=grant.project_id if grant else None)
    return {"items": items, "page": page, "has_more": len(items) == 50}


@router.get("/{ident}/grants")
def grants(ident: int, db: Session = Depends(get_db)):
    connection(db, ident, enabled=False)
    return [
        {k: getattr(g, k) for k in ("provider_id", "path", "default_branch", "allowed", "project_id")}
        for g in db.query(GitRepository).filter_by(connection_id=ident).order_by(GitRepository.path)
    ]


@router.put("/{ident}/repositories/{provider_id}")
def grant_repository(ident: int, provider_id: str, body: Grant, request: Request, db: Session = Depends(get_db)):
    row = connection(db, ident, enabled=body.allowed, lock=True)
    # Metadata is always fetched from the provider by immutable ID, never accepted from the browser.
    metadata = GitProvider(row).repo(provider_id) if body.allowed else None
    grant = db.query(GitRepository).filter_by(connection_id=ident, provider_id=provider_id).first()
    if body.allowed and not grant:
        db.execute(text("SELECT pg_advisory_xact_lock(41494442)"))
        if db.query(AppSecProject).count() >= 200:
            raise HTTPException(409, "Project limit reached (200)")
        suffix = f" [Git {ident}:{provider_id}]"
        project = AppSecProject(
            name=metadata["path"][: 120 - len(suffix)] + suffix, repository_url=row.origin + "/" + metadata["path"]
        )
        db.add(project)
        db.flush()
        grant = GitRepository(
            connection_id=ident,
            provider_id=provider_id,
            project_id=project.id,
            **{k: metadata[k] for k in ("path", "default_branch")},
        )
        db.add(grant)
    if not grant:
        raise HTTPException(404, "Repository grant not found")
    grant.allowed = body.allowed
    if metadata:
        grant.path = metadata["path"]
        grant.default_branch = metadata["default_branch"]
        db.get(AppSecProject, grant.project_id).repository_url = row.origin + "/" + grant.path
    else:
        cancel_projects(db, [grant.project_id])
    db.commit()
    audit(
        db,
        action="appsec.git.repository_allowed" if body.allowed else "appsec.git.repository_revoked",
        request=request,
        resource_type="git_repository",
        resource_id=grant.id,
    )
    return {k: getattr(grant, k) for k in ("provider_id", "path", "default_branch", "allowed", "project_id")}
