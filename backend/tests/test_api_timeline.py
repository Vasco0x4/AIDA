"""
Integration tests for the attack timeline (api/timeline.py +
services/timeline_service.py): manual events, listing with filters and
linked-entity enrichment, deletion, and auto-generation from
commands / findings / recon data (idempotent).
"""
from __future__ import annotations

import pytest

from middleware.rate_limit import limiter
from models.assessment import Assessment
from models.card import Card
from models.command_history import CommandHistory
from models.recon_data import ReconData
from models.timeline_event import TimelineEvent


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def assessment(db) -> Assessment:
    a = Assessment(name="tl-assessment", scope="127.0.0.1", status="active")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _event_payload(**overrides) -> dict:
    payload = {"phase": "recon", "event_type": "manual", "title": "Kickoff",
               "description": "scope agreed", "severity": "INFO",
               "icon": "flag", "tags": "start"}
    payload.update(overrides)
    return payload


def _command(db, assessment_id, command="nmap -sV target", phase=None):
    row = CommandHistory(assessment_id=assessment_id, command=command,
                         success=True, returncode=0, phase=phase)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- manual events ------------------------------------------------------------------

def test_create_and_list_event(client, db, admin_headers, assessment):
    r = client.post(f"/api/assessments/{assessment.id}/timeline",
                    headers=admin_headers, json=_event_payload())
    assert r.status_code == 201
    body = r.json()
    assert body["assessment_id"] == assessment.id
    assert body["title"] == "Kickoff"
    assert body["created_at"]

    r = client.get(f"/api/assessments/{assessment.id}/timeline",
                   headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["phases"] == {"recon": 1}
    assert data["events"][0]["tags"] == "start"


def test_create_event_validation(client, db, admin_headers, assessment):
    bad = _event_payload()
    del bad["title"]
    assert client.post(f"/api/assessments/{assessment.id}/timeline",
                       headers=admin_headers, json=bad).status_code == 422


def test_list_filters(client, db, admin_headers, assessment):
    for i, phase in enumerate(["recon", "recon", "exploitation"]):
        client.post(f"/api/assessments/{assessment.id}/timeline",
                    headers=admin_headers,
                    json=_event_payload(title=f"e{i}", phase=phase,
                                        event_type="manual" if i else "command"))

    base = f"/api/assessments/{assessment.id}/timeline"
    assert client.get(base, headers=admin_headers,
                      params={"phase": "recon"}).json()["total"] == 2
    assert client.get(base, headers=admin_headers,
                      params={"event_type": "command"}).json()["total"] == 1
    assert client.get(base, headers=admin_headers,
                      params={"phase": "reporting"}).json()["total"] == 0
    assert client.get(base, headers=admin_headers,
                      params={"limit": 2}).json()["total"] == 2
    assert client.get(base, headers=admin_headers,
                      params={"limit": 0}).status_code == 422
    assert client.get(base, headers=admin_headers,
                      params={"limit": 1001}).status_code == 422


def test_list_linked_entity_enrichment(client, db, admin_headers, assessment):
    cmd = _command(db, assessment.id, command="nmap " + "-v " * 60)
    card = Card(assessment_id=assessment.id, card_type="finding",
                title="SQLi in login", severity="CRITICAL")
    recon = ReconData(assessment_id=assessment.id, data_type="subdomain",
                      name="api.target.example")
    db.add_all([card, recon])
    db.commit()
    db.refresh(card)
    db.refresh(recon)

    client.post(f"/api/assessments/{assessment.id}/timeline",
                headers=admin_headers,
                json=_event_payload(title="cmd", event_type="command",
                                    command_id=cmd.id))
    client.post(f"/api/assessments/{assessment.id}/timeline",
                headers=admin_headers,
                json=_event_payload(title="finding", event_type="finding",
                                    card_id=card.id, phase="exploitation"))
    client.post(f"/api/assessments/{assessment.id}/timeline",
                headers=admin_headers,
                json=_event_payload(title="recon", event_type="recon",
                                    recon_id=recon.id))

    events = {e["title"]: e for e in client.get(
        f"/api/assessments/{assessment.id}/timeline",
        headers=admin_headers).json()["events"]}
    assert events["cmd"]["command_text"].startswith("nmap")
    assert len(events["cmd"]["command_text"]) <= 100
    assert events["finding"]["card_title"] == "SQLi in login"
    assert events["recon"]["recon_name"] == "api.target.example"


def test_delete_event(client, db, admin_headers, assessment):
    created = client.post(f"/api/assessments/{assessment.id}/timeline",
                          headers=admin_headers,
                          json=_event_payload()).json()
    assert client.delete(
        f"/api/assessments/{assessment.id}/timeline/{created['id']}",
        headers=admin_headers).status_code == 204
    assert db.query(TimelineEvent).count() == 0
    assert client.delete(
        f"/api/assessments/{assessment.id}/timeline/{created['id']}",
        headers=admin_headers).status_code == 404


def test_writes_require_auditor(client, db, viewer_headers, assessment):
    assert client.post(f"/api/assessments/{assessment.id}/timeline",
                       headers=viewer_headers,
                       json=_event_payload()).status_code == 403
    assert client.get(f"/api/assessments/{assessment.id}/timeline",
                      headers=viewer_headers).status_code == 200


# --- auto-generation -------------------------------------------------------------------

def test_auto_generate_from_all_sources(client, db, admin_headers, assessment):
    _command(db, assessment.id, "nmap -sV target")            # → recon
    _command(db, assessment.id, "sqlmap -u http://t/?id=1")   # → exploitation
    card = Card(assessment_id=assessment.id, card_type="finding",
                title="RCE", severity="CRITICAL")             # → exploitation
    recon = ReconData(assessment_id=assessment.id, data_type="endpoint",
                      name="/api/v1/users")
    db.add_all([card, recon])
    db.commit()

    r = client.post(f"/api/assessments/{assessment.id}/timeline/auto-generate",
                    headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["generated"] == 4
    assert "Generated 4" in body["message"]

    phases = client.get(f"/api/assessments/{assessment.id}/timeline",
                        headers=admin_headers).json()["phases"]
    # nmap→recon, sqlmap→exploitation, CRITICAL finding→exploitation,
    # recon-data item→recon
    assert phases == {"recon": 2, "exploitation": 2}

    # Idempotent: nothing new on a second pass
    r2 = client.post(f"/api/assessments/{assessment.id}/timeline/auto-generate",
                     headers=admin_headers)
    assert r2.json() == {"generated": 0, "message": "No new events to generate"}


def test_auto_generate_respects_stored_phase(client, db, admin_headers, assessment):
    _command(db, assessment.id, "nmap -sV target", phase="reporting")
    client.post(f"/api/assessments/{assessment.id}/timeline/auto-generate",
                headers=admin_headers)
    events = client.get(f"/api/assessments/{assessment.id}/timeline",
                        headers=admin_headers).json()["events"]
    assert events[0]["phase"] == "reporting"  # stored phase wins over guess


def test_auto_generate_empty_assessment(client, db, admin_headers, assessment):
    r = client.post(f"/api/assessments/{assessment.id}/timeline/auto-generate",
                    headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["generated"] == 0
