"""api/context_documents.py — upload/list/delete/tree/markdown endpoints with
the docker boundaries (ContainerService, subprocess exec, tree generator) faked."""
from __future__ import annotations

import io
import zipfile

import pytest

from models.assessment import Assessment
from models.platform_settings import PlatformSettings


# ── pure helpers ──────────────────────────────────────────────────────────────

def test_sanitize_filename():
    from api.context_documents import _sanitize_filename

    assert _sanitize_filename("notes.md") == "notes.md"
    assert _sanitize_filename("../../etc/passwd") == "passwd.txt"  # no ext → .txt added
    assert _sanitize_filename("we!rd@name.txt") == "we_rd_name.txt"
    assert _sanitize_filename("noext") == "noext.txt"
    assert _sanitize_filename("sub/dir/file.pdf") == "file.pdf"


def test_zip_contains_git():
    from api.context_documents import _zip_contains_git

    def zipped(names):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in names:
                z.writestr(n, "x")
        return buf.getvalue()

    assert _zip_contains_git(zipped([".git/config", "README.md"])) is True
    assert _zip_contains_git(zipped(["app/.git/HEAD"])) is True
    assert _zip_contains_git(zipped(["src/a.py", "README.md"])) is False
    assert _zip_contains_git(b"not a zip at all") is False  # BadZipFile → False


def test_sanitize_source_name():
    from api.context_documents import _sanitize_source_name

    assert _sanitize_source_name("my repo!") == "my_repo_"
    assert _sanitize_source_name("..lead") == "lead"
    assert _sanitize_source_name("") == "source"


# ── docker boundary fakes ─────────────────────────────────────────────────────

class FakeCS:
    instances = []
    commands = []

    @staticmethod
    def handler(cmd):
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    def __init__(self):
        self.current_container = None
        FakeCS.instances.append(self)

    async def execute_container_command(self, cmd, working_directory=None):
        FakeCS.commands.append(cmd)
        return FakeCS.handler(cmd)


class FakeProc:
    def __init__(self, returncode=0, stderr=b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return b"", self._stderr


def _coro(value):
    async def _c():
        return value
    return _c()


@pytest.fixture(autouse=True)
def _reset_fake_cs():
    FakeCS.commands = []
    FakeCS.instances = []
    FakeCS.handler = staticmethod(
        lambda cmd: {"success": True, "returncode": 0, "stdout": "", "stderr": ""})


def _fake_exec(monkeypatch, returncode=0, stderr=b""):
    calls = []

    def fake_exec(*args, **kw):
        calls.append(list(args))
        return _coro(FakeProc(returncode, stderr))

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_exec)
    return calls


def _seed(db, workspace_path="/workspace/cd", container_name="exegol-x"):
    asn = Assessment(name="CD", scope="t.example", workspace_path=workspace_path,
                     container_name=container_name)
    db.add(asn)
    db.commit()
    db.refresh(asn)
    return asn


# ── upload: regular context file ──────────────────────────────────────────────

def test_upload_requires_auth(client, db):
    res = client.post("/api/assessments/1/context/upload",
                      files={"file": ("a.txt", b"x", "text/plain")})
    assert res.status_code == 401


def test_upload_rejects_extension(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    cp = _fake_exec(monkeypatch)
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("evil.exe", b"MZ", "application/x-exe")},
                      headers=admin_headers)
    assert res.status_code == 400
    assert "not allowed" in res.json()["detail"]
    assert cp == [] and FakeCS.commands == []


def test_upload_success(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    cp = _fake_exec(monkeypatch)
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("Spec Notes.pdf", b"%PDF-1.4", "application/pdf")},
                      headers=admin_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["routed_to"] == "context"
    assert body["filename"] == "Spec Notes.pdf"
    assert body["size"] == 8
    assert body["path"] == "/workspace/cd/context/Spec Notes.pdf"
    # mkdir ran inside the assessment container; docker cp moved the temp file
    assert FakeCS.commands == ["mkdir -p /workspace/cd/context"]
    assert len(cp) == 1 and cp[0][0] == "docker" and cp[0][1] == "cp"
    assert cp[0][3] == "exegol-x:/workspace/cd/context/Spec Notes.pdf"


def test_upload_sanitizes_traversal_filename(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    cp = _fake_exec(monkeypatch)
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("../../etc/shadow.txt", b"x", "text/plain")},
                      headers=admin_headers)
    assert res.status_code == 201
    assert cp[0][3] == "exegol-x:/workspace/cd/context/shadow.txt"


def test_upload_oversize(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    db.add(PlatformSettings(key="max_context_file_size", value="1"))
    db.commit()
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    cp = _fake_exec(monkeypatch)
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("big.txt", b"x" * (2 * 1024 * 1024), "text/plain")},
                      headers=admin_headers)
    assert res.status_code == 400
    assert "exceeds limit" in res.json()["detail"]
    assert cp == [] and FakeCS.commands == []


