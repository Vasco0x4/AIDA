"""NotificationService — channel CRUD, report building, and senders with
httpx/smtplib mocked at the boundary (no network, no SMTP)."""
from __future__ import annotations

import hashlib
import hmac
import io
import json
from email.mime.text import MIMEText

import pytest

import services.notification_service as ns
from models.assessment import Assessment
from models.card import Card
from models.command_history import CommandHistory
from models.notification_config import NotificationConfig
from services.notification_service import NotificationService


@pytest.fixture()
def svc(db):
    return NotificationService(db)


def _cfg(db, channel="telegram", enabled=True, **kw):
    row = NotificationConfig(channel=channel, enabled=enabled,
                             config=kw.pop("config", {}), **kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# --- config CRUD -------------------------------------------------------------

def test_config_crud_roundtrip(db, svc):
    assert svc.get_config("telegram") is None
    assert svc.delete_config("telegram") is False

    created = svc.upsert_config("telegram", enabled=True,
                                config={"bot_token": "t", "chat_id": "c"})
    assert created.channel == "telegram"
    fetched = svc.get_config("telegram")
    assert fetched.id == created.id

    svc.upsert_config("telegram", enabled=False)  # update, not duplicate
    assert len(svc.get_all_configs()) == 1
    assert svc.get_config("telegram").enabled is False

    assert svc.delete_config("telegram") is True
    assert svc.get_config("telegram") is None


def test_upsert_ignores_none_values(db, svc):
    svc.upsert_config("slack", enabled=True, on_scan_complete=True)
    svc.upsert_config("slack", enabled=None)  # None → no overwrite
    row = svc.get_config("slack")
    assert row.enabled is True
    assert row.on_scan_complete is True


# --- notify gating -----------------------------------------------------------

async def test_notify_finding_gates_on_severity_and_flags(db, svc, monkeypatch):
    sent = []

    async def fake_send(_self, config, message):
        sent.append((config.channel, message))

    monkeypatch.setattr(NotificationService, "_send", fake_send)
    _cfg(db, "telegram", enabled=True, on_critical_finding=True, on_high_finding=True)
    _cfg(db, "slack", enabled=False, on_critical_finding=True, on_high_finding=True)
    _cfg(db, "email", enabled=True, on_critical_finding=False, on_high_finding=True)

    await svc.notify_finding("asm", "SQLi", "CRITICAL", details="d" * 900)
    # telegram (critical on) sends; slack disabled; email opted out of critical
    assert [c for c, _ in sent] == ["telegram"]
    assert "[CRITICAL]" in sent[0][1]
    assert len(sent[0][1].split("Details: ")[1].rstrip("\n")) == 500  # truncated

    sent.clear()
    await svc.notify_finding("asm", "Header", "HIGH")
    assert [c for c, _ in sent] == ["telegram", "email"]

    sent.clear()
    await svc.notify_finding("asm", "Info", "MEDIUM")  # below HIGH → nobody
    assert sent == []


async def test_notify_scan_and_assessment_complete_gating(db, svc, monkeypatch):
    sent = []

    async def fake_send(_self, config, message):
        sent.append((config.channel, message))

    monkeypatch.setattr(NotificationService, "_send", fake_send)
    _cfg(db, "webhook", enabled=True, on_scan_complete=True,
         on_assessment_complete=False)
    _cfg(db, "email", enabled=True, on_scan_complete=False,
         on_assessment_complete=True)

    await svc.notify_scan_complete("asm", "nmap " + "x" * 400, "summary")
    assert [c for c, _ in sent] == ["webhook"]
    assert len([ln for ln in sent[0][1].splitlines() if ln.startswith("Command:")][0]) <= 210

    sent.clear()
    await svc.notify_assessment_complete("asm")
    assert [c for c, _ in sent] == ["email"]
    assert "Assessment Complete: asm" in sent[0][1]


async def test_test_channel(db, svc, monkeypatch):
    assert await svc.test_channel("nope") == (False, "No configuration found for channel: nope")

    _cfg(db, "telegram", enabled=True)

    async def ok_send(_self, config, message):
        pass

    monkeypatch.setattr(NotificationService, "_send", ok_send)
    ok, msg = await svc.test_channel("telegram")
    assert ok and "successfully" in msg

    async def bad_send(_self, config, message):
        raise RuntimeError("boom")

    monkeypatch.setattr(NotificationService, "_send", bad_send)
    ok, msg = await svc.test_channel("telegram")
    assert not ok and "boom" in msg


# --- report building ----------------------------------------------------------

def _seed_assessment(db):
    asn = Assessment(name="ACME web", client_name="ACME", scope="acme.com",
                     status="active")
    db.add(asn)
    db.commit()
    db.add(Card(assessment_id=asn.id, card_type="finding", title="SQLi",
                severity="CRITICAL", target_service="login", status="confirmed"))
    db.add(Card(assessment_id=asn.id, card_type="finding", title="XSS",
                severity="LOW", target_service="search"))
    db.add(Card(assessment_id=asn.id, card_type="observation", title="Old TLS"))
    db.add(Card(assessment_id=asn.id, card_type="info", title="note"))
    db.add(CommandHistory(assessment_id=asn.id, command="nmap -sV target",
                          success=True))
    db.add(CommandHistory(assessment_id=asn.id, command="rm -rf /",
                          success=False))
    db.commit()
    return asn


def test_build_assessment_report_sections(db, svc):
    asn = _seed_assessment(db)
    report = svc.build_assessment_report(asn.id, include_commands=True,
                                         custom_message="hello")
    assert "AIDA Assessment Report" in report
    assert "Client: ACME" in report
    assert "Scope: acme.com" in report
    assert "Total Findings: 2" in report
    assert "Observations: 1" in report
    assert "Commands Executed: 2" in report
    assert "[CRITICAL] SQLi" in report and "[LOW] XSS" in report
    assert "[OK] nmap -sV target" in report and "[FAIL] rm -rf /" in report
    assert "hello" in report
    assert report.index("SQLi") < report.index("XSS")  # severity-ordered


def test_build_assessment_report_minimal(db, svc):
    asn = _seed_assessment(db)
    report = svc.build_assessment_report(asn.id, include_findings=False,
                                         include_stats=False)
    assert "Statistics" not in report
    assert "Findings" not in report
    assert svc.build_assessment_report(424242) == "Assessment not found"


# --- send_report (PDF delivery) ----------------------------------------------

async def test_send_report_channel_gates(db, svc, monkeypatch):
    asn = _seed_assessment(db)
    no_cfg, msg = await svc.send_report("telegram", asn.id)
    assert not no_cfg and "not configured" in msg

    _cfg(db, "telegram", enabled=False)
    no_cfg, msg = await svc.send_report("telegram", asn.id)
    assert not no_cfg and "disabled" in msg


async def test_send_report_success_and_pdf_failure(db, svc, monkeypatch):
    asn = _seed_assessment(db)
    _cfg(db, "telegram", enabled=True, config={"bot_token": "b", "chat_id": "c"})

    async def fake_pdf(db_, aid):
        return io.BytesIO(b"%PDF")

    monkeypatch.setattr("services.report_service.generate_pdf_report", fake_pdf)

    files = []

    async def fake_send_file(_self, config, blob, filename, caption):
        files.append((blob, filename, caption))

    monkeypatch.setattr(NotificationService, "_send_file", fake_send_file)
    ok, msg = await svc.send_report("telegram", asn.id, custom_message="see attach")
    assert ok and files
    blob, filename, caption = files[0]
    assert blob == b"%PDF"
    assert filename == "AIDA_Report_ACME_web.pdf"
    assert "ACME web" in caption and "see attach" in caption

    async def exploding_pdf(db_, aid):
        raise RuntimeError("weasy died")

    monkeypatch.setattr("services.report_service.generate_pdf_report", exploding_pdf)
    ok, msg = await svc.send_report("telegram", asn.id)
    assert not ok and "weasy died" in msg

    async def failing_file(_self, config, blob, filename, caption):
        raise RuntimeError("telegram down")

    monkeypatch.setattr("services.report_service.generate_pdf_report", fake_pdf)
    monkeypatch.setattr(NotificationService, "_send_file", failing_file)
    ok, msg = await svc.send_report("telegram", asn.id)
    assert not ok and "telegram down" in msg


async def test_send_file_routes_by_channel(db, svc, monkeypatch):
    routed = []

    def _make_route(ch):
        async def route(_self, cfg, blob, filename, caption):
            routed.append(ch)
        return route

    def _make_msg_route(ch):
        async def route(_self, cfg, message):
            routed.append(ch)
        return route

    for ch, meth in (("telegram", "_send_telegram_file"),
                     ("slack", "_send_slack_file"),
                     ("email", "_send_email_file")):
        monkeypatch.setattr(NotificationService, meth, _make_route(ch))
        await svc._send_file(_cfg(db, ch, config={}), b"x", "f.pdf", "cap")

    # webhook falls back to the plain-text sender, not a file sender
    monkeypatch.setattr(NotificationService, "_send_webhook", _make_msg_route("webhook"))
    await svc._send_file(_cfg(db, "webhook", config={}), b"x", "f.pdf", "cap")

    assert routed == ["telegram", "slack", "email", "webhook"]

    with pytest.raises(ValueError):
        await svc._send_file(NotificationConfig(channel="carrier-pigeon"), b"x", "f", "c")


# --- outbound senders (httpx / smtp mocked) -----------------------------------

class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeHttpClient:
    last_request = None

    def __init__(self, response=None, exc=None):
        self._response = response or FakeResponse()
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kw):
        FakeHttpClient.last_request = {"url": url, **kw}
        if self._exc:
            raise self._exc
        return self._response


