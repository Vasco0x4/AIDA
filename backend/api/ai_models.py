"""
AI model provider config API.

CRUD over configured model backends (OpenRouter / Kimi / GLM / OpenAI / …) plus
a connectivity /test endpoint. API keys are write-only: accepted on create/update,
never returned (only a masked hint).
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from models.ai_model_config import AIModelConfig
from schemas.ai_model import (
    AIModelCreate,
    AIModelUpdate,
    AIModelResponse,
    AIModelTestResponse,
    ProviderPreset,
)
from services.audit_service import record as audit
from services.ai_model_service import AIModelService
from services.llm import PROVIDER_PRESETS, LLMError
from utils.crypto import decrypt_secret, mask_secret

router = APIRouter(prefix="/ai-models", tags=["ai-models"])


def _to_response(row: AIModelConfig) -> AIModelResponse:
    masked = None
    if row.api_key_encrypted:
        try:
            masked = mask_secret(decrypt_secret(row.api_key_encrypted))
        except Exception:
            masked = "…"
    return AIModelResponse(
        id=row.id,
        name=row.name,
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        enabled=row.enabled,
        is_default=row.is_default,
        params=row.params or {},
        api_key_masked=masked,
        has_api_key=bool(row.api_key_encrypted),
    )


@router.get("/presets", response_model=List[ProviderPreset])
def list_presets():
    """List provider presets (base URLs + example models) for the UI."""
    return [
        ProviderPreset(
            key=key,
            label=p["label"],
            base_url=p["base_url"],
            example_model=p["example_model"],
            supports_tools=p["supports_tools"],
        )
        for key, p in PROVIDER_PRESETS.items()
    ]


@router.get("", response_model=List[AIModelResponse])
def list_models(db: Session = Depends(get_db)):
    service = AIModelService(db)
    return [_to_response(r) for r in service.list_configs()]


@router.get("/{config_id}", response_model=AIModelResponse)
def get_model(config_id: int, db: Session = Depends(get_db)):
    service = AIModelService(db)
    row = service.get(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model config not found")
    return _to_response(row)


@router.post("", response_model=AIModelResponse, status_code=201)
def create_model(body: AIModelCreate, request: Request, db: Session = Depends(get_db)):
    service = AIModelService(db)
    if service.get_by_name(body.name):
        raise HTTPException(status_code=409, detail=f"'{body.name}' already exists")
    if body.provider not in PROVIDER_PRESETS:
        raise HTTPException(status_code=422, detail=f"Unknown provider '{body.provider}'")
    try:
        row = service.create(
            name=body.name,
            provider=body.provider,
            model=body.model,
            api_key=body.api_key,
            base_url=body.base_url,
            enabled=body.enabled,
            is_default=body.is_default,
            params=body.params,
        )
    except LLMError as e:
        raise HTTPException(status_code=422, detail=str(e))
    audit(db, action="model.created", request=request, resource_type="ai_model",
          resource_id=row.id, detail={"name": row.name, "provider": row.provider})
    return _to_response(row)


@router.put("/{config_id}", response_model=AIModelResponse)
def update_model(config_id: int, body: AIModelUpdate, request: Request, db: Session = Depends(get_db)):
    service = AIModelService(db)
    if body.provider and body.provider not in PROVIDER_PRESETS:
        raise HTTPException(status_code=422, detail=f"Unknown provider '{body.provider}'")
    try:
        row = service.update(config_id, **body.model_dump(exclude_unset=True))
    except LLMError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not row:
        raise HTTPException(status_code=404, detail="Model config not found")
    audit(db, action="model.updated", request=request, resource_type="ai_model",
          resource_id=config_id, detail={"fields": sorted(body.model_dump(exclude_unset=True))})
    return _to_response(row)


@router.delete("/{config_id}", status_code=204)
def delete_model(config_id: int, request: Request, db: Session = Depends(get_db)):
    service = AIModelService(db)
    if not service.delete(config_id):
        raise HTTPException(status_code=404, detail="Model config not found")
    audit(db, action="model.deleted", request=request, resource_type="ai_model", resource_id=config_id)


@router.post("/{config_id}/test", response_model=AIModelTestResponse)
async def test_model(config_id: int, db: Session = Depends(get_db)):
    service = AIModelService(db)
    row = service.get(config_id)
    if not row:
        raise HTTPException(status_code=404, detail="Model config not found")
    result = await service.test(row)
    return AIModelTestResponse(**result)
