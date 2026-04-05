"""
Notification API endpoints
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.notification import (
    NotificationConfigCreate,
    NotificationConfigUpdate,
    NotificationConfigResponse,
    NotificationTestRequest,
    NotificationTestResponse,
    SendReportRequest,
    SendReportResponse,
)
from services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=List[NotificationConfigResponse])
def list_notification_configs(db: Session = Depends(get_db)):
    """List all notification channel configurations"""
    service = NotificationService(db)
    return service.get_all_configs()


@router.get("/{channel}", response_model=NotificationConfigResponse)
def get_notification_config(channel: str, db: Session = Depends(get_db)):
    """Get configuration for a specific notification channel"""
    service = NotificationService(db)
    config = service.get_config(channel)
    if not config:
        raise HTTPException(status_code=404, detail=f"No configuration for channel: {channel}")
    return config


@router.put("/{channel}", response_model=NotificationConfigResponse)
def upsert_notification_config(
    channel: str,
    body: NotificationConfigUpdate,
    db: Session = Depends(get_db),
):
    """Create or update a notification channel configuration"""
    service = NotificationService(db)
    config = service.upsert_config(channel, **body.model_dump(exclude_unset=True))
    return config


@router.post("", response_model=NotificationConfigResponse, status_code=201)
def create_notification_config(
    body: NotificationConfigCreate,
    db: Session = Depends(get_db),
):
    """Create a new notification channel configuration"""
    service = NotificationService(db)
    existing = service.get_config(body.channel)
    if existing:
        raise HTTPException(status_code=409, detail=f"Configuration for {body.channel} already exists. Use PUT to update.")
    config = service.upsert_config(**body.model_dump())
    return config


@router.delete("/{channel}", status_code=204)
def delete_notification_config(channel: str, db: Session = Depends(get_db)):
    """Delete a notification channel configuration"""
    service = NotificationService(db)
    if not service.delete_config(channel):
        raise HTTPException(status_code=404, detail=f"No configuration for channel: {channel}")


@router.post("/test", response_model=NotificationTestResponse)
async def test_notification(
    body: NotificationTestRequest,
    db: Session = Depends(get_db),
):
    """Send a test notification to verify channel configuration"""
    service = NotificationService(db)
    success, message = await service.test_channel(body.channel)
    return NotificationTestResponse(success=success, message=message)


@router.post("/send-report/{assessment_id}", response_model=SendReportResponse)
async def send_assessment_report(
    assessment_id: int,
    body: SendReportRequest,
    db: Session = Depends(get_db),
):
    """Send an assessment report to a specific notification channel"""
    service = NotificationService(db)
    success, message = await service.send_report(
        channel=body.channel,
        assessment_id=assessment_id,
        include_findings=body.include_findings,
        include_stats=body.include_stats,
        include_commands=body.include_commands,
        custom_message=body.custom_message,
    )
    return SendReportResponse(success=success, message=message, channel=body.channel)
