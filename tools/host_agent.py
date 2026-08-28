#!/usr/bin/env python3
"""
AIDA Host Agent — Unix-socket execution bridge for localhost deployment mode.

Runs on the host (not in Docker). The backend container reaches it via a
bind-mounted socket at /var/run/aida-host-agent.sock. This lets the backend
execute commands directly on the host instead of `docker exec`-ing into the
aida-pentest container.

Security model
--------------
The agent is invoked only when the user opts into localhost mode via
`./start.sh --localhost`. Running commands on the host is intrinsically
risky, so the agent has several layers of defense:

  1. Unix domain socket in ~/.aida/, chmod 0600 — only the owner UID can
     connect. The socket is not reachable from the network.
  2. Shared-secret token handshake on every request. The token is generated
     at setup time (32 random bytes, hex-encoded) and also chmod 0600.
     Defense in depth against a local attacker who somehow bypassed (1).
  3. Commands are executed via bash -c / python3 -, exactly the same way
     docker exec would execute them inside the pentest container. The
     approval layer in the AIDA backend (open / filter / closed modes) is
     the primary safety gate — localhost mode defaults to `closed` on
     first start so the user explicitly approves every command.

Wire protocol
-------------
Newline-delimited JSON over the Unix socket. One request per connection,
one response, then close. The backend uses a short-lived connection per
request — simpler to reason about than long-lived multiplexed streams.

Request:
  {"token": "<hex>", "method": "<method_name>", "params": {...}}

Response:
  {"ok": true/false, "error": "<msg>" (on failure), ...method-specific fields}

Methods:
  - ping                                         → {"ok": true}
  - exec_shell   {command, cwd, timeout, env}    → {ok, success, stdout,
                                                    stderr, returncode,
                                                    execution_time}
  - exec_python  {code, cwd, timeout, env}       → (same shape as exec_shell)
  - ensure_dir   {path, subdirs?}                → {ok, created: [paths]}

All shell/python output is UTF-8 decoded with errors='replace' and sanitized
(null-byte stripping) to match the existing CommandHistory storage format.
"""
import argparse
import asyncio
import errno
import hmac
import json
import logging
import os
import signal
import stat
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

LOG_FILE = os.environ.get("AIDA_HOST_AGENT_LOG", "/tmp/aida_host_agent.log")
DEFAULT_SOCKET = os.environ.get(
    "AIDA_HOST_AGENT_SOCKET",
    str(Path.home() / ".aida" / "host-agent.sock"),
)
DEFAULT_TOKEN_PATH = os.environ.get(
    "AIDA_HOST_AGENT_TOKEN",
    str(Path.home() / ".aida" / "host-agent.token"),
)

# Hard cap on any single response (stdout + stderr combined). The backend
# enforces its own truncation for display; this is the raw-output safety net.
MAX_OUTPUT_BYTES = 50 * 1024 * 1024  # 50 MB
DEFAULT_TIMEOUT = 300.0
MAX_TIMEOUT = 3600.0


logger = logging.getLogger("aida.host_agent")

# Populated in main() from --workspace-map. Keys are container-view path
# prefixes (e.g. "/workspace") seen by the Dockerized backend; values are
# the corresponding real host paths (e.g. "$HOME/.aida/workspaces"). Every
# `path` and `cwd` received from the backend is rewritten through this
# table before touching the filesystem — the backend has no way to know
# the real $HOME of the host user, so we translate on the agent side.
_PATH_MAP: list = []  # list of (container_prefix, host_prefix) tuples


def _translate_path(path: Optional[str]) -> Optional[str]:
    """Rewrite a container-view path to its real host path.

    Matching rules:
      - exact prefix match on a full path component boundary
      - empty/None input passes through
      - paths that don't match any prefix pass through unchanged (useful
        for absolute host paths the caller already translated, or for
        paths like /tmp that are identical in both views)
    """
    if not path:
        return path
    for container_prefix, host_prefix in _PATH_MAP:
        if path == container_prefix:
            return host_prefix
        if path.startswith(container_prefix + "/"):
            return host_prefix + path[len(container_prefix):]
    return path


def _setup_logging() -> None:
    handler = logging.FileHandler(LOG_FILE)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _sanitize_output(output: bytes) -> str:
    """Decode bytes as UTF-8 (with replacement) and strip null bytes.

    Matches ContainerService._sanitize_output so CommandHistory storage
    behavior is identical in both modes.
    """
    if not output:
        return ""
    text = output.decode("utf-8", errors="replace").replace("\x00", "")
    if len(text.encode("utf-8", errors="replace")) > MAX_OUTPUT_BYTES:
        truncated = text.encode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
        text = truncated.decode("utf-8", errors="replace")
        text += "\n\n...(output truncated by host agent at 50 MB)"
    return text


def _load_token(token_path: str) -> str:
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()
    except FileNotFoundError:
        raise SystemExit(
            f"Token file not found: {token_path}\n"
            "Run ./start.sh --localhost to generate one."
        )
    if not token:
        raise SystemExit(f"Token file is empty: {token_path}")
    return token


