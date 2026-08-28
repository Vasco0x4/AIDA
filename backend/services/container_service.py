"""
Container Service - Command execution + database logging layer.

This service is the public entry point used by API routes (commands.py,
pending_commands.py). It handles:

  - Resolving the active execution target (container name or "localhost")
  - Creating/refreshing workspaces for an assessment
  - Executing shell / Python / HTTP-request commands
  - Logging every command to `CommandHistory` and broadcasting results
    over the WebSocket manager

The "how do I actually run a command" part is delegated to an
`ExecutionBackend` (see `services/execution/`). In container mode that's
a docker-exec wrapper; in localhost mode it's a Unix-socket call to the
aida-host-agent daemon on the host. This service layer is agnostic.
"""
import asyncio
import json
import shlex
import time
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models import CommandHistory, Assessment
from models.platform_settings import PlatformSettings
from config import settings
from utils.logger import get_logger
from utils.log_context import log_context, timed_operation
from utils.subprocess_runner import run_subprocess
from websocket.manager import manager
from websocket.events import event_command_completed, event_command_failed, EventType, create_event

from services.execution import (
    ExecResult,
    ExecutionBackend,
    get_execution_backend,
)

logger = get_logger(__name__)


class ContainerService:
    """Public command-execution API used by the FastAPI routes."""

    def __init__(self):
        # In container mode, this is the Docker container name (aida-pentest
        # or an Exegol variant). In localhost mode, it's the synthetic
        # "localhost" label so UI filters, CommandHistory rows, and logs
        # have a consistent value to key on.
        self.current_container: Optional[str] = (
            settings.LOCALHOST_CONTAINER_LABEL
            if settings.DEPLOYMENT_MODE == "localhost"
            else settings.DEFAULT_CONTAINER_NAME
        )
        # Discovery cache (container mode only — localhost has no list).
        self.containers_cache: List[Dict[str, Any]] = []
        self.cache_timestamp: float = 0
        self.cache_ttl: int = 30

    # ========== Utility helpers ==========

    @staticmethod
    def _sanitize_output(output: str) -> str:
        """Strip null bytes + replace invalid UTF-8.

        Postgres with UTF-8 encoding can't store 0x00 bytes, and some
        pentesting tools emit them (notably binary protocols dumped to
        stdout). The execution backends already apply this, but we do
        it again before DB insert as a belt-and-braces guarantee.
        """
        if not output:
            return output
        sanitized = output.replace("\x00", "")
        return sanitized.encode("utf-8", errors="replace").decode(
            "utf-8", errors="replace"
        )

    async def _run_command(self, command: List[str], timeout: float = 30.0) -> Dict[str, Any]:
        """Run a system command with a timeout to prevent hangs on docker socket
        issues. The process lifecycle, timeout and output cap live in the shared
        ``run_subprocess`` helper; this wrapper keeps the service's return shape.

        Kept for parts of the codebase that still `docker ps`, `docker inspect`,
        etc. directly. Assessment command execution goes through
        ``self._get_backend()`` instead.
        """
        result = await run_subprocess(command, timeout)
        out = {
            "success": result["success"],
            "returncode": result["returncode"],
            "stdout": result["stdout"],
            "stderr": result["stderr"],
        }
        if result["status"] == "not_found":
            out["stderr"] = f"Executable not found: {result.get('raw_error', '')}"
            out["error_type"] = "executable_not_found"
        elif result["status"] == "failed":
            out["stderr"] = str(result.get("raw_error", ""))
        return out

    def _get_backend(self, container_name: Optional[str] = None) -> ExecutionBackend:
        """Build the execution backend matching the current deployment mode."""
        return get_execution_backend(container_name or self.current_container)

    # ========== Container discovery (container mode only) ==========

    async def discover_containers(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """List candidate pentest containers on this host.

        In localhost mode there's no list to return — the single target is
        the host itself, surfaced as a synthetic "localhost" entry so any
        upstream UI or logic that iterates containers keeps working.
        """
        if settings.DEPLOYMENT_MODE == "localhost":
            # Report the host-agent's health as the "status" of the
            # synthetic container. Makes the Settings UI show a red dot
            # when the daemon isn't reachable.
            backend = self._get_backend(settings.LOCALHOST_CONTAINER_LABEL)
            health = await backend.validate_ready()
            status = "running" if health.get("success") else "unreachable"
            return [
                {
                    "name": settings.LOCALHOST_CONTAINER_LABEL,
                    "image": "(host)",
                    "status": status,
                    "id": "localhost",
                }
            ]

        current_time = time.time()
        if (
            not force_refresh
            and self.containers_cache
            and (current_time - self.cache_timestamp) < self.cache_ttl
        ):
            return self.containers_cache

        containers: List[Dict[str, Any]] = []
        try:
            result = await self._run_command(
                ["docker", "ps", "-a", "--format", "json"]
            )
            if result["success"] and result["stdout"]:
                for line in result["stdout"].split("\n"):
                    if not line.strip():
                        continue
                    try:
                        container_data = json.loads(line)
                        container_name = container_data.get("Names", "unknown").lstrip("/")
                        image = container_data.get("Image", "")
                        allowed_prefixes = tuple(
                            p.strip()
                            for p in settings.CONTAINER_PREFIX_FILTER.split(",")
                            if p.strip()
                        )
                        if container_name.lower().startswith(allowed_prefixes):
                            containers.append(
                                {
                                    "name": container_name,
                                    "image": image,
                                    "status": container_data.get("State", "unknown"),
                                    "id": container_data.get("ID", "unknown")[:12],
                                }
                            )
                    except json.JSONDecodeError:
                        continue
        except Exception:
            containers = []

        self.containers_cache = containers
        self.cache_timestamp = current_time
        return containers

    async def select_container(self, container_name: str) -> Dict[str, Any]:
        """Pick the active execution target.

        Only meaningful in container mode. Localhost mode is single-target
        so we accept the request silently and keep the label.
        """
        if settings.DEPLOYMENT_MODE == "localhost":
            self.current_container = settings.LOCALHOST_CONTAINER_LABEL
            return {
                "success": True,
                "message": "Running in localhost mode — single-target",
            }

        containers = await self.discover_containers()
        if any(c["name"] == container_name for c in containers):
            self.current_container = container_name
            return {"success": True, "message": f"Container '{container_name}' selected"}
        return {"success": False, "error": f"Container '{container_name}' not found"}

    async def validate_container_status(self) -> Dict[str, Any]:
        """Pre-flight check the execution target is reachable."""
        backend = self._get_backend()
        return await backend.validate_ready()

    async def execute_container_command(
        self,
        command: str,
        working_directory: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Thin wrapper used by tests and a handful of legacy call sites."""
        backend = self._get_backend()
        result = await backend.exec_shell(command, cwd=working_directory)
        return {
            "success": result["success"],
            "container": result.get("container", self.current_container),
            "command": command,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "returncode": result["returncode"],
            "execution_time": result["execution_time"],
        }

    # ========== Active target resolution ==========

    async def _resolve_active_container(self, db: AsyncSession) -> str:
        """Pick the execution target for this request.

        Container mode:
          1. PlatformSettings.container_name (UI override).
          2. settings.DEFAULT_CONTAINER_NAME.
          3. First running container matching CONTAINER_PREFIX_FILTER.

        Localhost mode: always returns the synthetic "localhost" label.
        """
        if settings.DEPLOYMENT_MODE == "localhost":
            return settings.LOCALHOST_CONTAINER_LABEL

        stmt = select(PlatformSettings).filter(PlatformSettings.key == "container_name")
        result = await db.execute(stmt)
        container_setting = result.scalar_one_or_none()
        configured = (
            container_setting.value
            if (container_setting and container_setting.value)
            else settings.DEFAULT_CONTAINER_NAME
        )

        containers = await self.discover_containers()
        running = [c for c in containers if c["status"] == "running"]

        if any(c["name"] == configured for c in running):
            return configured

        if running:
            selected = running[0]["name"]
            logger.info(
                "Configured container not running, auto-selecting running container",
                configured=configured,
                selected=selected,
            )
            return selected

        return configured

    # ========== Workspace provisioning ==========

    async def _ensure_workspace_exists(
        self,
        assessment: Assessment,
        db: AsyncSession,
    ) -> Optional[str]:
        """Make sure the assessment's workspace directory exists and return its path.

        Creates the workspace on first encounter and repairs it if the user
        rebuilt the container / switched deployment modes and the directory
        went missing.
        """
        if not assessment:
            return None

        if not assessment.workspace_path:
            workspace_result = await self.create_workspace(
                assessment_name=assessment.name, db=None
            )
            stmt = (
                update(Assessment)
                .where(Assessment.id == assessment.id)
                .values(
                    workspace_path=workspace_result["workspace_path"],
                    container_name=workspace_result["container_name"],
                )
            )
            await db.execute(stmt)
            await db.commit()
            await db.refresh(assessment)
            assessment.workspace_path = workspace_result["workspace_path"]
            assessment.container_name = workspace_result["container_name"]
            return assessment.workspace_path

        # Workspace exists in DB — verify it's actually present on the
        # execution target. This protects against mode switches and
        # container rebuilds.
        backend = self._get_backend()
        subdirs = ["recon", "exploits", "loot", "notes", "scripts", "context"]
        await backend.ensure_workspace(assessment.workspace_path, subdirs)
        return assessment.workspace_path

    # ========== Command execution + logging ==========

    async def _resolve_timeout(
        self, db: AsyncSession, explicit: Optional[int]
    ) -> int:
        if explicit is not None:
            return explicit
        stmt = select(PlatformSettings).filter(
            PlatformSettings.key == "command_timeout"
        )
        result = await db.execute(stmt)
        timeout_setting = result.scalar_one_or_none()
        if timeout_setting:
            try:
                return int(timeout_setting.value)
            except ValueError:
                return settings.COMMAND_TIMEOUT
        return settings.COMMAND_TIMEOUT

    async def _broadcast_result(
        self,
        command_log: CommandHistory,
        assessment: Optional[Assessment],
        assessment_id: int,
    ) -> None:
        from schemas.command import CommandResponse

        command_dict = CommandResponse.model_validate(command_log).model_dump(mode="json")
        command_dict["assessment_name"] = assessment.name if assessment else None
        if command_log.success:
            await manager.broadcast(
                event_command_completed(assessment_id, command_dict),
                assessment_id=assessment_id,
            )
        else:
            await manager.broadcast(
                event_command_failed(assessment_id, command_dict),
                assessment_id=assessment_id,
            )

    async def _broadcast_timeout(
        self, command_log: CommandHistory, assessment_id: int
    ) -> None:
        from schemas.command import CommandResponse

        command_dict = CommandResponse.model_validate(command_log).model_dump(mode="json")
        await manager.broadcast(
            create_event(
                EventType.COMMAND_TIMEOUT,
                {"command": command_dict},
                assessment_id=assessment_id,
            ),
            assessment_id=assessment_id,
        )

    async def execute_and_log_command(
        self,
        assessment_id: int,
        command: str,
        phase: Optional[str],
        db: AsyncSession,
        timeout: Optional[int] = None,
    ) -> CommandHistory:
        """Execute a shell command, log it to CommandHistory, broadcast result."""
        timeout = await self._resolve_timeout(db, timeout)

        self.current_container = await self._resolve_active_container(db)
        backend = self._get_backend()

        stmt = select(Assessment).filter(Assessment.id == assessment_id)
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()
        working_directory = await self._ensure_workspace_exists(assessment, db)

        command_log = CommandHistory(
            assessment_id=assessment_id,
            container_name=self.current_container,
            command=command,
            phase=phase,
            status="running",
        )
        db.add(command_log)
        await db.commit()
        await db.refresh(command_log)

        try:
            result = await asyncio.wait_for(
                backend.exec_shell(
                    command, cwd=working_directory, timeout=float(timeout)
                ),
                timeout=timeout + 5,
            )
            command_log.stdout = self._sanitize_output(result.get("stdout") or "")
            command_log.stderr = self._sanitize_output(result.get("stderr") or "")
            command_log.returncode = result.get("returncode")
            command_log.execution_time = result.get("execution_time")
            command_log.success = result.get("success")
            command_log.status = "completed" if result.get("success") else "failed"

            await db.commit()
            await db.refresh(command_log)
            await self._broadcast_result(command_log, assessment, assessment_id)
            return command_log

        except asyncio.TimeoutError:
            command_log.status = "timeout"
            command_log.timeout_at = datetime.utcnow()
            command_log.stderr = f"Command exceeded {timeout}s timeout limit"
            command_log.success = False
            command_log.execution_time = timeout
            await db.commit()
            await db.refresh(command_log)
            await self._broadcast_timeout(command_log, assessment_id)
            return command_log

        except Exception as e:
            # Any other failure (container crash, broadcast/serialization error,
            # ...) must not leave the row stuck in "running" forever. If the
            # result was already recorded and only a later step failed, keep the
            # recorded status instead of overwriting it.
            if command_log.status == "running":
                command_log.status = "failed"
                command_log.success = False
                command_log.stderr = self._sanitize_output(str(e))
                try:
                    await db.commit()
                    await db.refresh(command_log)
                except Exception:
                    await db.rollback()
            return command_log

    async def execute_python_stdin(
        self,
        code: str,
        working_directory: Optional[str] = None,
        timeout: float = 300.0,
    ) -> Dict[str, Any]:
        """Direct-exec Python helper (used by tests and a few legacy paths)."""
        backend = self._get_backend()
        result = await backend.exec_python(code, cwd=working_directory, timeout=timeout)
        return {
            "success": result["success"],
            "stdout": self._sanitize_output(result["stdout"]),
            "stderr": self._sanitize_output(result["stderr"]),
            "returncode": result["returncode"],
            "execution_time": result["execution_time"],
            "container": result.get("container", self.current_container),
        }

    async def execute_and_log_python(
        self,
        assessment_id: int,
        code: str,
        phase: Optional[str],
        db: AsyncSession,
        timeout: Optional[int] = None,
    ) -> "CommandHistory":
        """Execute Python code via stdin and log it to CommandHistory.

        Mirrors execute_and_log_command() but calls backend.exec_python() and
        stores command_type='python' + source_code=code in CommandHistory.
        """
        timeout = await self._resolve_timeout(db, timeout)

        self.current_container = await self._resolve_active_container(db)
        backend = self._get_backend()

        stmt = select(Assessment).filter(Assessment.id == assessment_id)
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()
        working_directory = await self._ensure_workspace_exists(assessment, db)

        command_log = CommandHistory(
            assessment_id=assessment_id,
            container_name=self.current_container,
            command="python3 -",
            phase=phase,
            status="running",
            command_type="python",
            source_code=code,
        )
        db.add(command_log)
        await db.commit()
        await db.refresh(command_log)

        try:
            result = await asyncio.wait_for(
                backend.exec_python(
                    code, cwd=working_directory, timeout=float(timeout)
                ),
                timeout=timeout + 5,
            )
            command_log.stdout = self._sanitize_output(result.get("stdout") or "")
            command_log.stderr = self._sanitize_output(result.get("stderr") or "")
            command_log.returncode = result.get("returncode")
            command_log.execution_time = result.get("execution_time")
            command_log.success = result.get("success")
            command_log.status = "completed" if result.get("success") else "failed"

            await db.commit()
            await db.refresh(command_log)
            await self._broadcast_result(command_log, assessment, assessment_id)
            return command_log

        except asyncio.TimeoutError:
            command_log.status = "timeout"
            command_log.timeout_at = datetime.utcnow()
            command_log.stderr = f"Python execution exceeded {timeout}s timeout limit"
            command_log.success = False
            command_log.execution_time = timeout
            await db.commit()
            await db.refresh(command_log)
            await self._broadcast_timeout(command_log, assessment_id)
            return command_log

        except Exception as e:
            if command_log.status == "running":
                command_log.status = "failed"
                command_log.success = False
                command_log.stderr = self._sanitize_output(str(e))
                try:
                    await db.commit()
                    await db.refresh(command_log)
                except Exception:
                    await db.rollback()
            return command_log

    # ========== HTTP-request helper (mode-agnostic) ==========

    def _generate_http_python_script(self, params) -> str:
        """Generate a Python requests script from HttpRequestRequest params.

        The script is piped via stdin to `python3 -` on whatever backend
        we're using. Output format is human-readable: status line, headers,
        optional cookies, body. Identical across container and localhost
        modes — the script doesn't know or care where it runs.
        """
        import json as _json

        method = params.method.upper()
        url = params.url
        headers = params.headers or {}
        query_params = params.params or {}
        cookies = params.cookies or {}
        timeout = params.timeout
        follow_redirects = params.follow_redirects
        verify_ssl = params.verify_ssl

        if params.auth and len(params.auth) >= 2:
            auth_repr = repr(tuple(params.auth[:2]))
        else:
            auth_repr = "None"

        if params.proxy:
            proxy_repr = repr({"http": params.proxy, "https": params.proxy})
        else:
            proxy_repr = "None"

        if params.json_body is not None:
            body_line = f"    json={_json.dumps(params.json_body)!r},"
        elif params.data is not None:
            body_line = f"    data={params.data!r},"
        else:
            body_line = "    data=None,"

        script = f"""\
import requests, json as _json, time, sys

_start = time.time()
_session = requests.Session()
_session.verify = {verify_ssl!r}

try:
    _resp = _session.request(
        method={method!r},
        url={url!r},
        headers={headers!r},
        params={query_params!r},
{body_line}
        cookies={cookies!r},
        auth={auth_repr},
        proxies={proxy_repr},
        timeout={timeout!r},
        allow_redirects={follow_redirects!r},
    )
    _ms = int((time.time() - _start) * 1000)

    try:
        _body = _json.dumps(_resp.json(), indent=2, ensure_ascii=False)
        _is_json = True
    except Exception:
        _body = _resp.text
        _is_json = False

    print(f"HTTP {{_resp.status_code}} {{_resp.reason}}  [{{_ms}}ms]")
    print(f"URL: {{_resp.url}}")

    if _resp.history:
        _chain = " -> ".join(str(r.status_code) for r in _resp.history)
        print(f"Redirects: {{_chain}} -> {{_resp.status_code}}")

    print("\\n--- Response Headers ---")
    for _k, _v in _resp.headers.items():
        print(f"  {{_k}}: {{_v}}")

    if _resp.cookies:
        print("\\n--- Cookies Set ---")
        for _k, _v in _resp.cookies.items():
            print(f"  {{_k}}: {{_v}}")

    _label = " (JSON)" if _is_json else ""
    print(f"\\n--- Body{{_label}} ---")
    print(_body[:20000])

except requests.exceptions.SSLError as _e:
    print(f"SSL Error: {{_e}}", file=sys.stderr)
    print("Hint: use verify_ssl=false to disable certificate verification", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.ConnectionError as _e:
    print(f"Connection Error: {{_e}}", file=sys.stderr)
    sys.exit(1)
except requests.exceptions.Timeout:
    print(f"Request timed out after {timeout}s", file=sys.stderr)
    sys.exit(1)
except Exception as _e:
    print(f"Error: {{_e}}", file=sys.stderr)
    sys.exit(1)
"""
        return script

    async def execute_and_log_http_request(
        self,
        assessment_id: int,
        params,
        db: AsyncSession,
        timeout: Optional[int] = None,
    ) -> "CommandHistory":
        """Execute an HTTP request via the generated Python script.

        Generates a Python script from the structured HttpRequestRequest params,
        then hands it to backend.exec_python() (docker exec or host-agent). Stores
        command_type='http' in CommandHistory with a human-readable command field
        ('HTTP POST http://target') and the generated Python script in source_code.
        """
        timeout = await self._resolve_timeout(db, timeout)

        self.current_container = await self._resolve_active_container(db)
        backend = self._get_backend()

        stmt = select(Assessment).filter(Assessment.id == assessment_id)
        result = await db.execute(stmt)
        assessment = result.scalar_one_or_none()
        working_directory = await self._ensure_workspace_exists(assessment, db)

        code = self._generate_http_python_script(params)
        display_command = f"HTTP {params.method.upper()} {params.url}"

        command_log = CommandHistory(
            assessment_id=assessment_id,
            container_name=self.current_container,
            command=display_command,
            phase=params.phase,
            status="running",
            command_type="http",
            source_code=code,
        )
        db.add(command_log)
        await db.commit()
        await db.refresh(command_log)

        try:
            result = await asyncio.wait_for(
                backend.exec_python(
                    code, cwd=working_directory, timeout=float(timeout)
                ),
                timeout=timeout + 5,
            )
            command_log.stdout = self._sanitize_output(result.get("stdout") or "")
            command_log.stderr = self._sanitize_output(result.get("stderr") or "")
            command_log.returncode = result.get("returncode")
            command_log.execution_time = result.get("execution_time")
            command_log.success = result.get("success")
            command_log.status = "completed" if result.get("success") else "failed"

            await db.commit()
            await db.refresh(command_log)
            await self._broadcast_result(command_log, assessment, assessment_id)
            return command_log

        except asyncio.TimeoutError:
            command_log.status = "timeout"
            command_log.timeout_at = datetime.utcnow()
            command_log.stderr = f"HTTP request exceeded {timeout}s timeout limit"
            command_log.success = False
            command_log.execution_time = timeout
            await db.commit()
            await db.refresh(command_log)
            await self._broadcast_timeout(command_log, assessment_id)
            return command_log

        except Exception as e:
            if command_log.status == "running":
                command_log.status = "failed"
                command_log.success = False
                command_log.stderr = self._sanitize_output(str(e))
                try:
                    await db.commit()
                    await db.refresh(command_log)
                except Exception:
                    await db.rollback()
            return command_log

    # ========== Workspace creation ==========

    async def create_workspace(
        self, assessment_name: str, db: Session = None
    ) -> Dict[str, str]:
        """Create the workspace folder for an assessment.

        Creates the directory structure:
            {base}/{assessment_name}/
            ├── recon/
            ├── exploits/
            ├── loot/
            ├── notes/
            ├── scripts/
            └── context/

        In container mode the base is `/workspace` inside the pentest
        container (bind-mounted to `~/.aida/workspaces` on the host).
        In localhost mode the base is the same `/workspace` path but the
        host-agent resolves it against the real host filesystem — start.sh
        creates the directory if it doesn't exist and wires the mount.
        """
        if settings.DEPLOYMENT_MODE != "localhost" and db:
            container_setting = (
                db.query(PlatformSettings)
                .filter(PlatformSettings.key == "container_name")
                .first()
            )
            if container_setting and container_setting.value:
                self.current_container = container_setting.value
            else:
                self.current_container = settings.DEFAULT_CONTAINER_NAME

        safe_name = assessment_name.replace(" ", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in ("_", "-"))

        base = (
            settings.LOCALHOST_WORKSPACE_BASE
            if settings.DEPLOYMENT_MODE == "localhost"
            else settings.CONTAINER_WORKSPACE_BASE
        )
        workspace_path = f"{base}/{safe_name}"

        backend = self._get_backend()
        subdirs = ["recon", "exploits", "loot", "notes", "scripts", "context"]
        await backend.ensure_workspace(workspace_path, subdirs)

        # Seed methodology.md — the agent updates this at the end of the
        # engagement. Written via a quoted heredoc so the content (which
        # contains an apostrophe in "AI's") doesn't require any escaping —
        # a plain `printf '...'` wrapper produced an unbalanced-quote error.
        methodology_path = shlex.quote(f"{workspace_path}/methodology.md")
        methodology_body = (
            "# Methodology Report\n"
            "\n"
            "> Generated by AIDA AI at the end of the engagement.\n"
            "> This document explains the AI's reasoning, approach, tools used, "
            "and full engagement summary.\n"
        )
        heredoc = f"cat > {methodology_path} <<'AIDA_METHODOLOGY_EOF'\n{methodology_body}AIDA_METHODOLOGY_EOF\n"
        await backend.exec_shell(heredoc)

        return {
            "workspace_path": workspace_path,
            "container_name": self.current_container,
        }
