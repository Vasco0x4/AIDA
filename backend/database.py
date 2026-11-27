"""
Database connection and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Sync engine (legacy compatibility)
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

# Async engine for improved performance
async_database_url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(
    async_database_url,
    pool_pre_ping=True,
    echo=False
)

# Session factories
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI routes to get database session (sync)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """
    Dependency for FastAPI routes to get async database session
    """
    async with AsyncSessionLocal() as session:
        yield session


def init_db():
    """
    Initialize database via Alembic migrations, then ensure any new
    models not yet covered by migrations are created via create_all().
    """
    try:
        from alembic.config import Config
        from alembic import command
        import os

        # Locate alembic.ini relative to this file
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        alembic_ini = os.path.join(backend_dir, "alembic.ini")

        if os.path.exists(alembic_ini):
            alembic_cfg = Config(alembic_ini)
            alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
            alembic_cfg.set_main_option("sqlalchemy.url", str(settings.DATABASE_URL))
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        # Non-fatal: create_all() below still provisions the schema, but a real
        # migration/permission error should be visible rather than swallowed.
        logger.warning("Alembic upgrade failed; falling back to create_all", error=str(e))

    # Always run create_all to pick up new models not yet in migrations.
    # create_all is safe: it only creates tables that don't already exist.
    Base.metadata.create_all(bind=engine)

    # create_all does NOT add new columns to pre-existing tables. Ensure simple
    # column additions exist via idempotent ADD COLUMN IF NOT EXISTS (no migration
    # files needed, matching project convention).
    _ensure_columns()


def _ensure_columns():
    """Idempotently add simple new columns to existing tables (Postgres)."""
    from sqlalchemy import text

    statements = [
        # ASVS methodology fields on assessments
        "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS methodology VARCHAR(50) DEFAULT 'standard'",
        "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS asvs_level INTEGER",
        "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS asvs_version VARCHAR(20)",
        # Binds an MCP API key to one assessment (agent keys from `aida run`)
        "ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS assessment_id INTEGER"
        " REFERENCES assessments(id) ON DELETE CASCADE",
    ]
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except Exception as e:
        # Non-fatal: a fresh DB already has these via create_all.
        logger.warning("_ensure_columns failed (non-fatal)", error=str(e))
