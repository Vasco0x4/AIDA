"""Authenticated source review API. Mutations require auditor; AI opt-in requires admin."""

import hashlib
import html
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, text
from sqlalchemy.orm import Session
from database import get_db
from models.appsec import AppSecProject, AppSecScan, AppSecFinding
from models.ai_model_config import AIModelConfig
from models.git_connection import GitConnection, GitRepository
from services.git_access import binding
from services.git_provider import GitError
from services.appsec_source import repository, read_source, MAX_ARCHIVE, SourceError
from services.audit_service import record as audit

router = APIRouter(prefix="/appsec", tags=["Application Security"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository_url: str = Field("", max_length=500)

    @field_validator("name")
    @classmethod
    def name_valid(cls, value):
        if not value.strip():
            raise ValueError("Project name is required")
        return value.strip()

    @field_validator("repository_url")
    @classmethod
    def repo_valid(cls, value):
        return repository(value)[0]


class ScanCreate(BaseModel):
    ref: str = Field("main", min_length=1, max_length=160, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./-]*$")
    model_config_id: int | None = None
    allow_source_to_model: bool = False


class Triage(BaseModel):
    status: str = Field(pattern="^(open|confirmed|false_positive|accepted_risk)$")


def get_or_404(db, cls, ident):
    row = db.get(cls, ident)
    if not row:
        raise HTTPException(404, "AppSec resource not found")
    return row


def project_json(row):
    return {key: getattr(row, key) for key in ("id", "name", "repository_url", "created_at")}


def scan_json(row, details=False):
    result = {
        key: getattr(row, key)
        for key in (
            "id",
            "project_id",
            "status",
            "source",
            "requested_ref",
            "commit_sha",
            "archive_sha256",
            "summary",
            "error",
            "created_at",
            "completed_at",
            "ai_requested",
        )
    }
    if not details:
        result["summary"] = {
            k: v for k, v in (row.summary or {}).items() if k in {"findings", "new_findings", "text_files"}
        }
    return result


def finding_json(row):
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "scan_id",
            "fingerprint",
            "rule_id",
            "category",
            "severity",
            "confidence",
            "path",
            "line",
            "title",
            "description",
            "recommendation",
            "status",
            "task_id",
        )
    }


@router.get("/projects")
def projects(db: Session = Depends(get_db)):
    rows = []
    grants = {g.project_id: g for g in db.query(GitRepository)}
    connections = {c.id: c for c in db.query(GitConnection)}
    for p in db.query(AppSecProject).order_by(AppSecProject.id.desc()).limit(200):
        item = project_json(p)
        g = grants.get(p.id)
        if g:
            c = connections.get(g.connection_id)
            item.update(
                git_connection_id=g.connection_id,
                git_allowed=bool(g.allowed and c and c.enabled),
                default_branch=g.default_branch,
            )
        rows.append(item)
    return rows


