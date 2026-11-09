"""
Configuration for AIDA - AI-Driven Security Assessment
"""
import os
from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

    # Application Metadata
    PROJECT_NAME: str = "AIDA"
    PROJECT_TAGLINE: str = "AI-Driven Security Assessment"
    PROJECT_DESCRIPTION: str = "Intelligent autonomous penetration testing powered by AI"
    VERSION: str = "1.1.0"
    API_V1_PREFIX: str = "/api"

    # Database Credentials
    POSTGRES_USER: str = "aida"
    POSTGRES_PASSWORD: str = "aida"
    POSTGRES_DB: str = "aida_assessments"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"

    # Database URL (will be constructed in validator if not provided)
    DATABASE_URL: Optional[str] = None

    # CORS — explicit list of allowed origins. The wildcard "*" is rejected
    # at startup because it is incompatible with allow_credentials=True per
    # the CORS spec (browsers silently drop the response).
    BACKEND_CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Container Configuration
    CONTAINER_WORKSPACE_BASE: str = "/workspace"
    DEFAULT_CONTAINER_NAME: str = "aida-pentest"
    # Comma-separated list of accepted container name prefixes.
    # Both aida- (new) and exegol- (legacy) are accepted for backward compat.
    CONTAINER_PREFIX_FILTER: str = "aida-,exegol-"
    COMMAND_TIMEOUT: int = 300  # seconds (5 minutes default)

    # Upload size limits (bytes). Surfaced as MB in the Settings UI and used as
    # the default when no platform_settings row overrides them.
    MAX_CONTEXT_FILE_SIZE: int = 10 * 1024 * 1024   # 10 MB per /context file
    MAX_SOURCE_ZIP_SIZE: int = 100 * 1024 * 1024    # 100 MB per /source ZIP

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or console
    LOG_DIR: str = "logs"
    LOG_FILE_ENABLED: bool = True
    LOG_CONSOLE_ENABLED: bool = True
    LOG_FILE_MAX_BYTES: int = 10485760  # 10MB
    LOG_FILE_BACKUP_COUNT: int = 5

    # Backend API URL (for MCP server)
    BACKEND_API_URL: str = "http://localhost:8000/api"

    # Authentication (JWT). The signing key is provisioned by
    # bootstrap_secrets.ensure_secret_key() and read directly from the
    # environment by auth.py — never from here — so there is no hardcoded
    # default to leak.
    SECRET_KEY: Optional[str] = None
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Environment
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    @field_validator('DATABASE_URL', mode='before')
    @classmethod
    def construct_database_url(cls, v: Optional[str], values) -> str:
        """Construct DATABASE_URL from components if not provided"""
        if v:
            return v

        # Get values from environment or defaults
        user = os.getenv("POSTGRES_USER", "aida")
        password = os.getenv("POSTGRES_PASSWORD", "aida")
        host = os.getenv("POSTGRES_HOST", "localhost")
        port = os.getenv("POSTGRES_PORT", "5432")
        db = os.getenv("POSTGRES_DB", "aida_assessments")

        # Kubernetes injects docker-link-style service env vars: a Service
        # named "postgres" in the namespace sets POSTGRES_PORT to
        # "tcp://<cluster-ip>:5432". Strip down to the bare port number.
        if port.startswith("tcp://"):
            port = port.rsplit(":", 1)[-1]

        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @field_validator('BACKEND_CORS_ORIGINS', mode='after')
    @classmethod
    def parse_cors_origins(cls, v) -> list[str]:
        """Parse CORS origins from a comma-separated string to a list.

        Wildcard "*" is rejected: combined with allow_credentials=True it
        violates the CORS spec and browsers refuse to send credentials.
        """
        if isinstance(v, list):
            origins = v
        else:
            if v.strip() == "*":
                raise ValueError(
                    'BACKEND_CORS_ORIGINS="*" is not allowed with credentials. '
                    'Set an explicit comma-separated list, e.g. '
                    '"http://localhost:5173,http://127.0.0.1:5173".'
                )
            origins = [origin.strip() for origin in v.split(",") if origin.strip()]
        if not origins:
            raise ValueError("BACKEND_CORS_ORIGINS must contain at least one origin")
        return origins

    @field_validator('LOG_FILE_ENABLED', 'LOG_CONSOLE_ENABLED', 'DEBUG', mode='before')
    @classmethod
    def parse_bool(cls, v):
        """Parse boolean from string"""
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
