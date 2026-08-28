"""
Host-agent execution backend — runs commands on the host machine via a
Unix-socket call to the aida-host-agent daemon.

The daemon lives in `tools/host_agent.py` and is started on the host by
`start.sh --localhost`. The backend container connects to a socket that's
bind-mounted from `~/.aida/host-agent.sock` (host) to
`/var/run/aida-host-agent.sock` (container).

Wire protocol mirrors the daemon's: one newline-delimited JSON object per
connection, response on the same connection, then close. Every request
carries a shared-secret token read from a file bind-mounted read-only into
the backend container.
"""
import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

from .base import ExecResult, ExecutionBackend

logger = get_logger(__name__)


# Upper bound on a single response line. The daemon itself caps raw output
# at 50 MB before sending, so anything past that is pathological.
_MAX_LINE_BYTES = 64 * 1024 * 1024  # 64 MB


class HostAgentExecutionBackend(ExecutionBackend):
    """Execute on the host by proxying through the host-agent socket."""

    mode = "localhost"

    def __init__(
        self,
        socket_path: str,
        token_path: str,
        label: str = "localhost",
    ):
        self.socket_path = socket_path
        self.token_path = token_path
        self.label = label
        self._token_cache: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.label

    def _load_token(self) -> Optional[str]:
        # Read-once cache. The token file is mounted read-only; re-reading
        # it every request would just be unnecessary fs work.
        if self._token_cache is not None:
            return self._token_cache
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except OSError as e:
            logger.error(
                "Failed to read host-agent token",
                token_path=self.token_path,
                error=str(e),
            )
            return None
        if not token:
            logger.error("Host-agent token file is empty", token_path=self.token_path)
            return None
        self._token_cache = token
        return token

    async def _call(
        self,
        method: str,
        params: Dict[str, Any],
        *,
        timeout: float,
    ) -> Dict[str, Any]:
        """Send one request to the host-agent, return its parsed response.

        On any transport-level failure (socket missing, daemon not running,
        auth rejected, malformed JSON) we return an error dict that the
        caller turns into a failed ExecResult. We never raise — the upper
        layers are built around the ExecResult shape.
        """
        token = self._load_token()
        if not token:
            return {
                "ok": False,
                "error": (
                    f"Host agent token not available at {self.token_path}. "
                    "Run ./start.sh --localhost to generate one."
                ),
            }

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self.socket_path),
                timeout=5.0,
            )
        except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
            return {
                "ok": False,
                "error": (
                    f"Cannot reach host agent at {self.socket_path}: {e}. "
                    "Make sure the host agent is running (./start.sh --localhost)."
                ),
            }
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": f"Timed out connecting to host agent at {self.socket_path}",
            }

        try:
            request = {"token": token, "method": method, "params": params}
            payload = json.dumps(request).encode("utf-8") + b"\n"
            writer.write(payload)
            await writer.drain()

            try:
                line = await asyncio.wait_for(
                    reader.readline(), timeout=timeout + 10.0
                )
            except asyncio.TimeoutError:
                return {
                    "ok": False,
                    "error": f"Host agent did not respond within {timeout + 10.0}s",
                }

            if not line:
                return {"ok": False, "error": "Host agent closed the connection"}

            if len(line) > _MAX_LINE_BYTES:
                return {
                    "ok": False,
                    "error": f"Host agent response exceeded {_MAX_LINE_BYTES} bytes",
                }

            try:
                return json.loads(line.decode("utf-8"))
            except json.JSONDecodeError as e:
                return {
                    "ok": False,
                    "error": f"Host agent returned malformed JSON: {e}",
                }
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def validate_ready(self) -> Dict[str, Any]:
        response = await self._call("ping", {}, timeout=5.0)
        if response.get("ok") and response.get("pong"):
            return {"success": True, "status": "running"}
        return {
            "success": False,
            "error": response.get("error", "Host agent ping failed"),
        }

    def _response_to_exec_result(
        self, response: Dict[str, Any], *, elapsed: float
    ) -> ExecResult:
        # Transport-level failure — the daemon never got a chance to answer.
        if not response.get("ok"):
            return {
                "success": False,
                "stdout": "",
                "stderr": response.get("error", "Host agent error"),
                "returncode": -1,
                "execution_time": elapsed,
                "container": self.display_name,
                "error": response.get("error", "Host agent error"),
            }

        # Daemon responded but the underlying process failed — normal case,
        # propagate its fields verbatim.
        return {
            "success": bool(response.get("success", False)),
            "stdout": response.get("stdout", "") or "",
            "stderr": response.get("stderr", "") or "",
            "returncode": int(response.get("returncode", -1)),
            "execution_time": float(response.get("execution_time", elapsed)),
            "container": self.display_name,
        }

    async def exec_shell(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        params: Dict[str, Any] = {"command": command, "timeout": timeout}
        if cwd:
            params["cwd"] = cwd
        if env:
            params["env"] = env

        start = time.time()
        response = await self._call("exec_shell", params, timeout=timeout)
        elapsed = time.time() - start
        return self._response_to_exec_result(response, elapsed=elapsed)

    async def exec_python(
        self,
        code: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        params: Dict[str, Any] = {"code": code, "timeout": timeout}
        if cwd:
            params["cwd"] = cwd
        if env:
            params["env"] = env

        start = time.time()
        response = await self._call("exec_python", params, timeout=timeout)
        elapsed = time.time() - start
        return self._response_to_exec_result(response, elapsed=elapsed)

    async def ensure_workspace(self, path: str, subdirs: List[str]) -> ExecResult:
        response = await self._call(
            "ensure_dir", {"path": path, "subdirs": subdirs}, timeout=10.0
        )
        if not response.get("ok"):
            return {
                "success": False,
                "stdout": "",
                "stderr": response.get("error", "ensure_dir failed"),
                "returncode": -1,
                "execution_time": 0.0,
                "container": self.display_name,
                "error": response.get("error", "ensure_dir failed"),
            }
        created = response.get("created") or []
        return {
            "success": True,
            "stdout": "\n".join(created),
            "stderr": "",
            "returncode": 0,
            "execution_time": 0.0,
            "container": self.display_name,
        }
