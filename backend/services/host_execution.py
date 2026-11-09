"""Opt-in, policy-constrained direct host command execution."""
from __future__ import annotations

import asyncio
import ipaddress
import math
import os
import re
import signal
import time
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from utils.redact import redact_text


_DEFAULT_NETWORK_ACTIONS = frozenset({
    "nmap", "masscan", "naabu", "nuclei", "httpx", "curl", "wget", "nc", "ncat",
    "netcat", "ping", "dig", "host", "sslscan", "testssl.sh", "ffuf", "gobuster",
    "dirsearch", "whatweb", "amass", "subfinder", "dnsx", "hydra", "medusa", "nxc",
    "netexec", "crackmapexec", "smbclient", "snmpwalk", "enum4linux", "enum4linux-ng",
})
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_SAFE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_REDACTED = "***REDACTED***"
_SENSITIVE_TEXT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[-_]?key|authorization|credential|"
    r"private[-_]?key|access[-_]?key|session|cookie)\b\s*[=:]\s*)([^\s&]+)",
)


def _redact_secret_text(value: str) -> str:
    return _SENSITIVE_TEXT.sub(lambda match: match.group(1) + _REDACTED, redact_text(value))


def _is_sensitive_key(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower().lstrip("-")).strip("_")
    parts = set(normalized.split("_"))
    return bool(parts & {
        "password", "passwd", "secret", "token", "authorization", "credential", "cookie",
    }) or normalized.endswith(("api_key", "access_key", "private_key", "session_key"))


def sanitize_args(args: list[str]) -> list[str]:
    """Return argv safe for operation history and audit records."""
    sanitized = []
    redact_next = False
    for arg in args:
        if redact_next:
            sanitized.append(_REDACTED)
            redact_next = False
            continue
        if "=" in arg:
            key, _value = arg.split("=", 1)
            if _is_sensitive_key(key):
                sanitized.append(f"{key}={_REDACTED}")
                continue
        if arg.startswith("-") and _is_sensitive_key(arg):
            sanitized.append(arg)
            redact_next = True
            continue
        sanitized.append(_redact_secret_text(arg))
    return sanitized


_DANGEROUS_ACTIONS = frozenset({
    "sudo", "su", "doas", "pkexec", "sh", "bash", "dash", "zsh", "fish", "ksh",
    "python", "python2", "python3", "perl", "ruby", "node", "php", "lua", "env",
    "xargs", "find", "awk", "gawk", "eval", "exec", "ssh", "scp", "sftp", "telnet",
    "rm", "dd", "mkfs", "mkfs.ext4", "fdisk", "parted", "mount", "umount", "chroot",
    "nsenter", "unshare", "docker", "podman", "kubectl", "systemctl", "service", "init",
    "shutdown", "reboot", "halt", "poweroff", "kill", "killall", "pkill", "yes",
    "stress", "stress-ng", "msfconsole", "msfvenom", "responder",
})
_DANGEROUS_ARGUMENTS = frozenset({
    "--interactive", "--flood", "--infinite", "-exec", "--exec", "--execute",
    "--command", "--shell", "--system", "--remote-command", "--script", "--lua-exec",
    "--config", "--input-file", "--list", "-il", "-list", "-t5",
})