async def test_send_webhook_hmac_signature(monkeypatch):
    def factory(**kw):
        return FakeHttpClient()

    monkeypatch.setattr(ns.httpx, "AsyncClient", factory)
    svc_shell = ns.NotificationService.__new__(ns.NotificationService)

    await ns.NotificationService._send_webhook(
        svc_shell, {"url": "https://hooks.example/x", "secret": "s3cret"}, "alert text")
    req = FakeHttpClient.last_request
    assert req["url"] == "https://hooks.example/x"
    body = req["content"]
    assert json.loads(body)["event"] == "notification"
    assert json.loads(body)["text"] == "alert text"
    expected = "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()
    assert req["headers"]["X-AIDA-Signature"] == expected
    assert req["headers"]["Content-Type"] == "application/json"


async def test_send_webhook_error_paths(monkeypatch):
    svc_shell = ns.NotificationService.__new__(ns.NotificationService)
    with pytest.raises(ValueError, match="url is required"):
        await ns.NotificationService._send_webhook(svc_shell, {}, "m")

    monkeypatch.setattr(ns.httpx, "AsyncClient",
                        lambda **kw: FakeHttpClient(FakeResponse(500, text="oops")))
    with pytest.raises(RuntimeError, match="Webhook error"):
        await ns.NotificationService._send_webhook(
            svc_shell, {"url": "https://hooks.example/x"}, "m")


