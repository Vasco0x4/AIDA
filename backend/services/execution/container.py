"""
Container execution backend — runs commands inside the aida-pentest
(or any configured) Docker container via `docker exec`.

This is the historical AIDA execution path. All the logic here was lifted
verbatim from the original `ContainerService` helpers; the only change is
that it now lives behind the `ExecutionBackend` interface so the service
layer can swap to `HostAgentExecutionBackend` when deployment mode is
"localhost".
"""
import asyncio
import shlex
import time
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

from .base import ExecResult, ExecutionBackend

logger = get_logger(__name__)


# Stderr noise emitted by RVM/zsh hooks in the Exegol image; filtered so
# the dashboard doesn't surface it as a "warning" for every successful run.
_NOISE_MARKERS = ("chpwd", "rvm/scripts", "bash_zsh_support")


def _sanitize_output(output: str) -> str:
    """Strip null bytes and replace invalid UTF-8 so PostgreSQL can store it."""
    if not output:
        return output
    sanitized = output.replace("\x00", "")
    return sanitized.encode("utf-8", errors="replace").decode(
        "utf-8", errors="replace"
    )


def _filter_stderr_noise(stderr: str) -> str:
    if not stderr:
        return stderr
    return "\n".join(
        line for line in stderr.split("\n")
        if not any(marker in line for marker in _NOISE_MARKERS)
    ).strip()


class ContainerExecutionBackend(ExecutionBackend):
    """`docker exec` into a configured pentest container."""

    mode = "container"

    def __init__(self, container_name: str):
        self.container_name = container_name
        # Small health-check cache shared with ContainerService so we don't
        # docker-inspect on every command.
        self._health_cache: Optional[Dict[str, Any]] = None
        self._health_cache_ts: float = 0.0
        self._health_cache_ttl: float = 30.0

    @property
    def display_name(self) -> str:
        return self.container_name

    async def _run_process(
        self,
        argv: List[str],
        *,
        stdin_data: Optional[bytes] = None,
        timeout: float,
    ) -> Dict[str, Any]:
        """Spawn `argv` with a timeout and collect its output."""
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE
                if stdin_data is not None
                else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            return {
                "success": False,
                "returncode": 127,
                "stdout": "",
                "stderr": f"Command not found: {argv[0]} ({e})",
            }

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=stdin_data),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.communicate()
            except Exception:
                pass
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
            }

        return {
            "success": process.returncode == 0,
            "returncode": process.returncode,
            "stdout": stdout_bytes.decode("utf-8", errors="replace").strip(),
            "stderr": stderr_bytes.decode("utf-8", errors="replace").strip(),
        }

    async def validate_ready(self) -> Dict[str, Any]:
        """Confirm the target container exists and is running; start it if idle."""
        if not self.container_name:
            return {"success": False, "error": "No container name configured"}

        now = time.time()
        if self._health_cache and (now - self._health_cache_ts) < self._health_cache_ttl:
            return self._health_cache

        inspect = await self._run_process(
            ["docker", "inspect", self.container_name, "--format", "{{.State.Status}}"],
            timeout=15.0,
        )
        if not inspect["success"]:
            result = {
                "success": False,
                "error": "Container not found",
                "details": inspect["stderr"],
            }
            self._health_cache = result
            self._health_cache_ts = now
            return result

        status = inspect["stdout"].strip()
        if status == "running":
            result = {"success": True, "status": "running"}
        elif status in {"created", "exited"}:
            start = await self._run_process(
                ["docker", "start", self.container_name], timeout=30.0
            )
            if start["success"]:
                result = {"success": True, "status": "started"}
            else:
                result = {
                    "success": False,
                    "error": "Failed to start container",
                    "details": start["stderr"],
                }
        else:
            result = {
                "success": False,
                "error": f"Container in invalid state: {status}",
            }

        self._health_cache = result
        self._health_cache_ts = now
        return result

    async def exec_shell(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        validation = await self.validate_ready()
        if not validation["success"]:
            return {
                "success": False,
                "stdout": "",
                "stderr": validation.get("details", validation.get("error", "")),
                "returncode": -1,
                "execution_time": 0.0,
                "container": self.display_name,
                "error": f"Container validation failed: {validation.get('error', '')}",
            }

        # unset -f cd → RVM hooks redefine `cd` with noisy chpwd side effects.
        # source /root/.bashrc → picks up PATH for pre-installed tools.
        if cwd:
            wrapped = (
                f"unset -f cd 2>/dev/null; source /root/.bashrc 2>/dev/null"
                f" && cd {shlex.quote(cwd)} 2>/dev/null && {command}"
            )
        else:
            wrapped = (
                f"unset -f cd 2>/dev/null; source /root/.bashrc 2>/dev/null && {command}"
            )

        argv = ["docker", "exec"]
        if env:
            for key, value in env.items():
                argv += ["-e", f"{key}={value}"]
        argv += [self.container_name, "bash", "-c", wrapped]

        start = time.time()
        result = await self._run_process(argv, timeout=timeout)
        execution_time = time.time() - start

        return {
            "success": result["returncode"] == 0,
            "stdout": _sanitize_output(result["stdout"]),
            "stderr": _sanitize_output(_filter_stderr_noise(result["stderr"])),
            "returncode": result["returncode"],
            "execution_time": execution_time,
            "container": self.display_name,
        }

    async def exec_python(
        self,
        code: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        validation = await self.validate_ready()
        if not validation["success"]:
            return {
                "success": False,
                "stdout": "",
                "stderr": validation.get("details", validation.get("error", "")),
                "returncode": -1,
                "execution_time": 0.0,
                "container": self.display_name,
                "error": f"Container validation failed: {validation.get('error', '')}",
            }

        argv: List[str] = ["docker", "exec", "-i"]
        if cwd:
            argv += ["-w", cwd]
        argv += ["-e", "PYTHONUNBUFFERED=1"]
        if env:
            for key, value in env.items():
                argv += ["-e", f"{key}={value}"]
        argv += [self.container_name, "python3", "-"]

        start = time.time()
        result = await self._run_process(
            argv, stdin_data=code.encode("utf-8"), timeout=timeout
        )
        execution_time = time.time() - start

        return {
            "success": result["returncode"] == 0,
            "stdout": _sanitize_output(result["stdout"]),
            "stderr": _sanitize_output(result["stderr"]),
            "returncode": result["returncode"],
            "execution_time": execution_time,
            "container": self.display_name,
        }

    async def ensure_workspace(self, path: str, subdirs: List[str]) -> ExecResult:
        subdir_paths = [f"{path}/{sub}" for sub in subdirs]
        all_paths = [path] + subdir_paths
        mkdir = f"mkdir -p {' '.join(shlex.quote(p) for p in all_paths)}"

        result = await self._run_process(
            ["docker", "exec", self.container_name, "bash", "-c", mkdir],
            timeout=15.0,
        )
        return {
            "success": result["returncode"] == 0,
            "stdout": result["stdout"],
            "stderr": result["stderr"],
            "returncode": result["returncode"],
            "execution_time": 0.0,
            "container": self.display_name,
        }
