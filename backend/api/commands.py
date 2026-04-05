"""
Command execution and history API endpoints
"""
from typing import List, Optional
import re
import base64
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from database import get_db, get_async_db
from models import CommandHistory, Assessment, Credential
from schemas.command import CommandExecute, PythonExecRequest, HttpRequestRequest, CommandResponse, CommandsPaginatedResponse, CommandWithAssessmentResponse
from services.container_service import ContainerService
from middleware.rate_limit import limiter

# Router for assessment-specific commands
router = APIRouter(prefix="/assessments/{assessment_id}/commands", tags=["commands"])


async def _substitute_credentials(text: str, assessment_id: int, db: AsyncSession) -> str:
    """Replace {{PLACEHOLDER}} tokens in text with actual credential values.

    Reused by both execute-with-credentials and python-exec endpoints.
    Raises HTTP 404 if a placeholder is not found in credentials.
    """
    placeholders = re.findall(r'\{\{([A-Z0-9_]+)\}\}', text)
    if not placeholders:
        return text

    stmt = select(Credential).filter(Credential.assessment_id == assessment_id)
    result = await db.execute(stmt)
    credentials = result.scalars().all()
    creds_map = {cred.placeholder.strip("{}"): cred for cred in credentials}

    for placeholder in placeholders:
        if placeholder in creds_map:
            cred = creds_map[placeholder]
            if cred.credential_type == "bearer_token":
                replacement = cred.token
            elif cred.credential_type == "api_key":
                replacement = cred.token
            elif cred.credential_type == "cookie":
                replacement = cred.cookie_value
            elif cred.credential_type == "basic_auth":
                auth_str = f"{cred.username}:{cred.password}"
                replacement = base64.b64encode(auth_str.encode()).decode()
            elif cred.credential_type == "ssh":
                replacement = f"{cred.username}:{cred.password}"
            elif cred.credential_type == "custom":
                replacement = cred.token or str(cred.custom_data or "")
            else:
                replacement = ""
            text = text.replace(f"{{{{{placeholder}}}}}", replacement)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Placeholder '{{{{{placeholder}}}}}' not found in credentials"
            )

    return text

# Router for global commands view
global_router = APIRouter(prefix="/commands", tags=["global-commands"])


@router.get("", response_model=List[CommandResponse])
async def list_commands(
    assessment_id: int,
    limit: int = 10000,
    db: Session = Depends(get_db)
):
    """Get command history for an assessment"""
    # Verify assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    commands = (
        db.query(CommandHistory)
        .filter(CommandHistory.assessment_id == assessment_id)
        .order_by(CommandHistory.created_at.desc())
        .limit(limit)
        .all()
    )

    return commands


