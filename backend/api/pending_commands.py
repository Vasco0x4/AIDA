"""
Pending Commands and Command Settings API endpoints
"""
import json
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database import SessionLocal, get_db, get_async_db
from models import PendingCommand, Assessment, PlatformSettings
from schemas.pending_command import (
    PendingCommandResponse, 
    PendingCommandApprove, 
    PendingCommandReject,
    CommandSettingsResponse,
    CommandSettingsUpdate,
    KeywordAdd,
    PendingCommandsListResponse
)
from services.container_service import ContainerService
from services.audit_service import record as audit
from schemas.command import HttpRequestRequest
from websocket.manager import manager

router = APIRouter(prefix="/pending-commands", tags=["pending-commands"])
settings_router = APIRouter(prefix="/command-settings", tags=["command-settings"])

# Default settings
DEFAULT_EXECUTION_MODE = "open"
DEFAULT_FILTER_KEYWORDS = ["rm", "delete", "drop", "truncate", "sudo", "chmod", "chown", "mkfs", "dd", "format"]
DEFAULT_TIMEOUT_SECONDS = 30  # 30 seconds
DEFAULT_HTTP_METHOD_RULES = {}  # All methods inherit global mode by default


# ========== Helper Functions ==========

def get_command_settings(db: Session) -> dict:
    """Get current command settings from platform_settings"""
    mode_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "command_execution_mode"
    ).first()

    keywords_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "command_filter_keywords"
    ).first()

    timeout_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "command_timeout_seconds"
    ).first()

    http_method_rules_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "command_http_method_rules"
    ).first()

    exploit_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "exploit_approval"
    ).first()
    exploit_admin_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "exploit_admin_approval"
    ).first()
    exploit_timeout_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "exploit_approval_timeout"
    ).first()

    return {
        "execution_mode": mode_setting.value if mode_setting else DEFAULT_EXECUTION_MODE,
        "filter_keywords": json.loads(keywords_setting.value) if keywords_setting else DEFAULT_FILTER_KEYWORDS,
        "timeout_seconds": int(timeout_setting.value) if timeout_setting else DEFAULT_TIMEOUT_SECONDS,
        "http_method_rules": json.loads(http_method_rules_setting.value) if http_method_rules_setting else DEFAULT_HTTP_METHOD_RULES,
        "exploit_approval": exploit_setting.value if exploit_setting else "on",
        "exploit_admin_approval": (exploit_admin_setting.value if exploit_admin_setting else "true").lower() in ("true", "1", "yes", "on"),
        "exploit_approval_timeout": int(exploit_timeout_setting.value) if exploit_timeout_setting else 600,
    }


def set_command_setting(db: Session, key: str, value: str, description: str = None):
    """Set a command setting in platform_settings"""
    setting = db.query(PlatformSettings).filter(PlatformSettings.key == key).first()
    if setting:
        setting.value = value
    else:
        setting = PlatformSettings(key=key, value=value, description=description)
        db.add(setting)
    db.commit()
    return setting


def check_and_timeout_expired_commands(db: Session):
    """Check for expired pending commands and mark them as timeout (sync version)"""
    now = datetime.utcnow()
    settings = get_command_settings(db)
    timeout_seconds = settings.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    
    # Find pending commands that have exceeded timeout
    pending_cmds = db.query(PendingCommand).filter(
        PendingCommand.status == "pending"
    ).all()
    
    timed_out_ids = []
    for cmd in pending_cmds:
        # Use command-specific timeout or fall back to global setting
        cmd_timeout = cmd.timeout_seconds if cmd.timeout_seconds is not None else timeout_seconds

        if cmd.created_at:
            # Normalize created_at to naive UTC so we never mix aware/naive
            # datetimes (created_at may be stored either way depending on the
            # driver), which previously raised TypeError mid-loop.
            created_at = cmd.created_at
            if created_at.tzinfo is not None:
                created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)

            elapsed_seconds = (now - created_at).total_seconds()

            if elapsed_seconds > cmd_timeout:
                cmd.status = "timeout"
                cmd.resolved_at = now
                cmd.rejection_reason = f"Auto-cancelled: exceeded {cmd_timeout}s timeout"
                timed_out_ids.append(cmd.id)
    
    if timed_out_ids:
        db.commit()
    
    return timed_out_ids


