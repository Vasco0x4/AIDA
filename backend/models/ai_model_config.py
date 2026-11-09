"""
AI Model provider configuration.

Stores one row per configured model backend (OpenRouter, Moonshot/Kimi,
Zhipu/GLM, OpenAI, DeepSeek, or any OpenAI-compatible endpoint). The API key is
stored encrypted-at-rest (see utils.crypto). This is what lets the platform
itself reason, instead of only relaying to an external MCP client.
"""
from sqlalchemy import Column, Integer, String, Boolean, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from database import Base


class AIModelConfig(Base):
    __tablename__ = "ai_model_configs"

    id = Column(Integer, primary_key=True, index=True)

    # Human label, unique (e.g. "OpenRouter-Kimi", "GLM-prod").
    name = Column(String(120), nullable=False, unique=True, index=True)

    # Provider preset key: openrouter | moonshot | moonshot_cn | zhipu | openai
    #                      | deepseek | anthropic | custom
    provider = Column(String(40), nullable=False, default="openrouter")

    # Resolved OpenAI-compatible base URL (preset default, overridable).
    base_url = Column(String(255), nullable=False)

    # Model id as the provider expects it (e.g. "moonshotai/kimi-k2",
    # "z-ai/glm-4.6", "openai/gpt-4o", "deepseek-chat").
    model = Column(String(160), nullable=False)

    # Fernet-encrypted API key ("enc::..."). Never returned to clients.
    api_key_encrypted = Column(Text, nullable=True)

    enabled = Column(Boolean, default=True)
    # Exactly one row should be the default; enforced in the service layer.
    is_default = Column(Boolean, default=False)

    # Free-form knobs: {"temperature": 0.2, "max_tokens": 4096,
    #                   "extra_headers": {...}, "supports_tools": true}
    params = Column(JSONB, default={})

    created_at = Column(TIMESTAMP, server_default=func.now())
    updated_at = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
