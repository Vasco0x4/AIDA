"""
Global commands API endpoints (across all assessments)
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from database import get_db
from models import CommandHistory, Assessment
from schemas.command import CommandsPaginatedResponse, CommandWithAssessmentResponse

router = APIRouter(prefix="/commands", tags=["global-commands"])


@router.get("/stats")
async def get_command_stats(db: Session = Depends(get_db)):
    """Get command statistics for dashboard header"""
    try:
        total = db.query(CommandHistory).count()
        passed = db.query(CommandHistory).filter(CommandHistory.success == True).count()
        failed = db.query(CommandHistory).filter(CommandHistory.success == False).count()
        avg_time = db.query(func.avg(CommandHistory.execution_time)).scalar() or 0

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "avg_execution_time": round(float(avg_time), 2)
        }
    except Exception:
        # Return empty stats on error (e.g. table missing)
        return {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "avg_execution_time": 0
        }


@router.get("", response_model=CommandsPaginatedResponse)
async def list_all_commands(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of records to return"),
    status: Optional[str] = Query(None, description="Filter by status: 'success', 'failed', or null for all"),
    search: Optional[str] = Query(None, description="Search in command text, assessment name, or phase"),
    command_type: Optional[str] = Query(None, description="Filter by type: 'shell', 'python', 'http'"),
    db: Session = Depends(get_db)
):
    """
    Get all commands across all assessments with pagination and filters.

    This endpoint is optimized for the global commands view page.
    - Supports infinite scroll with skip/limit
    - Filters by success status and command type
    - Full-text search across commands, assessments, and phases
    - Returns assessment names with commands
    """
    # Build base query with join to get assessment name
    query = db.query(
        CommandHistory.id,
        CommandHistory.assessment_id,
        CommandHistory.container_name,
        CommandHistory.command,
        CommandHistory.stdout,
        CommandHistory.stderr,
        CommandHistory.returncode,
        CommandHistory.execution_time,
        CommandHistory.success,
        CommandHistory.status,
        CommandHistory.phase,
        CommandHistory.command_type,
        CommandHistory.source_code,
        CommandHistory.created_at,
        Assessment.name.label('assessment_name')
    ).join(Assessment, CommandHistory.assessment_id == Assessment.id)

    # Apply status filter
    if status == 'success':
        query = query.filter(CommandHistory.success == True)
    elif status == 'failed':
        query = query.filter(CommandHistory.success == False)

    # Apply command type filter
    if command_type:
        if command_type == 'shell':
            # Shell includes null and 'shell'
            query = query.filter(
                or_(CommandHistory.command_type == 'shell', CommandHistory.command_type == None)
            )
        else:
            query = query.filter(CommandHistory.command_type == command_type)

    # Apply search filter
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            or_(
                CommandHistory.command.ilike(search_pattern),
                Assessment.name.ilike(search_pattern),
                CommandHistory.phase.ilike(search_pattern)
            )
        )

    # Count total matching records
    total = query.count()

    # Get paginated results
    results = query.order_by(CommandHistory.created_at.desc())\
                   .offset(skip)\
                   .limit(limit)\
                   .all()

    # Convert to response format
    commands = [
        CommandWithAssessmentResponse(
            id=row.id,
            assessment_id=row.assessment_id,
            container_name=row.container_name,
            command=row.command,
            stdout=row.stdout,
            stderr=row.stderr,
            returncode=row.returncode,
            execution_time=row.execution_time,
            success=row.success,
            status=row.status,
            phase=row.phase,
            command_type=row.command_type or 'shell',
            source_code=row.source_code,
            created_at=row.created_at,
            assessment_name=row.assessment_name
        )
        for row in results
    ]

    # Calculate if there are more records
    has_more = (skip + limit) < total

    return CommandsPaginatedResponse(
        commands=commands,
        total=total,
        skip=skip,
        limit=limit,
        has_more=has_more
    )
