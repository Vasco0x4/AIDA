"""
Prometheus metrics for the platform (E1 observability).

Counters are incremented where the action happens (LLM client, agent runtime);
the task-board gauges are computed on scrape from the database so they can
never drift from the source of truth.

Expose via GET /metrics (see main.py). Note: like /health, the endpoint is
unauthenticated — put it behind your edge (or scrape the container port) and
keep it off the public internet in production.
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

LLM_CALLS = Counter(
    "aida_llm_calls_total",
    "LLM chat completions by provider/model",
    ["provider", "model"],
)
LLM_ERRORS = Counter(
    "aida_llm_errors_total",
    "LLM call failures",
    ["provider", "model"],
)
LLM_TOKENS = Counter(
    "aida_llm_tokens_total",
    "LLM tokens consumed",
    ["provider", "model", "kind"],  # kind: prompt | completion
)
AGENT_STEPS = Counter(
    "aida_agent_steps_total",
    "Agent loop steps by kind",
    ["kind"],
)
TASKS_BY_STATUS = Gauge(
    "aida_tasks_by_status",
    "Tasks currently in each Kanban column",
    ["status"],
)
TASK_CLAIMS = Counter(
    "aida_task_claims_total", "Atomic task claims by agent workers")
TASK_RECOVERIES = Counter(
    "aida_task_recoveries_total", "Tasks fenced and returned to the queue", ["reason"])
TASK_RETRIES = Counter(
    "aida_task_retries_total", "Task retries by operator or crash policy", ["trigger"])
NVD_REFRESHES = Counter(
    "aida_nvd_refreshes_total", "NVD refresh outcomes", ["result"])
HOST_EXECUTIONS = Counter(
    "aida_host_executions_total", "Direct host execution outcomes", ["result"])
WORKER_ACTIVE = Gauge("aida_agent_workers_active", "Agent jobs currently running")
TASK_ATTEMPTS = Counter(
    "aida_task_attempts_total", "Finished agent attempts by persisted task status", ["status"])
TASK_DURATION = Histogram(
    "aida_task_attempt_duration_seconds", "Agent attempt latency",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600, 14400, 86400))
NVD_CACHE_AGE = Gauge("aida_nvd_cache_age_seconds", "Age of the last successful NVD refresh")
NVD_CACHED_ITEMS = Gauge("aida_nvd_cached_items", "Items in the current NVD cache window")
HOST_DURATION = Histogram(
    "aida_host_execution_duration_seconds", "Direct host operation latency", ["result"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 5, 15, 30, 60, 120, 300, 600))


def collect_task_gauges() -> None:
    """Refresh the board gauges from the DB (called on each /metrics scrape)."""
    from sqlalchemy import func

    from database import SessionLocal
    from models.task import Task, TASK_COLUMNS

    db = None
    try:
        db = SessionLocal()
        counts = dict.fromkeys(TASK_COLUMNS, 0)
        for status, n in db.query(Task.status, func.count(Task.id)) \
                .group_by(Task.status).all():
            counts[status] = n
        for status, n in counts.items():
            TASKS_BY_STATUS.labels(status=status).set(n)
        from datetime import datetime, timezone
        from models.nvd import NVDDigestState
        nvd = db.get(NVDDigestState, 1)
        if nvd and nvd.last_success_at:
            last_success = nvd.last_success_at
            if last_success.tzinfo is None:
                last_success = last_success.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - last_success).total_seconds()
            NVD_CACHE_AGE.set(max(0, age))
            NVD_CACHED_ITEMS.set(nvd.item_count or 0)
        else:
            NVD_CACHE_AGE.set(-1)
            NVD_CACHED_ITEMS.set(0)
    except Exception:
        pass  # metrics must never break the app (not even on connect failure)
    finally:
        if db is not None:
            db.close()


def render() -> tuple[bytes, str]:
    collect_task_gauges()
    return generate_latest(), CONTENT_TYPE_LATEST