def _authorized(provided: Optional[str], expected: str) -> bool:
    if not provided or not isinstance(provided, str):
        return False
    return hmac.compare_digest(provided, expected)


async def _run_process(
    argv: list,
    *,
    stdin_data: Optional[bytes] = None,
    cwd: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Spawn a subprocess and collect its output with a timeout."""
    start = time.time()
    full_env = os.environ.copy()
    if env:
        full_env.update({str(k): str(v) for k, v in env.items()})

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=full_env,
        )
    except FileNotFoundError as e:
        return {
            "ok": True,
            "success": False,
            "stdout": "",
            "stderr": f"Command not found: {argv[0]} ({e})",
            "returncode": 127,
            "execution_time": 0.0,
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
            "ok": True,
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
            "execution_time": timeout,
        }

    execution_time = time.time() - start
    return {
        "ok": True,
        "success": process.returncode == 0,
        "stdout": _sanitize_output(stdout_bytes),
        "stderr": _sanitize_output(stderr_bytes),
        "returncode": process.returncode,
        "execution_time": execution_time,
    }


# ========== Method handlers ==========


async def _method_ping(_params: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "pong": True}


async def _method_exec_shell(params: Dict[str, Any]) -> Dict[str, Any]:
    command = params.get("command")
    if not isinstance(command, str) or not command.strip():
        return {"ok": False, "error": "command must be a non-empty string"}

    cwd = params.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        return {"ok": False, "error": "cwd must be a string"}

    env = params.get("env")
    if env is not None and not isinstance(env, dict):
        return {"ok": False, "error": "env must be an object"}

    timeout = float(params.get("timeout", DEFAULT_TIMEOUT))
    timeout = max(1.0, min(timeout, MAX_TIMEOUT))

    host_cwd = _translate_path(cwd)
    # cwd is a caller hint; if it doesn't exist we let bash produce the
    # error so the user sees a consistent "cd: no such file" message.
    argv = ["bash", "-c", command]
    result = await _run_process(argv, cwd=host_cwd, env=env, timeout=timeout)
    logger.info(
        "exec_shell cwd=%s host_cwd=%s rc=%s elapsed=%.2fs",
        cwd, host_cwd, result.get("returncode"), result.get("execution_time", 0.0),
    )
    return result


async def _method_exec_python(params: Dict[str, Any]) -> Dict[str, Any]:
    code = params.get("code")
    if not isinstance(code, str) or not code.strip():
        return {"ok": False, "error": "code must be a non-empty string"}

    cwd = params.get("cwd")
    if cwd is not None and not isinstance(cwd, str):
        return {"ok": False, "error": "cwd must be a string"}

    env = params.get("env")
    if env is not None and not isinstance(env, dict):
        return {"ok": False, "error": "env must be an object"}

    timeout = float(params.get("timeout", DEFAULT_TIMEOUT))
    timeout = max(1.0, min(timeout, MAX_TIMEOUT))

    py_env = dict(env) if env else {}
    py_env.setdefault("PYTHONUNBUFFERED", "1")

    host_cwd = _translate_path(cwd)
    result = await _run_process(
        ["python3", "-"],
        stdin_data=code.encode("utf-8"),
        cwd=host_cwd,
        env=py_env,
        timeout=timeout,
    )
    logger.info(
        "exec_python cwd=%s host_cwd=%s rc=%s elapsed=%.2fs bytes=%d",
        cwd, host_cwd, result.get("returncode"), result.get("execution_time", 0.0), len(code),
    )
    return result


async def _method_ensure_dir(params: Dict[str, Any]) -> Dict[str, Any]:
    path = params.get("path")
    if not isinstance(path, str) or not path.strip():
        return {"ok": False, "error": "path must be a non-empty string"}

    subdirs = params.get("subdirs") or []
    if not isinstance(subdirs, list) or not all(isinstance(s, str) for s in subdirs):
        return {"ok": False, "error": "subdirs must be a list of strings"}

    host_path = _translate_path(path)
    created = []
    try:
        root = Path(host_path).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        created.append(str(root))
        for sub in subdirs:
            if "/" in sub or sub.startswith(".."):
                return {"ok": False, "error": f"invalid subdir name: {sub!r}"}
            child = root / sub
            child.mkdir(parents=True, exist_ok=True)
            created.append(str(child))
    except OSError as e:
        return {"ok": False, "error": f"mkdir failed: {e}"}

    logger.info("ensure_dir path=%s host_path=%s subdirs=%s", path, host_path, subdirs)
    return {"ok": True, "created": created}


METHODS = {
    "ping": _method_ping,
    "exec_shell": _method_exec_shell,
    "exec_python": _method_exec_python,
    "ensure_dir": _method_ensure_dir,
}


# ========== Connection handling ==========


async def _read_request(reader: asyncio.StreamReader) -> Optional[Dict[str, Any]]:
    # One request per connection, delimited by a newline. Keeps the framing
    # dead simple. Backend code writes a single JSON object + '\n' and
    # waits for our response.
    try:
        line = await asyncio.wait_for(reader.readline(), timeout=30.0)
    except asyncio.TimeoutError:
        return None
    if not line:
        return None
    try:
        return json.loads(line.decode("utf-8"))
    except json.JSONDecodeError as e:
        return {"__decode_error__": str(e)}


async def _write_response(writer: asyncio.StreamWriter, payload: Dict[str, Any]) -> None:
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        writer.write(data)
        await writer.drain()
    except Exception as e:
        logger.warning("failed to write response: %s", e)


async def _handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    token: str,
) -> None:
    try:
        req = await _read_request(reader)
        if req is None:
            await _write_response(writer, {"ok": False, "error": "empty request"})
            return
        if "__decode_error__" in req:
            await _write_response(
                writer,
                {"ok": False, "error": f"invalid JSON: {req['__decode_error__']}"},
            )
            return

        if not _authorized(req.get("token"), token):
            await _write_response(writer, {"ok": False, "error": "unauthorized"})
            logger.warning("unauthorized request (bad or missing token)")
            return

        method = req.get("method")
        params = req.get("params") or {}
        if not isinstance(params, dict):
            await _write_response(writer, {"ok": False, "error": "params must be an object"})
            return

        handler = METHODS.get(method)
        if handler is None:
            await _write_response(writer, {"ok": False, "error": f"unknown method: {method!r}"})
            return

        try:
            response = await handler(params)
        except Exception as e:
            logger.exception("handler %s raised", method)
            response = {"ok": False, "error": f"handler error: {e}"}

        await _write_response(writer, response)
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


# ========== Server lifecycle ==========


def _prepare_socket_path(socket_path: str) -> None:
    sock = Path(socket_path)
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        try:
            sock.unlink()
        except OSError as e:
            raise SystemExit(f"Cannot remove stale socket {sock}: {e}")
    try:
        sock.parent.chmod(stat.S_IRWXU)
    except OSError:
        # Non-fatal; parent dir may already be owned by another UID in
        # edge cases. The socket itself is the important part.
        pass


def _lock_socket_permissions(socket_path: str) -> None:
    try:
        os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError as e:
        logger.warning("chmod 0600 on socket failed: %s", e)


async def _run_server(socket_path: str, token: str) -> None:
    _prepare_socket_path(socket_path)

    async def _client_cb(reader, writer):
        await _handle_connection(reader, writer, token=token)

    server = await asyncio.start_unix_server(_client_cb, path=socket_path)
    _lock_socket_permissions(socket_path)
    logger.info("listening on %s (pid=%d)", socket_path, os.getpid())

    stop_event = asyncio.Event()

    def _stop(signum, _frame):
        logger.info("received signal %s — shutting down", signum)
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows fallback; not supported here anyway.
            signal.signal(sig, _stop)

    async with server:
        server_task = asyncio.create_task(server.serve_forever())
        await stop_event.wait()
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    try:
        os.unlink(socket_path)
    except OSError as e:
        if e.errno != errno.ENOENT:
            logger.warning("cleanup failed for %s: %s", socket_path, e)
    logger.info("shutdown complete")


def main() -> None:
    parser = argparse.ArgumentParser(description="AIDA host-agent daemon (localhost mode)")
    parser.add_argument("--socket", default=DEFAULT_SOCKET, help="Unix socket path")
    parser.add_argument("--token", default=DEFAULT_TOKEN_PATH, help="Path to shared-secret token")
    parser.add_argument("--pidfile", default=None, help="Optional pidfile path")
    parser.add_argument(
        "--workspace-map",
        action="append",
        default=None,
        metavar="CONTAINER_PREFIX=HOST_PREFIX",
        help=(
            "Translate a container-view path prefix to a host path. "
            "May be given multiple times. Defaults to "
            "'/workspace=$HOME/.aida/workspaces'."
        ),
    )
    args = parser.parse_args()

    _setup_logging()

    # Build the container→host path prefix table. Default matches the bind
    # mount layout set up by docker-compose.localhost.yml.
    mappings = args.workspace_map or [
        f"/workspace={os.path.expanduser('~/.aida/workspaces')}"
    ]
    for raw in mappings:
        if "=" not in raw:
            raise SystemExit(
                f"--workspace-map expects CONTAINER_PREFIX=HOST_PREFIX, got {raw!r}"
            )
        container_prefix, host_prefix = raw.split("=", 1)
        container_prefix = container_prefix.rstrip("/") or "/"
        host_prefix = os.path.expanduser(host_prefix.rstrip("/"))
        _PATH_MAP.append((container_prefix, host_prefix))
    logger.info("workspace path map: %s", _PATH_MAP)

    token = _load_token(args.token)

    if args.pidfile:
        try:
            with open(args.pidfile, "w", encoding="utf-8") as f:
                f.write(str(os.getpid()))
        except OSError as e:
            logger.warning("failed to write pidfile %s: %s", args.pidfile, e)

    try:
        asyncio.run(_run_server(args.socket, token))
    except KeyboardInterrupt:
        pass
    finally:
        if args.pidfile and os.path.exists(args.pidfile):
            try:
                os.unlink(args.pidfile)
            except OSError:
                pass


if __name__ == "__main__":
    main()