def test_upload_docker_cp_failure(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    _fake_exec(monkeypatch, returncode=1, stderr=b"no such container")
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("a.txt", b"x", "text/plain")},
                      headers=admin_headers)
    assert res.status_code == 500
    assert "Failed to copy file" in res.json()["detail"]


# ── upload: zip containing .git → routed to /source ──────────────────────────

def _git_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(".git/config", "[core]")
        z.writestr("app.py", "print('hi')")
    return buf.getvalue()


class CtxScript:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, container, cmd, timeout=120):
        self.calls.append((container, list(cmd)))
        for matcher, reply in self.replies:
            if matcher(cmd):
                return reply
        return 0, "", ""


def test_upload_git_zip_routed_to_source(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    script = CtxScript([
        (lambda cmd: cmd[:2] == ["test", "-d"], (1, "", "")),
        (lambda cmd: cmd[0] == "which", (0, "", "")),   # unzip available
        (lambda cmd: cmd[0] == "unzip", (0, "", "")),
    ])
    monkeypatch.setattr("api.context_documents._docker_exec_ctx", script)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    cp = _fake_exec(monkeypatch)

    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("Web Repo.zip", _git_zip(), "application/zip")},
                      headers=admin_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["routed_to"] == "source"
    assert body["name"] == "Web_Repo"
    assert body["path"] == "source/Web_Repo"
    assert body["size"] == len(_git_zip())
    # .git stripped and .source_meta written after extraction
    execs = [c for _, c in script.calls]
    assert any(c[:2] == ["rm", "-rf"] and c[2].endswith("/.git") for c in execs)
    assert any(c[0] == "bash" and ".source_meta" in c[-1] for c in execs)
    # zip file copied into the container then removed
    assert cp and cp[0][:2] == ["docker", "cp"]
    assert any(c[:2] == ["rm", "-f"] and c[2].endswith(".zip") for c in execs)
    # regular-context path never taken
    assert FakeCS.commands == []


def test_upload_git_zip_already_exists(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    script = CtxScript([(lambda cmd: cmd[:2] == ["test", "-d"], (0, "", ""))])
    monkeypatch.setattr("api.context_documents._docker_exec_ctx", script)
    _fake_exec(monkeypatch)
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("repo.zip", _git_zip(), "application/zip")},
                      headers=admin_headers)
    assert res.status_code == 409


