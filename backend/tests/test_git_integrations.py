import asyncio
import hashlib
from types import SimpleNamespace
import httpx
import pytest
from services import git_provider as gp
from models.git_connection import GitConnection
from models.appsec import AppSecScan
from tests.test_appsec import source_zip

TOKEN = "fixture-token-never-real"
ROOT = "/api/appsec/integrations"
META = {"provider_id": "42", "path": "team/private", "default_branch": "develop", "private": True}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(gp.GitProvider, "check", lambda self: "fixture-user")
    monkeypatch.setattr(gp.GitProvider, "repo", lambda self, ident: dict(META))
    monkeypatch.setattr(gp.GitProvider, "repositories", lambda self, page: [dict(META)])


def connect(client, headers):
    response = client.post(
        ROOT,
        headers=headers,
        json={"name": "Fixture", "provider": "github", "origin": "https://github.com", "token": TOKEN},
    )
    assert response.status_code == 201, response.text
    assert TOKEN not in response.text and "token" not in response.text
    return response.json()["id"]


def test_admin_only(client, viewer_headers):
    assert client.get(ROOT).status_code == 401
    assert client.get(ROOT, headers=viewer_headers).status_code == 403
    assert client.post(ROOT, headers=viewer_headers, json={}).status_code == 403


def test_validation_does_not_echo_secret(client, admin_headers):
    response = client.post(ROOT, headers=admin_headers, json={"token": {"sensitive": TOKEN}})
    assert response.status_code == 422 and TOKEN not in response.text


def test_grant_scan_revoke_and_disconnect(client, admin_headers, db, runtime_sessions, monkeypatch, provider):
    ident = connect(client, admin_headers)
    row = db.get(GitConnection, ident)
    assert row.token_encrypted.startswith("enc::") and TOKEN not in row.token_encrypted
    assert gp.unseal(row.token_encrypted) == TOKEN
    base = f"{ROOT}/{ident}"
    assert client.get(base + "/repositories", headers=admin_headers).json()["items"][0]["allowed"] is False
    grant = client.put(base + "/repositories/42", headers=admin_headers, json={"allowed": True}).json()
    project = grant["project_id"]
    assert (
        client.put(base + "/repositories/42", headers=admin_headers, json={"allowed": True}).json()["project_id"]
        == project
    )
    url = f"/api/appsec/projects/{project}/scans"
    archive = source_zip({"repo/app.py": "eval(user_input)"})
    calls = []

    def fetch(self, repo, ref):
        calls.append((repo, ref))
        return "a" * 40, archive, hashlib.sha256(archive).hexdigest()

    monkeypatch.setattr(gp.GitProvider, "fetch", fetch)
    scan = client.post(url, headers=admin_headers, json={"ref": "develop"}).json()
    db.query(AppSecScan).filter_by(id=scan["id"]).update({"status": "running"})
    db.commit()
    from services.appsec_worker import process_scan

    asyncio.run(process_scan(scan["id"], runtime_sessions))
    result = client.get(f"/api/appsec/scans/{scan['id']}", headers=admin_headers).json()
    assert result["status"] == "completed" and result["findings"] and calls == [("42", "develop")]
    queued = client.post(url, headers=admin_headers, json={}).json()
    assert client.put(base + "/repositories/42", headers=admin_headers, json={"allowed": False}).status_code == 200
    assert client.get(f"/api/appsec/scans/{queued['id']}", headers=admin_headers).json()["status"] == "cancelled"
    assert client.post(url, headers=admin_headers, json={}).status_code == 409
    db.query(AppSecScan).filter_by(id=queued["id"]).update({"status": "running"})
    db.commit()
    asyncio.run(process_scan(queued["id"], runtime_sessions))
    assert client.get(f"/api/appsec/scans/{queued['id']}", headers=admin_headers).json()["status"] == "failed"
    assert len(calls) == 1
    assert client.delete(base, headers=admin_headers).status_code == 200
    db.expire_all()
    assert db.get(GitConnection, ident).token_encrypted == ""
    assert client.put(base + "/token", headers=admin_headers, json={"token": TOKEN}).status_code == 200
    assert client.get(base + "/grants", headers=admin_headers).json()[0]["allowed"] is False


