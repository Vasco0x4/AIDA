"""Pydantic schemas for Tasks (Kanban board + autonomous work queue)."""
from typing import Optional, Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

TaskStatus = Literal["backlog", "queued", "running", "needs_review", "done", "failed"]
TaskPriority = Literal["low", "medium", "high", "critical"]
ExecutionTarget = Literal["container", "host"]


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    target: Optional[str] = None
    authorized_scope: Optional[str] = None
    priority: TaskPriority = "medium"
    execution_target: ExecutionTarget = "container"
    model_config_id: Optional[int] = None
    token_budget: Optional[int] = Field(default=None, ge=0)
    assessment_id: Optional[int] = None
    assignee: Optional[str] = None
    parent_task_id: Optional[int] = None
    orchestrate: bool = True
    meta: Optional[dict] = None


class TaskCreate(TaskBase):
    status: TaskStatus = "backlog"
    source: Optional[str] = "ui"
    dependency_ids: list[int] = Field(default_factory=list, max_length=100)


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    target: Optional[str] = None
    authorized_scope: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    execution_target: Optional[ExecutionTarget] = None
    model_config_id: Optional[int] = None
    token_budget: Optional[int] = Field(default=None, ge=0)
    assessment_id: Optional[int] = None
    assignee: Optional[str] = None
    result_summary: Optional[str] = None
    meta: Optional[dict] = None
    expected_version: Optional[int] = Field(default=None, ge=1)


class TaskMove(BaseModel):
    status: TaskStatus
    position: int = Field(..., ge=0)
    expected_version: Optional[int] = Field(default=None, ge=1)


class TaskDependenciesUpdate(BaseModel):
    dependency_ids: list[int] = Field(..., max_length=100)
    expected_version: Optional[int] = Field(default=None, ge=1)


class TaskEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    event_type: str
    payload: dict
    created_at: datetime


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    position: int
    version: int
    source: str
    phase: Optional[str] = None
    role: Optional[str] = None
    order_index: int = 0
    created_by: Optional[int] = None
    lease_owner: Optional[str] = None
    heartbeat_at: Optional[datetime] = None
    lease_expires_at: Optional[datetime] = None
    dependency_ids: list[int] = Field(default_factory=list)
    result_summary: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class BoardColumn(BaseModel):
    key: str
    tasks: list[TaskResponse]


class BoardResponse(BaseModel):
    columns: list[BoardColumn]
