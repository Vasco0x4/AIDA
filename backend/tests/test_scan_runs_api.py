"""Operational Scan Run API: run history, evidence, diffs and controls."""
from __future__ import annotations

from models.assessment import Assessment
from models.task import Task
from services.finding_service import FindingService


def seed_run(db, assessment, title="run", status="done"):
    row = Task(title=title, target="http://127.0.0.1:3000", authorized_scope="127.0.0.1",
               assessment_id=assessment.id, status=status, orchestrate=False,
               meta={"scan_profile": "safe_web_baseline"})
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_scan_run_history_findings_diff_and_report(client, db, admin_headers, viewer_headers):
    assessment = Assessment(name="API lab", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    first = seed_run(db, assessment, "run one")
    second = seed_run(db, assessment, "run two <script>alert(1)</script>")
    service = FindingService(db)
    service.record(assessment.id, first.id, {
        "title": "Exposed debug console", "target_service": "http://127.0.0.1:3000/debug",
        "severity": "HIGH", "proof": "first evidence"})
    service.finalize_run(assessment.id, first.id)
    service.record(assessment.id, second.id, {
        "title": "Missing Content-Security-Policy", "target_service": "http://127.0.0.1:3000",
        "severity": "MEDIUM", "proof": "second evidence"})
    service.finalize_run(assessment.id, second.id)

    response = client.get(f"/api/scan-runs?assessment_id={assessment.id}&limit=1&skip=0",
                          headers=viewer_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1
    assert response.json()[0]["id"] == second.id

    findings = client.get(f"/api/scan-runs/{second.id}/findings", headers=viewer_headers)
    assert findings.status_code == 200
    assert findings.json()[0]["proof"] == "second evidence"
    assert findings.json()[0]["fingerprint"]

    diff = client.get(f"/api/scan-runs/{second.id}/diff", headers=viewer_headers)
    assert diff.status_code == 200
    assert diff.json()["summary"]["new"] == 1
    assert diff.json()["summary"]["remediated"] == 1

    events = client.get(f"/api/scan-runs/{second.id}/events?limit=10", headers=viewer_headers)
    assert events.status_code == 200
    assert isinstance(events.json(), list)

    assessment_runs = client.get(f"/api/assessments/{assessment.id}/runs", headers=viewer_headers)
    assert assessment_runs.status_code == 200
    assert len(assessment_runs.json()) == 2

    report = client.get(f"/api/scan-runs/{second.id}/report?format=html", headers=viewer_headers)
    assert report.status_code == 200
    assert "Missing Content-Security-Policy" in report.text
    assert "second evidence" in report.text
    assert "run two &lt;script&gt;alert(1)&lt;/script&gt;" in report.text
    assert "run two <script>" not in report.text


def test_scan_run_pause_resume_and_rbac(client, db, admin_headers, viewer_headers):
    assessment = Assessment(name="Controls", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    run = seed_run(db, assessment, "queued run", status="queued")

    denied = client.post(f"/api/scan-runs/{run.id}/pause", headers=viewer_headers)
    assert denied.status_code == 403
    paused = client.post(f"/api/scan-runs/{run.id}/pause", headers=admin_headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["meta"]["paused"] is True
    assert paused.json()["status"] == "queued"

    resumed = client.post(f"/api/scan-runs/{run.id}/resume", headers=admin_headers)
    assert resumed.status_code == 200
    assert resumed.json()["meta"]["paused"] is False


def test_scan_run_retry_requeues_terminal_run(client, db, admin_headers):
    assessment = Assessment(name="Retry", scope="127.0.0.1")
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    run = seed_run(db, assessment, "retry run", status="failed")
    response = client.post(f"/api/scan-runs/{run.id}/retry", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "queued"
