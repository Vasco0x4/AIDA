"""
E2 — OIDC SSO unit tests: signed state, config round-trip (encrypted secret),
PKCE authorization URL, id_token verification against a local RSA key, and
JIT provisioning that never escalates an existing role.
"""
from __future__ import annotations

import base64
import time
import types
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import jwt as jose_jwt

import services.oidc_service as oidc
from models.platform_settings import PlatformSettings
from models.user import User
from services.oidc_service import OIDCError

ISSUER = "https://sso.example.com/realms/aida"
CLIENT_ID = "aida-client"


# --- state --------------------------------------------------------------------

def test_state_roundtrip_and_tamper():
    state = oidc._sign_state({"v": "verifier-1", "e": int(time.time()) + 60})
    assert oidc.load_state(state)["v"] == "verifier-1"
    # tampered payload/signature → rejected
    assert oidc.load_state(state[:-3] + "aaa") is None
    assert oidc.load_state("not-a-state") is None


def test_state_expiry():
    expired = oidc._sign_state({"v": "v", "e": int(time.time()) - 1})
    assert oidc.load_state(expired) is None


# --- configuration --------------------------------------------------------------

def test_config_roundtrip_secret_encrypted_at_rest(db):
    oidc.save_config(db, enabled=True, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret="s3cret-value", default_role="viewer",
                     redirect_base="http://localhost:5174")
    row = (db.query(PlatformSettings)
           .filter(PlatformSettings.key == "oidc_client_secret").one())
    assert row.value != "s3cret-value"          # never plaintext
    assert row.value.startswith("enc::")        # Fernet envelope

    cfg = oidc.get_config(db)
    assert cfg["enabled"] and cfg["issuer"] == ISSUER
    assert cfg["client_secret"] == "s3cret-value"  # decrypts for the flow


def test_empty_secret_keeps_stored_one(db):
    oidc.save_config(db, enabled=False, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret="first", default_role="viewer", redirect_base="")
    oidc.save_config(db, enabled=False, issuer=ISSUER, client_id=CLIENT_ID,
                     client_secret=None, default_role="viewer", redirect_base="")
    assert oidc.get_config(db)["client_secret"] == "first"


# --- authorization URL / PKCE ----------------------------------------------------

@pytest.mark.anyio
async def test_authorization_url(monkeypatch):
    async def fake_discovery(issuer):
        return {"authorization_endpoint": f"{issuer}/authorize",
                "token_endpoint": f"{issuer}/token",
                "jwks_uri": f"{issuer}/jwks"}

    monkeypatch.setattr(oidc, "_discovery", fake_discovery)
    cfg = {"enabled": True, "issuer": ISSUER, "client_id": CLIENT_ID,
           "client_secret": "x", "scopes": "openid profile email"}
    url, state, verifier = await oidc.build_authorization_url(
        cfg, "http://api/api/auth/oidc/callback")
    assert url.startswith(f"{ISSUER}/authorize?")
    assert "code_challenge_method=S256" in url
    assert oidc.load_state(state)["v"] == verifier
    # S256: the challenge must be the SHA-256 of the verifier, not the verifier
    import hashlib
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert f"code_challenge={challenge}" in url


@pytest.mark.anyio
async def test_unconfigured_flow_rejected():
    with pytest.raises(OIDCError):
        await oidc.build_authorization_url(
            {"enabled": False, "issuer": "", "client_id": "", "client_secret": ""},
            "http://cb")


# --- id_token verification --------------------------------------------------------

def _b64u_int(n: int) -> str:
    raw = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture()
