"""
Task extras API — comments + context file attachments on /api/tasks.

Comments: thread per task, author resolved from the JWT identity. Files:
upload with best-effort text extraction (txt/md/html/pdf/binary), 15 MB cap,
inline content streaming, deletion. Extraction edge cases are pinned through
the upload endpoint plus direct calls to extract_text.
"""
from __future__ import annotations

import pytest

from models.task import Task
from models.task_comment import TaskComment
from models.task_file import TaskFile


@pytest.fixture()
def task(db):
    t = Task(title="extras-task", status="backlog")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ------------------------------------------------------------------ comments
def test_comments_require_auth(client, task):
    assert client.get(f"/api/tasks/{task.id}/comments").status_code == 401


def test_add_and_list_comments(client, db, admin_headers, task):
    r = client.post(f"/api/tasks/{task.id}/comments", headers=admin_headers,
                    json={"body": "  focus on the login flow  "})
    assert r.status_code == 201
    body = r.json()
    assert body["author"] == "admin"       # from the JWT, not the payload
    assert body["body"] == "focus on the login flow"  # stripped
    assert body["task_id"] == task.id

    client.post(f"/api/tasks/{task.id}/comments", headers=admin_headers,
                json={"body": "second"})
    r = client.get(f"/api/tasks/{task.id}/comments", headers=admin_headers)
    assert [c["body"] for c in r.json()] == \
        ["focus on the login flow", "second"]


def test_add_comment_unknown_task_404(client, admin_headers):
    r = client.post("/api/tasks/404/comments", headers=admin_headers,
                    json={"body": "hi"})
    assert r.status_code == 404


def test_add_comment_requires_body_422(client, admin_headers, task):
    assert client.post(f"/api/tasks/{task.id}/comments",
                       headers=admin_headers, json={}).status_code == 422


def test_delete_comment(client, db, admin_headers, task):
    row = TaskComment(task_id=task.id, author="admin", body="bye")
    db.add(row)
    db.commit()
    assert client.delete(f"/api/tasks/comments/{row.id}",
                         headers=admin_headers).status_code == 204
    assert db.query(TaskComment).count() == 0
    assert client.delete(f"/api/tasks/comments/{row.id}",
                         headers=admin_headers).status_code == 404


def test_comment_write_requires_auditor(client, viewer_headers, task):
    r = client.post(f"/api/tasks/{task.id}/comments", headers=viewer_headers,
                    json={"body": "viewer says"})
    assert r.status_code == 403


# ------------------------------------------------------------------ files
def test_upload_txt_extracts_text(client, db, admin_headers, task):
    r = client.post(f"/api/tasks/{task.id}/files", headers=admin_headers,
                    files={"file": ("notes.txt", b"read this first",
                                    "text/plain")})
    assert r.status_code == 201
    body = r.json()
    assert body["filename"] == "notes.txt"
    assert body["size_bytes"] == len(b"read this first")
    assert body["has_text"] is True
    row = db.query(TaskFile).one()
    assert row.extracted_text == "read this first"
    assert row.data == b"read this first"


def test_upload_html_strips_tags(client, db, admin_headers, task):
    html = (b"<html><head><style>body{color:red}</style></head>"
            b"<body><script>evil()</script><h1>Title</h1> text &nbsp;here"
            b"</body></html>")
    r = client.post(f"/api/tasks/{task.id}/files", headers=admin_headers,
                    files={"file": ("page.html", html, "text/html")})
    assert r.status_code == 201
    text = db.query(TaskFile).one().extracted_text
    assert "Title" in text and "text here" in text
    assert "evil()" not in text and "color:red" not in text


def test_upload_binary_has_no_text(client, db, admin_headers, task):
    r = client.post(f"/api/tasks/{task.id}/files", headers=admin_headers,
                    files={"file": ("blob.bin", b"\x00\xff\xfe\xfd",
                                    "application/octet-stream")})
    assert r.status_code == 201
    assert r.json()["has_text"] is False


