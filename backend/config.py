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
    VERSION: str = "1.0.0-alpha"
    API_V1_PREFIX: str = "/api"

    # Database Credentials
    POSTGRES_USER: str = "aida"
    POSTGRES_PASSWORD: str = "aida"
    POSTGRES_DB: str = "aida_assessments"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5434"

    # Database URL (will be constructed in validator if not provided)
    DATABASE_URL: Optional[str] = None

    # CORS - Allow all origins for development (use specific origins in production)
    # For production, set BACKEND_CORS_ORIGINS in .env to specific origins
    BACKEND_CORS_ORIGINS: str = "*"

    # Container Configuration
    CONTAINER_WORKSPACE_BASE: str = "/workspace"
    DEFAULT_CONTAINER_NAME: str = "aida-test-pentest"
    # Comma-separated list of accepted container name prefixes.
    # Both aida- (new) and exegol- (legacy) are accepted for backward compat.
    CONTAINER_PREFIX_FILTER: str = "aida-,exegol-"
    COMMAND_TIMEOUT: int = 300  # seconds (5 minutes default)

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or console
    LOG_DIR: str = "logs"
    LOG_FILE_ENABLED: bool = True
    LOG_CONSOLE_ENABLED: bool = True
    LOG_FILE_MAX_BYTES: int = 10485760  # 10MB
    LOG_FILE_BACKUP_COUNT: int = 5

    # Backend API URL (for MCP server)
    BACKEND_API_URL: str = "http://localhost:8001/api"

    # Authentication (JWT)
    SECRET_KEY: str = "aida-test-secret-key-change-in-production-min-32-chars!"
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
        port = os.getenv("POSTGRES_PORT", "5434")
        db = os.getenv("POSTGRES_DB", "aida_assessments")

        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    @field_validator('BACKEND_CORS_ORIGINS', mode='after')
    @classmethod
    def parse_cors_origins(cls, v: str) -> list[str]:
        """Parse CORS origins from comma-separated string to list"""
        if isinstance(v, list):
            return v
        # Handle wildcard
        if v.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in v.split(",") if origin.strip()]

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


settings = Settings()