@router.get("/{command_id}", response_model=CommandResponse)
async def get_command(
    assessment_id: int,
    command_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific command result"""
    command = db.query(CommandHistory).filter(
        CommandHistory.id == command_id,
        CommandHistory.assessment_id == assessment_id
    ).first()

    if not command:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Command with id {command_id} not found"
        )

    return command


@router.post("/execute", response_model=CommandResponse)
@limiter.limit("30/minute")
async def execute_command(
    request: Request,
    assessment_id: int,
    command_data: CommandExecute,
    db: AsyncSession = Depends(get_async_db)
):
    """Execute a command in Exegol and log it (async optimized)"""
    # Verify assessment exists
    stmt = select(Assessment).filter(Assessment.id == assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()

    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    # Execute command via Exegol service
    container_service = ContainerService()
    result = await container_service.execute_and_log_command(
        assessment_id=assessment_id,
        command=command_data.command,
        phase=command_data.phase,
        db=db
    )

    return result


@router.post("/execute-with-credentials", response_model=CommandResponse)
async def execute_command_with_credentials(
    assessment_id: int,
    command_data: CommandExecute,
    db: AsyncSession = Depends(get_async_db)
):
    """Execute command with automatic credential substitution (optimized single-call endpoint)"""
    # Verify assessment exists
    stmt = select(Assessment).filter(Assessment.id == assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()

    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    # Apply credential substitution via shared helper
    command = await _substitute_credentials(command_data.command, assessment_id, db)

    # Execute command via Exegol service
    container_service = ContainerService()
    result = await container_service.execute_and_log_command(
        assessment_id=assessment_id,
        command=command,
        phase=command_data.phase,
        db=db
    )

    return result


@router.post("/python-exec", response_model=CommandResponse)
async def execute_python(
    assessment_id: int,
    payload: PythonExecRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """Execute Python code in Exegol via stdin (no heredoc escaping needed).

    Supports {{PLACEHOLDER}} credential substitution in the code.
    The code is piped directly to `python3 -` via docker exec stdin.
    """
    # Verify assessment exists
    stmt = select(Assessment).filter(Assessment.id == assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()

    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    # Apply credential substitution to the code (same {{PLACEHOLDER}} syntax)
    code = await _substitute_credentials(payload.code, assessment_id, db)

    # Execute via stdin — zero escaping
    container_service = ContainerService()
    result = await container_service.execute_and_log_python(
        assessment_id=assessment_id,
        code=code,
        phase=payload.phase,
        db=db
    )

    return result


@router.post("/http-request", response_model=CommandResponse)
async def http_request_endpoint(
    assessment_id: int,
    payload: HttpRequestRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """Make a structured HTTP request from inside Exegol (no curl escaping).

    Generates a Python requests script dynamically and pipes it via stdin to
    python3 inside the container. Execution stays in Exegol (network isolation,
    VPN access, Burp proxy routing).

    Supports {{PLACEHOLDER}} substitution on url, headers, cookies, and auth.
    """
    # Verify assessment exists
    stmt = select(Assessment).filter(Assessment.id == assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()

    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment with id {assessment_id} not found"
        )

    # Apply credential substitution to all string fields that support {{PLACEHOLDER}}
    payload.url = await _substitute_credentials(payload.url, assessment_id, db)

    if payload.headers:
        payload.headers = {
            k: await _substitute_credentials(v, assessment_id, db)
            for k, v in payload.headers.items()
        }

    if payload.cookies:
        payload.cookies = {
            k: await _substitute_credentials(v, assessment_id, db)
            for k, v in payload.cookies.items()
        }

    if payload.auth:
        payload.auth = [
            await _substitute_credentials(v, assessment_id, db)
            for v in payload.auth
        ]

    # Execute inside Exegol via generated Python script
    container_service = ContainerService()
    result = await container_service.execute_and_log_http_request(
        assessment_id=assessment_id,
        params=payload,
        db=db
    )

    return result


# ========== GLOBAL COMMANDS ROUTES ==========

@global_router.get("", response_model=CommandsPaginatedResponse)
async def list_all_commands(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    search: Optional[str] = None,
    command_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all commands across all assessments with pagination and filtering"""

    # Start with base query joining Assessment for name
    query = db.query(CommandHistory).join(
        Assessment,
        CommandHistory.assessment_id == Assessment.id
    )

    # Filter by status — frontend sends 'success' (passed) or 'failed'
    if status and status != "all":
        if status in ("completed", "success"):
            query = query.filter(CommandHistory.returncode == 0)
        elif status == "failed":
            query = query.filter(CommandHistory.returncode != 0)

    # Filter by command type — 'shell' includes null values (default type)
    if command_type and command_type != "all":
        if command_type == "shell":
            query = query.filter(
                or_(CommandHistory.command_type == "shell", CommandHistory.command_type == None)
            )
        else:
            query = query.filter(CommandHistory.command_type == command_type)

    # Search filter across command, assessment name, and phase
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                CommandHistory.command.ilike(search_term),
                Assessment.name.ilike(search_term),
                CommandHistory.phase.ilike(search_term)
            )
        )

    # Get total count before pagination
    total = query.count()

    # Apply pagination and ordering
    commands = (
        query.order_by(CommandHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # Build response with assessment names
    commands_with_assessment = [
        CommandWithAssessmentResponse(
            id=cmd.id,
            assessment_id=cmd.assessment_id,
            container_name=cmd.container_name,
            command=cmd.command,
            stdout=cmd.stdout,
            stderr=cmd.stderr,
            returncode=cmd.returncode,
            execution_time=cmd.execution_time,
            success=cmd.success,
            phase=cmd.phase,
            status=cmd.status,
            command_type=cmd.command_type or 'shell',
            source_code=cmd.source_code,
            created_at=cmd.created_at,
            assessment_name=cmd.assessment.name if cmd.assessment else "Unknown"
        )
        for cmd in commands
    ]

    return CommandsPaginatedResponse(
        commands=commands_with_assessment,
        total=total,
        skip=skip,
        limit=limit,
        has_more=(skip + limit) < total
    )
