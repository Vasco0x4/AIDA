"""api/source_code.py — git clone / zip upload / list / delete endpoints with
the docker exec/cp boundary faked."""
from __future__ import annotations

import pytest

from api.source_code import _sanitize_dir_name, _validate_git_url
from config import settings
from fastapi import HTTPException
from models.assessment import Assessment


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_validate_git_url_accepts_and_normalizes():
    assert _validate_git_url("  https://github.com/a/b.git  ") == "https://github.com/a/b.git"
    assert _validate_git_url("git://host/repo") == "git://host/repo"


@pytest.mark.parametrize("bad", [
    "", "   ", "ssh://git@host/repo", "file:///etc/passwd",
    "https://x/repo;rm -rf /", "https://x/repo$(id)",
    "https://x/repo`id`", "https://x/repo && id",
    "https://x/repo|cat", "https://x/repo'quote",
])
def test_validate_git_url_rejects(bad):
    with pytest.raises(HTTPException) as ei:
        _validate_git_url(bad)
    assert ei.value.status_code == 400


def test_sanitize_dir_name():
    assert _sanitize_dir_name("my-repo_1.2") == "my-repo_1.2"
    assert _sanitize_dir_name("we!rd@name") == "we_rd_name"
    assert _sanitize_dir_name("..hidden") == "hidden"
    assert _sanitize_dir_name("-leading") == "leading"
    assert _sanitize_dir_name("...") == "source"
    assert _sanitize_dir_name("") == "source"
    assert len(_sanitize_dir_name("x" * 300)) == 128


# ── docker boundary fake ──────────────────────────────────────────────────────

class DockerScript:
    """Replaces api.source_code._docker_exec; replies dispatched on cmd."""

    def __init__(self, replies=None):
        self.replies = list(replies or [])
        self.calls = []
        self.cp_calls = []

    async def __call__(self, container, cmd, timeout=60):
        self.calls.append((container, list(cmd)))
        for matcher, reply in self.replies:
            if matcher(cmd):
                if isinstance(reply, Exception):
                    raise reply
                return reply
        return 0, "", ""

    async def cp(self, container, src, dst):
        self.cp_calls.append((container, src, dst))


@pytest.fixture()
def docker(monkeypatch):
    script = DockerScript()
    monkeypatch.setattr("api.source_code._docker_exec", script)
    monkeypatch.setattr("api.source_code._docker_cp_to_container", script.cp)
    return script


def _seed(db, workspace_path="/workspace/sc", container_name=None):
    asn = Assessment(name="SC", scope="t.example", workspace_path=workspace_path,
                     container_name=container_name)
    db.add(asn)
    db.commit()
    db.refresh(asn)
    return asn


def test_branches_requires_auth(client, db):
    res = client.post("/api/assessments/1/source/branches", json={"url": "https://x/y"})
    assert res.status_code == 401


def test_detect_branches_success(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[0] == "git" and cmd[1] == "ls-remote",
         (0, "a1\trefs/heads/main\na2\trefs/heads/dev\na3\trefs/tags/v1\n", "")),
    ]
    res = client.post(f"/api/assessments/{asn.id}/source/branches",
                      json={"url": "https://github.com/a/b.git"}, headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["branches"] == ["main", "dev"]
    assert res.json()["url"] == "https://github.com/a/b.git"
    # git ls-remote ran inside the assessment's container
    assert docker.calls[0][0] == settings.DEFAULT_CONTAINER_NAME
    assert docker.calls[0][1][:2] == ["git", "ls-remote"]


def test_detect_branches_git_failure(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[0] == "git", (128, "", "repository not found")),
    ]
    res = client.post(f"/api/assessments/{asn.id}/source/branches",
                      json={"url": "https://github.com/a/b"}, headers=admin_headers)
    assert res.status_code == 400
    assert "repository not found" in res.json()["detail"]


def test_detect_branches_bad_url(client, db, admin_headers, docker):
    asn = _seed(db)
    res = client.post(f"/api/assessments/{asn.id}/source/branches",
                      json={"url": "ssh://nope"}, headers=admin_headers)
    assert res.status_code == 400
    assert docker.calls == []


# ── clone ─────────────────────────────────────────────────────────────────────