class HostExecutionError(Exception):
    """A host execution request was rejected by policy."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class HostExecutionPolicy:
    enabled: bool = False
    allowed_working_directories: tuple[str, ...] = ()
    allowed_executables: frozenset[str] = frozenset()
    network_actions: frozenset[str] = frozenset()
    allowed_networks: tuple[str, ...] = ()
    allowed_dns_names: frozenset[str] = frozenset()
    timeout_seconds: float = 30.0
    max_output_bytes: int = 65536
    max_concurrent_executions: int = 4
    max_operation_history: int = 100

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "HostExecutionPolicy":
        """Load policy without inheriting application secrets or implicit opt-in."""
        env = os.environ if environ is None else environ
        prefix = "AIDA_HOST_EXECUTION_"
        defaults = cls()

        def csv(name: str) -> tuple[str, ...]:
            return tuple(item.strip() for item in env.get(prefix + name, "").split(",") if item.strip())

        def boolean(name: str) -> bool:
            key = prefix + name
            value = env.get(key, "false").strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off", ""}:
                return False
            raise ValueError(f"{key} must be a boolean")

        def number(name: str, default, cast):
            key = prefix + name
            try:
                value = cast(env.get(key, default))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{key} must be numeric") from exc
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"{key} must be finite and greater than zero")
            return value

        return cls(
            enabled=boolean("ENABLED"),
            allowed_working_directories=csv("ALLOWED_WORKING_DIRECTORIES"),
            allowed_executables=frozenset(csv("ALLOWED_EXECUTABLES")),
            network_actions=frozenset(csv("NETWORK_ACTIONS")),
            allowed_networks=csv("ALLOWED_NETWORKS"),
            allowed_dns_names=frozenset(csv("ALLOWED_DNS_NAMES")),
            timeout_seconds=number("TIMEOUT_SECONDS", defaults.timeout_seconds, float),
            max_output_bytes=number("MAX_OUTPUT_BYTES", defaults.max_output_bytes, int),
            max_concurrent_executions=number(
                "MAX_CONCURRENT_EXECUTIONS", defaults.max_concurrent_executions, int,
            ),
            max_operation_history=number(
                "MAX_OPERATION_HISTORY", defaults.max_operation_history, int,
            ),
        )


class HostExecutionService:
    def __init__(self, policy: HostExecutionPolicy):
        self.policy = policy
        self._operations: dict[str, dict] = {}
        self._active = 0
        self._allowed_networks = tuple(
            ipaddress.ip_network(network, strict=True) for network in policy.allowed_networks
        )
        self._allowed_dns_names = frozenset(
            name.lower().rstrip(".") for name in policy.allowed_dns_names
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _working_directory(self, value: str) -> str:
        try:
            candidate = Path(value).resolve(strict=True)
            roots = [Path(root).resolve(strict=True) for root in self.policy.allowed_working_directories]
        except (OSError, RuntimeError) as exc:
            raise HostExecutionError(
                "invalid_working_directory", "Working directory or allowlisted root is unavailable",
            ) from exc
        if not candidate.is_dir() or not all(root.is_dir() for root in roots):
            raise HostExecutionError("invalid_working_directory", "Working directory is not a directory")
        if not any(candidate == root or candidate.is_relative_to(root) for root in roots):
            raise HostExecutionError("working_directory_denied", "Working directory is not allowlisted")
        return str(candidate)

    def _executable(self, action: str) -> str:
        if action not in self.policy.allowed_executables:
            raise HostExecutionError("action_denied", "Executable or action is not allowlisted")
        executable = shutil.which(action, path=_SAFE_PATH)
        if not executable:
            raise HostExecutionError("executable_not_found", "Allowlisted executable was not found")
        return executable

    @staticmethod
    def _validate_args(args: list[str]) -> None:
        if len(args) > 64 or sum(len(arg) for arg in args if isinstance(arg, str)) > 16384:
            raise HostExecutionError("unsafe_argument", "Argument count or size exceeds policy")
        for arg in args:
            if not isinstance(arg, str) or len(arg) > 4096:
                raise HostExecutionError("unsafe_argument", "Arguments must be bounded strings")
            if any(ord(char) < 32 or ord(char) == 127 for char in arg):
                raise HostExecutionError("unsafe_argument", "Control characters are not allowed")
            if re.search(r"[;&|<>`$(){}\[\]*?]", arg):
                raise HostExecutionError("unsafe_argument", "Shell metacharacters are not allowed")
            # Host commands are not a filesystem sandbox. Keep every explicit
            # file operand inside the already-resolved working roots; service
            # accounts must additionally have least-privilege filesystem ACLs.
            if (arg.startswith("/") or "=/" in arg or arg == ".."
                    or arg.startswith("../") or "/../" in arg or arg.endswith("/..")):
                raise HostExecutionError(
                    "unsafe_argument", "Absolute paths and parent traversal are not allowed")

    @staticmethod
    def _validate_not_dangerous(action: str, args: list[str]) -> None:
        if action in _DANGEROUS_ACTIONS:
            raise HostExecutionError("dangerous_action", "Dangerous or privileged actions are forbidden")
        for arg in args:
            normalized = arg.lower()
            option = normalized.split("=", 1)[0]
            if normalized in _DANGEROUS_ARGUMENTS or option in _DANGEROUS_ARGUMENTS:
                raise HostExecutionError(
                    "dangerous_argument", "Command execution, privilege escalation, and DoS flags are forbidden",
                )

    def _validate_target(self, value: str) -> str:
        if not isinstance(value, str) or not value or len(value) > 253 or "%" in value:
            raise HostExecutionError("target_denied", "Network target is invalid or not authorized")
        target = value.lower().rstrip(".")
        try:
            if "/" in target:
                network = ipaddress.ip_network(target, strict=True)
                if any(
                    network.version == allowed.version and network.subnet_of(allowed)
                    for allowed in self._allowed_networks
                ):
                    return str(network)
            else:
                address = ipaddress.ip_address(target)
                if any(
                    address.version == allowed.version and address in allowed
                    for allowed in self._allowed_networks
                ):
                    return str(address)
        except ValueError:
            pass
        labels = target.split(".")
        if (
            target in self._allowed_dns_names
            and len(target) <= 253
            and all(_DNS_LABEL.fullmatch(label) for label in labels)
        ):
            return target
        raise HostExecutionError("target_denied", "Network target is outside authorized scope")

    def _extract_argument_targets(self, args: list[str], declared: set[str]) -> list[str]:
        extracted: list[str] = []
        for arg in args:
            candidate = arg
            if arg.startswith(("http://", "https://")):
                try:
                    candidate = urlsplit(arg).hostname or ""
                except ValueError:
                    candidate = ""
            elif "=" in arg and arg.split("=", 1)[0].lower() in {
                "--target", "-target", "--url", "-u", "--host", "--domain", "-d",
            }:
                candidate = arg.split("=", 1)[1]
            elif arg.startswith("-"):
                continue
            looks_like_target = (
                "." in candidate or ":" in candidate or "/" in candidate
                or candidate.lower().rstrip(".") in declared
                or candidate.lower().rstrip(".") in self._allowed_dns_names
            )
            if candidate and looks_like_target:
                extracted.append(self._validate_target(candidate))
        return extracted

    def _validate_network(self, action: str, args: list[str], targets: list[str]) -> list[str]:
        if action not in _DEFAULT_NETWORK_ACTIONS and action not in self.policy.network_actions:
            return []
        if not targets:
            raise HostExecutionError("target_required", "Network actions require explicit targets")
        validated = [self._validate_target(target) for target in targets]
        declared = set(validated)
        extracted = set(self._extract_argument_targets(args, declared))
        if not extracted or extracted != declared:
            raise HostExecutionError(
                "target_mismatch", "Declared targets must exactly match targets in command arguments",
            )
        return validated

    async def _read_bounded(self, stream) -> tuple[bytes, bool]:
        captured = bytearray()
        truncated = False
        limit = self.policy.max_output_bytes
        while True:
            remaining = limit - len(captured)
            chunk = await stream.read(remaining + 1 if remaining < 65536 else 65536)
            if not chunk:
                return bytes(captured), truncated
            if len(chunk) > remaining:
                truncated = True
                captured.extend(chunk[:remaining])
            else:
                captured.extend(chunk)

    async def _collect_output(self, process) -> tuple[bytes, bytes, bool, bool]:
        if hasattr(process, "stdout") and hasattr(process, "stderr"):
            stdout_task = asyncio.create_task(self._read_bounded(process.stdout))
            stderr_task = asyncio.create_task(self._read_bounded(process.stderr))
            (stdout, stdout_truncated), (stderr, stderr_truncated) = await asyncio.gather(
                stdout_task, stderr_task,
            )
            await process.wait()
            return stdout, stderr, stdout_truncated, stderr_truncated
        # Lightweight subprocess doubles may only implement communicate().
        stdout, stderr = await process.communicate()
        limit = self.policy.max_output_bytes
        return stdout[:limit], stderr[:limit], len(stdout) > limit, len(stderr) > limit

    def _render_output(self, value: bytes, *, truncated: bool, suffix: str = "") -> tuple[str, bool]:
        """Redact decoded output, then enforce the cap on the final UTF-8 bytes."""
        text = _redact_secret_text(value.decode("utf-8", errors="replace")) + suffix
        encoded = text.encode("utf-8")
        if len(encoded) > self.policy.max_output_bytes:
            truncated = True
            text = encoded[:self.policy.max_output_bytes].decode("utf-8", errors="ignore")
        return text, truncated

    async def execute(
        self, *, action: str, args: list[str], working_directory: str,
        targets: list[str] | None = None,
    ):
        if self._active >= self.policy.max_concurrent_executions:
            raise HostExecutionError(
                "concurrency_limit", "Host execution concurrency limit reached",
            )
        self._active += 1
        started = time.monotonic()
        try:
            result = await self._execute(
                action=action, args=args, working_directory=working_directory, targets=targets,
            )
            from services.metrics import HOST_EXECUTIONS
            HOST_EXECUTIONS.labels(result=result["status"]).inc()
            from services.metrics import HOST_DURATION
            HOST_DURATION.labels(result=result["status"]).observe(time.monotonic() - started)
            return result
        except HostExecutionError as exc:
            from services.metrics import HOST_EXECUTIONS
            HOST_EXECUTIONS.labels(result=exc.code).inc()
            from services.metrics import HOST_DURATION
            HOST_DURATION.labels(result=exc.code).observe(time.monotonic() - started)
            raise
        finally:
            self._active -= 1

    async def _execute(
        self, *, action: str, args: list[str], working_directory: str,
        targets: list[str] | None = None,
    ):
        if not self.policy.enabled:
            raise HostExecutionError("disabled", "Direct host execution is disabled")
        cwd = self._working_directory(working_directory)
        self._validate_not_dangerous(action, args)
        self._validate_args(args)
        validated_targets = self._validate_network(action, args, targets or [])
        executable = self._executable(action)
        operation_id = uuid.uuid4().hex
        record = {
            "operation_id": operation_id,
            "action": action,
            "args": sanitize_args(args),
            "targets": validated_targets,
            "working_directory": cwd,
            "status": "running",
            "success": False,
            "stdout": "",
            "stderr": "",
            "returncode": None,
            "created_at": self._now(),
            "completed_at": None,
        }
        while len(self._operations) >= self.policy.max_operation_history:
            self._operations.pop(next(iter(self._operations)))
        self._operations[operation_id] = record
        process = await asyncio.create_subprocess_exec(
            executable,
            *args,
            cwd=cwd,
            env={
                "PATH": _SAFE_PATH,
                "HOME": cwd,
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
                "TERM": "dumb",
                "NO_COLOR": "1",
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr, stdout_truncated, stderr_truncated = await asyncio.wait_for(
                self._collect_output(process), timeout=self.policy.timeout_seconds,
            )
        except TimeoutError:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except (AttributeError, NotImplementedError, PermissionError):
                process.kill()
            stdout, stderr, stdout_truncated, stderr_truncated = await self._collect_output(process)
        stdout_text, stdout_truncated = self._render_output(
            stdout, truncated=stdout_truncated,
        )
        stderr_text, stderr_truncated = self._render_output(
            stderr,
            truncated=stderr_truncated,
            suffix=(f"Execution timed out after {self.policy.timeout_seconds} seconds\n" if timed_out else ""),
        )
        record.update({
            "status": "timeout" if timed_out else ("completed" if process.returncode == 0 else "failed"),
            "success": not timed_out and process.returncode == 0,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "returncode": process.returncode,
            "completed_at": self._now(),
        })
        return dict(record)

    def list_operations(self) -> list[dict]:
        return [dict(record) for record in self._operations.values()]

    def get_operation(self, operation_id: str) -> dict | None:
        record = self._operations.get(operation_id)
        return dict(record) if record else None

    @property
    def active_count(self) -> int:
        return self._active
