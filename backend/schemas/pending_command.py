"""
Pending Command Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict


class PendingCommandCreate(BaseModel):
    """Schema for creating a pending command"""
    command: str
    phase: Optional[str] = None
    matched_keywords: List[str] = []


class PendingCommandResponse(BaseModel):
    """Schema for pending command response"""
    id: int
    assessment_id: int
    command: str
    phase: Optional[str]
    matched_keywords: List[str]
    status: str  # pending, approved, rejected, executed
    resolved_by: Optional[str]
    rejection_reason: Optional[str]
    resolved_at: Optional[datetime]
    execution_result: Optional[dict]
    created_at: datetime
    timeout_seconds: Optional[int] = None  # Command-specific timeout
    assessment_name: Optional[str] = None  # Added for list view

    model_config = ConfigDict(from_attributes=True)


class PendingCommandApprove(BaseModel):
    """Schema for approving a pending command"""
    approved_by: str = "admin"


class PendingCommandReject(BaseModel):
    """Schema for rejecting a pending command"""
    rejected_by: str = "admin"
    rejection_reason: Optional[str] = None


class CommandSettingsResponse(BaseModel):
    """Schema for command settings"""
    execution_mode: str  # open, filter, closed
    filter_keywords: List[str]
    timeout_seconds: int = 300  # Default 5 minutes
    http_method_rules: Dict[str, str] = {}  # method -> "auto_approve" | "require_approval" | "inherit"


class CommandSettingsUpdate(BaseModel):
    """Schema for updating command settings"""
    execution_mode: Optional[str] = None
    filter_keywords: Optional[List[str]] = None
    timeout_seconds: Optional[int] = None
    http_method_rules: Optional[Dict[str, str]] = None


class KeywordAdd(BaseModel):
    """Schema for adding a keyword"""
    keyword: str


class PendingCommandsListResponse(BaseModel):
    """Schema for paginated pending commands"""
    commands: List[PendingCommandResponse]
    total: int
    pending_count: int
