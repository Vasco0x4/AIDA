"""Scheduler integration for the persistent NVD refresh policy."""
from __future__ import annotations

import pytest

from services.nvd_service import NVDService


@pytest.fixture()
def scheduler(monkeypatch, runtime_sessions):
    from services import nvd_scheduler as module
    sessions = []

    def factory():
        session = runtime_sessions()
        original_close = session.close

        def close():
            session.closed_for_test = True
            original_close()

        session.close = close
        sessions.append(session)
        return session

    monkeypatch.setattr(module, "SessionLocal", factory)
    instance = module.NVDScheduler()
    instance.test_sessions = sessions
    return instance


async def test_tick_uses_a_fresh_session_and_persistent_due_policy(
        db, scheduler, monkeypatch):
    NVDService(db, api_key=None).update_schedule(enabled=True)
    calls = []

    def refresh(self):
        calls.append(self.db)
        return self.get_digest()

    monkeypatch.setattr(NVDService, "refresh_if_due", refresh)
    await scheduler.tick()

    assert len(calls) == 1
    assert calls[0] is not db
    assert scheduler.test_sessions[0].closed_for_test is True


async def test_tick_logs_and_contains_refresh_failures(db, scheduler, monkeypatch):
    def fail(self):
        raise RuntimeError("NVD unavailable")

    monkeypatch.setattr(NVDService, "refresh_if_due", fail)
    # A single failed tick must not terminate the application or its scheduler.
    await scheduler.tick()