def test_upload_invalid_pdf_falls_back(client, db, admin_headers, task):
    r = client.post(f"/api/tasks/{task.id}/files", headers=admin_headers,
                    files={"file": ("doc.pdf", b"not a real pdf",
                                    "application/pdf")})
    assert r.status_code == 201
    text = db.query(TaskFile).one().extracted_text
    assert text == "(PDF text extraction unavailable)"


def test_upload_empty_file_422(client, admin_headers, task):
    r = client.post(f"/api/tasks/{task.id}/files", headers=admin_headers,
                    files={"file": ("empty.txt", b"", "text/plain")})
    assert r.status_code == 422
    assert "Empty" in r.json()["detail"]


def test_upload_too_large_413(client, admin_headers, task):
    big = b"x" * (15 * 1024 * 1024 + 1)
    r = client.post(f"/api/tasks/{task.id}/files", headers=admin_headers,
                    files={"file": ("big.txt", big, "text/plain")})
    assert r.status_code == 413
    assert "15 MB" in r.json()["detail"]


def test_upload_unknown_task_404(client, admin_headers):
    r = client.post("/api/tasks/405/files", headers=admin_headers,
                    files={"file": ("x.txt", b"data", "text/plain")})
    assert r.status_code == 404


def test_list_files_meta(client, db, admin_headers, task):
    db.add(TaskFile(task_id=task.id, filename="a.txt", content_type="text/plain",
                    size_bytes=1, extracted_text="t", data=b"t"))
    db.add(TaskFile(task_id=task.id, filename="b.bin",
                    content_type="application/octet-stream",
                    size_bytes=2, extracted_text="", data=b"\x00"))
    db.commit()
    r = client.get(f"/api/tasks/{task.id}/files", headers=admin_headers)
    assert r.status_code == 200
    metas = {m["filename"]: m for m in r.json()}
    assert metas["a.txt"]["has_text"] is True
    assert metas["b.bin"]["has_text"] is False
    assert "data" not in metas["a.txt"]  # metadata only, no payload


def test_get_file_content_streams_bytes(client, db, admin_headers, task):
    row = TaskFile(task_id=task.id, filename="report.md",
                   content_type="text/markdown", size_bytes=4,
                   extracted_text="abcd", data=b"abcd")
    db.add(row)
    db.commit()
    r = client.get(f"/api/tasks/files/{row.id}/content", headers=admin_headers)
    assert r.status_code == 200
    assert r.content == b"abcd"
    assert r.headers["content-type"].startswith("text/markdown")
    assert "report.md" in r.headers["content-disposition"]
    assert client.get("/api/tasks/files/999/content",
                      headers=admin_headers).status_code == 404


def test_delete_file(client, db, admin_headers, task):
    row = TaskFile(task_id=task.id, filename="x.txt",
                   content_type="text/plain", size_bytes=1,
                   extracted_text="", data=b"x")
    db.add(row)
    db.commit()
    assert client.delete(f"/api/tasks/files/{row.id}",
                         headers=admin_headers).status_code == 204
    assert db.query(TaskFile).count() == 0
    assert client.delete(f"/api/tasks/files/{row.id}",
                         headers=admin_headers).status_code == 404


# ------------------------------------------------------------------ extract_text
from api.task_extras import extract_text  # noqa: E402


@pytest.mark.parametrize("filename,ctype,data,expected", [
    ("a.md", "text/markdown", "# hi".encode(), "# hi"),
    ("a.json", "application/json", b'{"k": 1}', '{"k": 1}'),
    ("a.log", "", b"line", "line"),
    ("", "text/csv", b"1,2", "1,2"),
    ("a.yml", "application/x-yaml", b"k: v", "k: v"),
    ("a.htm", "text/html", b"<b>x</b>", "x"),
    ("unknown.bin", "application/weird", b"abc", ""),
    # latin-1 fallback for non-utf8 bytes in a text-typed file
    ("a.txt", "text/plain", "caf\xe9".encode("latin-1"), "café"),
])
def test_extract_text_matrix(filename, ctype, data, expected):
    assert extract_text(filename, ctype, data) == expected