async def test_send_telegram_and_slack_validations(monkeypatch):
    svc_shell = ns.NotificationService.__new__(ns.NotificationService)
    with pytest.raises(ValueError, match="bot_token"):
        await ns.NotificationService._send_telegram(svc_shell, {}, "m")
    with pytest.raises(ValueError, match="webhook_url"):
        await ns.NotificationService._send_slack(svc_shell, {}, "m")

    monkeypatch.setattr(ns.httpx, "AsyncClient", lambda **kw: FakeHttpClient())
    await ns.NotificationService._send_telegram(
        svc_shell, {"bot_token": "tok", "chat_id": "42"}, "m")
    assert FakeHttpClient.last_request["url"] == "https://api.telegram.org/bottok/sendMessage"
    assert FakeHttpClient.last_request["json"] == {
        "chat_id": "42", "text": "m", "parse_mode": "HTML"}

    await ns.NotificationService._send_slack(
        svc_shell, {"webhook_url": "https://hooks.slack/x"}, "m")
    assert FakeHttpClient.last_request["json"] == {"text": "m"}

    monkeypatch.setattr(ns.httpx, "AsyncClient",
                        lambda **kw: FakeHttpClient(FakeResponse(502, text="bad gw")))
    with pytest.raises(RuntimeError, match="Telegram API error"):
        await ns.NotificationService._send_telegram(
            svc_shell, {"bot_token": "t", "chat_id": "c"}, "m")


async def test_send_email_requires_smtp_config(monkeypatch):
    svc_shell = ns.NotificationService.__new__(ns.NotificationService)
    with pytest.raises(ValueError, match="SMTP host"):
        await ns.NotificationService._send_email(svc_shell, {"smtp_host": ""}, "m")
    with pytest.raises(ValueError, match="to_emails"):
        await ns.NotificationService._send_email(
            svc_shell, {"smtp_host": "smtp.x", "to_emails": []}, "m")


def test_smtp_send_starttls_login_and_sendmail(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port):
            calls.append(("init", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u))

        def sendmail(self, frm, to, body):
            calls.append(("sendmail", frm, to, body))

    monkeypatch.setattr(ns.smtplib, "SMTP", FakeSMTP)
    msg = MIMEText("body text")
    ns.NotificationService._smtp_send(
        "smtp.x", 587, "user", "pw", "from@x", ["a@x", "b@x"], msg, "starttls")
    assert ("init", "smtp.x", 587) in calls
    assert ("starttls",) in calls and ("login", "user") in calls
    frm, to, body = [c for c in calls if c[0] == "sendmail"][0][1:]
    assert frm == "from@x" and to == ["a@x", "b@x"] and body == msg.as_string()


def test_smtp_send_ssl_and_no_auth(monkeypatch):
    calls = []

    class FakeSMTP_SSL:
        def __init__(self, host, port):
            calls.append(("init", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, u, p):
            calls.append(("login", u))

        def sendmail(self, frm, to, body):
            calls.append(("sendmail", frm, to))

    monkeypatch.setattr(ns.smtplib, "SMTP_SSL", FakeSMTP_SSL)
    ns.NotificationService._smtp_send("smtp.x", 465, "", "", "f@x", ["t@x"],
                                      MIMEText("body"), "ssl")
    assert ("init", "smtp.x", 465) in calls
    assert not any(c[0] == "login" for c in calls)  # no creds → no login


async def test_send_dispatch_unknown_channel_is_swallowed(svc, monkeypatch):
    # _send logs a warning for unknown channels instead of raising.
    await ns.NotificationService._send(
        svc, NotificationConfig(channel="sms", config={}), "m")


async def test_send_propagates_sender_errors(db, svc, monkeypatch):
    async def boom(_self, cfg, message):
        raise RuntimeError("network gone")

    monkeypatch.setattr(NotificationService, "_send_telegram", boom)
    with pytest.raises(RuntimeError, match="network gone"):
        await ns.NotificationService._send(
            svc, _cfg(db, "telegram", config={}), "m")