async def check_and_timeout_expired_commands_async(db: Session):
    """Check for expired pending commands, mark as timeout, and broadcast WebSocket events"""
    timed_out_ids = check_and_timeout_expired_commands(db)
    
    # Broadcast timeout events for each expired command
    for cmd_id in timed_out_ids:
        await manager.broadcast({
            "type": "command_timeout",
            "data": {
                "command_id": cmd_id
            }
        })
    
    return len(timed_out_ids)


# ========== Command Settings Routes ==========

@settings_router.get("", response_model=CommandSettingsResponse)
async def get_settings(db: Session = Depends(get_db)):
    """Get current command execution settings"""
    try:
        settings = get_command_settings(db)
        return CommandSettingsResponse(**settings)
    except Exception:
        # Return defaults if database error
        return CommandSettingsResponse(
            execution_mode=DEFAULT_EXECUTION_MODE,
            filter_keywords=DEFAULT_FILTER_KEYWORDS,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS
        )


@settings_router.put("", response_model=CommandSettingsResponse)
async def update_settings(
    update: CommandSettingsUpdate,
    db: Session = Depends(get_db)
):
    """Update command execution settings"""
    if update.execution_mode:
        if update.execution_mode not in ["open", "filter", "closed"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="execution_mode must be 'open', 'filter', or 'closed'"
            )
        set_command_setting(
            db, 
            "command_execution_mode", 
            update.execution_mode,
            "Command execution mode: open, filter, or closed"
        )
    
    if update.filter_keywords is not None:
        set_command_setting(
            db,
            "command_filter_keywords",
            json.dumps(update.filter_keywords),
            "Keywords that trigger approval in filter mode"
        )
    
    if update.timeout_seconds is not None:
        set_command_setting(
            db,
            "command_timeout_seconds",
            str(update.timeout_seconds),
            "Timeout in seconds for pending commands"
        )

    if update.http_method_rules is not None:
        # Validate actions
        valid_actions = {"auto_approve", "require_approval", "inherit"}
        for method, action in update.http_method_rules.items():
            if action not in valid_actions:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid action '{action}' for method {method}. Must be one of: {', '.join(valid_actions)}"
                )
        set_command_setting(
            db,
            "command_http_method_rules",
            json.dumps(update.http_method_rules),
            "Per-HTTP-method approval rules: auto_approve, require_approval, or inherit"
        )

    # E4 PoC approval chain settings
    if update.exploit_approval is not None:
        if update.exploit_approval not in ("on", "off"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="exploit_approval must be 'on' or 'off'")
        set_command_setting(db, "exploit_approval", update.exploit_approval,
                            "Exploit-class commands require human approval")
    if update.exploit_admin_approval is not None:
        set_command_setting(
            db, "exploit_admin_approval",
            "true" if update.exploit_admin_approval else "false",
            "High-risk (exploit-class) approvals require an admin")
    if update.exploit_approval_timeout is not None:
        if not 30 <= update.exploit_approval_timeout <= 86400:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="exploit_approval_timeout must be 30..86400 seconds")
        set_command_setting(
            db, "exploit_approval_timeout", str(update.exploit_approval_timeout),
            "Seconds an agent waits for a human exploit-approval decision")
    from services.agent.agent_settings import invalidate_settings_cache
    invalidate_settings_cache()

    # Broadcast settings change
    await manager.broadcast({
        "type": "command_settings_updated",
        "data": get_command_settings(db)
    })
    
    return CommandSettingsResponse(**get_command_settings(db))


@settings_router.post("/keywords", response_model=CommandSettingsResponse)
async def add_keyword(
    keyword_data: KeywordAdd,
    db: Session = Depends(get_db)
):
    """Add a keyword to the filter list"""
    settings = get_command_settings(db)
    keywords = settings["filter_keywords"]
    
    keyword = keyword_data.keyword.strip().lower()
    if keyword and keyword not in keywords:
        keywords.append(keyword)
        set_command_setting(
            db,
            "command_filter_keywords",
            json.dumps(keywords),
            "Keywords that trigger approval in filter mode"
        )
    
    return CommandSettingsResponse(**get_command_settings(db))


@settings_router.delete("/keywords/{keyword}", response_model=CommandSettingsResponse)
async def remove_keyword(
    keyword: str,
    db: Session = Depends(get_db)
):
    """Remove a keyword from the filter list"""
    settings = get_command_settings(db)
    keywords = settings["filter_keywords"]
    
    keyword = keyword.strip().lower()
    if keyword in keywords:
        keywords.remove(keyword)
        set_command_setting(
            db,
            "command_filter_keywords",
            json.dumps(keywords),
            "Keywords that trigger approval in filter mode"
        )
    
    return CommandSettingsResponse(**get_command_settings(db))


