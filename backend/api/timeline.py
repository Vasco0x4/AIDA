"""
Timeline API endpoints
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from schemas.timeline import (
    TimelineEventCreate,
    TimelineEventResponse,
    TimelineResponse,
    TimelineAutoGenerateResponse,
)
from services.timeline_service import TimelineService

router = APIRouter(prefix="/assessments/{assessment_id}/timeline", tags=["timeline"])


@router.get("", response_model=TimelineResponse)
def get_timeline(
    assessment_id: int,
    phase: Optional[str] = Query(None, description="Filter by phase"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Get timeline events for an assessment"""
    service = TimelineService(db)
    events = service.get_events(assessment_id, phase=phase, event_type=event_type, limit=limit)
    phases = service.get_phase_counts(assessment_id)

    event_responses = []
    for e in events:
        resp = TimelineEventResponse(
            id=e.id,
            assessment_id=e.assessment_id,
            phase=e.phase,
            event_type=e.event_type,
            title=e.title,
            description=e.description,
            command_id=e.command_id,
            card_id=e.card_id,
            recon_id=e.recon_id,
            severity=e.severity,
            icon=e.icon,
            tags=e.tags,
            created_at=e.created_at,
            command_text=e.command.command[:100] if e.command else None,
            card_title=e.card.title if e.card else None,
            recon_name=e.recon.name if e.recon else None,
        )
        event_responses.append(resp)

    return TimelineResponse(events=event_responses, total=len(event_responses), phases=phases)


@router.post("", response_model=TimelineEventResponse, status_code=201)
def create_timeline_event(
    assessment_id: int,
    event: TimelineEventCreate,
    db: Session = Depends(get_db),
):
    """Create a manual timeline event"""
    service = TimelineService(db)
    e = service.create_event(assessment_id=assessment_id, **event.model_dump())
    return TimelineEventResponse(
        id=e.id,
        assessment_id=e.assessment_id,
        phase=e.phase,
        event_type=e.event_type,
        title=e.title,
        description=e.description,
        command_id=e.command_id,
        card_id=e.card_id,
        recon_id=e.recon_id,
        severity=e.severity,
        icon=e.icon,
        tags=e.tags,
        created_at=e.created_at,
    )


@router.delete("/{event_id}", status_code=204)
def delete_timeline_event(
    assessment_id: int,
    event_id: int,
    db: Session = Depends(get_db),
):
    """Delete a timeline event"""
    service = TimelineService(db)
    if not service.delete_event(event_id, assessment_id):
        raise HTTPException(status_code=404, detail="Timeline event not found")


@router.post("/auto-generate", response_model=TimelineAutoGenerateResponse)
def auto_generate_timeline(
    assessment_id: int,
    db: Session = Depends(get_db),
):
    """Auto-generate timeline events from existing commands, findings, and recon data"""
    service = TimelineService(db)
    count = service.auto_generate(assessment_id)
    return TimelineAutoGenerateResponse(
        generated=count,
        message=f"Generated {count} timeline events" if count > 0 else "No new events to generate",
    )
