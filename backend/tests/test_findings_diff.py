"""
E4 findings-diff tests — the recurring-audit regression view: new / fixed /
persistent classification, severity drift, false-positive exclusion and the
(title, target) identity normalization that makes run-over-run matching work.
"""
from __future__ import annotations

import pytest

from models.assessment import Assessment
from models.card import Card
from services.findings_diff import diff_assessments


def _asmt(db, name):
    row = Assessment(name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _finding(db, assessment_id, title, *, severity="HIGH", status="confirmed",
             target="https://app.example.com", card_type="finding"):
    row = Card(assessment_id=assessment_id, card_type=card_type, title=title,
               severity=severity, status=status, target_service=target)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@pytest.fixture()
def pair(db):
    old = _asmt(db, "audit-round-1")
    new = _asmt(db, "audit-round-2")
    return old, new


def test_new_fixed_persistent(db, pair):
    old, new = pair
    _finding(db, old.id, "SQL Injection in /search")          # persists
    _finding(db, old.id, "Directory listing on /backup")      # gets fixed
    _finding(db, new.id, "SQL Injection in /search")          # persists
    _finding(db, new.id, "Reflected XSS in ?q")               # newly found

    out = diff_assessments(db, old.id, new.id)

    assert out["summary"] == {"total_old": 2, "total_new": 2, "new": 1,
                              "fixed": 1, "persistent": 1, "severity_changed": 0}
    assert [f["title"] for f in out["new"]] == ["Reflected XSS in ?q"]
    assert [f["title"] for f in out["fixed"]] == ["Directory listing on /backup"]
    assert [p["new"]["title"] for p in out["persistent"]] == ["SQL Injection in /search"]
    assert out["old_assessment"]["id"] == old.id
    assert out["new_assessment"]["id"] == new.id


def test_severity_and_status_change_flags(db, pair):
    old, new = pair
    _finding(db, old.id, "Weak TLS configuration", severity="MEDIUM")
    _finding(db, new.id, "Weak TLS configuration", severity="HIGH",
             status="potential")

    p = diff_assessments(db, old.id, new.id)["persistent"][0]
    assert p["severity_changed"] is True
    assert p["old_severity"] == "MEDIUM"
    assert p["new_severity"] == "HIGH"
    assert p["status_changed"] is True
    assert diff_assessments(db, old.id, new.id)["summary"]["severity_changed"] == 1


def test_false_positives_excluded_from_both_sides(db, pair):
    old, new = pair
    # Dismissed in the old round → not a "fixed" finding.
    _finding(db, old.id, "Banner disclosure", status="false_positive")
    # Dismissed in the new round → not a "new" finding.
    _finding(db, new.id, "Cookie without Secure flag", status="false_positive")

    out = diff_assessments(db, old.id, new.id)
    assert out["summary"]["total_old"] == 0
    assert out["summary"]["total_new"] == 0
    assert out["summary"]["fixed"] == 0
    assert out["summary"]["new"] == 0


def test_identity_is_normalized_title_and_target(db, pair):
    old, new = pair
    _finding(db, old.id, "  SQL   injection in /SEARCH ", severity="HIGH",
             target="https://app.example.com")
    _finding(db, new.id, "sql injection in /search", severity="HIGH",
             target="HTTPS://APP.EXAMPLE.COM")

    out = diff_assessments(db, old.id, new.id)
    assert out["summary"]["new"] == 0
    assert out["summary"]["fixed"] == 0
    assert out["summary"]["persistent"] == 1


def test_missing_target_service_matches_empty(db, pair):
    old, new = pair
    _finding(db, old.id, "Open S3 bucket", target=None)
    _finding(db, new.id, "Open S3 bucket", target="")
    assert diff_assessments(db, old.id, new.id)["summary"]["persistent"] == 1


def test_non_finding_cards_ignored(db, pair):
    old, new = pair
    _finding(db, old.id, "Observation note", card_type="observation")
    _finding(db, new.id, "Info note", card_type="info")
    out = diff_assessments(db, old.id, new.id)
    assert out["summary"]["total_old"] == 0
    assert out["summary"]["total_new"] == 0


def test_new_findings_sorted_by_severity(db, pair):
    old, new = pair
    for title, sev in (("Low noise", "LOW"), ("Critical RCE", "CRITICAL"),
                       ("Medium issue", "MEDIUM")):
        _finding(db, new.id, title, severity=sev)

    titles = [f["title"] for f in diff_assessments(db, old.id, new.id)["new"]]
    assert titles == ["Critical RCE", "Medium issue", "Low noise"]


def test_self_diff_is_all_persistent(db, pair):
    old, _ = pair
    _finding(db, old.id, "SQL Injection in /search")
    out = diff_assessments(db, old.id, old.id)
    assert out["summary"]["new"] == 0
    assert out["summary"]["fixed"] == 0
    assert out["summary"]["persistent"] == 1
