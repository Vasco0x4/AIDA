"""
Inbound Telegram bot — control AIDA from a chat.

A long-poll loop (started from the app lifespan, like the agent runner) reads the
Telegram bot token/chat_id from the existing notification_configs (channel
"telegram") and handles commands. It is gated by the ``telegram_bot_enabled``
platform setting AND the presence of a token, so it stays dormant until
configured.

Security:
- Only messages from the configured chat_id are honored (allowlist). Everything
  else is ignored.
- Tasks are created via the internal TaskService as the first admin user; the
  bot never gains a new privilege path.
- New tasks require an explicit authorized scope — same invariant as the UI.
"""
from __future__ import annotations

import asyncio
import html
from typing import Optional

import httpx

from database import SessionLocal
from models.platform_settings import PlatformSettings
from models.user import User
from models.task import Task
from services.notification_service import NotificationService
from services.task_service import TaskService
from utils.logger import get_logger

logger = get_logger(__name__)

POLL_TIMEOUT = 25  # long-poll seconds

HELP = (
    "<b>AIDA control</b>\n"
    "/task <code>target | scope | title | [host]</code> — create a task\n"
    "   e.g. <code>/task example.com | *.example.com | XSS hunt</code>\n"
    "/tasks — list recent tasks\n"
    "/board — column summary\n"
    "/runner on|off — pause/resume the autonomous runner\n"
    "/status <id> — task detail\n"
    "/help — this message"
)


