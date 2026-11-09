import asyncio
import io
import json
import stat
import zipfile
import pytest
from services.appsec_source import read_source, repository, fetch_repository, SourceError
from services.appsec_analyzer import analyze, ai_payload, parse_ai


def source_zip(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_source_never_extracts_traversal():
    for path in ("../bad.py", "/root/bad.py", "a/../../bad.py", "a\\bad.py", "C:bad.py"):
        with pytest.raises(SourceError):
            read_source(source_zip({path: "print(1)"}))


def test_binary_symlink_and_exclusions_are_visible():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        link = zipfile.ZipInfo("link.py")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/etc/passwd")
        archive.writestr("node_modules/a.js", "eval(x)")
        archive.writestr("binary.dat", b"\x00")
        archive.writestr("app.py", "print(1)")
    files, coverage = read_source(output.getvalue())
    assert list(files) == ["app.py"]
    assert coverage["skipped"] == {"symlinks": 1, "excluded directories": 1, "binary files": 1}


def test_zip_bomb_duplicate_and_invalid_archives_fail():
    with pytest.raises(SourceError):
        read_source(source_zip({"large": "a" * (21 * 1024 * 1024)}))
    with pytest.raises(SourceError):
        read_source(b"not a zip")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("a.py", "a")
        archive.writestr("a.py", "b")
    with pytest.raises(SourceError):
        read_source(output.getvalue())


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/a/b",
        "https://localhost/a/b",
        "https://github.com.evil/a/b",
        "https://user:pass@github.com/a/b",
        "file:///tmp/repo",
        "https://github.com/a/b/tree/main",
        "https://gitlab.com/a/../b",
    ],
)
def test_repository_rejects_unsafe_origins(url):
    with pytest.raises(SourceError):
        repository(url)


@pytest.mark.parametrize(
    "url,host",
    [("https://github.com/team/repo.git", "github.com"), ("https://gitlab.com/team/group/repo", "gitlab.com")],
)
def test_repository_resolves_commit_before_archive(monkeypatch, url, host):
    from services import appsec_source

    sha = "a" * 40
    calls = []

    def download(address, limit=0):
        calls.append(address)
        if len(calls) == 1:
            return json.dumps({"sha": sha, "id": sha}).encode()
        return source_zip({"repo/app.py": "print(1)"})

    monkeypatch.setattr(appsec_source, "_download", download)
    resolved, archive, digest = fetch_repository(url, "feature/security")
    assert resolved == sha and len(digest) == 64
    assert sha in calls[1] and "feature/security" not in calls[1]
    assert list(read_source(archive, strip_root=True)[0]) == ["app.py"]


def test_rules_detect_candidates_without_exposing_secret():
    secret = "ghp_" + "a" * 36
    files = {
        "app.py": "import subprocess as sp\nsp.run(user_input, shell=True)\neval(user_input)\n",
        ".env": f"TOKEN={secret}",
        "web.js": "element.innerHTML = input;",
        "package.json": json.dumps(
            {"dependencies": {"demo": "^1.0.0", "private": "https://user:credential@example.invalid/package"}}
        ),
    }
    rows, summary = analyze(files)
    assert {"python.shell", "python.dynamic-code", "javascript.innerhtml", "secret.github-token"} <= {
        x["rule_id"] for x in rows
    }
    assert secret not in json.dumps(rows)
    assert "credential" not in json.dumps(summary["dependencies"])
    assert summary["dependency_advisories"] == "not_checked"


def test_ai_payload_masks_entire_private_key_and_preserves_line_numbers():
    content = 'key = """-----BEGIN PRIVATE KEY-----\nSENSITIVEBODY\n-----END PRIVATE KEY-----"""\nprint(1)'
    payload = ai_payload({"app.py": content})
    assert "SENSITIVEBODY" not in payload["app.py"]
    assert "4: print(1)" in payload["app.py"]
    assert not ai_payload({"big.py": "a" * 50000, ".env": "PASSWORD=123"})