def test_clone_repository_success(client, db, admin_headers, docker):
    asn = _seed(db, container_name="exegol-1")
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),          # not exists
        (lambda cmd: cmd[0] == "git" and cmd[1] == "clone", (0, "", "")),
        (lambda cmd: cmd[:2] == ["cat", "/workspace/sc/source/b/.git/HEAD"],
         (0, "ref: refs/heads/main\n", "")),
        (lambda cmd: cmd[0] == "rm", (0, "", "")),
        (lambda cmd: cmd[0] == "bash", (0, "", "")),
    ]
    res = client.post(
        f"/api/assessments/{asn.id}/source/clone",
        json={"url": "https://github.com/acme/b.git", "branch": "dev", "shallow": True},
        headers=admin_headers)
    assert res.status_code == 201
    body = res.json()
    assert body == {"success": True, "name": "b", "type": "git", "branch": "dev",
                    "url": "https://github.com/acme/b.git", "path": "source/b"}
    # git clone got --depth 1 + explicit branch → HEAD not consulted
    clone_cmd = [c for _, c in docker.calls if c[:2] == ["git", "clone"]][0]
    assert "--depth" in clone_cmd and "--branch" in clone_cmd and "--single-branch" in clone_cmd
    assert clone_cmd[-1] == "/workspace/sc/source/b"
    # .git removed and .source_meta written with the given branch
    assert any(c[:2] == ["rm", "-rf"] and c[2].endswith("/.git") for _, c in docker.calls)
    bash_cmds = [c for _, c in docker.calls if c[0] == "bash"]
    assert ".source_meta" in bash_cmds[0][-1] and "branch=dev" in bash_cmds[0][-1]


def test_clone_repository_resolves_head_branch(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),
        (lambda cmd: cmd[1] == "clone", (0, "", "")),
        (lambda cmd: cmd[0] == "cat", (0, "ref: refs/heads/develop\n", "")),
        (lambda cmd: True, (0, "", "")),
    ]
    res = client.post(f"/api/assessments/{asn.id}/source/clone",
                      json={"url": "https://github.com/a/b.git"}, headers=admin_headers)
    assert res.status_code == 201
    assert res.json()["branch"] == "develop"


def test_clone_repository_already_exists(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (0, "", "")),  # exists → 409
    ]
    res = client.post(f"/api/assessments/{asn.id}/source/clone",
                      json={"url": "https://github.com/a/b"}, headers=admin_headers)
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]
    # No clone attempted
    assert not any(c[0] == "git" for _, c in docker.calls)


def test_clone_repository_failure_cleans_up(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),
        (lambda cmd: cmd[1] == "clone", (128, "", "fatal: auth failed")),
        (lambda cmd: cmd[:2] == ["rm", "-rf"], (0, "", "")),
    ]
    res = client.post(f"/api/assessments/{asn.id}/source/clone",
                      json={"url": "https://github.com/a/b"}, headers=admin_headers)
    assert res.status_code == 400
    assert "auth failed" in res.json()["detail"]
    cleanup = [c for _, c in docker.calls if c[:2] == ["rm", "-rf"]]
    assert cleanup and cleanup[0][2] == "/workspace/sc/source/b"


def test_clone_requires_workspace(client, db, admin_headers, docker):
    asn = _seed(db, workspace_path=None)
    res = client.post(f"/api/assessments/{asn.id}/source/clone",
                      json={"url": "https://github.com/a/b"}, headers=admin_headers)
    assert res.status_code == 400
    assert "no workspace" in res.json()["detail"]


# ── zip upload ────────────────────────────────────────────────────────────────

def _zip_bytes():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("app.py", "print('hi')")
    return buf.getvalue()


def test_upload_zip_success(client, db, admin_headers, docker):
    asn = _seed(db, container_name="exegol-1")
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),
        (lambda cmd: cmd[0] == "which", (0, "", "")),  # unzip available
        (lambda cmd: cmd[0] == "unzip", (0, "", "")),
        (lambda cmd: True, (0, "", "")),
    ]
    res = client.post(
        f"/api/assessments/{asn.id}/source/upload-zip",
        files={"file": ("My App.zip", _zip_bytes(), "application/zip")},
        headers=admin_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "My_App"
    assert body["type"] == "zip"
    assert body["path"] == "source/My_App"
    assert body["size"] == len(_zip_bytes())
    # docker cp used for the transfer; extraction via unzip; zip removed after
    assert docker.cp_calls and docker.cp_calls[0][0] == "exegol-1"
    assert docker.cp_calls[0][2] == "/workspace/sc/source/My_App.zip"
    assert any(c[0] == "unzip" for _, c in docker.calls)
    assert any(c[:2] == ["rm", "-f"] and c[2].endswith(".zip") for _, c in docker.calls)


def test_upload_zip_python_fallback(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),
        (lambda cmd: cmd[0] == "which", (1, "", "")),  # no unzip binary
        (lambda cmd: cmd[0] == "python3", (0, "", "")),
        (lambda cmd: True, (0, "", "")),
    ]
    res = client.post(
        f"/api/assessments/{asn.id}/source/upload-zip",
        files={"file": ("app.zip", _zip_bytes(), "application/zip")},
        headers=admin_headers)
    assert res.status_code == 201
    assert any(c[0] == "python3" and "zipfile" in c[2] for _, c in docker.calls)