# ========== Pending Commands Routes ==========

@router.get("", response_model=PendingCommandsListResponse)
async def list_pending_commands(
    status_filter: Optional[str] = None,
    assessment_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """List pending commands with optional filters"""
    # Check and timeout expired commands first (with WebSocket broadcast)
    await check_and_timeout_expired_commands_async(db)
    
    query = db.query(PendingCommand).join(Assessment)
    
    if status_filter:
        query = query.filter(PendingCommand.status == status_filter)
    
    if assessment_id:
        query = query.filter(PendingCommand.assessment_id == assessment_id)
    
    commands = query.order_by(PendingCommand.created_at.desc()).all()
    
    # Count pending
    pending_count = db.query(PendingCommand).filter(
        PendingCommand.status == "pending"
    ).count()
    
    # Build response with assessment names
    result = []
    for cmd in commands:
        cmd_dict = {
            "id": cmd.id,
            "assessment_id": cmd.assessment_id,
            "command": cmd.command,
            "phase": cmd.phase,
            "matched_keywords": cmd.matched_keywords or [],
            "risk_level": cmd.risk_level or "normal",
            "risk_reason": cmd.risk_reason,
            "status": cmd.status,
            "resolved_by": cmd.resolved_by,
            "rejection_reason": cmd.rejection_reason,
            "resolved_at": cmd.resolved_at,
            "execution_result": cmd.execution_result,
            "created_at": cmd.created_at,
            "timeout_seconds": cmd.timeout_seconds,
            "assessment_name": cmd.assessment.name if cmd.assessment else None
        }
        result.append(PendingCommandResponse(**cmd_dict))
    
    return PendingCommandsListResponse(
        commands=result,
        total=len(result),
        pending_count=pending_count
    )


@router.get("/count")
async def get_pending_count(db: Session = Depends(get_db)):
    """Get count of pending commands (for notification badge)"""
    # Check and timeout expired commands first (with WebSocket broadcast)
    await check_and_timeout_expired_commands_async(db)
    
    count = db.query(PendingCommand).filter(
        PendingCommand.status == "pending"
    ).count()
    return {"pending_count": count}


@router.get("/{command_id}", response_model=PendingCommandResponse)
async def get_pending_command(
    command_id: int,
    db: Session = Depends(get_db)
):
    """Get a single pending command by ID (for polling status)"""
    # Check and timeout expired commands first (with WebSocket broadcast)
    await check_and_timeout_expired_commands_async(db)
    
    cmd = db.query(PendingCommand).filter(PendingCommand.id == command_id).first()
    
    if not cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending command {command_id} not found"
        )
    
    # Get assessment name
    assessment = db.query(Assessment).filter(Assessment.id == cmd.assessment_id).first()
    
    return PendingCommandResponse(
        id=cmd.id,
        assessment_id=cmd.assessment_id,
        command=cmd.command,
        phase=cmd.phase,
        matched_keywords=cmd.matched_keywords or [],
        risk_level=cmd.risk_level or "normal",
        risk_reason=cmd.risk_reason,
        status=cmd.status,
        resolved_by=cmd.resolved_by,
        rejection_reason=cmd.rejection_reason,
        resolved_at=cmd.resolved_at,
        execution_result=cmd.execution_result,
        created_at=cmd.created_at,
        assessment_name=assessment.name if assessment else None
    )

