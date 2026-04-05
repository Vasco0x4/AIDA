"""
Database connection and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from config import settings

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
    except Exception:
        pass

    # Always run create_all to pick up new models not yet in migrations.
    # create_all is safe: it only creates tables that don't already exist.
    Base.metadata.create_all(bind=engine)