@router.post("/projects", status_code=201)
def create_project(body: ProjectCreate, request: Request, db: Session = Depends(get_db)):
    db.execute(text("SELECT pg_advisory_xact_lock(41494442)"))
    if db.query(AppSecProject).filter(func.lower(AppSecProject.name) == body.name.lower()).first():
        raise HTTPException(409, "An AppSec project with this name already exists")
    if db.query(AppSecProject).count() >= 200:
        raise HTTPException(409, "Project limit reached (200)")
    row = AppSecProject(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(db, action="appsec.project.created", request=request, resource_type="appsec_project", resource_id=row.id)
    return project_json(row)


def enqueue(db, project_id, request, body, archive=None):
    project = get_or_404(db, AppSecProject, project_id)
    if archive is None:
        try:
            binding(db, project_id, lock=True)
        except GitError as exc:
            raise HTTPException(409, str(exc)) from exc
    if archive is None and not project.repository_url:
        raise HTTPException(422, "Upload a ZIP snapshot for this project")
    if body.model_config_id:
        if getattr(request.state.user, "role", None) != "admin":
            raise HTTPException(403, "Only admins can authorize source transfer to an AI model")
        if not body.allow_source_to_model:
            raise HTTPException(422, "Explicit source-transfer consent is required for AI review")
        cfg = db.get(AIModelConfig, body.model_config_id)
        if not cfg or not cfg.enabled:
            raise HTTPException(422, "Select an enabled AI model")
    db.execute(text("SELECT pg_advisory_xact_lock(41494442)"))
    active = db.query(AppSecScan).filter(AppSecScan.status.in_(["queued", "running"]))
    if active.filter_by(project_id=project_id).first():
        raise HTTPException(409, "This project already has an active scan")
    if active.count() >= 4:
        raise HTTPException(409, "AppSec queue is full (4 scans). Wait for a scan to finish.")
    row = AppSecScan(
        project_id=project_id,
        source="upload" if archive is not None else "repository",
        requested_ref=body.ref,
        commit_sha=body.ref if archive is not None else None,
        archive=archive,
        archive_sha256=hashlib.sha256(archive).hexdigest() if archive is not None else None,
        model_config_id=body.model_config_id,
        ai_requested=int(bool(body.model_config_id)),
        created_by=request.state.user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    audit(
        db,
        action="appsec.scan.queued",
        request=request,
        resource_type="appsec_scan",
        resource_id=row.id,
        detail={"source": row.source, "ai_requested": bool(row.ai_requested)},
    )
    return scan_json(row)


@router.post("/projects/{project_id}/scans", status_code=202)
def start_scan(project_id: int, body: ScanCreate, request: Request, db: Session = Depends(get_db)):
    return enqueue(db, project_id, request, body)


@router.post("/projects/{project_id}/upload", status_code=202)
async def upload(
    project_id: int,
    request: Request,
    commit: str = Query(pattern=r"^[0-9a-fA-F]{40}$"),
    model_config_id: int | None = None,
    allow_source_to_model: bool = False,
    db: Session = Depends(get_db),
):
    get_or_404(db, AppSecProject, project_id)
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_ARCHIVE:
            raise HTTPException(413, "ZIP exceeds 10 MiB")
    try:
        # Validation only. No files are extracted to the host.
        import asyncio

        await asyncio.to_thread(read_source, bytes(data))
    except SourceError as exc:
        raise HTTPException(422, str(exc)) from exc
    return enqueue(
        db,
        project_id,
        request,
        ScanCreate(ref=commit.lower(), model_config_id=model_config_id, allow_source_to_model=allow_source_to_model),
        bytes(data),
    )


@router.get("/projects/{project_id}/scans")
def scans(project_id: int, db: Session = Depends(get_db)):
    get_or_404(db, AppSecProject, project_id)
    return [
        scan_json(s)
        for s in db.query(AppSecScan).filter_by(project_id=project_id).order_by(AppSecScan.id.desc()).limit(100)
    ]


@router.get("/scans/{scan_id}")
def scan(scan_id: int, db: Session = Depends(get_db)):
    result = scan_json(get_or_404(db, AppSecScan, scan_id), details=True)
    result["findings"] = [
        finding_json(f) for f in db.query(AppSecFinding).filter_by(scan_id=scan_id).order_by(AppSecFinding.id)
    ]
    return result


@router.post("/scans/{scan_id}/cancel")
def cancel(scan_id: int, request: Request, db: Session = Depends(get_db)):
    row = db.query(AppSecScan).filter_by(id=scan_id).with_for_update().first()
    if not row:
        raise HTTPException(404, "Scan not found")
    if row.status not in {"queued", "running"}:
        raise HTTPException(409, "Scan already finished")
    row.status = "cancelled"
    row.archive = None
    row.completed_at = datetime.utcnow()
    db.commit()
    audit(db, action="appsec.scan.cancelled", request=request, resource_type="appsec_scan", resource_id=scan_id)
    return scan_json(row)


@router.patch("/findings/{finding_id}")
def triage(finding_id: int, body: Triage, request: Request, db: Session = Depends(get_db)):
    row = get_or_404(db, AppSecFinding, finding_id)
    row.status = body.status
    db.commit()
    audit(
        db,
        action="appsec.finding.triaged",
        request=request,
        resource_type="appsec_finding",
        resource_id=row.id,
        detail={"status": body.status},
    )
    return finding_json(row)


@router.post("/findings/{finding_id}/task", status_code=201)
def create_task(finding_id: int, request: Request, db: Session = Depends(get_db)):
    from services.task_service import TaskService

    row = db.query(AppSecFinding).filter_by(id=finding_id).with_for_update().first()
    if not row:
        raise HTTPException(404, "Finding not found")
    if not row.task_id:
        scan = db.get(AppSecScan, row.scan_id)
        task = TaskService(db).create(
            _commit=False,
            title=f"AppSec: {row.title}"[:255],
            status="backlog",
            description=f"AppSec scan #{scan.id}, commit {scan.commit_sha}\n{row.path}:{row.line}\n\n{row.description}\n\nRecommendation: {row.recommendation}\n\nReview in /appsec?project={scan.project_id}&scan={scan.id}",
            priority=row.severity,
            source="appsec",
            orchestrate=False,
            created_by=request.state.user.id,
            meta={"appsec_finding_id": row.id, "appsec_scan_id": scan.id},
        )
        row.task_id = task.id
        db.commit()
        audit(
            db,
            action="appsec.finding.task_created",
            request=request,
            resource_type="appsec_finding",
            resource_id=row.id,
        )
    return {"task_id": row.task_id}


@router.get("/scans/{scan_id}/report")
def report(scan_id: int, format: str = Query("json", pattern="^(json|html|sarif)$"), db: Session = Depends(get_db)):
    data = scan(scan_id, db)
    if data["status"] not in {"completed", "partial"}:
        raise HTTPException(409, "Report is available after analysis finishes")
    if format == "html":

        def esc(value):
            return html.escape(str(value))

        content = '<!doctype html><html lang="en"><meta charset="utf-8"><title>AIDA AppSec report</title><body><h1>AIDA Application Security</h1>'
        content += f"<p>Scan #{scan_id} · {esc(data['status'])} · commit {esc(data['commit_sha'])}</p><p>Static review candidates; no source code was executed. Dependency advisories were not checked.</p>"
        for item in data["findings"]:
            content += f"<article><h2>{esc(item['title'])}</h2><p>{esc(item['severity'])} · {esc(item['status'])} · {esc(item['path'])}:{item['line']}</p><p>{esc(item['description'])}</p><p>{esc(item['recommendation'])}</p></article>"
        content += (
            "<h2>Coverage and limitations</h2><pre>"
            + esc(json.dumps(data["summary"], indent=2))
            + "</pre></body></html>"
        )
        media = "text/html"
    elif format == "sarif":
        from urllib.parse import quote

        content = json.dumps(
            {
                "version": "2.1.0",
                "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
                "runs": [
                    {
                        "tool": {
                            "driver": {
                                "name": "AIDA AppSec",
                                "version": data["summary"].get("engine_version", "baseline-1"),
                            }
                        },
                        "invocations": [{"executionSuccessful": data["status"] == "completed"}],
                        "results": [
                            {
                                "ruleId": f["rule_id"],
                                "level": "error" if f["severity"] in {"high", "critical"} else "warning",
                                "message": {"text": f["title"] + ": " + f["description"]},
                                "partialFingerprints": {"aida/v1": f["fingerprint"]},
                                "locations": [
                                    {
                                        "physicalLocation": {
                                            "artifactLocation": {"uri": quote(f["path"], safe="/")},
                                            "region": {"startLine": f["line"]},
                                        }
                                    }
                                ],
                                "properties": {"triage": f["status"], "confidence": f["confidence"]},
                            }
                            for f in data["findings"]
                        ],
                    }
                ],
            }
        )
        media = "application/json"
    else:
        content, media = json.dumps(data, default=str, indent=2), "application/json"
    return Response(
        content,
        media_type=media,
        headers={
            "Content-Disposition": f'attachment; filename="appsec-{scan_id}.{format}"',
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
