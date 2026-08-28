"""
Abstract execution backend interface.

An `ExecutionBackend` encapsulates "how do I run a shell command or Python
snippet against the target environment". The two concrete implementations
are:

- ContainerExecutionBackend — `docker exec` against the pentest container.
- HostAgentExecutionBackend — Unix-socket call to the host-agent daemon
  which subprocess-executes on the host itself.

Both return results with the same shape (`ExecResult`) so the surrounding
service layer can treat them interchangeably.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TypedDict


class ExecResult(TypedDict, total=False):
    """Canonical result shape returned by every execution backend.

    Mirrors the historical dict returned by ContainerService._run_command
    so CommandHistory storage code (stdout/stderr/returncode/execution_time
    fields) keeps working without changes.
    """
    success: bool
    stdout: str
    stderr: str
    returncode: int
    execution_time: float
    container: str           # display label (real container name or "localhost")
    error: str               # optional — only on transport-level failures


class ExecutionBackend(ABC):
    """Common contract for container-vs-localhost command execution."""

    # Human-readable mode name, used in logs and as `CommandHistory.container_name`
    # when a backend is active.
    mode: str = "abstract"

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Short string identifying this backend instance ("aida-pentest",
        "localhost"). Used for CommandHistory.container_name so the UI
        and logs show where a command actually ran."""

    @abstractmethod
    async def exec_shell(
        self,
        command: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Run a shell command end-to-end. `bash -c <command>`.

        Implementations must:
          - Wrap with `cd <cwd>` if cwd is provided.
          - Source /root/.bashrc (container mode) or fall back to the
            user's default shell init (localhost mode). This is best-effort
            — callers shouldn't rely on shell aliases.
          - Enforce `timeout`, killing stragglers on expiry.
          - Return the ExecResult shape with sanitized UTF-8 output.
        """

    @abstractmethod
    async def exec_python(
        self,
        code: str,
        *,
        cwd: Optional[str] = None,
        timeout: float = 300.0,
        env: Optional[Dict[str, str]] = None,
    ) -> ExecResult:
        """Run a Python snippet by piping it to `python3 -` via stdin."""

    @abstractmethod
    async def ensure_workspace(self, path: str, subdirs: List[str]) -> ExecResult:
        """Idempotent `mkdir -p` for the workspace and its subdirectories.

        Returns an ExecResult for uniformity, even though the useful
        information is just the success flag. Callers don't care about
        stdout for mkdir, but may surface stderr on failure.
        """

    @abstractmethod
    async def validate_ready(self) -> Dict[str, Any]:
        """Pre-flight check: is this backend reachable and usable?

        Container mode: verify the container exists and is running, start
        it if `created`/`exited`.
        Localhost mode: open the socket, send `ping`, confirm `pong`.

        Returns:
            Dict with at least `{"success": bool}`, plus optional
            `status`/`error`/`details` keys for diagnostics.
        """
