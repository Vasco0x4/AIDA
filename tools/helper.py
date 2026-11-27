#!/usr/bin/env python3
"""
AIDA Host Helper — small local HTTP helper running on the host (not Docker).

Provides three actions to the AIDA frontend:
  POST /open    {path}                    → open a folder in the host file explorer
  POST /launch  {assessment_name, mode}   → open a terminal running, for mode
                                            "agent": aida run <name> (Claude Code
                                            in the assessment's container), for
                                            "cli" (default): aida --assessment <name>
  GET  /status                            → liveness check (no system info)

Security model
--------------
The helper binds to 127.0.0.1 only, so the network attack surface is limited
to processes on the same machine. The realistic threats are:

  1. A malicious website loaded in the user's browser making cross-origin
     requests to localhost:9876.
  2. Crafted input that breaks out of shell quoting or path validation.

Defenses applied:

  - Strict Origin allowlist — every request must carry an Origin header
    pointing at the AIDA frontend (https://localhost:31337 or the Vite dev
    server on port 5173). Browsers always send accurate Origin headers
    on cross-origin XHR/fetch, so a website at https://evil.com cannot
    forge it. The CORS response echoes the validated origin (never *).
  - Path allowlist on /open — only directories under AIDA_ROOT or
    ~/.aida/workspaces can be opened, so the helper cannot be used to
    enumerate the user's home directory.
  - Strict regex on assessment_name — alphanumerics, spaces, dashes,
    underscores, dots only. Defense in depth on top of shlex quoting.
    The UI shows the command to copy for names it rejects.
  - mode picks one of two fixed command lines; nothing else from the
    request reaches the shell.
  - shlex.quote on every shell argument and proper AppleScript escaping
    so quoting can never let attacker-controlled strings break out.
  - subprocess.run(check=True) for AppleScript so a broken script returns
    a real error to the frontend instead of being silently swallowed.
  - /status returns only {"ok": true} — no OS, no terminal binary name.
"""
import http.server
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import urllib.parse
from http import HTTPStatus
from pathlib import Path
from typing import Optional

PORT = 9876
AIDA_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOTS = [
    AIDA_ROOT,
    Path.home() / ".aida" / "workspaces",
]

_UI_PORT = os.environ.get("AIDA_PORT", "31337")
ALLOWED_ORIGINS = {
    # Web UI served by Caddy (aida start)
    f"https://localhost:{_UI_PORT}",
    f"https://127.0.0.1:{_UI_PORT}",
    # Vite dev server (aida start --dev)
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}

# Conservative — matches assessment names that the backend already accepts.
ASSESSMENT_NAME_RE = re.compile(r"^[A-Za-z0-9 _\-.]{1,128}$")

# What /launch can run, by mode: argv after the `aida` command.
LAUNCH_MODES = {
    "agent": lambda name: ["run", name],            # Claude Code in the assessment's container
    "cli": lambda name: ["--assessment", name],     # AI CLI installed on this machine
}


def _origin_ok(headers) -> Optional[str]:
    """Return the validated origin or None if it should be rejected."""
    origin = headers.get("Origin", "")
    return origin if origin in ALLOWED_ORIGINS else None


