"""
AgentSession — runs one headless Claude session end-to-end.

Two execution paths share the same persistence/WS plumbing below:
    * Real: spawns `claude` via claude-code-sdk when CLAUDE_CODE_OAUTH_TOKEN
      (or ANTHROPIC_API_KEY) is set in the backend env. Uses the AIDA MCP
      server for tool access and the same Docs/PrePrompt.txt system prompt
      the CLI path loads.
    * Mock: scripted events mimicking the real SDK shape. Kept around so the
      panel is demoable without credentials, and so plumbing regressions
      show up deterministically.

The branch is picked at runtime in `_run_session()` — nothing about the
DB / WS layer differs between the two.
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from auth import create_api_token
from database import SessionLocal
from models import AgentRun, Assessment, User
from schemas.agent_run import AgentRunResponse
from utils.logger import get_logger
from websocket.manager import manager
from websocket.events import (
    event_agent_run_started,
    event_agent_run_message,
    event_agent_run_completed,
    event_agent_run_failed,
    event_agent_run_stopped,
)

from .mcp_config import build_mcp_servers
from .preprompt import build_system_prompt, get_workspace_cwd


logger = get_logger(__name__)

DEFAULT_PERMISSION_MODE = "bypassPermissions"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _response_dict(run: AgentRun) -> dict:
    """Serialise an AgentRun ORM instance to the shape the UI consumes."""
    return AgentRunResponse.model_validate(run).model_dump(mode="json")


def _has_claude_credentials() -> bool:
    """Real SDK path needs either an OAuth token (Max) or an API key."""
    return bool(
        os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
        or os.getenv("ANTHROPIC_API_KEY")
    )


class AgentSession:
    """One execution of a UI-initiated scan."""

    MOCK_STEP_DELAY = 1.0  # seconds between scripted mock events

    def __init__(
        self,
        run_id: int,
        assessment_id: int,
        goal: str,
        permission_mode: Optional[str],
        model: Optional[str],
    ) -> None:
        self.run_id = run_id
        self.assessment_id = assessment_id
        self.goal = goal
        self.permission_mode = permission_mode or DEFAULT_PERMISSION_MODE
        self.model = model
        self._transcript: List[Dict[str, Any]] = []

    async def run(self) -> None:
        """Main entry point scheduled as an asyncio.Task."""
        started_at_wall = time.monotonic()
        try:
            await self._mark_running()
            await self._run_session()
            duration_ms = int((time.monotonic() - started_at_wall) * 1000)
            await self._mark_completed(duration_ms=duration_ms)
        except asyncio.CancelledError:
            await self._mark_stopped()
        except Exception as exc:
            logger.exception("Agent session failed", run_id=self.run_id)
            await self._mark_failed(str(exc))

    async def _run_session(self) -> None:
        if _has_claude_credentials():
            await self._run_real_session()
        else:
            logger.info(
                "CLAUDE_CODE_OAUTH_TOKEN/ANTHROPIC_API_KEY not set — "
                "running mock session",
                run_id=self.run_id,
            )
            await self._run_mock_session()

    # ------------------------------------------------------------------
    # Real SDK session
    # ------------------------------------------------------------------
    async def _run_real_session(self) -> None:
        # Imported lazily so backend still starts without the SDK installed
        # (e.g. first boot before an image rebuild).
        from claude_code_sdk import query, ClaudeCodeOptions

        assessment, aida_token = self._prepare_session_context()

        options_kwargs = dict(
            system_prompt=build_system_prompt(assessment, self.goal),
            mcp_servers=build_mcp_servers(aida_token),
            permission_mode=self.permission_mode,
        )
        if self.model:
            options_kwargs["model"] = self.model
        cwd = get_workspace_cwd(assessment)
        if cwd:
            options_kwargs["cwd"] = cwd

        options = ClaudeCodeOptions(**options_kwargs)

        async for message in query(prompt=self.goal, options=options):
            await self._handle_sdk_message(message)

    def _prepare_session_context(self) -> tuple[Assessment, Optional[str]]:
        """Load the assessment row and mint a scoped MCP token."""
        db: Session = SessionLocal()
        try:
            assessment = (
                db.query(Assessment)
                .filter(Assessment.id == self.assessment_id)
                .first()
            )
            if assessment is None:
                raise RuntimeError(
                    f"Assessment {self.assessment_id} vanished before run start"
                )

            run = db.query(AgentRun).filter(AgentRun.id == self.run_id).first()
            user = None
            if run and run.user_id:
                user = db.query(User).filter(User.id == run.user_id).first()

            aida_token = None
            if user:
                aida_token = create_api_token(
                    user_id=user.id, username=user.username
                )

            # Detach so the ORM instance is usable after the session closes.
            db.expunge(assessment)
            return assessment, aida_token
        finally:
            db.close()

    async def _handle_sdk_message(self, message: Any) -> None:
        """Convert an SDK message to one or more transcript events."""
        # Use class-name sniffing so we don't hard-fail if the SDK changes
        # its public typing surface between minor versions.
        cls_name = type(message).__name__

        if cls_name == "SystemMessage":
            subtype = getattr(message, "subtype", None)
            data = getattr(message, "data", {}) or {}
            if subtype == "init":
                await self._emit({
                    "type": "system_init",
                    "session_id": data.get("session_id"),
                    "model": data.get("model") or self.model,
                })
            else:
                await self._emit({
                    "type": "system",
                    "subtype": subtype,
                    "data": data,
                })
            return

        if cls_name == "AssistantMessage":
            for block in getattr(message, "content", []) or []:
                await self._emit_block(block, role="assistant")
            return

        if cls_name == "UserMessage":
            # User messages in the SDK stream are synthetic — they carry
            # tool_result blocks produced by MCP tools.
            for block in getattr(message, "content", []) or []:
                await self._emit_block(block, role="user")
            return

        if cls_name == "ResultMessage":
            await self._emit({
                "type": "result",
                "num_turns": getattr(message, "num_turns", None),
                "duration_ms": getattr(message, "duration_ms", None),
                "total_cost_usd": getattr(message, "total_cost_usd", None),
                "is_error": getattr(message, "is_error", False),
            })
            return

        # Fallthrough — unknown message shape: surface it so we can iterate.
        await self._emit({
            "type": "unknown",
            "class": cls_name,
            "repr": repr(message)[:2000],
        })

    async def _emit_block(self, block: Any, role: str) -> None:
        cls_name = type(block).__name__
        if cls_name == "TextBlock":
            text = getattr(block, "text", "") or ""
            if text.strip():
                await self._emit({"type": "assistant_text", "text": text})
            return
        if cls_name == "ThinkingBlock":
            thinking = getattr(block, "thinking", "") or ""
            if thinking.strip():
                await self._emit({"type": "thinking", "text": thinking})
            return
        if cls_name == "ToolUseBlock":
            await self._emit({
                "type": "tool_use",
                "id": getattr(block, "id", None),
                "name": getattr(block, "name", None),
                "input": getattr(block, "input", None),
            })
            return
        if cls_name == "ToolResultBlock":
            await self._emit({
                "type": "tool_result",
                "tool_use_id": getattr(block, "tool_use_id", None),
                "content": _normalize_tool_result(getattr(block, "content", None)),
                "is_error": bool(getattr(block, "is_error", False)),
            })
            return

        await self._emit({
            "type": "block",
            "class": cls_name,
            "role": role,
            "repr": repr(block)[:2000],
        })

    # ------------------------------------------------------------------
    # Mock fallback
    # ------------------------------------------------------------------
    async def _run_mock_session(self) -> None:
        self.model = self.model or "mock-claude"
        await self._emit({
            "type": "system_init",
            "session_id": f"mock-{self.run_id}",
            "model": self.model,
        })
        await asyncio.sleep(self.MOCK_STEP_DELAY)

        await self._emit({
            "type": "assistant_text",
            "text": (
                f"Understood. I will work on the following goal: {self.goal}\n"
                "Starting with reconnaissance."
            ),
        })
        await asyncio.sleep(self.MOCK_STEP_DELAY)

        await self._emit({
            "type": "tool_use",
            "name": "mcp__aida__execute_command",
            "input": {"command": "nmap -sV -top-ports 20 example.local"},
        })
        await asyncio.sleep(self.MOCK_STEP_DELAY * 2)

        await self._emit({
            "type": "tool_result",
            "content": (
                "PORT     STATE SERVICE    VERSION\n"
                "22/tcp   open  ssh        OpenSSH 8.4\n"
                "80/tcp   open  http       nginx 1.24\n"
                "443/tcp  open  https      nginx 1.24\n"
            ),
        })
        await asyncio.sleep(self.MOCK_STEP_DELAY)

        await self._emit({
            "type": "assistant_text",
            "text": (
                "Found SSH + nginx on the target. This is a mock run — set "
                "CLAUDE_CODE_OAUTH_TOKEN in backend/.env to run against the "
                "real model."
            ),
        })
        await asyncio.sleep(self.MOCK_STEP_DELAY)

        await self._emit({
            "type": "result",
            "num_turns": 2,
            "total_cost_usd": 0.0,
            "duration_ms": int(self.MOCK_STEP_DELAY * 5 * 1000),
        })

    # ------------------------------------------------------------------
    # Event emission and persistence
    # ------------------------------------------------------------------
    async def _emit(self, message: Dict[str, Any]) -> None:
        message = {**message, "ts": _utcnow().isoformat()}
        self._transcript.append(message)
        await manager.broadcast(
            event_agent_run_message(self.assessment_id, self.run_id, message),
            assessment_id=self.assessment_id,
        )

    # ------------------------------------------------------------------
    # State transitions (DB + WS)
    # ------------------------------------------------------------------
    async def _mark_running(self) -> None:
        db: Session = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == self.run_id).first()
            if run is None:
                raise RuntimeError(f"AgentRun {self.run_id} vanished before start")
            run.status = "running"
            run.started_at = _utcnow()
            if self.model:
                run.model = self.model
            db.commit()
            db.refresh(run)
            payload = _response_dict(run)
        finally:
            db.close()

        await manager.broadcast(
            event_agent_run_started(self.assessment_id, payload),
            assessment_id=self.assessment_id,
        )

    async def _mark_completed(self, duration_ms: int) -> None:
        result_meta = next(
            (m for m in reversed(self._transcript) if m.get("type") == "result"),
            None,
        )

        db: Session = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == self.run_id).first()
            if run is None:
                return
            run.status = "completed"
            run.ended_at = _utcnow()
            run.transcript = self._transcript
            run.duration_ms = duration_ms
            if result_meta:
                run.num_turns = result_meta.get("num_turns")
                cost = result_meta.get("total_cost_usd")
                if cost is not None:
                    run.cost_usd = float(cost)
            db.commit()
            db.refresh(run)
            payload = _response_dict(run)
        finally:
            db.close()

        await manager.broadcast(
            event_agent_run_completed(self.assessment_id, payload),
            assessment_id=self.assessment_id,
        )

    async def _mark_failed(self, error: str) -> None:
        db: Session = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == self.run_id).first()
            if run is None:
                return
            run.status = "failed"
            run.ended_at = _utcnow()
            run.error = error
            run.transcript = self._transcript or None
            db.commit()
        finally:
            db.close()

        await manager.broadcast(
            event_agent_run_failed(self.assessment_id, self.run_id, error),
            assessment_id=self.assessment_id,
        )

    async def _mark_stopped(self) -> None:
        db: Session = SessionLocal()
        try:
            run = db.query(AgentRun).filter(AgentRun.id == self.run_id).first()
            if run is None:
                return
            run.status = "stopped"
            run.ended_at = _utcnow()
            run.transcript = self._transcript or None
            db.commit()
        finally:
            db.close()

        await manager.broadcast(
            event_agent_run_stopped(self.assessment_id, self.run_id),
            assessment_id=self.assessment_id,
        )


def _normalize_tool_result(content: Any) -> Any:
    """Flatten SDK tool-result content blocks to plain strings/dicts."""
    if content is None:
        return None
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[Any] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text") or item)
            else:
                parts.append(repr(item))
        return "\n".join(p if isinstance(p, str) else repr(p) for p in parts)
    return repr(content)
