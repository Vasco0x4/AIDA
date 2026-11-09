"""
Integration tests for AI model provider configs (api/ai_models.py).

CRUD + presets + connectivity test endpoint. API keys are write-only: the
plaintext must never appear in any response (only a masked hint). The /test
happy path is exercised with the LLM client's test_connection mocked — no
network in tests.
"""
from __future__ import annotations

import pytest

from middleware.rate_limit import limiter
from models.ai_model_config import AIModelConfig


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def make_model(db):
    def _make(name="m1", provider="openrouter", model="some/model",
              api_key=None, is_default=False, enabled=True) -> AIModelConfig:
        from utils.crypto import encrypt_secret
        row = AIModelConfig(name=name, provider=provider, model=model,
                            base_url="https://openrouter.ai/api/v1",
                            api_key_encrypted=encrypt_secret(api_key) if api_key else None,
                            enabled=enabled, is_default=is_default, params={})
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    return _make


def test_models_are_admin_only(client, db, viewer_headers):
    assert client.get("/api/ai-models", headers=viewer_headers).status_code == 403
    assert client.post("/api/ai-models", headers=viewer_headers,
                       json={"name": "x", "model": "y"}).status_code == 403


def test_list_presets(client, db, admin_headers):
    r = client.get("/api/ai-models/presets", headers=admin_headers)
    assert r.status_code == 200
    presets = {p["key"]: p for p in r.json()}
    assert "openrouter" in presets
    assert "custom" in presets
    assert presets["openrouter"]["base_url"].startswith("https://")
    assert presets["custom"]["supports_tools"] is True


def test_create_model_hides_api_key(client, db, admin_headers):
    r = client.post("/api/ai-models", headers=admin_headers, json={
        "name": "kimi-prod", "provider": "openrouter",
        "model": "moonshotai/kimi-k2", "api_key": "sk-supersecret-value"})
    assert r.status_code == 201
    body = r.json()
    assert body["has_api_key"] is True
    assert body["api_key_masked"].endswith("alue")  # last 4 chars visible
    # The plaintext key never appears anywhere in the payload
    assert "sk-supersecret-value" not in r.text

    row = db.query(AIModelConfig).filter(AIModelConfig.name == "kimi-prod").one()
    assert row.api_key_encrypted.startswith("enc::")
    assert "sk-supersecret-value" not in row.api_key_encrypted


def test_create_model_resolves_base_url_from_preset(client, db, admin_headers):
    r = client.post("/api/ai-models", headers=admin_headers, json={
        "name": "glm", "provider": "zhipu", "model": "glm-4.6"})
    assert r.status_code == 201
    assert r.json()["base_url"]  # resolved from the preset, not empty
    assert r.json()["api_key_masked"] is None
    assert r.json()["has_api_key"] is False


def test_create_model_duplicate_name(client, db, admin_headers, make_model):
    make_model(name="dup")
    r = client.post("/api/ai-models", headers=admin_headers,
                    json={"name": "dup", "provider": "openrouter", "model": "m"})
    assert r.status_code == 409


def test_create_model_unknown_provider(client, db, admin_headers):
    r = client.post("/api/ai-models", headers=admin_headers,
                    json={"name": "bad", "provider": "nope", "model": "m"})
    assert r.status_code == 422


def test_create_custom_provider_requires_base_url(client, db, admin_headers):
    r = client.post("/api/ai-models", headers=admin_headers,
                    json={"name": "selfhost", "provider": "custom", "model": "m"})
    assert r.status_code == 422

    r = client.post("/api/ai-models", headers=admin_headers, json={
        "name": "selfhost2", "provider": "custom", "model": "m",
        "base_url": "http://llm.internal:8000/v1"})
    assert r.status_code == 201
    assert r.json()["base_url"] == "http://llm.internal:8000/v1"


def test_get_model(client, db, admin_headers, make_model):
    row = make_model(name="getme")
    assert client.get("/api/ai-models/9999",
                      headers=admin_headers).status_code == 404
    r = client.get(f"/api/ai-models/{row.id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "getme"


def test_list_models_orders_default_first(client, db, admin_headers, make_model):
    make_model(name="zz-default", is_default=True)
    make_model(name="aa-plain")
    r = client.get("/api/ai-models", headers=admin_headers)
    names = [m["name"] for m in r.json()]
    assert names[0] == "zz-default"
    assert set(names) == {"zz-default", "aa-plain"}


def test_update_model_fields(client, db, admin_headers, make_model):
    row = make_model(name="updateme", api_key=None)
    r = client.put(f"/api/ai-models/{row.id}", headers=admin_headers,
                   json={"model": "new/model", "enabled": False, "api_key": "sk-fresh"})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "new/model"
    assert body["enabled"] is False
    assert body["has_api_key"] is True

    assert client.put("/api/ai-models/9999", headers=admin_headers,
                      json={"enabled": True}).status_code == 404
    assert client.put(f"/api/ai-models/{row.id}", headers=admin_headers,
                      json={"provider": "nope"}).status_code == 422


def test_update_default_switches_exclusivity(client, db, admin_headers, make_model):
    first = make_model(name="first", is_default=True)
    second = make_model(name="second")
    r = client.put(f"/api/ai-models/{second.id}", headers=admin_headers,
                   json={"is_default": True})
    assert r.status_code == 200
    db.refresh(first)
    db.refresh(second)
    assert second.is_default is True
    assert first.is_default is False  # exactly one default


def test_delete_model(client, db, admin_headers, make_model):
    row = make_model(name="deleteme")
    assert client.delete(f"/api/ai-models/{row.id}",
                         headers=admin_headers).status_code == 204
    assert db.query(AIModelConfig).count() == 0
    assert client.delete(f"/api/ai-models/{row.id}",
                         headers=admin_headers).status_code == 404


def test_test_model_without_key(client, db, admin_headers, make_model):
    row = make_model(name="keyless")
    r = client.post(f"/api/ai-models/{row.id}/test", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "No API key" in body["message"]


def test_test_model_with_key(client, db, admin_headers, make_model, monkeypatch):
    row = make_model(name="keyed", api_key="sk-x")

    async def fake_test_connection(self, temperature=0.2):
        return {"ok": True, "message": "connected", "latency_ms": 7, "model_count": 12}

    from services.llm.provider import LLMClient
    monkeypatch.setattr(LLMClient, "test_connection", fake_test_connection)
    r = client.post(f"/api/ai-models/{row.id}/test", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["latency_ms"] == 7
    assert body["model_count"] == 12


def test_test_model_llm_error(client, db, admin_headers, make_model, monkeypatch):
    row = make_model(name="err", api_key="sk-x")

    async def boom(self, temperature=0.2):
        from services.llm import LLMError
        raise LLMError("dns failure")

    from services.llm.provider import LLMClient
    monkeypatch.setattr(LLMClient, "test_connection", boom)
    r = client.post(f"/api/ai-models/{row.id}/test", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert "dns failure" in r.json()["message"]


def test_test_model_unknown_id(client, db, admin_headers):
    assert client.post("/api/ai-models/4242/test",
                       headers=admin_headers).status_code == 404