def _path_under_allowed_root(path: Path) -> bool:
    """True if `path` resolves under one of the allowed workspace roots."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in WORKSPACE_ROOTS:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def build_launch_command(assessment_name: str, mode: str) -> Optional[str]:
    """Shell command the new terminal runs, or None if `aida` is missing.

    Callers validate ``assessment_name`` (ASSESSMENT_NAME_RE) and ``mode``
    (LAUNCH_MODES) first; every argument is shlex-quoted on top of that.
    """
    aida = AIDA_ROOT / "aida"
    if not aida.exists():
        return None
    argv = [str(aida), *LAUNCH_MODES[mode](assessment_name)]
    return f"cd {shlex.quote(str(AIDA_ROOT))} && " + " ".join(shlex.quote(a) for a in argv)


class HelperHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default per-request logging — we print our own
        pass

    # ---------- response helpers ----------

    def _cors_headers(self, origin: Optional[str]):
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, status, data, origin=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers(origin)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _read_body(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length:
            try:
                return json.loads(self.rfile.read(content_length))
            except json.JSONDecodeError:
                return {}
        return {}

    # ---------- routing ----------

    def do_OPTIONS(self):
        # CORS preflight — only succeeds for allowed origins
        origin = _origin_ok(self.headers)
        if not origin:
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Origin not allowed"})
            return
        self.send_json(HTTPStatus.OK, {"ok": True}, origin=origin)

    def do_GET(self):
        if self.path.startswith("/status"):
            self._handle_status()
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"})

    def do_POST(self):
        # Every state-changing endpoint requires a valid Origin
        origin = _origin_ok(self.headers)
        if not origin:
            # Drain the (small) body first, so the client reads the 403
            # instead of a connection reset.
            length = int(self.headers.get("Content-Length", 0) or 0)
            if 0 < length <= 65536:
                self.rfile.read(length)
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Origin not allowed"})
            return

        if self.path.startswith("/open"):
            self._handle_open(origin)
        elif self.path.startswith("/launch"):
            self._handle_launch(origin)
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"}, origin=origin)

    # ---------- handlers ----------

    def _handle_status(self):
        # Liveness only — no OS, no terminal name, no path. The CORS header
        # (allowed origins only) lets the UI read it: without it the browser
        # hid the answer and the UI always thought the helper was down.
        self.send_json(HTTPStatus.OK, {"ok": True}, origin=_origin_ok(self.headers))

    def _handle_open(self, origin: str):
        """Open a folder in the host file explorer (path must be under AIDA root)."""
        body = self._read_body()
        folder_path = body.get("path")

        if not folder_path:
            # Backward compat: also accept ?path= query string
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            folder_path = params.get("path", [None])[0]

        if not folder_path:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'path' parameter"}, origin=origin)
            return

        path = Path(folder_path)
        if not path.exists():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Path not found"}, origin=origin)
            return

        if not _path_under_allowed_root(path):
            self.send_json(HTTPStatus.FORBIDDEN, {"error": "Path is not under an allowed workspace root"}, origin=origin)
            return

        os_name = platform.system()
        try:
            if os_name == "Darwin":
                subprocess.run(["open", str(path)], check=True, timeout=10)
            elif os_name == "Linux":
                subprocess.run(["xdg-open", str(path)], check=True, timeout=10)
            elif os_name == "Windows":
                subprocess.run(["explorer", str(path)], check=True, timeout=10)
            else:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Unsupported OS"}, origin=origin)
                return
            print(f"✓ Opened: {path}")
            self.send_json(HTTPStatus.OK, {"success": True}, origin=origin)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)}, origin=origin)

    def _handle_launch(self, origin: str):
        """Open a new terminal window running `aida run` or `aida --assessment`."""
        body = self._read_body()
        assessment_name = body.get("assessment_name", "")
        mode = body.get("mode", "cli")

        if not isinstance(assessment_name, str) or not ASSESSMENT_NAME_RE.fullmatch(assessment_name):
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "Invalid assessment_name (allowed: A-Z, a-z, 0-9, space, _, -, .)"},
                origin=origin,
            )
            return
        if not isinstance(mode, str) or mode not in LAUNCH_MODES:
            self.send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": f"Invalid mode (allowed: {', '.join(LAUNCH_MODES)})"},
                origin=origin,
            )
            return

        full_cmd = build_launch_command(assessment_name, mode)
        if full_cmd is None:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "aida command not found"}, origin=origin)
            return

        os_name = platform.system()
        try:
            if os_name == "Darwin":
                # Escape for AppleScript string literal: backslashes first, then quotes
                apple_str = full_cmd.replace("\\", "\\\\").replace('"', '\\"')
                apple_script = (
                    'tell application "Terminal"\n'
                    "    activate\n"
                    f'    do script "{apple_str}"\n'
                    "end tell"
                )
                result = subprocess.run(
                    ["osascript", "-e", apple_script],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "osascript failed")
            elif os_name == "Linux":
                terminal = self._find_linux_terminal()
                if not terminal:
                    self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "No terminal emulator found"}, origin=origin)
                    return
                bash_payload = f"{full_cmd}; exec bash"
                if "gnome-terminal" in terminal:
                    subprocess.Popen([terminal, "--", "bash", "-c", bash_payload])
                else:
                    subprocess.Popen([terminal, "-e", "bash", "-c", bash_payload])
            else:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Unsupported OS"}, origin=origin)
                return

            print(f"✓ Launched ({mode}): {assessment_name}")
            self.send_json(
                HTTPStatus.OK,
                {"success": True, "assessment_name": assessment_name, "mode": mode},
                origin=origin,
            )
        except Exception as e:
            print(f"✗ Launch failed: {e}")
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)}, origin=origin)

    @staticmethod
    def _find_linux_terminal():
        terminals = [
            "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
            "qterminal", "mate-terminal", "tilix", "terminator", "alacritty",
            "kitty", "xterm",
        ]
        for term in terminals:
            if shutil.which(term):
                return term
        return None


def main():
    print(f"🛠  AIDA Host Helper on http://127.0.0.1:{PORT}")
    print(f"   Allowed origins: {', '.join(sorted(ALLOWED_ORIGINS))}")
    with http.server.HTTPServer(("127.0.0.1", PORT), HelperHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n✓ Helper stopped")


if __name__ == "__main__":
    main()