@router.post("/{command_id}/approve", response_model=PendingCommandResponse)
async def approve_command(
    command_id: int,
    approval: PendingCommandApprove,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Approve and execute a pending command"""
    # Find command
    stmt = select(PendingCommand).filter(PendingCommand.id == command_id)
    result = await db.execute(stmt)
    pending_cmd = result.scalar_one_or_none()
    
    if not pending_cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending command {command_id} not found"
        )
    
    if pending_cmd.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Command is already {pending_cmd.status}"
        )

    # E4 PoC approval chain: exploit-class commands carry an escalation level —
    # when exploit_admin_approval is on, only an ADMIN may sign them off.
    # (Normal commands stay approvable by any auditor.)
    user = getattr(request.state, "user", None)
    if (pending_cmd.risk_level == "high"):
        admin_setting = (await db.execute(
            select(PlatformSettings).filter(
                PlatformSettings.key == "exploit_admin_approval")
        )).scalar_one_or_none()
        needs_admin = (admin_setting.value if admin_setting else "true").lower() \
            in ("true", "1", "yes", "on")
        if needs_admin and getattr(user, "role", None) != "admin":
            audit(SessionLocal(), action="command.approval_denied", request=request,
                  resource_type="pending_command", resource_id=command_id,
                  detail={"reason": "admin_required",
                          "role": getattr(user, "role", None)})
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This is an exploit-class command (PoC approval chain) — "
                       "only an admin may approve it.")

    # Record WHO approved: the authenticated identity wins over the
    # client-supplied string (non-repudiation for the approval chain).
    approver = getattr(user, "username", None) or approval.approved_by

    # Execute the command — route based on command_type
    container_service = ContainerService()
    try:
        if pending_cmd.command_type == "python":
            exec_result = await container_service.execute_and_log_python(
                assessment_id=pending_cmd.assessment_id,
                code=pending_cmd.command,
                phase=pending_cmd.phase,
                db=db
            )
        elif pending_cmd.command_type == "http":
            # pending_cmd.command stores the JSON-serialized HttpRequestRequest params
            http_params_dict = json.loads(pending_cmd.command)
            http_params = HttpRequestRequest(**http_params_dict)
            exec_result = await container_service.execute_and_log_http_request(
                assessment_id=pending_cmd.assessment_id,
                params=http_params,
                db=db
            )
        else:
            exec_result = await container_service.execute_and_log_command(
                assessment_id=pending_cmd.assessment_id,
                command=pending_cmd.command,
                phase=pending_cmd.phase,
                db=db
            )
    except Exception as e:
        # Don't leave the command stuck in "pending" (and re-approvable forever)
        # if execution raises — bad JSON payload, container down, etc. Mark it
        # as failed and surface the error to the caller.
        pending_cmd.status = "failed"
        pending_cmd.resolved_by = approver
        pending_cmd.resolved_at = datetime.utcnow()
        pending_cmd.rejection_reason = f"Execution failed: {e}"
        pending_cmd.execution_result = {"success": False, "error": str(e)}
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Command execution failed: {e}"
        )


    # Update pending command
    pending_cmd.status = "executed"
    pending_cmd.resolved_by = approver
    pending_cmd.resolved_at = datetime.utcnow()
    pending_cmd.execution_result = {
        "stdout": exec_result.stdout,
        "stderr": exec_result.stderr,
        "returncode": exec_result.returncode,
        "success": exec_result.success
    }
    
    await db.commit()
    await db.refresh(pending_cmd)
    audit(SessionLocal(), action="command.approved", request=request,
          resource_type="pending_command", resource_id=command_id,
          detail={"command": (pending_cmd.command or "")[:200]})
    
    # Broadcast approval to assessment-specific connections
    await manager.broadcast({
        "type": "command_approved",
        "data": {
            "command_id": command_id,
            "assessment_id": pending_cmd.assessment_id,
            "result": pending_cmd.execution_result
        }
    }, assessment_id=pending_cmd.assessment_id)
    
    # Also broadcast globally for sidebar/notifications
    await manager.broadcast({
        "type": "command_approved",
        "data": {
            "command_id": command_id,
            "assessment_id": pending_cmd.assessment_id
        }
    })
    
    # Get assessment name for response
    stmt = select(Assessment).filter(Assessment.id == pending_cmd.assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()
    
    return PendingCommandResponse(
        id=pending_cmd.id,
        assessment_id=pending_cmd.assessment_id,
        command=pending_cmd.command,
        phase=pending_cmd.phase,
        matched_keywords=pending_cmd.matched_keywords or [],
        risk_level=pending_cmd.risk_level or "normal",
        risk_reason=pending_cmd.risk_reason,
        status=pending_cmd.status,
        resolved_by=pending_cmd.resolved_by,
        rejection_reason=pending_cmd.rejection_reason,
        resolved_at=pending_cmd.resolved_at,
        execution_result=pending_cmd.execution_result,
        created_at=pending_cmd.created_at,
        assessment_name=assessment.name if assessment else None
    )


@router.post("/{command_id}/reject", response_model=PendingCommandResponse)
async def reject_command(
    command_id: int,
    rejection: PendingCommandReject,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """Reject a pending command"""
    stmt = select(PendingCommand).filter(PendingCommand.id == command_id)
    result = await db.execute(stmt)
    pending_cmd = result.scalar_one_or_none()
    
    if not pending_cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending command {command_id} not found"
        )
    
    if pending_cmd.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Command is already {pending_cmd.status}"
        )
    
    # Update pending command (identity: the authenticated user wins over the
    # client-supplied string).
    pending_cmd.status = "rejected"
    user = getattr(request.state, "user", None)
    pending_cmd.resolved_by = getattr(user, "username", None) or rejection.rejected_by
    pending_cmd.rejection_reason = rejection.rejection_reason
    pending_cmd.resolved_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(pending_cmd)
    audit(SessionLocal(), action="command.rejected", request=request,
          resource_type="pending_command", resource_id=command_id,
          detail={"reason": (rejection.reason or "")[:200] if hasattr(rejection, "reason") else None})
    
    # Broadcast rejection to assessment-specific connections
    await manager.broadcast({
        "type": "command_rejected",
        "data": {
            "command_id": command_id,
            "assessment_id": pending_cmd.assessment_id,
            "reason": rejection.rejection_reason
        }
    }, assessment_id=pending_cmd.assessment_id)
    
    # Also broadcast globally for sidebar/notifications
    await manager.broadcast({
        "type": "command_rejected",
        "data": {
            "command_id": command_id,
            "assessment_id": pending_cmd.assessment_id
        }
    })
    
    # Get assessment name
    stmt = select(Assessment).filter(Assessment.id == pending_cmd.assessment_id)
    result = await db.execute(stmt)
    assessment = result.scalar_one_or_none()
    
    return PendingCommandResponse(
        id=pending_cmd.id,
        assessment_id=pending_cmd.assessment_id,
        command=pending_cmd.command,
        phase=pending_cmd.phase,
        matched_keywords=pending_cmd.matched_keywords or [],
        risk_level=pending_cmd.risk_level or "normal",
        risk_reason=pending_cmd.risk_reason,
        status=pending_cmd.status,
        resolved_by=pending_cmd.resolved_by,
        rejection_reason=pending_cmd.rejection_reason,
        resolved_at=pending_cmd.resolved_at,
        execution_result=pending_cmd.execution_result,
        created_at=pending_cmd.created_at,
        assessment_name=assessment.name if assessment else None
    )


@router.delete("/{command_id}")
async def delete_pending_command(
    command_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Delete a pending command"""
    cmd = db.query(PendingCommand).filter(PendingCommand.id == command_id).first()
    
    if not cmd:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending command {command_id} not found"
        )
    
    db.delete(cmd)
    db.commit()
    audit(db, action="command.deleted", request=request,
          resource_type="pending_command", resource_id=command_id)
    
    return {"message": f"Pending command {command_id} deleted"}