def test_upload_zip_rejects_non_zip(client, db, admin_headers, docker):
    asn = _seed(db)
    res = client.post(
        f"/api/assessments/{asn.id}/source/upload-zip",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=admin_headers)
    assert res.status_code == 400
    assert "Only .zip files" in res.json()["detail"]
    assert docker.calls == []


def test_upload_zip_too_large(client, db, admin_headers, docker, monkeypatch):
    import api.source_code as sc

    monkeypatch.setattr(sc, "MAX_ZIP_SIZE", 10)
    asn = _seed(db)
    res = client.post(
        f"/api/assessments/{asn.id}/source/upload-zip",
        files={"file": ("big.zip", b"x" * 2048, "application/zip")},
        headers=admin_headers)
    assert res.status_code == 400
    assert "ZIP too large" in res.json()["detail"]
    assert docker.calls == []


def test_upload_zip_already_exists(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [(lambda cmd: cmd[:2] == ["test", "-d"], (0, "", ""))]
    res = client.post(
        f"/api/assessments/{asn.id}/source/upload-zip",
        files={"file": ("app.zip", _zip_bytes(), "application/zip")},
        headers=admin_headers)
    assert res.status_code == 409


def test_upload_zip_extraction_failure_cleans_up(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),
        (lambda cmd: cmd[0] == "which", (0, "", "")),
        (lambda cmd: cmd[0] == "unzip", (9, "", "corrupt archive")),
        (lambda cmd: cmd[:2] == ["rm", "-rf"], (0, "", "")),
    ]
    res = client.post(
        f"/api/assessments/{asn.id}/source/upload-zip",
        files={"file": ("bad.zip", b"not-a-zip", "application/zip")},
        headers=admin_headers)
    assert res.status_code == 500
    assert "corrupt archive" in res.json()["detail"]
    assert any(c[:2] == ["rm", "-rf"] for _, c in docker.calls)


# ── list / delete ─────────────────────────────────────────────────────────────

def test_list_source_code(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (0, "", "")),  # /source exists
        (lambda cmd: cmd[0] == "find",
         (0, "/workspace/sc/source/webapp\n/workspace/sc/source/api\n", "")),
        (lambda cmd: cmd[0] == "cat" and cmd[1].endswith("webapp/.source_meta"),
         (0, "url=https://github.com/a/webapp\nbranch=main\ntype=git\n", "")),
        (lambda cmd: cmd[0] == "du" and "webapp" in cmd[2], (0, "12M\t/webapp\n", "")),
        (lambda cmd: cmd[0] == "cat" and cmd[1].endswith(".git/HEAD"),
         (0, "ref: refs/heads/master\n", "")),
        (lambda cmd: cmd[0] == "cat", (1, "", "")),  # api: no .source_meta
        (lambda cmd: cmd[:2] == ["test", "-d"] and cmd[2].endswith("api/.git"),
         (0, "", "")),  # legacy git repo detected
        (lambda cmd: cmd[0] == "du", (0, "3.5M\t/api\n", "")),
    ]
    res = client.get(f"/api/assessments/{asn.id}/source/list", headers=admin_headers)
    assert res.status_code == 200
    entries = res.json()
    assert [e["name"] for e in entries] == ["api", "webapp"]  # sorted
    webapp = next(e for e in entries if e["name"] == "webapp")
    assert webapp == {"name": "webapp", "type": "git", "branch": "main",
                      "url": "https://github.com/a/webapp", "size_human": "12M",
                      "path": "source/webapp"}
    api = next(e for e in entries if e["name"] == "api")
    assert api["type"] == "git" and api["branch"] == "master" and api["url"] is None


def test_list_source_code_no_source_dir(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [(lambda cmd: cmd[:2] == ["test", "-d"], (1, "", ""))]
    res = client.get(f"/api/assessments/{asn.id}/source/list", headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_delete_source_code(client, db, admin_headers, docker):
    asn = _seed(db)
    docker.replies = [
        (lambda cmd: cmd[:2] == ["test", "-d"], (0, "", "")),
        (lambda cmd: cmd[:2] == ["rm", "-rf"], (0, "", "")),
    ]
    res = client.delete(f"/api/assessments/{asn.id}/source/webapp", headers=admin_headers)
    assert res.status_code == 204
    rm = [c for _, c in docker.calls if c[:2] == ["rm", "-rf"]][0]
    assert rm[2] == "/workspace/sc/source/webapp"


def test_delete_source_code_validation_and_missing(client, db, admin_headers, docker):
    asn = _seed(db)
    # "we!rd" sanitizes to a different name → rejected before any docker call
    res = client.delete(f"/api/assessments/{asn.id}/source/we!rd", headers=admin_headers)
    assert res.status_code == 400
    assert docker.calls == []
    docker.replies = [(lambda cmd: cmd[:2] == ["test", "-d"], (1, "", ""))]
    res = client.delete(f"/api/assessments/{asn.id}/source/ghost", headers=admin_headers)
    assert res.status_code == 404
