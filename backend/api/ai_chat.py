"""
AI Chat API - Allows running AI-driven scans from the web UI.
Uses Anthropic Claude API with tool definitions matching MCP tools.
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from database import get_db, get_async_db
from models import Assessment, PlatformSettings
from services.ai_chat_service import AIChatService
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai-chat"])


class ChatRequest(BaseModel):
    assessment_id: int
    message: str
    # Optional: override model
    model: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: list = []
    error: Optional[str] = None


class AIKeyUpdate(BaseModel):
    api_key: str
    provider: str = "anthropic"  # anthropic, openai


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    req: ChatRequest,
    db: Session = Depends(get_db),
    async_db: AsyncSession = Depends(get_async_db),
):
    """Send a message to AI with assessment context. AI can execute tools."""
    # Check API key
    key_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "ai_api_key"
    ).first()

    if not key_setting or not key_setting.value:
        raise HTTPException(
            status_code=400,
            detail="AI API key not configured. Go to Settings > AI to set it up."
        )

    # Verify assessment exists
    assessment = db.query(Assessment).filter(Assessment.id == req.assessment_id).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    # Get provider
    provider_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "ai_provider"
    ).first()
    provider = provider_setting.value if provider_setting else "anthropic"

    service = AIChatService(
        api_key=key_setting.value,
        provider=provider,
        db=db,
        async_db=async_db,
    )

    try:
        result = await service.chat(
            assessment_id=req.assessment_id,
            assessment_name=assessment.name,
            message=req.message,
            model=req.model,
        )
        return ChatResponse(**result)
    except Exception as e:
        logger.error("AI chat error", error=str(e))
        return ChatResponse(response="", error=str(e))


@router.get("/config")
def get_ai_config(db: Session = Depends(get_db)):
    """Get AI configuration (key masked)"""
    key_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "ai_api_key"
    ).first()
    provider_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "ai_provider"
    ).first()

    has_key = bool(key_setting and key_setting.value)
    masked = ""
    if has_key:
        val = key_setting.value
        masked = val[:8] + "..." + val[-4:] if len(val) > 12 else "****"

    return {
        "has_key": has_key,
        "masked_key": masked,
        "provider": provider_setting.value if provider_setting else "anthropic",
    }


@router.put("/config")
def update_ai_config(body: AIKeyUpdate, db: Session = Depends(get_db)):
    """Save AI API key and provider"""
    # Upsert api key
    key_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "ai_api_key"
    ).first()
    if key_setting:
        key_setting.value = body.api_key
    else:
        db.add(PlatformSettings(key="ai_api_key", value=body.api_key))

    # Upsert provider
    prov_setting = db.query(PlatformSettings).filter(
        PlatformSettings.key == "ai_provider"
    ).first()
    if prov_setting:
        prov_setting.value = body.provider
    else:
        db.add(PlatformSettings(key="ai_provider", value=body.provider))

    db.commit()
    return {"status": "ok", "provider": body.provider}


@router.delete("/config")
def delete_ai_config(db: Session = Depends(get_db)):
    """Remove AI API key"""
    db.query(PlatformSettings).filter(
        PlatformSettings.key.in_(["ai_api_key", "ai_provider"])
    ).delete(synchronize_session=False)
    db.commit()
    return {"status": "ok"}