def test_upload_plain_zip_stays_in_context(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    cp = _fake_exec(monkeypatch)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.txt", "x")
    res = client.post(f"/api/assessments/{asn.id}/context/upload",
                      files={"file": ("docs.zip", buf.getvalue(), "application/zip")},
                      headers=admin_headers)
    assert res.status_code == 201
    assert res.json()["routed_to"] == "context"
    assert cp and cp[0][3].startswith("exegol-x:/workspace/cd/context/docs.zip")


def test_upload_missing_assessment(client, db, admin_headers, monkeypatch):
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.post("/api/assessments/999999/context/upload",
                      files={"file": ("a.txt", b"x", "text/plain")},
                      headers=admin_headers)
    assert res.status_code == 404


# ── list / delete / tree ──────────────────────────────────────────────────────

def test_list_context_documents(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    files = [{"filename": "spec.pdf", "size_human": "1.2 KB", "type": "pdf",
              "path": "/workspace/cd/context/spec.pdf"}]

    async def fake_list(container, workspace):
        return files

    monkeypatch.setattr("api.context_documents.get_context_files_list", fake_list)
    res = client.get(f"/api/assessments/{asn.id}/context/files", headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == files


def test_list_context_documents_no_workspace(client, db, admin_headers):
    asn = _seed(db, workspace_path=None)
    res = client.get(f"/api/assessments/{asn.id}/context/files", headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_delete_context_document(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.delete(f"/api/assessments/{asn.id}/context/notes.md",
                        headers=admin_headers)
    assert res.status_code == 204
    assert FakeCS.commands == ["rm -f /workspace/cd/context/notes.md"]


def test_delete_context_document_failure(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    FakeCS.handler = staticmethod(
        lambda cmd: {"success": False, "returncode": 1, "stdout": "", "stderr": "nope"})
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.delete(f"/api/assessments/{asn.id}/context/notes.md",
                        headers=admin_headers)
    assert res.status_code == 500
    assert "Failed to delete file" in res.json()["detail"]


def test_workspace_tree(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    seen = {}

    async def fake_tree(container_name, workspace_path, max_depth=2):
        seen.update(container=container_name, wp=workspace_path, depth=max_depth)
        return "├── recon/"

    monkeypatch.setattr("api.context_documents.generate_workspace_tree", fake_tree)
    res = client.get(f"/api/assessments/{asn.id}/context/tree", headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == {"tree": "├── recon/", "workspace_path": "/workspace/cd"}
    assert seen == {"container": "exegol-x", "wp": "/workspace/cd", "depth": 2}


def test_workspace_tree_no_workspace(client, db, admin_headers):
    asn = _seed(db, workspace_path=None)
    res = client.get(f"/api/assessments/{asn.id}/context/tree", headers=admin_headers)
    assert res.status_code == 200
    assert res.json()["tree"] == "Workspace not created yet"


# ── markdown files / content ──────────────────────────────────────────────────

def test_list_markdown_files(client, db, admin_headers, monkeypatch):
    asn = _seed(db)

    def handler(cmd):
        if cmd.startswith("find /workspace/cd ") and cmd.split()[1] == "/workspace/cd":
            pass
        if "find" in cmd and cmd.split()[3] == "1":  # root search (maxdepth 1)
            return {"success": True, "returncode": 0,
                    "stdout": "/workspace/cd/README.md\n", "stderr": ""}
        if "find" in cmd and "notes" in cmd:
            return {"success": True, "returncode": 0,
                    "stdout": "/workspace/cd/notes/todo.md\n/other/ws/evil.md\n",
                    "stderr": ""}
        if cmd.startswith("stat"):
            return {"success": True, "returncode": 0,
                    "stdout": "2048 1700000000\n", "stderr": ""}
        return {"success": True, "returncode": 0, "stdout": "", "stderr": ""}

    FakeCS.handler = staticmethod(handler)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.get(f"/api/assessments/{asn.id}/markdown/files", headers=admin_headers)
    assert res.status_code == 200
    files = res.json()
    # evil.md outside this workspace is skipped
    assert [f["path"] for f in files] == ["README.md", "notes/todo.md"]
    readme = files[0]
    assert readme["filename"] == "README.md"
    assert readme["size"] == 2048
    assert readme["size_human"] == "2.00KB"
    assert readme["folder"] == "."
    assert readme["modified"] == 1700000000
    # find used -maxdepth to stay inside the workspace
    finds = [c for c in FakeCS.commands if c.startswith("find")]
    assert all("-maxdepth" in f for f in finds)


def test_list_markdown_files_no_workspace(client, db, admin_headers, monkeypatch):
    asn = _seed(db, workspace_path=None)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.get(f"/api/assessments/{asn.id}/markdown/files", headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == []


def test_markdown_content_success(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    replies = [
        {"success": True, "returncode": 0, "stdout": "exists\n", "stderr": ""},
        {"success": True, "returncode": 0, "stdout": "# Notes\ncontent", "stderr": ""},
    ]
    FakeCS.handler = staticmethod(lambda cmd: replies.pop(0))
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.get(f"/api/assessments/{asn.id}/markdown/content",
                     params={"path": "notes/todo.md"}, headers=admin_headers)
    assert res.status_code == 200
    assert res.json() == {"filename": "todo.md", "path": "notes/todo.md",
                          "content": "# Notes\ncontent"}
    assert FakeCS.commands[0].startswith("test -f /workspace/cd/notes/todo.md")
    assert FakeCS.commands[1] == "cat /workspace/cd/notes/todo.md"


def test_markdown_content_validation(client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.get(f"/api/assessments/{asn.id}/markdown/content",
                     params={"path": "../secret.md"}, headers=admin_headers)
    assert res.status_code == 400
    res = client.get(f"/api/assessments/{asn.id}/markdown/content",
                     params={"path": "/abs/path.md"}, headers=admin_headers)
    assert res.status_code == 400
    res = client.get(f"/api/assessments/{asn.id}/markdown/content",
                     params={"path": "notes/todo.txt"}, headers=admin_headers)
    assert res.status_code == 400
    assert FakeCS.commands == []  # rejected before any container call


def test_markdown_content_not_found_and_read_failure(
        client, db, admin_headers, monkeypatch):
    asn = _seed(db)
    FakeCS.handler = staticmethod(
        lambda cmd: {"success": False, "returncode": 1, "stdout": "", "stderr": "missing"})
    monkeypatch.setattr("api.context_documents.ContainerService", FakeCS)
    res = client.get(f"/api/assessments/{asn.id}/markdown/content",
                     params={"path": "gone.md"}, headers=admin_headers)
    assert res.status_code == 404

    replies = [
        {"success": True, "returncode": 0, "stdout": "exists\n", "stderr": ""},
        {"success": False, "returncode": 1, "stdout": "", "stderr": "permission denied"},
    ]
    FakeCS.handler = staticmethod(lambda cmd: replies.pop(0))
    res = client.get(f"/api/assessments/{asn.id}/markdown/content",
                     params={"path": "locked.md"}, headers=admin_headers)
    assert res.status_code == 500
    assert "permission denied" in res.json()["detail"]
