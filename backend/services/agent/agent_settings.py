"""
Agent platform settings, shared by the runner pool and the runtime.

Kept in its own module so both can import it without an import cycle, with a
short TTL cache so 8 worker polls don't turn into 8 setting queries per tick.
The API calls ``invalidate_settings_cache()`` after changing an agent_* key so
a new concurrency/budget applies immediately.
"""
from __future__ import annotations

import time

from database import SessionLocal
from models.platform_settings import PlatformSettings
from utils.logger import get_logger

logger = get_logger(__name__)

_settings_cache: dict[str, tuple[float, str]] = {}
_SETTINGS_TTL = 10.0

# Keys the AgentOps UI may set (validated centrally, see api/tasks.py).
AGENT_SETTING_KEYS = (
    "agent_runner_enabled",
    "agent_max_concurrency",
    "agent_max_steps",
    "agent_target_min_interval",
    "agent_token_budget",
    "model_fallback_chain",
    "agent_goal_mode",
    "agent_max_auto_continuations",
    "agent_goal_judge_max_cont",
)


def get_setting(key: str, default: str) -> str:
    """Read a platform setting with a short TTL cache (default when unset)."""
    cached = _settings_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _SETTINGS_TTL:
        return cached[1]
    db = SessionLocal()
    try:
        row = (db.query(PlatformSettings)
               .filter(PlatformSettings.key == key).first())
        value = row.value if row else default
    except Exception:
        value = default
    finally:
        db.close()
    _settings_cache[key] = (now, value)
    return value


def int_setting(key: str, default: int) -> int:
    try:
        return int(get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default


def bool_setting(key: str, default: bool) -> bool:
    """Read a boolean platform setting (truthy spellings match the inline
    parsing the runner and the API already use)."""
    raw = get_setting(key, "true" if default else "false").strip().lower()
    return raw in ("true", "1", "yes", "on")


def invalidate_settings_cache() -> None:
    _settings_cache.clear()
