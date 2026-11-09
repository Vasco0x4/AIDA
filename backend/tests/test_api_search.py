"""Unified search router integration tests."""
from __future__ import annotations

from models.assessment import Assessment
from models.card import Card
from models.command_history import CommandHistory
from models.recon_data import ReconData


def make_assessment(db, name, client_name=None, category=None):
    a = Assessment(name=name, scope=f"{name} scope line", status="active",
                   client_name=client_name, category=category)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def seed_world(db):
    """One of each searchable entity, plus noise that must NOT match."""
    a = make_assessment(db, "Acme Web", client_name="Acme Corp", category="Website")
    noise = make_assessment(db, "Unrelated", client_name="Other Ltd")

    db.add(Card(assessment_id=a.id, card_type="finding", title="Acme SQL Injection",
                severity="CRITICAL", status="confirmed",
                technical_analysis="union select"))
    db.add(Card(assessment_id=a.id, card_type="observation",
                title="Acme verbose banner", severity="LOW", status="potential"))
    db.add(Card(assessment_id=noise.id, card_type="finding",
                title="Boring finding", severity="INFO", status="untested"))

    db.add(CommandHistory(assessment_id=a.id, command="nuclei -u https://acme.test",
                          stdout="acme matched", phase="recon", success=True,
                          status="completed"))
    db.add(CommandHistory(assessment_id=noise.id, command="whoami",
                          phase="enum", status="completed"))

    db.add(ReconData(assessment_id=a.id, data_type="subdomain", name="acme-api.test",
                     details={"ip": "1.2.3.4"}))
    db.add(ReconData(assessment_id=noise.id, data_type="endpoint", name="/healthz"))
    db.commit()
    return a, noise


# --- auth + validation ---------------------------------------------------------

def test_search_requires_token(client, db):
    assert client.get("/api/search", params={"q": "x"}).status_code == 401


def test_search_query_validation(client, db, admin_headers):
    assert client.get("/api/search", headers=admin_headers).status_code == 422
    assert client.get("/api/search", headers=admin_headers,
                      params={"q": ""}).status_code == 422
    assert client.get("/api/search", headers=admin_headers,
                      params={"q": "x", "limit": 0}).status_code == 422
    assert client.get("/api/search", headers=admin_headers,
                      params={"q": "x", "limit": 101}).status_code == 422


# --- happy paths ---------------------------------------------------------------

def test_search_across_entity_types(client, db, admin_headers):
    a, _noise = seed_world(db)

    r = client.get("/api/search", headers=admin_headers, params={"q": "acme"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "acme"
    assert body["total"] == len(body["results"]) > 0
    assert body["execution_time"] >= 0
    types = {res["type"] for res in body["results"]}
    assert {"assessment", "command", "finding", "observation", "recon"} <= types
    assert set(body["grouped"]) == types
    # every result mentions the query somewhere
    for res in body["results"]:
        blob = " ".join(filter(None, [res["title"], res["subtitle"],
                                      res["description"] or ""])).lower()
        assert "acme" in blob or "unrelated" not in blob


def test_search_no_match(client, db, admin_headers):
    seed_world(db)
    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "zzzznothing"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["results"] == []
    assert body["grouped"] == {}


def test_search_type_filter(client, db, admin_headers):
    seed_world(db)
    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "types": "assessment"})
    assert r.status_code == 200
    assert {res["type"] for res in r.json()["results"]} == {"assessment"}

    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "types": "finding,info"})
    assert {res["type"] for res in r.json()["results"]} == {"finding"}


def test_search_card_filters(client, db, admin_headers):
    a, _noise = seed_world(db)

    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "severity": "critical"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert results and all(res["type"] != "finding"
                           or res["metadata"]["severity"] == "CRITICAL" for res in results)
    assert not any(res["title"] == "Acme verbose banner" for res in results)

    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "status": "potential"})
    results = r.json()["results"]
    assert any(res["title"] == "Acme verbose banner" for res in results)
    assert not any(res["title"] == "Acme SQL Injection" for res in results)


def test_search_scoped_to_assessment(client, db, admin_headers):
    a, noise = seed_world(db)
    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "a", "assessment_id": noise.id, "limit": 100})
    assert r.status_code == 200
    for res in r.json()["results"]:
        assert noise.name in res["subtitle"] or a.name not in res["subtitle"]


def test_search_date_filters(client, db, admin_headers):
    seed_world(db)
    # everything is created "now": a future window keeps it, a past one drops it
    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "date_from": "2000-01-01T00:00:00",
                           "date_to": "2099-01-01T00:00:00"})
    assert r.json()["total"] > 0

    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "date_from": "2098-01-01T00:00:00"})
    assert r.json()["total"] == 0

    # malformed dates are ignored rather than rejected
    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "date_from": "not-a-date"})
    assert r.status_code == 200
    assert r.json()["total"] > 0


def test_search_limit(client, db, admin_headers):
    seed_world(db)
    r = client.get("/api/search", headers=admin_headers,
                   params={"q": "acme", "limit": 2})
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 2
