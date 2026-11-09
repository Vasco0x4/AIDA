"""
Integration tests for notification channels (api/notifications.py +
services/notification_service.py).

Channel CRUD and the report builder run against the real DB; every endpoint
that would touch the outside world (Telegram/Slack/SMTP/PDF rendering) is
mocked — the suite is hermetic.
"""
from __future__ import annotations

import json
import pytest

from middleware.rate_limit import limiter
from models.assessment import Assessment
from models.card import Card
from models.command_history import CommandHistory
from models.notification_config import NotificationConfig
from services.notification_service import NotificationService


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    limiter.reset()
    yield
    limiter.reset()


TELEGRAM_BODY = {
    "channel": "telegram",
    "enabled": True,
    "config": {"bot_token": "123:abc", "chat_id": "42"},
    "on_critical_finding": True,
    "on_high_finding": False,
    "on_scan_complete": True,
    "on_assessment_complete": False,
}


def _assessment(db, name="notify-me") -> Assessment:
    a = Assessment(name=name, scope="127.0.0.1", status="active",
                   client_name="ACME")
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# --- CRUD ---------------------------------------------------------------------------

def test_list_empty(client, db, viewer_headers):
    r = client.get("/api/notifications", headers=viewer_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_put_upserts_channel(client, db, admin_headers):
    r = client.put("/api/notifications/telegram", headers=admin_headers,
                   json=TELEGRAM_BODY)
    assert r.status_code == 200
    body = r.json()
    assert body["channel"] == "telegram"
    assert body["enabled"] is True
    assert body["config"]["chat_id"] == "42"

    # PUT again updates in place
    r = client.put("/api/notifications/telegram", headers=admin_headers,
                   json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False
    assert r.json()["config"] == {"bot_token": "123:abc", "chat_id": "42"}


def test_get_channel(client, db, admin_headers):
    client.put("/api/notifications/slack", headers=admin_headers,
               json={"config": {"webhook_url": "https://hooks.example/x"}})
    r = client.get("/api/notifications/slack", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["channel"] == "slack"
    assert client.get("/api/notifications/email",
                      headers=admin_headers).status_code == 404


def test_post_create_and_conflict(client, db, admin_headers):
    body = {k: v for k, v in TELEGRAM_BODY.items() if k != "channel"}
    r = client.post("/api/notifications", headers=admin_headers,
                    json={"channel": "telegram", **body})
    assert r.status_code == 201
    # Duplicate create → 409 (PUT is the update path)
    r = client.post("/api/notifications", headers=admin_headers,
                    json={"channel": "telegram", **body})
    assert r.status_code == 409


def test_delete_channel(client, db, admin_headers):
    client.put("/api/notifications/telegram", headers=admin_headers, json={})
    assert client.delete("/api/notifications/telegram",
                         headers=admin_headers).status_code == 204
    assert client.delete("/api/notifications/telegram",
                         headers=admin_headers).status_code == 404


def test_writes_require_auditor_role(client, db, viewer_headers):
    assert client.put("/api/notifications/telegram", headers=viewer_headers,
                      json=TELEGRAM_BODY).status_code == 403
    assert client.post("/api/notifications", headers=viewer_headers,
                       json={"channel": "x"}).status_code == 403


# --- test notification ----------------------------------------------------------------

def test_channel_with_no_config_fails_cleanly(client, db, admin_headers):
    r = client.post("/api/notifications/test", headers=admin_headers,
                    json={"channel": "telegram"})
    assert r.status_code == 200
    assert r.json() == {"success": False,
                        "message": "No configuration found for channel: telegram"}


def test_test_channel_success(client, db, admin_headers, monkeypatch):
    client.put("/api/notifications/telegram", headers=admin_headers,
               json=TELEGRAM_BODY)
    sent = []

    async def fake_send(self, config, message):
        sent.append((config.channel, message))

    monkeypatch.setattr(NotificationService, "_send", fake_send)
    r = client.post("/api/notifications/test", headers=admin_headers,
                    json={"channel": "telegram"})
    assert r.status_code == 200
    assert r.json()["success"] is True
    assert sent and sent[0][0] == "telegram"
    assert "Test Notification" in sent[0][1]


def test_test_channel_failure_reported(client, db, admin_headers, monkeypatch):
    client.put("/api/notifications/telegram", headers=admin_headers,
               json=TELEGRAM_BODY)

    async def boom(self, config, message):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(NotificationService, "_send", boom)
    r = client.post("/api/notifications/test", headers=admin_headers,
                    json={"channel": "telegram"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "telegram down" in body["message"]


# --- send report ------------------------------------------------------------------------

def _enable_channel(client, headers):
    client.put("/api/notifications/telegram", headers=headers,
               json=TELEGRAM_BODY)


def test_send_report_unconfigured_channel(client, db, admin_headers):
    a = _assessment(db)
    r = client.post(f"/api/notifications/send-report/{a.id}",
                    headers=admin_headers, json={"channel": "slack"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "not configured" in body["message"]


def test_send_report_disabled_channel(client, db, admin_headers):
    a = _assessment(db)
    client.put("/api/notifications/telegram", headers=admin_headers,
               json={"enabled": False, "config": {"bot_token": "1", "chat_id": "2"}})
    r = client.post(f"/api/notifications/send-report/{a.id}",
                    headers=admin_headers, json={"channel": "telegram"})
    assert r.status_code == 200
    assert "disabled" in r.json()["message"]


def test_send_report_success(client, db, admin_headers, monkeypatch):
    a = _assessment(db)
    _enable_channel(client, admin_headers)

    import io

    async def fake_pdf(db_, assessment_id):
        return io.BytesIO(b"%PDF-1.4 fake")

    delivered = []

    async def fake_send_file(self, config, file_bytes, filename, caption=""):
        delivered.append((filename, caption))

    import services.report_service as report_svc
    monkeypatch.setattr(report_svc, "generate_pdf_report", fake_pdf)
    monkeypatch.setattr(NotificationService, "_send_file", fake_send_file)

    r = client.post(f"/api/notifications/send-report/{a.id}",
                    headers=admin_headers,
                    json={"channel": "telegram", "custom_message": "final report"})
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["channel"] == "telegram"
    assert delivered[0][0] == "AIDA_Report_notify-me.pdf"
    assert "final report" in delivered[0][1]


def test_send_report_pdf_failure_reported(client, db, admin_headers, monkeypatch):
    a = _assessment(db)
    _enable_channel(client, admin_headers)

    async def boom(db_, assessment_id):
        raise RuntimeError("render failed")

    import services.report_service as report_svc
    monkeypatch.setattr(report_svc, "generate_pdf_report", boom)
    r = client.post(f"/api/notifications/send-report/{a.id}",
                    headers=admin_headers, json={"channel": "telegram"})
    assert r.status_code == 200
    assert r.json()["success"] is False
    assert "PDF" in r.json()["message"]


# --- report builder (service level) --------------------------------------------------------

def test_build_assessment_report_content(db):
    a = _assessment(db, "report-src")
    db.add(Card(assessment_id=a.id, card_type="finding", title="SQL injection",
                severity="CRITICAL", target_service="login", status="confirmed"))
    db.add(Card(assessment_id=a.id, card_type="finding", title="XSS",
                severity="LOW"))
    db.add(Card(assessment_id=a.id, card_type="observation", title="Old TLS"))
    db.add(CommandHistory(assessment_id=a.id, command="nmap -sV target",
                          success=True, returncode=0))
    db.commit()

    svc = NotificationService(db)
    report = svc.build_assessment_report(a.id, include_findings=True,
                                         include_stats=True,
                                         include_commands=True,
                                         custom_message="hello world")
    assert "AIDA Assessment Report" in report
    assert "Name: report-src" in report
    assert "Client: ACME" in report
    assert "Total Findings: 2" in report
    assert "Observations: 1" in report
    assert "[CRITICAL] SQL injection" in report
    assert "hello world" in report
    assert "nmap -sV target" in report


def test_build_assessment_report_unknown_id(db):
    assert NotificationService(db).build_assessment_report(9999) == \
        "Assessment not found"


# --- service-level delivery logic (senders mocked at the HTTP boundary) ------------


@pytest.fixture()
def channel_factory(db):
    def _add(channel, enabled=True, **flags):
        row = NotificationConfig(channel=channel, enabled=enabled, config={},
                                 on_critical_finding=flags.get("critical", True),
                                 on_high_finding=flags.get("high", True),
                                 on_scan_complete=flags.get("scan", False),
                                 on_assessment_complete=flags.get("done", False))
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
    return _add


def test_notify_finding_fans_out_by_severity(db, channel_factory, monkeypatch):
    import asyncio
    crit_only = channel_factory("telegram", critical=True, high=False)
    all_high = channel_factory("slack", critical=False, high=True)
    sent = []

    async def fake_send(self, config, message):
        sent.append((config.id, message))

    monkeypatch.setattr(NotificationService, "_send", fake_send)
    svc = NotificationService(db)

    asyncio.run(svc.notify_finding("web-app", "SQLi", "CRITICAL", "details"))
    assert [c for c, _ in sent] == [crit_only.id]
    assert "CRITICAL" in sent[0][1] and "SQLi" in sent[0][1]

    sent.clear()
    asyncio.run(svc.notify_finding("web-app", "XSS", "HIGH"))
    assert [c for c, _ in sent] == [all_high.id]

    sent.clear()
    asyncio.run(svc.notify_finding("web-app", "note", "MEDIUM"))
    assert sent == []  # only CRITICAL/HIGH are notifiable


def test_notify_scan_and_assessment_complete(db, channel_factory, monkeypatch):
    on_scan = channel_factory("telegram", scan=True)
    on_done = channel_factory("slack", scan=False, done=True)
    sent = []

    async def fake_send(self, config, message):
        sent.append((config.id, message))

    monkeypatch.setattr(NotificationService, "_send", fake_send)
    svc = NotificationService(db)

    import asyncio
    asyncio.run(svc.notify_scan_complete("web-app", "nmap -sV x", "3 hosts"))
    assert [c for c, _ in sent] == [on_scan.id]
    assert "nmap -sV x" in sent[0][1]

    sent.clear()
    asyncio.run(svc.notify_assessment_complete("web-app"))
    assert [c for c, _ in sent] == [on_done.id]
    assert sent[0][1] == "Assessment Complete: web-app"


def test_disabled_channels_never_send(db, channel_factory, monkeypatch):
    channel_factory("telegram", enabled=False, critical=True)
    sent = []

    async def fake_send(self, config, message):
        sent.append(config.id)

    monkeypatch.setattr(NotificationService, "_send", fake_send)
    import asyncio
    asyncio.run(NotificationService(db).notify_finding("a", "t", "CRITICAL"))
    assert sent == []


def _mock_ns_httpx(monkeypatch, status_code=200, text=""):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, data=None, files=None,
                       content=None, headers=None):
            class _Resp:
                pass
            resp = _Resp()
            resp.status_code = status_code
            resp.text = text
            resp.requested = {"url": url, "json": json, "data": data,
                              "files": files, "content": content,
                              "headers": headers or {}}
            _mock_ns_httpx.calls.append(resp)
            return resp

    _mock_ns_httpx.calls = []
    import services.notification_service as ns
    monkeypatch.setattr(ns.httpx, "AsyncClient", _Client)


def test_webhook_sender_signs_payload(db, monkeypatch):
    import asyncio
    import hashlib
    import hmac as _hmac
    import json as _json
    import services.notification_service as ns

    _mock_ns_httpx(monkeypatch)
    cfg = {"url": "https://jira.example/hook", "secret": "s3cret"}
    asyncio.run(ns.NotificationService._send_webhook(None, cfg, "hello"))

    resp = _mock_ns_httpx.calls[0]
    assert resp.requested["url"] == "https://jira.example/hook"
    payload = resp.requested["content"]
    body = _json.loads(payload)
    assert body["event"] == "notification" and body["text"] == "hello"
    expected = "sha256=" + _hmac.new(b"s3cret", payload,
                                     hashlib.sha256).hexdigest()
    assert resp.requested["headers"]["X-AIDA-Signature"] == expected


def test_webhook_sender_requires_url_and_raises_on_error(db, monkeypatch):
    import asyncio
    import services.notification_service as ns

    with pytest.raises(ValueError):
        asyncio.run(ns.NotificationService._send_webhook(None, {}, "m"))

    _mock_ns_httpx(monkeypatch, status_code=500, text="nope")
    with pytest.raises(RuntimeError):
        asyncio.run(ns.NotificationService._send_webhook(
            None, {"url": "https://x.example"}, "m"))


def test_telegram_sender_validation_and_error(db, monkeypatch):
    import asyncio
    import services.notification_service as ns

    with pytest.raises(ValueError):
        asyncio.run(ns.NotificationService._send_telegram(
            None, {"chat_id": "1"}, "m"))

    _mock_ns_httpx(monkeypatch, status_code=400, text="Bad Request")
    with pytest.raises(RuntimeError):
        asyncio.run(ns.NotificationService._send_telegram(
            None, {"bot_token": "t", "chat_id": "1"}, "m"))

    _mock_ns_httpx(monkeypatch, status_code=200)
    asyncio.run(ns.NotificationService._send_telegram(
        None, {"bot_token": "t", "chat_id": "1"}, "m"))
    assert _mock_ns_httpx.calls[0].requested["url"].startswith(
        "https://api.telegram.org/bot")


def test_slack_sender_validation_and_error(db, monkeypatch):
    import asyncio
    import services.notification_service as ns

    with pytest.raises(ValueError):
        asyncio.run(ns.NotificationService._send_slack(None, {}, "m"))

    _mock_ns_httpx(monkeypatch, status_code=403, text="no")
    with pytest.raises(RuntimeError):
        asyncio.run(ns.NotificationService._send_slack(
            None, {"webhook_url": "https://hooks.example/x"}, "m"))


def test_email_sender_requires_smtp_config(db):
    import asyncio
    import services.notification_service as ns

    with pytest.raises(ValueError):
        asyncio.run(ns.NotificationService._send_email(
            None, {"smtp_host": ""}, "m"))
    with pytest.raises(ValueError):
        asyncio.run(ns.NotificationService._send_email(
            None, {"smtp_host": "smtp.example", "to_emails": []}, "m"))


def test_send_routes_unknown_channel_without_raising(db):
    import asyncio
    row = NotificationConfig(channel="pigeonpost", enabled=True, config={})
    db.add(row)
    db.commit()
    # Unknown channel inside _send logs a warning and returns — never raises
    asyncio.run(NotificationService(db)._send(row, "message"))


def test_send_file_routes_webhook_as_plain_message(db, monkeypatch):
    import asyncio
    row = NotificationConfig(channel="webhook", enabled=True,
                             config={"url": "https://hooks.example/x"})
    db.add(row)
    db.commit()

    _mock_ns_httpx(monkeypatch, status_code=200)
    asyncio.run(NotificationService(db)._send_file(row, b"PDFBYTES",
                                                   "r.pdf", "caption"))
    resp = _mock_ns_httpx.calls[0]
    body = json.loads(resp.requested["content"])
    assert "caption" in body["text"]  # webhooks can't carry attachments


def test_send_telegram_file(db, monkeypatch):
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(NotificationService._send_telegram_file(
            None, {"chat_id": "1"}, b"pdf", "r.pdf", "cap"))

    _mock_ns_httpx(monkeypatch, status_code=200)
    asyncio.run(NotificationService._send_telegram_file(
        None, {"bot_token": "t", "chat_id": "1"}, b"pdf", "r.pdf", "cap"))
    call = _mock_ns_httpx.calls[0]
    assert "/sendDocument" in call.requested["url"]
    assert call.requested["files"]["document"][0] == "r.pdf"

    _mock_ns_httpx(monkeypatch, status_code=400, text="nope")
    with pytest.raises(RuntimeError):
        asyncio.run(NotificationService._send_telegram_file(
            None, {"bot_token": "t", "chat_id": "1"}, b"pdf", "r.pdf", "cap"))


def test_send_slack_file(db, monkeypatch):
    import asyncio
    with pytest.raises(ValueError):
        asyncio.run(NotificationService._send_slack_file(None, {}, b"pdf",
                                                         "r.pdf", "cap"))
    _mock_ns_httpx(monkeypatch, status_code=200)
    asyncio.run(NotificationService._send_slack_file(
        None, {"webhook_url": "https://hooks.example/x"}, b"pdf", "r.pdf", "cap"))
    body = _mock_ns_httpx.calls[0].requested["json"]
    assert "PDF report generated" in body["text"]


def test_send_email_file(db, monkeypatch):
    import asyncio
    svc = NotificationService(db)
    cfg = {"smtp_host": "smtp.example", "smtp_port": 587,
           "to_emails": ["soc@example.com"]}
    with pytest.raises(ValueError):
        asyncio.run(svc._send_email_file({}, b"pdf", "r.pdf", "cap"))

    delivered = []

    def fake_smtp_send(host, port, username, password, from_email,
                       to_emails, msg, encryption="starttls"):
        delivered.append((host, port, to_emails, msg.as_string(),
                          encryption))

    monkeypatch.setattr(NotificationService, "_smtp_send",
                        staticmethod(fake_smtp_send))
    asyncio.run(svc._send_email_file(cfg, b"pdf", "r.pdf", "cap"))
    host, port, tos, raw, encryption = delivered[0]
    assert (host, port, tos) == ("smtp.example", 587, ["soc@example.com"])
    assert "Subject: AIDA Report - r.pdf" in raw


def test_smtp_send_starttls_and_ssl(monkeypatch):
    import services.notification_service as ns
    from email.mime.text import MIMEText

    calls = []

    class _SMTP:
        def __init__(self, host, port):
            calls.append(("plain", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u))

        def sendmail(self, from_email, to_emails, body):
            calls.append(("sendmail", from_email, to_emails))

    class _SMTPSSL(_SMTP):
        def __init__(self, host, port):
            calls.append(("ssl", host, port))

    monkeypatch.setattr(ns.smtplib, "SMTP", _SMTP)
    monkeypatch.setattr(ns.smtplib, "SMTP_SSL", _SMTPSSL)

    msg = MIMEText("hello")
    msg["From"] = "a@x"
    msg["To"] = "b@y"
    msg["Subject"] = "s"

    # starttls + auth
    ns.NotificationService._smtp_send("smtp.example", 587, "u", "p",
                                      "a@x", ["b@y"], msg, "starttls")
    assert ("starttls",) in calls and ("login", "u") in calls
    # plain, no auth
    calls.clear()
    ns.NotificationService._smtp_send("smtp.example", 25, "", "",
                                      "a@x", ["b@y"], msg, "none")
    assert ("starttls",) not in calls and ("login", "u") not in calls
    assert ("sendmail", "a@x", ["b@y"]) in calls
    # ssl
    ns.NotificationService._smtp_send("smtp.example", 465, "u", "p",
                                      "a@x", ["b@y"], msg, "ssl")
    assert ("ssl", "smtp.example", 465) in calls
