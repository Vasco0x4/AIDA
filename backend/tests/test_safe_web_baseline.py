"""Real, bounded HTTP checks for the safe_web_baseline Scan Profile."""
from __future__ import annotations

import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from models.assessment import Assessment
from models.card import Card
from models.task import Task
from services.agent.scope import ScopeViolation, parse_scope
from services.scanning.safe_web import SafeHttpClient, SafeWebBaseline


class LabHandler(BaseHTTPRequestHandler):
    debug_enabled = True
    debug_status = 200
    redirect_target = "http://169.254.169.254/latest/meta-data"

    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", self.redirect_target)
            self.end_headers()
            return
        if self.path == "/debug" and self.debug_enabled:
            body = b"AIDA-E2E-CANARY: debug console exposed"
        elif self.path == "/":
            debug_link = b'<a href="/debug">debug</a>' if self.debug_enabled else b""
            body = b"<html><title>Isolated lab</title>" + debug_link + b"</html>"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(self.debug_status if self.path == "/debug" else 200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Server", "AIDA-Isolated-Lab/1.0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def lab():
    server = ThreadingHTTPServer(("127.0.0.1", 0), LabHandler)
    LabHandler.debug_enabled = True
    LabHandler.debug_status = 200
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


async def test_safe_http_denies_redirects(lab):
    client = SafeHttpClient(parse_scope("127.0.0.1"), timeout=2, max_response_bytes=10000)
    with pytest.raises(ScopeViolation, match="redirect"):
        await client.get(lab + "/redirect")


async def test_safe_http_denies_out_of_scope_before_connecting(lab):
    client = SafeHttpClient(parse_scope("example.com"), timeout=2, max_response_bytes=10000)
    with pytest.raises(ScopeViolation, match="out_of_scope"):
        await client.get(lab)


async def test_safe_http_enforces_response_cap(lab):
    client = SafeHttpClient(parse_scope("127.0.0.1"), timeout=2, max_response_bytes=10)
    with pytest.raises(ValueError, match="response too large"):
        await client.get(lab)


async def test_baseline_discovers_real_findings_and_remediation(db, lab):
    assessment = Assessment(name="Local HTTP lab", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    def run(title):
        task = Task(title=title, target=lab, authorized_scope="127.0.0.1",
                    assessment_id=assessment.id, status="running", orchestrate=False)
        db.add(task)
        db.commit()
        db.refresh(task)
        return task

    first = run("baseline 1")
    scanner = SafeWebBaseline(db, first, rate_limit_seconds=0, max_pages=4)
    summary1 = await scanner.run()
    assert summary1["requests"] >= 2
    assert summary1["findings"] >= 2
    titles = {row.title for row in db.query(Card).all()}
    assert "Exposed debug console" in titles
    assert "Missing Content-Security-Policy" in titles
    debug = db.query(Card).filter(Card.title == "Exposed debug console").one()
    assert "AIDA-E2E-CANARY" in debug.proof

    second = run("baseline 2")
    summary2 = await SafeWebBaseline(db, second, rate_limit_seconds=0, max_pages=4).run()
    assert summary2["recurring"] == summary1["findings"]
    assert summary2["new"] == 0
    assert db.query(Card).filter(Card.title == "Exposed debug console").count() == 1

    LabHandler.debug_enabled = False
    third = run("baseline 3")
    summary3 = await SafeWebBaseline(db, third, rate_limit_seconds=0, max_pages=4).run()
    # Every finding unique to the removed endpoint is remediated, including
    # its missing-security-header observations, not only the debug card.
    assert summary3["remediated"] >= 1
    assert debug.lifecycle_status == "remediated"

    LabHandler.debug_enabled = True
    fourth = run("baseline 4")
    summary4 = await SafeWebBaseline(db, fourth, rate_limit_seconds=0, max_pages=4).run()
    assert summary4["reopened"] >= 1
    assert debug.lifecycle_status == "reopened"
    assert db.query(Card).count() == summary1["findings"]


async def test_runtime_executes_safe_profile_without_ai_credentials(
    db, lab, monkeypatch, runtime_sessions,
):
    from services.agent.runtime import TaskRuntime
    import services.agent.runtime as runtime
    monkeypatch.setattr(runtime, "SessionLocal", runtime_sessions)

    assessment = Assessment(name="Runtime safe profile", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    task = Task(title="Runtime baseline", target=lab, authorized_scope="127.0.0.1",
                assessment_id=assessment.id, status="queued", orchestrate=False,
                meta={"scan_profile": "safe_web_baseline", "rate_limit_seconds": 0})
    db.add(task)
    db.commit()
    db.refresh(task)

    await TaskRuntime(task.id).run()
    db.refresh(task)
    assert task.status == "needs_review"
    assert task.started_at is not None and task.completed_at is not None
    assert task.meta["scan_summary"]["findings"] >= 2
    assert task.meta["finding_diff"]["summary"]["new"] >= 2
    assert "requests" in task.result_summary


async def test_http_failure_is_partial_not_remediated(db, lab):
    assessment = Assessment(name="Partial run lab", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    async def scan(name):
        task = Task(title=name, target=lab, authorized_scope="127.0.0.1",
                    assessment_id=assessment.id, status="running", orchestrate=False)
        db.add(task)
        db.commit()
        db.refresh(task)
        return await SafeWebBaseline(db, task, rate_limit_seconds=0).run()

    await scan("complete baseline")
    LabHandler.debug_status = 500
    partial = await scan("partial repeat")
    assert partial["complete"] is False
    assert partial["partial"] is True
    assert partial["remediated"] == 0


async def test_scheduler_runtime_recurring_remediation_and_reopen_e2e(
    db, lab, monkeypatch, runtime_sessions,
):
    """Schedule → queued Task → runtime → real HTTP → canonical finding diff."""
    import services.agent.runtime as runtime
    from models.scheduled_engagement import ScheduledEngagement
    from models.task import TaskEvent
    from services.agent.runtime import TaskRuntime
    from services.scheduler import EngagementScheduler

    monkeypatch.setattr(runtime, "SessionLocal", runtime_sessions)
    assessment = Assessment(name="Recurring E2E lab", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    engagement = ScheduledEngagement(
        name="Isolated recurring E2E", cron="0 3 * * *", task_title="Recurring safe baseline",
        target=lab, authorized_scope="127.0.0.1", assessment_id=assessment.id,
        scan_profile="safe_web_baseline", orchestrate=False, enabled=True,
        rate_limit_seconds=1, authorization_confirmed=True,
        authorization_reference="Test-owned in-process lab",
        next_run_at=datetime(2026, 11, 6, 3, 0),
    )
    db.add(engagement)
    db.commit()
    db.refresh(engagement)

    runs = []
    summaries = []
    for index in range(4):
        LabHandler.debug_enabled = index != 2
        task = await EngagementScheduler().fire(db, engagement, datetime(2026, 11, 6, 3, index))
        assert task is not None
        await TaskRuntime(task.id).run()
        db.expire_all()
        task = db.get(Task, task.id)
        runs.append(task)
        summaries.append(task.meta["scan_summary"])
        assert task.status == "needs_review"
        assert task.assessment_id == assessment.id
        assert task.meta["scheduled"].get("previous_task_id") == (runs[-2].id if index > 0 else None)

    assert summaries[0]["new"] == summaries[0]["findings"]
    assert summaries[1]["recurring"] == summaries[0]["findings"]
    assert summaries[1]["new"] == 0
    assert summaries[2]["remediated"] >= 1
    assert summaries[3]["reopened"] >= 1
    assert db.query(Assessment).count() == 1
    assert db.query(Card).count() == summaries[0]["findings"]
    assert db.query(Task).filter(Task.assessment_id == assessment.id).count() == 4
    assert db.query(TaskEvent).count() >= 4
    assert sum(len(task.meta.get("log", [])) for task in runs) >= 12
