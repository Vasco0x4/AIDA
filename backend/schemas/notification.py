"""
Notification Pydantic schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class NotificationConfigCreate(BaseModel):
    channel: str  # telegram, slack, email
    enabled: bool = False
    config: Dict[str, Any] = {}
    on_critical_finding: bool = True
    on_high_finding: bool = True
    on_scan_complete: bool = False
    on_assessment_complete: bool = False


class NotificationConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    on_critical_finding: Optional[bool] = None
    on_high_finding: Optional[bool] = None
    on_scan_complete: Optional[bool] = None
    on_assessment_complete: Optional[bool] = None


class NotificationConfigResponse(BaseModel):
    id: int
    channel: str
    enabled: bool
    config: Dict[str, Any] = {}
    on_critical_finding: bool
    on_high_finding: bool
    on_scan_complete: bool
    on_assessment_complete: bool

    model_config = {"from_attributes": True}


class NotificationTestRequest(BaseModel):
    channel: str


class NotificationTestResponse(BaseModel):
    success: bool
    message: str


class SendReportRequest(BaseModel):
    channel: str  # telegram, slack, email
    include_findings: bool = True
    include_stats: bool = True
    include_commands: bool = False
    custom_message: Optional[str] = None


class SendReportResponse(BaseModel):
    success: bool
    message: str
    channel: str