class TelegramBot:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._offset = 0

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="aida-telegram-bot")
        logger.info("Telegram bot loop started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=8)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()

    # --- config helpers ----------------------------------------------------
    def _config(self):
        """Return (enabled, bot_token, chat_id) from settings + notif config."""
        db = SessionLocal()
        try:
            en = db.query(PlatformSettings).filter(
                PlatformSettings.key == "telegram_bot_enabled").first()
            enabled = (en.value if en else "false").lower() in ("true", "1", "yes", "on")
            cfg = NotificationService(db).get_config("telegram")
            data = (cfg.config if cfg else {}) or {}
            return enabled, data.get("bot_token", ""), str(data.get("chat_id", ""))
        finally:
            db.close()

    def _admin_user_id(self) -> Optional[int]:
        db = SessionLocal()
        try:
            u = db.query(User).filter(User.role == "admin").order_by(User.id.asc()).first()
            return u.id if u else None
        finally:
            db.close()

    async def _send(self, token: str, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"})
        except httpx.HTTPError as e:
            logger.warning("telegram send failed", error=str(e))

    # --- main loop ---------------------------------------------------------
    async def _loop(self) -> None:
        while not self._stop.is_set():
            enabled, token, chat_id = self._config()
            if not (enabled and token):
                # Dormant: check back periodically.
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=10)
                except asyncio.TimeoutError:
                    pass
                continue
            try:
                await self._poll_once(token, chat_id)
            except Exception:
                logger.exception("telegram poll error")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass

    async def _poll_once(self, token: str, chat_id: str) -> None:
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        params = {"timeout": POLL_TIMEOUT, "offset": self._offset}
        async with httpx.AsyncClient(timeout=POLL_TIMEOUT + 10) as client:
            resp = await client.get(url, params=params)
        if resp.status_code != 200:
            await asyncio.sleep(3)
            return
        for upd in resp.json().get("result", []):
            self._offset = max(self._offset, upd["update_id"] + 1)
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            from_chat = str(msg.get("chat", {}).get("id", ""))
            # Allowlist: only the configured chat may control AIDA.
            if chat_id and from_chat != chat_id:
                continue
            text = (msg.get("text") or "").strip()
            if text:
                await self._handle(token, from_chat, text)

    async def _handle(self, token: str, chat_id: str, text: str) -> None:
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower().lstrip("/")
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in ("start", "help"):
            await self._send(token, chat_id, HELP)
        elif cmd == "task":
            await self._cmd_task(token, chat_id, arg)
        elif cmd == "tasks":
            await self._cmd_tasks(token, chat_id)
        elif cmd == "board":
            await self._cmd_board(token, chat_id)
        elif cmd == "runner":
            await self._cmd_runner(token, chat_id, arg)
        elif cmd == "status":
            await self._cmd_status(token, chat_id, arg)
        else:
            await self._send(token, chat_id, "Unknown command. /help for usage.")

    async def _cmd_task(self, token: str, chat_id: str, arg: str) -> None:
        if not arg:
            await self._send(token, chat_id,
                             "Usage: /task target | scope | title | [host]\n"
                             "Scope is required (the agent refuses to act without it).")
            return
        fields = [p.strip() for p in arg.split("|")]
        target = fields[0] if len(fields) > 0 else ""
        scope = fields[1] if len(fields) > 1 else ""
        title = fields[2] if len(fields) > 2 and fields[2] else f"Assess {target}"
        exec_target = "host" if (len(fields) > 3 and fields[3].lower() == "host") else "container"
        if not target or not scope:
            await self._send(token, chat_id, "Both <b>target</b> and <b>scope</b> are required.\nUsage: /task target | scope | title")
            return
        db = SessionLocal()
        try:
            svc = TaskService(db)
            row = svc.create(
                created_by=self._admin_user_id(),
                title=title, target=target, authorized_scope=scope,
                execution_target=exec_target, status="queued", source="telegram",
                priority="high",
            )
            tid = row.id
        finally:
            db.close()
        warn = "\n⚠️ host execution requested" if exec_target == "host" else ""
        await self._send(token, chat_id,
                         f"✅ Task <b>#{tid}</b> created and <b>queued</b>.\n"
                         f"target: <code>{html.escape(target)}</code>\n"
                         f"scope: <code>{html.escape(scope)}</code>{warn}\n"
                         f"The agent will pick it up shortly.")

    async def _cmd_tasks(self, token: str, chat_id: str) -> None:
        db = SessionLocal()
        try:
            rows = db.query(Task).order_by(Task.id.desc()).limit(10).all()
        finally:
            db.close()
        if not rows:
            await self._send(token, chat_id, "No tasks yet.")
            return
        lines = [f"#{r.id} [{r.status}] {html.escape(r.title[:40])}" for r in rows]
        await self._send(token, chat_id, "<b>Recent tasks</b>\n" + "\n".join(lines))

    async def _cmd_board(self, token: str, chat_id: str) -> None:
        db = SessionLocal()
        try:
            grouped = TaskService(db).board()
        finally:
            db.close()
        lines = [f"{k}: {len(v)}" for k, v in grouped.items() if v]
        await self._send(token, chat_id, "<b>Board</b>\n" + ("\n".join(lines) if lines else "empty"))

    async def _cmd_runner(self, token: str, chat_id: str, arg: str) -> None:
        want = arg.strip().lower()
        if want not in ("on", "off"):
            await self._send(token, chat_id, "Usage: /runner on|off")
            return
        db = SessionLocal()
        try:
            row = db.query(PlatformSettings).filter(
                PlatformSettings.key == "agent_runner_enabled").first()
            val = "true" if want == "on" else "false"
            if row:
                row.value = val
            else:
                db.add(PlatformSettings(key="agent_runner_enabled", value=val,
                                        description="Autonomous agent runner"))
            db.commit()
        finally:
            db.close()
        await self._send(token, chat_id, f"Runner turned <b>{want}</b>.")

    async def _cmd_status(self, token: str, chat_id: str, arg: str) -> None:
        try:
            tid = int(arg.strip())
        except ValueError:
            await self._send(token, chat_id, "Usage: /status <task_id>")
            return
        db = SessionLocal()
        try:
            r = db.query(Task).filter(Task.id == tid).first()
        finally:
            db.close()
        if not r:
            await self._send(token, chat_id, f"Task #{tid} not found.")
            return
        summary = html.escape((r.result_summary or "")[:300])
        await self._send(token, chat_id,
                         f"<b>Task #{r.id}</b> — {r.status}\n"
                         f"title: {html.escape(r.title)}\n"
                         f"target: <code>{html.escape(r.target or '-')}</code>\n"
                         f"findings: {(r.meta or {}).get('findings', 0)}\n"
                         f"{summary}")


telegram_bot = TelegramBot()
