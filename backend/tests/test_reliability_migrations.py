"""Idempotent reliability-schema migration checks against real PostgreSQL."""
from __future__ import annotations

from sqlalchemy import text

import database
from services.task_service import TaskService


def test_reliability_schema_ensure_is_idempotent_and_preserves_tasks(
        db, engine, monkeypatch):
    row = TaskService(db).create(
        title="survives reliability migration",
        status="queued",
        authorized_scope="127.0.0.1",
        orchestrate=False,
    )
    # Release the ORM session's post-refresh read transaction; PostgreSQL DDL
    # cannot acquire the table lock while that session remains idle-in-transaction.
    db.rollback()
    monkeypatch.setattr(database, "engine", engine)

    # Startup can run this on every process restart and on a legacy database.
    database._ensure_columns()
    database._ensure_columns()

    with engine.connect() as conn:
        columns = {
            value for (value,) in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'tasks'"
            ))
        }
        indexes = {
            value for (value,) in conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'tasks'"
            ))
        }

    assert {
        "version", "lease_owner", "lease_token", "heartbeat_at", "lease_expires_at",
    } <= columns
    assert {"tasks_claim_idx", "tasks_stale_lease_idx"} <= indexes
    db.expire_all()
    persisted = TaskService(db).get(row.id)
    assert persisted is not None
    assert persisted.title == "survives reliability migration"
    assert persisted.status == "queued"
