"""
Main FastAPI application
"""
# Provision the JWT signing key BEFORE anything else imports auth/config so
# the application can never run with the hardcoded legacy default.
from bootstrap_secrets import ensure_secret_key
ensure_secret_key()

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from auth import get_current_user, require_admin, verify_mcp_api_key
from middleware.rbac import RBACMiddleware
from config import settings
from database import init_db
from api import assessments, cards, recon, sections, containers, folders, global_commands, search, system, credentials, websocket, workspace, pending_commands, context_documents, source_code, auth, reports, timeline, notifications, templates, users, api_keys, asvs_requirements
from api import commands
from api import ai_models, tasks, artifacts, knowledge, task_extras, takeover, submission, schedules, branding, scan_runs, scan_profiles
from api import audit as audit_api
from api import sso as sso_api
from api import host, nvd, appsec, git_integrations
from api.commands import global_router as commands_global_router
from mcp_http_app import handle_mcp_request, mcp_lifespan
from utils.logger import setup_logging, get_logger
from middleware.logging_middleware import LoggingMiddleware
from middleware.rate_limit import limiter, rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Setup structured logging
setup_logging(
    log_level=settings.LOG_LEVEL,
    log_format=settings.LOG_FORMAT,
    log_dir=settings.LOG_DIR,
    enable_file_logging=settings.LOG_FILE_ENABLED,
    enable_console_logging=settings.LOG_CONSOLE_ENABLED,
    max_bytes=settings.LOG_FILE_MAX_BYTES,
    backup_count=settings.LOG_FILE_BACKUP_COUNT
)

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: run migrations, start MCP session manager, yield."""
    init_db()
    # Seed built-in offensive-security methodology playbooks (idempotent).
    try:
        from database import SessionLocal
        from services.knowledge_service import KnowledgeService
        _db = SessionLocal()
        try:
            n = KnowledgeService(_db).seed_playbooks()
            if n:
                logger.info("Seeded knowledge playbooks", count=n)
            # Load the offensive-security skill base (skills/*/SKILL.md).
            from services.skills_loader import load_skills
            s = load_skills(_db)
            if s:
                logger.info("Loaded offensive-security skills", count=s)
        finally:
            _db.close()
    except Exception as e:
        logger.warning("Knowledge seeding failed (non-fatal)", error=str(e))
    logger.info(
        "Application started",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=settings.DATABASE_URL.split("@")[-1],
        workspace=settings.CONTAINER_WORKSPACE_BASE,
        log_level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT,
        cors_origins=settings.BACKEND_CORS_ORIGINS,
    )
    # The MCP HTTP transport needs its session-manager task group alive for
    # the lifetime of the app. The ``verify_mcp_api_key`` dependency gates
    # the actual endpoint behind a feature flag, so spinning this up
    # unconditionally is cheap and keeps the wiring simple.
    # Start the autonomous agent runner and the inbound Telegram bot. Both are
    # gated at runtime by platform settings (agent_runner_enabled /
    # telegram_bot_enabled + a configured token), so spinning them up is cheap.
    from services.agent.runner import runner as agent_runner
    from services.telegram import telegram_bot
    from services.scheduler import scheduler as engagement_scheduler
    from services.nvd_scheduler import nvd_scheduler
    async with mcp_lifespan():
        from services.appsec_worker import appsec_worker
        appsec_worker.start()
        agent_runner.start()
        telegram_bot.start()
        engagement_scheduler.start()
        nvd_scheduler.start()
        try:
            yield
        finally:
            await appsec_worker.stop()
            await agent_runner.stop()
            await telegram_bot.stop()
            await engagement_scheduler.stop()
            await nvd_scheduler.stop()


# Disable the interactive API docs (Swagger UI, ReDoc and the OpenAPI schema)
# outside of development so the full API surface is not exposed publicly when
# the backend is reachable through the reverse proxy (e.g. ``--domain`` mode).
# DEBUG=true can force them back on for troubleshooting a production build.
_docs_enabled = settings.ENVIRONMENT != "production" or settings.DEBUG

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.PROJECT_TAGLINE,
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# RBAC (E2): role enforcement for every /api route; resolved user is stashed
# on request.state for the auth dependency to reuse. Added AFTER the rate
# limiter so limits still apply, BEFORE logging/CORS so denials are visible.
app.add_middleware(RBACMiddleware)

# Configure logging middleware (before CORS)
app.add_middleware(LoggingMiddleware)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Routers requiring an authenticated user. Applied at include time so any new
# router added here is protected by default — impossible to forget.
protected = [Depends(get_current_user)]

# Public routers (auth itself, websocket — token validated inside the handler).
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(websocket.router, prefix=settings.API_V1_PREFIX)

# Protected routers
app.include_router(git_integrations.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(appsec.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(assessments.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(cards.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(cards.global_router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(asvs_requirements.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(asvs_requirements.catalog_router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(recon.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(commands.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(commands_global_router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(credentials.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(global_commands.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(search.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(system.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(sections.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(containers.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(folders.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(workspace.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(pending_commands.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(pending_commands.settings_router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(context_documents.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(source_code.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(reports.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(timeline.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(templates.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(api_keys.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(ai_models.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(tasks.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(artifacts.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(knowledge.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(task_extras.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(takeover.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(submission.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(schedules.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(scan_runs.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(scan_runs.assessment_router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(scan_profiles.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(branding.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
# Audit trail — RBAC middleware restricts /api/audit* to admins.
app.include_router(audit_api.router, prefix=settings.API_V1_PREFIX)
app.include_router(sso_api.router, prefix=settings.API_V1_PREFIX)
app.include_router(nvd.router, prefix=settings.API_V1_PREFIX, dependencies=protected)
app.include_router(host.router, prefix=settings.API_V1_PREFIX, dependencies=protected)

# Admin-only router
app.include_router(
    users.router,
    prefix=settings.API_V1_PREFIX,
    dependencies=[Depends(require_admin)],
)


# --- MCP HTTP (Streamable HTTP) ------------------------------------------
# Gated by ``verify_mcp_api_key`` which enforces:
#   - feature flag (platform_settings.mcp_http_enabled)
#   - network policy (localhost / lan / any)
#   - bearer API key validation
# Streamable-HTTP uses POST for client→server messages, GET for the SSE
# stream clients open to receive server-initiated events, and DELETE to
# terminate the session.
@app.api_route(
    "/mcp",
    methods=["GET", "POST", "DELETE"],
    dependencies=[Depends(verify_mcp_api_key)],
    include_in_schema=False,
)
async def mcp_endpoint(request: Request):
    return await handle_mcp_request(request)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"{settings.PROJECT_NAME} API",
        "tagline": settings.PROJECT_TAGLINE,
        "version": settings.VERSION,
        "docs": "/docs" if _docs_enabled else None,
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/metrics")
async def metrics():
    """Prometheus scrape endpoint (see services/metrics.py).

    Unauthenticated like /health — keep it behind the edge in production.
    """
    from services.metrics import render

    body, content_type = render()
    return Response(content=body, media_type=content_type)
