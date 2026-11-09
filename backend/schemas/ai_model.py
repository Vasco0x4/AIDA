"""Pydantic schemas for AI model provider configs."""
from typing import Optional, Any
from pydantic import BaseModel, Field


class AIModelBase(BaseModel):
    name: str = Field(..., max_length=120)
    provider: str = Field("openrouter", max_length=40)
    model: str = Field(..., max_length=160)
    base_url: Optional[str] = Field(None, max_length=255)
    enabled: bool = True
    is_default: bool = False
    params: dict[str, Any] = Field(default_factory=dict)


class AIModelCreate(AIModelBase):
    # Plaintext key on the way in; stored encrypted, never returned.
    api_key: Optional[str] = None


class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    params: Optional[dict[str, Any]] = None
    api_key: Optional[str] = None


class AIModelResponse(BaseModel):
    id: int
    name: str
    provider: str
    model: str
    base_url: str
    enabled: bool
    is_default: bool
    params: dict[str, Any]
    # Masked, never the real key.
    api_key_masked: Optional[str] = None
    has_api_key: bool = False

    class Config:
        from_attributes = True


class AIModelTestResponse(BaseModel):
    ok: bool
    message: str
    latency_ms: int = 0
    model_count: Optional[int] = None


class ProviderPreset(BaseModel):
    key: str
    label: str
    base_url: str
    example_model: str
    supports_tools: bool
