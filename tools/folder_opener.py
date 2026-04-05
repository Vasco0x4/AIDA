#!/usr/bin/env python3
"""
AIDA Host Helper Service - Local HTTP server running on the host (not Docker)
Provides:
  POST /open?path=...       → Open folder in file explorer
  POST /launch              → Launch aida.py in a new terminal
"""
import http.server
import json
import os
import platform
import shutil
import subprocess
import urllib.parse
from http import HTTPStatus
from pathlib import Path

PORT = 9876
AIDA_ROOT = Path(__file__).resolve().parent.parent

class FolderOpenerHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress default logging
        pass

    def send_json(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_json(HTTPStatus.OK, {"status": "ok"})

    def _read_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length:
            return json.loads(self.rfile.read(content_length))
        return {}

    def do_POST(self):
        if self.path.startswith('/open'):
            self._handle_open()
        elif self.path.startswith('/launch-status'):
            self._handle_launch_status()
        elif self.path.startswith('/launch'):
            self._handle_launch()
        else:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "Unknown endpoint"})

    def _handle_open(self):
        """Open folder in file explorer"""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        folder_path = params.get('path', [None])[0]

        if not folder_path:
            body = self._read_body()
            folder_path = body.get('path')

        if not folder_path:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'path' parameter"})
            return

        if not os.path.exists(folder_path):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": f"Path not found: {folder_path}"})
            return

        os_name = platform.system()
        try:
            if os_name == "Darwin":
                subprocess.run(["open", folder_path], check=True)
            elif os_name == "Linux":
                subprocess.run(["xdg-open", folder_path], check=True)
            elif os_name == "Windows":
                subprocess.run(["explorer", folder_path], check=True)
            else:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": f"Unsupported OS: {os_name}"})
                return

            print(f"✓ Opened: {folder_path}")
            self.send_json(HTTPStatus.OK, {"success": True, "path": folder_path})
        except subprocess.CalledProcessError as e:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

    def _handle_launch(self):
        """Launch aida.py in a new terminal window"""
        body = self._read_body()
        assessment_name = body.get('assessment_name', '')

        if not assessment_name:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing 'assessment_name'"})
            return

        aida_py = AIDA_ROOT / "aida.py"
        if not aida_py.exists():
            self.send_json(HTTPStatus.NOT_FOUND, {"error": f"aida.py not found at {aida_py}"})
            return

        # Build the command
        python_bin = str(AIDA_ROOT / ".venv" / "bin" / "python") if (AIDA_ROOT / ".venv" / "bin" / "python").exists() else "python3"
        cmd_str = f'{python_bin} {aida_py} -a "{assessment_name}"'

        # Detect terminal emulator
        os_name = platform.system()
        try:
            if os_name == "Darwin":
                # macOS: use osascript to open Terminal.app
                apple_script = f'tell application "Terminal" to do script "{cmd_str}"'
                subprocess.Popen(["osascript", "-e", apple_script])
            elif os_name == "Linux":
                # Try common terminal emulators in order of preference
                terminal = self._find_linux_terminal()
                if terminal:
                    if "gnome-terminal" in terminal:
                        subprocess.Popen([terminal, "--", "bash", "-c", f'{cmd_str}; exec bash'])
                    elif "konsole" in terminal:
                        subprocess.Popen([terminal, "-e", "bash", "-c", f'{cmd_str}; exec bash'])
                    elif "xfce4-terminal" in terminal:
                        subprocess.Popen([terminal, "-e", f'bash -c "{cmd_str}; exec bash"'])
                    elif "qterminal" in terminal:
                        subprocess.Popen([terminal, "-e", f'bash -c "{cmd_str}; exec bash"'])
                    elif "xterm" in terminal:
                        subprocess.Popen([terminal, "-e", f'bash -c "{cmd_str}; exec bash"'])
                    else:
                        # Generic x-terminal-emulator
                        subprocess.Popen([terminal, "-e", f'bash -c "{cmd_str}; exec bash"'])
                else:
                    self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "No terminal emulator found"})
                    return
            else:
                self.send_json(HTTPStatus.BAD_REQUEST, {"error": f"Unsupported OS: {os_name}"})
                return

            print(f"✓ Launched AI scan: {assessment_name}")
            self.send_json(HTTPStatus.OK, {
                "success": True,
                "assessment_name": assessment_name,
                "command": cmd_str,
            })
        except Exception as e:
            print(f"✗ Launch failed: {e}")
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(e)})

    def _handle_launch_status(self):
        """Check if launch service is available"""
        self.send_json(HTTPStatus.OK, {
            "available": True,
            "os": platform.system(),
            "terminal": self._find_linux_terminal() if platform.system() == "Linux" else "Terminal.app",
        })

    @staticmethod
    def _find_linux_terminal():
        """Find available terminal emulator on Linux"""
        terminals = [
            "x-terminal-emulator",
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "qterminal",
            "mate-terminal",
            "tilix",
            "terminator",
            "alacritty",
            "kitty",
            "xterm",
        ]
        for term in terminals:
            if shutil.which(term):
                return term
        return None

def main():
    print(f"🛠️  AIDA Host Helper starting on http://localhost:{PORT}")
    print(f"   POST /open?path=...              → Open folder in file explorer")
    print(f"   POST /launch {{assessment_name}}  → Launch aida.py in terminal")
    print(f"   POST /launch-status              → Check service availability")
    print()
    
    with http.server.HTTPServer(('127.0.0.1', PORT), FolderOpenerHandler) as server:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n✓ Folder Opener Service stopped")

if __name__ == "__main__":
    main()