@router.post("/create", response_model=PendingCommandResponse)
async def create_pending_command(
    command_data: dict,
    db: Session = Depends(get_db)
):
    """Create a pending command (used by MCP handler)"""
    assessment_id = command_data.get("assessment_id")
    
    # Verify assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == assessment_id).first()
    if not assessment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found"
        )
    
    # Get current timeout setting
    settings = get_command_settings(db)
    timeout_sec = settings.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    
    # Create pending command
    pending_cmd = PendingCommand(
        assessment_id=assessment_id,
        command=command_data.get("command"),
        phase=command_data.get("phase"),
        matched_keywords=command_data.get("matched_keywords", []),
        status="pending",
        timeout_seconds=timeout_sec,
        command_type=command_data.get("command_type", "shell")  # 'shell' | 'python'
    )
    
    db.add(pending_cmd)
    db.commit()
    db.refresh(pending_cmd)
    
    # Broadcast notification
    await manager.broadcast({
        "type": "command_pending_approval",
        "data": {
            "id": pending_cmd.id,
            "assessment_id": assessment_id,
            "command": pending_cmd.command,
            "matched_keywords": pending_cmd.matched_keywords,
            "assessment_name": assessment.name,
            "created_at": pending_cmd.created_at.isoformat() if pending_cmd.created_at else None,
            "timeout_seconds": pending_cmd.timeout_seconds
        }
    })
    
    return PendingCommandResponse(
        id=pending_cmd.id,
        assessment_id=pending_cmd.assessment_id,
        command=pending_cmd.command,
        phase=pending_cmd.phase,
        matched_keywords=pending_cmd.matched_keywords or [],
        risk_level=pending_cmd.risk_level or "normal",
        risk_reason=pending_cmd.risk_reason,
        status=pending_cmd.status,
        timeout_seconds=pending_cmd.timeout_seconds,
        resolved_by=None,
        rejection_reason=None,
        resolved_at=None,
        execution_result=None,
        created_at=pending_cmd.created_at,
        assessment_name=assessment.name
    )
