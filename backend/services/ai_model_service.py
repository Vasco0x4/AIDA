"""
Service layer for AI model provider configs.

Handles encryption of API keys, single-default enforcement, and building a
ready-to-use LLMClient from a stored config.
"""
from typing import Optional

from sqlalchemy.orm import Session

from models.ai_model_config import AIModelConfig
from services.llm import LLMClient, resolve_base_url, LLMError
from utils.crypto import encrypt_secret, decrypt_secret
from utils.logger import get_logger

logger = get_logger(__name__)


class AIModelService:
    def __init__(self, db: Session):
        self.db = db

    # --- queries -----------------------------------------------------------
    def list_configs(self) -> list[AIModelConfig]:
        return (
            self.db.query(AIModelConfig)
            .order_by(AIModelConfig.is_default.desc(), AIModelConfig.name.asc())
            .all()
        )

    def get(self, config_id: int) -> Optional[AIModelConfig]:
        return self.db.query(AIModelConfig).filter(AIModelConfig.id == config_id).first()

    def get_by_name(self, name: str) -> Optional[AIModelConfig]:
        return self.db.query(AIModelConfig).filter(AIModelConfig.name == name).first()

    def get_default(self) -> Optional[AIModelConfig]:
        row = (
            self.db.query(AIModelConfig)
            .filter(AIModelConfig.is_default == True, AIModelConfig.enabled == True)  # noqa: E712
            .first()
        )
        if row:
            return row
        # Fall back to any enabled config.
        return (
            self.db.query(AIModelConfig)
            .filter(AIModelConfig.enabled == True)  # noqa: E712
            .order_by(AIModelConfig.id.asc())
            .first()
        )

    # --- mutations ---------------------------------------------------------
    def create(
        self,
        *,
        name: str,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        enabled: bool = True,
        is_default: bool = False,
        params: Optional[dict] = None,
    ) -> AIModelConfig:
        resolved_base = resolve_base_url(provider, base_url)
        row = AIModelConfig(
            name=name,
            provider=provider,
            base_url=resolved_base,
            model=model,
            api_key_encrypted=encrypt_secret(api_key) if api_key else None,
            enabled=enabled,
            is_default=is_default,
            params=params or {},
        )
        self.db.add(row)
        self.db.flush()
        if is_default:
            self._clear_other_defaults(row.id)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, config_id: int, **fields) -> Optional[AIModelConfig]:
        row = self.get(config_id)
        if not row:
            return None

        if "provider" in fields or "base_url" in fields:
            provider = fields.get("provider", row.provider)
            base_url = fields.get("base_url", None)
            # Only re-resolve when provider changes or an explicit base_url given.
            if "provider" in fields or base_url:
                row.base_url = resolve_base_url(provider, base_url or (None if "base_url" in fields else row.base_url))
            if "provider" in fields:
                row.provider = provider

        for key in ("name", "model", "enabled", "params"):
            if key in fields and fields[key] is not None:
                setattr(row, key, fields[key])

        # API key: only overwrite when a non-empty value is supplied.
        if fields.get("api_key"):
            row.api_key_encrypted = encrypt_secret(fields["api_key"])

        if fields.get("is_default"):
            row.is_default = True
            self.db.flush()
            self._clear_other_defaults(row.id)
        elif fields.get("is_default") is False:
            row.is_default = False

        self.db.commit()
        self.db.refresh(row)
        return row

    def delete(self, config_id: int) -> bool:
        row = self.get(config_id)
        if not row:
            return False
        self.db.delete(row)
        self.db.commit()
        return True

    def _clear_other_defaults(self, keep_id: int) -> None:
        self.db.query(AIModelConfig).filter(
            AIModelConfig.id != keep_id, AIModelConfig.is_default == True  # noqa: E712
        ).update({AIModelConfig.is_default: False})
        self.db.commit()

    # --- client ------------------------------------------------------------
    def build_client(self, row: AIModelConfig) -> LLMClient:
        api_key = decrypt_secret(row.api_key_encrypted) if row.api_key_encrypted else ""
        params = row.params or {}
        return LLMClient(
            base_url=row.base_url,
            api_key=api_key,
            model=row.model,
            provider=row.provider,
            extra_headers=params.get("extra_headers"),
        )

    async def test(self, row: AIModelConfig) -> dict:
        if not row.api_key_encrypted:
            return {"ok": False, "message": "No API key configured", "latency_ms": 0}
        try:
            client = self.build_client(row)
            temperature = (row.params or {}).get("temperature", 0.2)
            return await client.test_connection(temperature=temperature)
        except LLMError as e:
            return {"ok": False, "message": str(e), "latency_ms": 0}
