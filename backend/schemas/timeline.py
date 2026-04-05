"""
Timeline Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class TimelineEventCreate(BaseModel):
    phase: str  # recon, scanning, exploitation, post_exploitation, reporting
    event_type: str  # command, finding, observation, recon, credential, manual
    title: str
    description: Optional[str] = None
    command_id: Optional[int] = None
    card_id: Optional[int] = None
    recon_id: Optional[int] = None
    severity: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[str] = None


class TimelineEventResponse(BaseModel):
    id: int
    assessment_id: int
    phase: str
    event_type: str
    title: str
    description: Optional[str] = None
    command_id: Optional[int] = None
    card_id: Optional[int] = None
    recon_id: Optional[int] = None
    severity: Optional[str] = None
    icon: Optional[str] = None
    tags: Optional[str] = None
    created_at: datetime

    # Linked entity details (populated by service)
    command_text: Optional[str] = None
    card_title: Optional[str] = None
    recon_name: Optional[str] = None

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    events: List[TimelineEventResponse]
    total: int
    phases: Dict[str, int]  # count per phase


class TimelineAutoGenerateResponse(BaseModel):
    generated: int
    message: str
