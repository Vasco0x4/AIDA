"""Reusable Scan Profiles feed bounded policy into scheduled Scan Runs."""
from __future__ import annotations

from datetime import datetime

from models.assessment import Assessment
from models.scheduled_engagement import ScheduledEngagement
from services.scheduler import EngagementScheduler


async def test_saved_profile_crud_and_schedule_snapshot(client, db, admin_headers, viewer_headers):
    assessment = Assessment(name="Profile lab", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    payload = {
        "name": "Careful local baseline", "kind": "safe_web_baseline",
        "description": "Non-destructive GET-only checks", "rate_limit_seconds": 3,
        "max_pages": 4, "max_response_bytes": 250000, "timeout_seconds": 4,
    }
    denied = client.post("/api/scan-profiles", headers=viewer_headers, json=payload)
    assert denied.status_code == 403
    created = client.post("/api/scan-profiles", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["max_pages"] == 4
    assert client.post("/api/scan-profiles", headers=admin_headers, json=payload).status_code == 409

    scheduled = client.post("/api/schedules", headers=admin_headers, json={
        "name": "Profile-backed nightly", "cron": "0 3 * * *", "task_title": "Profile run",
        "target": "http://127.0.0.1:3000", "authorized_scope": "127.0.0.1",
        "assessment_id": assessment.id, "scan_profile_id": profile["id"],
        "scan_profile": "safe_web_baseline", "orchestrate": False,
        "authorization_confirmed": True, "authorization_reference": "Owned isolated lab",
    })
    assert scheduled.status_code == 201, scheduled.text
    assert scheduled.json()["scan_profile_id"] == profile["id"]

    engagement = db.query(ScheduledEngagement).one()
    task = await fire(engagement, db)
    assert task.meta["scan_profile"] == "safe_web_baseline"
    assert task.meta["rate_limit_seconds"] == 3
    assert task.meta["max_pages"] == 4
    assert task.meta["max_response_bytes"] == 250000
    assert task.meta["timeout_seconds"] == 4


async def fire(engagement, db):
    return await EngagementScheduler().fire(db, engagement, datetime(2026, 8, 17, 3, 0))
