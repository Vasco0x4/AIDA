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
        # Orchestration fields on tasks (parent audit → ordered sub-tasks)
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS parent_task_id INTEGER",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS orchestrate BOOLEAN DEFAULT TRUE",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS phase VARCHAR(30)",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS role VARCHAR(60)",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS order_index INTEGER DEFAULT 0",
        # E3 reliability: per-task token budget (NULL → platform default)
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS token_budget INTEGER",
        # Reliable Kanban: optimistic writes, durable worker leases and DAG edges
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS lease_owner VARCHAR(255)",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS lease_token VARCHAR(64)",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP",
        "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMP",
        ("CREATE INDEX IF NOT EXISTS tasks_claim_idx ON tasks(status, position, id) "
         "WHERE status = 'queued'"),
        ("CREATE INDEX IF NOT EXISTS tasks_stale_lease_idx ON tasks(lease_expires_at) "
         "WHERE status = 'running' AND lease_expires_at IS NOT NULL"),
        ("CREATE INDEX IF NOT EXISTS task_dependencies_task_idx "
         "ON task_dependencies(task_id)"),
        ("CREATE INDEX IF NOT EXISTS task_events_task_idx "
         "ON task_events(task_id, id)"),
        # E3 evidence hash chain on artifacts
        "ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS hash_prev VARCHAR(64)",
        "ALTER TABLE artifacts ADD COLUMN IF NOT EXISTS hash_self VARCHAR(64)",
        # E4 PoC approval chain: exploit-class commands are flagged at creation
        "ALTER TABLE pending_commands ADD COLUMN IF NOT EXISTS risk_level VARCHAR(20) DEFAULT 'normal'",
        "ALTER TABLE pending_commands ADD COLUMN IF NOT EXISTS risk_reason VARCHAR(100)",
        # E4 compliance mapping (manual override of the auto-classifier)
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS compliance_refs JSONB",
        # Recurring Scan Runs adopt one existing Assessment; safe per-schedule
        # execution policy is persisted with the schedule template.
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS assessment_id INTEGER REFERENCES assessments(id) ON DELETE SET NULL",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'UTC'",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS scan_profile VARCHAR(40) NOT NULL DEFAULT 'autonomous'",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS rate_limit_seconds INTEGER NOT NULL DEFAULT 60",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS max_concurrency INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS last_error TEXT",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS authorization_reference TEXT",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS authorization_confirmed BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE scheduled_engagements ADD COLUMN IF NOT EXISTS scan_profile_id INTEGER REFERENCES scan_profiles(id) ON DELETE SET NULL",
        "CREATE INDEX IF NOT EXISTS scheduled_engagements_assessment_idx ON scheduled_engagements(assessment_id)",
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS fingerprint VARCHAR(64)",
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(40) NOT NULL DEFAULT 'new'",
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS first_seen_run_id INTEGER",
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS last_seen_run_id INTEGER",
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMP",
        "ALTER TABLE cards ADD COLUMN IF NOT EXISTS seen_count INTEGER NOT NULL DEFAULT 0",
        "CREATE UNIQUE INDEX IF NOT EXISTS cards_assessment_fingerprint_idx ON cards(assessment_id, fingerprint)",
        "CREATE INDEX IF NOT EXISTS cards_lifecycle_status_idx ON cards(lifecycle_status)",
        # Full-text search index for the knowledge base (fast, well-ranked search
        # over 20k+ entries). Expression must match KnowledgeService.FTS_EXPR.
        ("CREATE INDEX IF NOT EXISTS knowledge_fts_idx ON knowledge_entries USING gin "
         "(to_tsvector('english', coalesce(title,'') || ' ' || coalesce(tags,'') "
         "|| ' ' || coalesce(description,'')))"),
        # Optional per-user TOTP. OIDC-only accounts can reauthenticate through
        # their verified SSO session instead of an unusable local password.
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) NOT NULL DEFAULT 'local'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_enabled BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_secret_encrypted TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_pending_secret_encrypted TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS otp_last_timestep BIGINT",
        # E2 RBAC: migrate the legacy two-role model to the three-role one.
        # "user" and "auditor" are operationally equivalent.
        "UPDATE users SET role = 'auditor' WHERE role = 'user'",
    ]
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
    except Exception as e:
        # Non-fatal: a fresh DB already has these via create_all.
        logger.warning("_ensure_columns failed (non-fatal)", error=str(e))