def test_ai_findings_must_point_to_supplied_source():
    item = {"path": "app.py", "line": 1, "title": "Candidate", "description": "Reason", "recommendation": "Fix"}
    rows = parse_ai(
        json.dumps({"findings": [item, {**item, "path": "/etc/passwd"}, {**item, "line": 900}]}), {"app.py": "print(1)"}
    )
    assert len(rows) == 1 and rows[0]["confidence"] == "low"


def test_read_only_role_and_unauthenticated_requests(client, viewer_headers):
    assert client.get("/api/appsec/projects").status_code == 401
    assert client.get("/api/appsec/projects", headers=viewer_headers).status_code == 200
    assert client.post("/api/appsec/projects", headers=viewer_headers, json={"name": "Denied"}).status_code == 403


def test_full_upload_review_triage_report_and_task(client, admin_headers, db, runtime_sessions):
    from models.appsec import AppSecScan
    from models.task import Task
    from services.appsec_worker import process_scan

    project = client.post("/api/appsec/projects", headers=admin_headers, json={"name": "Fixture AppSec"}).json()
    archive = source_zip({"app.py": "eval(user_input)\n", "requirements.txt": "requests==2.32.0\n"})
    url = f"/api/appsec/projects/{project['id']}/upload?commit=" + "a" * 40
    response = client.post(url, headers={**admin_headers, "Content-Type": "application/zip"}, content=archive)
    assert response.status_code == 202, response.text
    scan_id = response.json()["id"]
    assert "archive" not in response.json()
    assert client.post(url, headers=admin_headers, content=archive).status_code == 409
    row = db.get(AppSecScan, scan_id)
    row.status = "running"
    db.commit()
    asyncio.run(process_scan(scan_id, runtime_sessions))
    result = client.get(f"/api/appsec/scans/{scan_id}", headers=admin_headers).json()
    assert result["status"] == "completed" and result["summary"]["commit_provenance"] == "uploader_asserted"
    finding = result["findings"][0]
    assert (
        client.patch(
            f"/api/appsec/findings/{finding['id']}", headers=admin_headers, json={"status": "confirmed"}
        ).status_code
        == 200
    )
    task_url = f"/api/appsec/findings/{finding['id']}/task"
    task = client.post(task_url, headers=admin_headers).json()
    assert client.post(task_url, headers=admin_headers).json() == task
    db.expire_all()
    assert db.get(Task, task["task_id"]).status == "backlog"
    assert db.get(AppSecScan, scan_id).archive is None
    for format in ("json", "html", "sarif"):
        response = client.get(f"/api/appsec/scans/{scan_id}/report?format={format}", headers=admin_headers)
        assert response.status_code == 200
    sarif = client.get(f"/api/appsec/scans/{scan_id}/report?format=sarif", headers=admin_headers).json()
    assert sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]["startLine"] == 1


def test_cancelled_scan_cannot_publish_results(client, admin_headers, db, runtime_sessions):
    from models.appsec import AppSecScan
    from services.appsec_worker import process_scan

    project = client.post("/api/appsec/projects", headers=admin_headers, json={"name": "Cancel fixture"}).json()
    response = client.post(
        f"/api/appsec/projects/{project['id']}/upload?commit=" + "b" * 40,
        headers=admin_headers,
        content=source_zip({"app.py": "eval(x)"}),
    )
    scan_id = response.json()["id"]
    assert client.post(f"/api/appsec/scans/{scan_id}/cancel", headers=admin_headers).status_code == 200
    asyncio.run(process_scan(scan_id, runtime_sessions))
    db.expire_all()
    assert db.get(AppSecScan, scan_id).status == "cancelled"
    assert db.get(AppSecScan, scan_id).archive is None
    assert client.get(f"/api/appsec/scans/{scan_id}/report", headers=admin_headers).status_code == 409


def test_ai_requires_explicit_consent(client, admin_headers, db):
    from models.ai_model_config import AIModelConfig

    cfg = AIModelConfig(
        name="fixture-model", provider="custom", base_url="https://example.invalid", model="test", enabled=True
    )
    db.add(cfg)
    db.commit()
    project = client.post(
        "/api/appsec/projects",
        headers=admin_headers,
        json={"name": "Consent", "repository_url": "https://github.com/a/b"},
    ).json()
    result = client.post(
        f"/api/appsec/projects/{project['id']}/scans", headers=admin_headers, json={"model_config_id": cfg.id}
    )
    assert result.status_code == 422


