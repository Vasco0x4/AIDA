"""Optional per-user RFC 6238 TOTP, recovery codes, and two-step login."""
from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlparse

import pytest

from auth import create_access_token
from models.user import User
from services.otp_service import totp_at
from middleware.rate_limit import limiter


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


RFC_SECRET = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (59, "287082"),
        (1111111109, "081804"),
        (1111111111, "050471"),
        (1234567890, "005924"),
        (2000000000, "279037"),
        (20000000000, "353130"),
    ],
)
def test_rfc6238_sha1_vectors(timestamp, expected):
    assert totp_at(RFC_SECRET, timestamp=timestamp) == expected


def _enable_otp(client, headers, password="Sup3rSecret!x"):
    response = client.post("/api/auth/otp/setup", headers=headers, json={"password": password})
    assert response.status_code == 200, response.text
    setup = response.json()
    parsed_uri = urlparse(setup["otpauth_uri"])
    assert parsed_uri.scheme == "otpauth"
    assert parsed_uri.path.startswith("/AIDA%3A")
    assert parse_qs(parsed_uri.query)["secret"] == [setup["secret"]]
    assert setup["qr_svg"].lstrip().startswith("<svg")
    assert setup["secret"]
    assert client.get("/api/auth/me", headers=headers).json()["otp_enabled"] is False

    code = totp_at(setup["secret"])
    response = client.post(
        "/api/auth/otp/enable", headers=headers,
        json={"password": password, "code": code},
    )
    assert response.status_code == 200, response.text
    enabled = response.json()
    assert enabled["enabled"] is True
    assert len(enabled["recovery_codes"]) == 10
    assert len(set(enabled["recovery_codes"])) == 10
    assert client.get("/api/auth/me", headers=headers).json()["otp_enabled"] is True
    return setup["secret"], enabled["recovery_codes"]


def _login_challenge(client, username="admin", password="Sup3rSecret!x"):
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["otp_required"] is True
    assert body["challenge_id"]
    assert "access_token" not in body
    return body["challenge_id"]


def test_enrollment_encrypts_secret_and_recovery_codes(client, db, admin_user, admin_headers):
    secret, recovery_codes = _enable_otp(client, admin_headers)
    db.expire_all()
    stored = db.query(User).filter(User.id == admin_user.id).one()
    assert stored.otp_secret_encrypted.startswith("enc::")
    assert secret not in stored.otp_secret_encrypted
    assert stored.otp_pending_secret_encrypted is None

    from models.otp import RecoveryCode

    rows = db.query(RecoveryCode).filter(RecoveryCode.user_id == admin_user.id).all()
    assert len(rows) == 10
    for row in rows:
        assert row.used_at is None
        assert len(row.code_hash) == 64
        assert all(code not in row.code_hash for code in recovery_codes)


def test_enable_rejects_wrong_confirmation(client, admin_headers):
    setup = client.post(
        "/api/auth/otp/setup", headers=admin_headers, json={"password": "Sup3rSecret!x"}
    ).json()
    response = client.post(
        "/api/auth/otp/enable", headers=admin_headers,
        json={"password": "Sup3rSecret!x", "code": "000000"},
    )
    assert response.status_code == 401
    assert client.get("/api/auth/me", headers=admin_headers).json()["otp_enabled"] is False
    assert setup["secret"] not in response.text


def test_second_factor_issues_token_and_rejects_replay(client, admin_headers):
    secret, _ = _enable_otp(client, admin_headers)
    challenge_id = _login_challenge(client)
    code = totp_at(secret)
    response = client.post("/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": code})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    assert token
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # The challenge is consumed and the RFC timestep cannot be replayed in a new login.
    replay = client.post("/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": code})
    assert replay.status_code == 401
    second_challenge = _login_challenge(client)
    replay = client.post(
        "/api/auth/otp/verify", json={"challenge_id": second_challenge, "code": code}
    )
    assert replay.status_code == 401


def test_recovery_code_is_single_use(client, admin_headers):
    _, recovery_codes = _enable_otp(client, admin_headers)
    code = recovery_codes[0]
    first = _login_challenge(client)
    response = client.post("/api/auth/otp/verify", json={"challenge_id": first, "code": code})
    assert response.status_code == 200, response.text
    second = _login_challenge(client)
    response = client.post("/api/auth/otp/verify", json={"challenge_id": second, "code": code})
    assert response.status_code == 401
    status = client.get("/api/auth/otp/status", headers=admin_headers).json()
    assert status["recovery_codes_remaining"] == 9


def test_challenge_is_bounded_after_five_failures(client, admin_headers):
    _enable_otp(client, admin_headers)
    challenge_id = _login_challenge(client)
    for _ in range(5):
        response = client.post(
            "/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": "000000"}
        )
        assert response.status_code == 401
    response = client.post(
        "/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": "000000"}
    )
    assert response.status_code == 429


