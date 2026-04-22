"""
Agent Run Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict, Field


class AgentRunCreate(BaseModel):
    """Request payload for starting a new UI-initiated scan"""
    goal: str = Field(..., min_length=1, description="What the agent should do")
    permission_mode: Optional[str] = Field(
        default=None,
        description="Claude permission mode (e.g. acceptEdits, bypassPermissions)",
    )
    model: Optional[str] = Field(
        default=None, description="Override Claude model id"
    )


class AgentRunResponse(BaseModel):
    """Full state of an agent run"""
    id: int
    assessment_id: int
    user_id: Optional[int]
    goal: str
    status: str
    permission_mode: Optional[str]
    model: Optional[str]
    error: Optional[str]
    num_turns: Optional[int]
    cost_usd: Optional[float]
    duration_ms: Optional[int]
    transcript: Optional[List[Dict[str, Any]]]
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AgentRunSummary(BaseModel):
    """Lightweight view used in list endpoints (no transcript)"""
    id: int
    assessment_id: int
    user_id: Optional[int]
    goal: str
    status: str
    model: Optional[str]
    num_turns: Optional[int]
    cost_usd: Optional[float]
    duration_ms: Optional[int]
    created_at: datetime
    started_at: Optional[datetime]
    ended_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class AgentRunListResponse(BaseModel):
    runs: List[AgentRunSummary]
    total: int
