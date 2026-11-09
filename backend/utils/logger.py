"""
Structured logging configuration using structlog
Provides JSON-formatted logs for production and human-readable logs for development
"""
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any, Dict

import structlog
from structlog.types import EventDict, Processor

# Single source of truth for PII/secret masking (E2) — the same patterns the
# audit log uses. Only key-name matching lives here: values under
# obviously-named keys are suppressed wholesale, everything else goes through
# redact_text's shape-based patterns.
from utils.redact import redact_text as _redact_value


def add_severity_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Add severity level to log output (for compatibility with external systems)
    """
    if method_name == "debug":
        event_dict["severity"] = "DEBUG"
    elif method_name == "info":
        event_dict["severity"] = "INFO"
    elif method_name == "warning":
        event_dict["severity"] = "WARNING"
    elif method_name == "error":
        event_dict["severity"] = "ERROR"
    elif method_name == "critical":
        event_dict["severity"] = "CRITICAL"
    return event_dict


def filter_sensitive_data(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Filter sensitive data from logs (passwords, tokens, etc.)
    """
    sensitive_keys = [
        "password", "token", "secret", "api_key", "bearer",
        "authorization", "cookie", "csrf"
    ]

    def _filter_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively filter sensitive keys"""
        filtered = {}
        for key, value in d.items():
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                filtered[key] = "***REDACTED***"
            elif isinstance(value, dict):
                filtered[key] = _filter_dict(value)
            elif isinstance(value, list):
                filtered[key] = [
                    _filter_dict(item) if isinstance(item, dict)
                    else _redact_value(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            elif isinstance(value, str):
                filtered[key] = _redact_value(value)
            else:
                filtered[key] = value
        return filtered

    return _filter_dict(event_dict)


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_dir: str = "logs",
    enable_file_logging: bool = True,
    enable_console_logging: bool = True,
    max_bytes: int = 10485760,  # 10MB
    backup_count: int = 5
) -> None:
    """
    Configure structured logging for the application

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format (json or console)
        log_dir: Directory for log files
        enable_file_logging: Enable file output
        enable_console_logging: Enable console output
        max_bytes: Maximum size per log file
        backup_count: Number of backup files to keep
    """
    # Create log directory
    if enable_file_logging:
        log_path = Path(log_dir)
        log_path.mkdir(exist_ok=True)

    # When both file and console logging are disabled (e.g. MCP mode), silence all
    # output by replacing any handlers basicConfig would add with a NullHandler.
    # Without this, basicConfig unconditionally attaches a StreamHandler(stderr)
    # which leaks structured log lines into the terminal via Kimi Code CLI / Claude Code.
    if not enable_file_logging and not enable_console_logging:
        root_logger = logging.getLogger()
        root_logger.handlers = []
        root_logger.addHandler(logging.NullHandler())
        root_logger.setLevel(getattr(logging, log_level.upper()))
    else:
        # Configure stdlib logging
        # Use stderr for MCP compatibility (stdout is reserved for MCP JSON protocol)
        logging.basicConfig(
            format="%(message)s",
            stream=sys.stderr,
            level=getattr(logging, log_level.upper())
        )

    # Configure processors based on format
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        add_severity_level,
        filter_sensitive_data,
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure file handlers if enabled
    if enable_file_logging:
        root_logger = logging.getLogger()

        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Main application log (all levels)
        app_handler = logging.handlers.RotatingFileHandler(
            filename=Path(log_dir) / "app.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        app_handler.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(app_handler)

        # Error log (errors only)
        error_handler = logging.handlers.RotatingFileHandler(
            filename=Path(log_dir) / "error.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        root_logger.addHandler(error_handler)

        # Console handler if enabled (use stderr for MCP compatibility)
        if enable_console_logging:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(getattr(logging, log_level.upper()))
            root_logger.addHandler(console_handler)

    # Silence noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured structlog logger

    Example:
        logger = get_logger(__name__)
        logger.info("User created", user_id=123, username="john")
    """
    return structlog.get_logger(name)
