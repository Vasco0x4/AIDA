"""
Main FastAPI application
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db
from api import assessments, cards, recon, sections, containers, folders, global_commands, search, system, credentials, websocket, workspace, pending_commands, context_documents, source_code, auth, reports, timeline, notifications, templates
from api import commands
from api.commands import global_router as commands_global_router
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

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=settings.PROJECT_TAGLINE
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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

# Include routers
app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(assessments.router, prefix=settings.API_V1_PREFIX)
app.include_router(cards.router, prefix=settings.API_V1_PREFIX)
app.include_router(recon.router, prefix=settings.API_V1_PREFIX)
app.include_router(commands.router, prefix=settings.API_V1_PREFIX)
app.include_router(commands_global_router, prefix=settings.API_V1_PREFIX)  # Global commands view
app.include_router(credentials.router, prefix=settings.API_V1_PREFIX)
app.include_router(global_commands.router, prefix=settings.API_V1_PREFIX)
app.include_router(search.router, prefix=settings.API_V1_PREFIX)
app.include_router(system.router, prefix=settings.API_V1_PREFIX)
app.include_router(sections.router, prefix=settings.API_V1_PREFIX)
app.include_router(containers.router, prefix=settings.API_V1_PREFIX)
app.include_router(folders.router, prefix=settings.API_V1_PREFIX)
app.include_router(workspace.router, prefix=settings.API_V1_PREFIX)
app.include_router(websocket.router, prefix=settings.API_V1_PREFIX)
app.include_router(pending_commands.router, prefix=settings.API_V1_PREFIX)  # Pending commands
app.include_router(pending_commands.settings_router, prefix=settings.API_V1_PREFIX)  # Command settings
app.include_router(context_documents.router, prefix=settings.API_V1_PREFIX)  # Context documents
app.include_router(source_code.router, prefix=settings.API_V1_PREFIX)  # Source code import
app.include_router(reports.router, prefix=settings.API_V1_PREFIX)  # PDF report generation
app.include_router(timeline.router, prefix=settings.API_V1_PREFIX)  # Attack timeline
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)  # Notifications
app.include_router(templates.router, prefix=settings.API_V1_PREFIX)  # Assessment templates


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
    logger.info(
        "Application started",
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=settings.DATABASE_URL.split("@")[-1],  # Hide credentials
        workspace=settings.CONTAINER_WORKSPACE_BASE,
        log_level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": f"{settings.PROJECT_NAME} API",
        "tagline": settings.PROJECT_TAGLINE,
        "version": settings.VERSION,
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}