def test_failed_rotation_keeps_old_credential(client, admin_headers, db, monkeypatch, provider):
    ident = connect(client, admin_headers)
    old = db.get(GitConnection, ident).token_encrypted

    def reject(self):
        raise gp.GitError("Token identity could not be verified.")

    monkeypatch.setattr(gp.GitProvider, "check", reject)
    assert (
        client.put(f"{ROOT}/{ident}/token", headers=admin_headers, json={"token": "replacement-fixture"}).status_code
        == 422
    )
    db.expire_all()
    assert db.get(GitConnection, ident).token_encrypted == old


@pytest.mark.parametrize(
    "address,private,allowed",
    [
        ("8.8.8.8", False, True),
        ("192.168.8.29", False, False),
        ("192.168.8.29", True, True),
        ("127.0.0.1", True, False),
        ("169.254.169.254", True, False),
        ("::1", True, False),
    ],
)
def test_network_policy(monkeypatch, address, private, allowed):
    monkeypatch.setattr(gp.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, (address, 443))])
    if allowed:
        gp.validate_network("https://fixture.invalid", private)
    else:
        with pytest.raises(gp.GitError):
            gp.validate_network("https://fixture.invalid", private)


@pytest.mark.parametrize("provider", ["github", "gitlab"])
def test_private_download_headers_and_commit_pin(monkeypatch, provider):
    sha = "b" * 40
    raw = source_zip({"repo/app.py": "print(1)"})

    def handler(request):
        path = request.url.path
        if request.url.host == "codeload.github.com":
            assert "authorization" not in request.headers and "private-token" not in request.headers
            return httpx.Response(200, content=raw)
        assert request.headers.get("authorization" if provider == "github" else "private-token") == (
            "Bearer " + TOKEN if provider == "github" else TOKEN
        )
        if path.endswith("/42"):
            return httpx.Response(
                200,
                json={
                    "id": 42,
                    "full_name": "team/private",
                    "path_with_namespace": "team/private",
                    "default_branch": "main",
                },
            )
        if "/commits/" in path:
            return httpx.Response(200, json={"id": sha, "sha": sha})
        assert sha in str(request.url)
        if provider == "github":
            return httpx.Response(
                302, headers={"location": f"https://codeload.github.com/team/private/zip/{sha}?token=temporary"}
            )
        return httpx.Response(200, content=raw)

    original = httpx.Client
    monkeypatch.setattr(gp.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(gp, "validate_network", lambda *a: None)
    obj = gp.GitProvider(
        SimpleNamespace(
            provider=provider,
            origin=f"https://{provider}.com",
            allow_private_network=False,
            token_encrypted=gp.seal(TOKEN),
        )
    )
    resolved, data, digest = obj.fetch("42", "feature/security")
    assert resolved == sha and data == raw and digest == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.invalid/team/private/zip/a",
        "http://codeload.github.com/team/private/zip/a",
        "https://user:pass@codeload.github.com/team/private/zip/a",
    ],
)
def test_archive_redirect_cannot_leak_pat(monkeypatch, location):
    obj = gp.GitProvider(
        SimpleNamespace(
            provider="github", origin="https://github.com", allow_private_network=False, token_encrypted=gp.seal(TOKEN)
        )
    )
    monkeypatch.setattr(obj, "repo", lambda ident: META)
    monkeypatch.setattr(obj, "get", lambda suffix: {"sha": "a" * 40})
    original = httpx.Client
    monkeypatch.setattr(gp, "validate_network", lambda *a: None)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": location})

    monkeypatch.setattr(gp.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(gp.GitError):
        obj.fetch("42", "main")
    assert len(calls) == 1


def test_encryption_fails_closed(monkeypatch):
    def broken():
        raise RuntimeError("unavailable")

    monkeypatch.setattr(gp, "_fernet", broken)
    with pytest.raises(gp.GitError):
        gp.seal(TOKEN)