def test_invalid_zip_and_sha_do_not_queue(client, admin_headers):
    project = client.post("/api/appsec/projects", headers=admin_headers, json={"name": "Invalid"}).json()
    base = f"/api/appsec/projects/{project['id']}/upload?commit="
    assert client.post(base + "main", headers=admin_headers, content=b"bad").status_code == 422
    assert client.post(base + "a" * 40, headers=admin_headers, content=b"bad").status_code == 422


@pytest.mark.parametrize("ai_fails", [False, True])
def test_optional_ai_results_and_partial_failure(client, admin_headers, db, runtime_sessions, monkeypatch, ai_fails):
    from models.appsec import AppSecScan
    from models.ai_model_config import AIModelConfig
    from services.appsec_worker import process_scan
    from services.ai_model_service import AIModelService

    class FakeClient:
        async def chat(self, messages, **kwargs):
            assert kwargs["max_tokens"] == 4000
            assert len(messages) == 2
            if ai_fails:
                raise RuntimeError("provider failure with sensitive details")
            return {
                "content": json.dumps(
                    {
                        "findings": [
                            {
                                "path": "app.py",
                                "line": 1,
                                "title": "AI candidate",
                                "description": "Review this data flow",
                                "recommendation": "Validate input",
                            }
                        ]
                    }
                ),
                "usage": {"total_tokens": 100},
            }

    monkeypatch.setattr(AIModelService, "build_client", lambda *args: FakeClient())
    cfg = AIModelConfig(
        name="AI mock", provider="custom", base_url="https://example.invalid", model="test", enabled=True
    )
    db.add(cfg)
    db.commit()
    project = client.post("/api/appsec/projects", headers=admin_headers, json={"name": "AI fixture"}).json()
    result = client.post(
        f"/api/appsec/projects/{project['id']}/upload?commit="
        + "c" * 40
        + f"&model_config_id={cfg.id}&allow_source_to_model=true",
        headers=admin_headers,
        content=source_zip({"app.py": "eval(user_input)"}),
    )
    assert result.status_code == 202, result.text
    scan_id = result.json()["id"]
    row = db.get(AppSecScan, scan_id)
    row.status = "running"
    db.commit()
    asyncio.run(process_scan(scan_id, runtime_sessions))
    data = client.get(f"/api/appsec/scans/{scan_id}", headers=admin_headers).json()
    assert data["status"] == ("partial" if ai_fails else "completed")
    assert len(data["findings"]) == (1 if ai_fails else 2)
    assert "sensitive details" not in json.dumps(data)


def test_baseline_retains_triage_and_html_escapes_paths(client, admin_headers, db, runtime_sessions):
    from models.appsec import AppSecScan
    from services.appsec_worker import process_scan

    project = client.post("/api/appsec/projects", headers=admin_headers, json={"name": "Comparison fixture"}).json()

    def run(sha):
        response = client.post(
            f"/api/appsec/projects/{project['id']}/upload?commit={sha}",
            headers=admin_headers,
            content=source_zip({"<img src=x>.py": "eval(x)"}),
        )
        ident = response.json()["id"]
        row = db.get(AppSecScan, ident)
        row.status = "running"
        db.commit()
        asyncio.run(process_scan(ident, runtime_sessions))
        return client.get(f"/api/appsec/scans/{ident}", headers=admin_headers).json()

    first = run("a" * 40)
    client.patch(
        f"/api/appsec/findings/{first['findings'][0]['id']}", headers=admin_headers, json={"status": "false_positive"}
    )
    second = run("b" * 40)
    assert second["summary"]["new_findings"] == 0
    assert second["findings"][0]["status"] == "false_positive"
    report = client.get(f"/api/appsec/scans/{second['id']}/report?format=html", headers=admin_headers)
    assert "<img src=x>" not in report.text and "&lt;img src=x&gt;" in report.text