def test_disable_and_regenerate_require_reauthentication(client, admin_headers):
    secret, old_codes = _enable_otp(client, admin_headers)
    response = client.post(
        "/api/auth/otp/disable", headers=admin_headers,
        json={"password": "wrong", "code": totp_at(secret)},
    )
    assert response.status_code == 401

    # A fresh challenge verifies that regenerate also requires a valid second factor.
    response = client.post(
        "/api/auth/otp/recovery-codes", headers=admin_headers,
        json={"password": "Sup3rSecret!x", "code": "000000"},
    )
    assert response.status_code == 401
    response = client.post(
        "/api/auth/otp/recovery-codes", headers=admin_headers,
        json={"password": "Sup3rSecret!x", "code": totp_at(secret)},
    )
    assert response.status_code == 200, response.text
    new_codes = response.json()["recovery_codes"]
    assert len(new_codes) == 10
    assert set(new_codes).isdisjoint(old_codes)

    response = client.post(
        "/api/auth/otp/disable", headers=admin_headers,
        json={"password": "Sup3rSecret!x", "code": new_codes[0]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Sup3rSecret!x"})
    assert login.json()["otp_enabled"] is False
    assert login.json()["access_token"]


def test_admin_reset_clears_otp_and_pending_challenges(client, admin_user, admin_headers):
    secret, _ = _enable_otp(client, admin_headers)
    challenge_id = _login_challenge(client)
    response = client.post(f"/api/users/{admin_user.id}/reset-otp", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["otp_enabled"] is False
    response = client.post(
        "/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": totp_at(secret)}
    )
    assert response.status_code == 401
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Sup3rSecret!x"})
    assert "access_token" in login.json()


def test_non_admin_cannot_reset_another_users_otp(client, db, admin_user):
    user = User(username="ordinary", hashed_password="x", role="viewer", is_active=True)
    db.add(user)
    db.commit()
    token = create_access_token(user.id, user.username)
    response = client.post(
        f"/api/users/{admin_user.id}/reset-otp", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_password_change_invalidates_pending_challenge(client, admin_headers):
    secret, _ = _enable_otp(client, admin_headers)
    full_token = client.post(
        "/api/auth/otp/verify",
        json={"challenge_id": _login_challenge(client), "code": totp_at(secret)},
    ).json()["access_token"]
    challenge_id = _login_challenge(client)
    response = client.post(
        "/api/auth/change-password", headers={"Authorization": f"Bearer {full_token}"},
        json={"current_password": "Sup3rSecret!x", "new_password": "a-new-password-123"},
    )
    assert response.status_code == 200, response.text
    response = client.post(
        "/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": totp_at(secret)}
    )
    assert response.status_code == 401


def test_oidc_only_account_can_enroll_without_local_password(client, db):
    user = User(
        username="sso-only", hashed_password="random-unusable", role="viewer",
        is_active=True, auth_provider="oidc",
    )
    db.add(user)
    db.commit()
    token = create_access_token(user.id, user.username)
    response = client.post(
        "/api/auth/otp/setup", headers={"Authorization": f"Bearer {token}"}, json={}
    )
    assert response.status_code == 200, response.text


def test_oidc_callback_requires_second_factor_before_full_token(
        client, admin_user, admin_headers, monkeypatch):
    import services.oidc_service as oidc

    secret, _ = _enable_otp(client, admin_headers)
    cfg = {
        "enabled": True, "issuer": "https://idp.example", "client_id": "aida",
        "client_secret": "x", "default_role": "viewer", "redirect_base": "http://frontend",
    }

    async def fake_exchange(*args):
        return {"id_token": "verified-by-fake-verifier"}

    async def fake_verify(*args):
        return {"preferred_username": admin_user.username}

    monkeypatch.setattr(oidc, "get_config", lambda db: cfg)
    monkeypatch.setattr(oidc, "load_state", lambda state: {"v": "verifier"})
    monkeypatch.setattr(oidc, "exchange_code", fake_exchange)
    monkeypatch.setattr(oidc, "verify_id_token", fake_verify)
    monkeypatch.setattr(oidc, "provision_user", lambda db, claims, role: db.get(User, admin_user.id))

    response = client.get(
        "/api/auth/oidc/callback?code=authorization-code&state=signed-state",
        follow_redirects=False,
    )
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert location.startswith("http://frontend/sso#challenge=")
    assert "token=" not in location
    challenge_id = location.rsplit("=", 1)[1]
    verified = client.post(
        "/api/auth/otp/verify", json={"challenge_id": challenge_id, "code": totp_at(secret)}
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["access_token"]