def rsa_jwks():
    """A local RSA keypair + the JWKS document advertising its public half."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "kid": "test-kid", "alg": "RS256", "use": "sig",
           "n": _b64u_int(pub.n), "e": _b64u_int(pub.e)}
    pem = key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return key, pem, {"keys": [jwk]}


def _claims():
    now = int(time.time())
    return {"iss": ISSUER, "aud": CLIENT_ID, "sub": "idp-123",
            "preferred_username": "sso.user", "email": "sso.user@corp.example",
            "iat": now, "exp": now + 300}


def _fake_httpx(monkeypatch, jwks):
    """Replace httpx.AsyncClient inside oidc_service with a JWKS stub."""
    class _Client:
        def __init__(self, *a: Any, **k: Any):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a: Any):
            return False

        async def get(self, url: str):
            return types.SimpleNamespace(json=lambda: jwks)

    monkeypatch.setattr(oidc.httpx, "AsyncClient", _Client)


@pytest.mark.anyio
async def test_verify_id_token_ok(monkeypatch, rsa_jwks):
    _, pem, jwks = rsa_jwks
    async def fake_discovery(issuer):
        return {"jwks_uri": f"{issuer}/jwks"}
    monkeypatch.setattr(oidc, "_discovery", fake_discovery)
    _fake_httpx(monkeypatch, jwks)

    token = jose_jwt.encode(_claims(), pem, algorithm="RS256",
                            headers={"kid": "test-kid"})
    cfg = {"enabled": True, "issuer": ISSUER, "client_id": CLIENT_ID,
           "client_secret": "x"}
    claims = await oidc.verify_id_token(cfg, token)
    assert claims["sub"] == "idp-123"


@pytest.mark.anyio
async def test_verify_id_token_wrong_issuer(monkeypatch, rsa_jwks):
    _, pem, jwks = rsa_jwks
    async def fake_discovery(issuer):
        return {"jwks_uri": f"{issuer}/jwks"}
    monkeypatch.setattr(oidc, "_discovery", fake_discovery)
    _fake_httpx(monkeypatch, jwks)

    claims = _claims()
    claims["iss"] = "https://evil.example"
    token = jose_jwt.encode(claims, pem, algorithm="RS256",
                            headers={"kid": "test-kid"})
    cfg = {"enabled": True, "issuer": ISSUER, "client_id": CLIENT_ID,
           "client_secret": "x"}
    with pytest.raises(OIDCError):
        await oidc.verify_id_token(cfg, token)


@pytest.mark.anyio
async def test_verify_id_token_foreign_signature(monkeypatch, rsa_jwks):
    _, pem, jwks = rsa_jwks
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    from cryptography.hazmat.primitives import serialization
    other_pem = other.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    async def fake_discovery(issuer):
        return {"jwks_uri": f"{issuer}/jwks"}
    monkeypatch.setattr(oidc, "_discovery", fake_discovery)
    _fake_httpx(monkeypatch, jwks)

    token = jose_jwt.encode(_claims(), other_pem, algorithm="RS256",
                            headers={"kid": "test-kid"})
    cfg = {"enabled": True, "issuer": ISSUER, "client_id": CLIENT_ID,
           "client_secret": "x"}
    with pytest.raises(OIDCError):
        await oidc.verify_id_token(cfg, token)


# --- provisioning -----------------------------------------------------------------

@pytest.mark.anyio
@pytest.mark.parametrize('access_token', ['matching-access-token', 'wrong-token', None])
async def test_id_token_access_token_hash(monkeypatch, rsa_jwks, access_token):
    """Keycloak includes at_hash; validate it, rather than disabling the check."""
    _, pem, jwks = rsa_jwks
    async def discovery(issuer):
        return {'jwks_uri': issuer + '/jwks'}
    monkeypatch.setattr(oidc, '_discovery', discovery)
    _fake_httpx(monkeypatch, jwks)
    token = jose_jwt.encode(_claims(), pem, algorithm='RS256',
                            headers={'kid': 'test-kid'}, access_token='matching-access-token')
    cfg = {'enabled': True, 'issuer': ISSUER, 'client_id': CLIENT_ID, 'client_secret': 'x'}
    if access_token == 'matching-access-token':
        assert (await oidc.verify_id_token(cfg, token, access_token))['sub'] == 'idp-123'
    else:
        with pytest.raises(OIDCError, match='at_hash'):
            await oidc.verify_id_token(cfg, token, access_token)

def test_provision_creates_with_default_role(db):
    user = oidc.provision_user(db, {"preferred_username": "new.sso",
                                    "email": "new@corp.example"}, "auditor")
    assert user.role == "auditor"
    assert user.must_change_password is False


def test_provision_never_escalates(db):
    admin = User(username="big.admin", email="big@corp.example",
                 hashed_password="x", role="admin", is_active=True)
    db.add(admin)
    db.commit()
    user = oidc.provision_user(db, {"preferred_username": "big.admin"}, "viewer")
    assert user.id == admin.id
    assert user.role == "admin"  # SSO login must not demote/override


def test_provision_links_by_email(db):
    local = User(username="local.guy", email="same@corp.example",
                 hashed_password="x", role="viewer", is_active=True)
    db.add(local)
    db.commit()
    user = oidc.provision_user(db, {"preferred_username": "idp.name",
                                    "email": "same@corp.example"}, "viewer")
    assert user.id == local.id


def test_provision_rejects_disabled_account(db):
    local = User(username="disabled.sso", hashed_password="x", role="viewer", is_active=False)
    db.add(local)
    db.commit()
    with pytest.raises(OIDCError, match="disabled"):
        oidc.provision_user(db, {"preferred_username": "disabled.sso"}, "viewer")


def test_provision_defers_last_login_for_otp_users(db):
    local = User(username="otp.sso", hashed_password="x", role="viewer",
                 is_active=True, otp_enabled=True)
    db.add(local)
    db.commit()
    user = oidc.provision_user(db, {"preferred_username": "otp.sso"}, "viewer")
    assert user.last_login_at is None
