"""
Build the MCP stdio-server config that the headless Claude process uses.

Equivalent to the `generate_mcp_config` in aida.py, but tailored for running
inside the backend container:
    - `python3` is already on PATH (no venv detection needed)
    - working directory is /app, so PYTHONPATH=/app points at the backend code
    - the MCP server file is shipped as part of the image at /app/mcp/...
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, Optional

from config import settings


# Inside the backend container the MCP server lives next to the other modules.
MCP_SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp",
    "aida_mcp_server.py",
)
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_mcp_servers(aida_token: Optional[str]) -> Dict[str, Any]:
    """Return the `mcp_servers` dict expected by claude-code-sdk.

    `aida_token` must be a valid JWT so the MCP server can call the protected
    backend API on behalf of the user who started the run.
    """
    return {
        "aida-mcp": {
            "type": "stdio",
            "command": sys.executable,
            "args": [MCP_SERVER_PATH],
            "env": {
                # MCP server imports from the backend package; anchor the path.
                "PYTHONPATH": BACKEND_DIR,
                "DATABASE_URL": str(settings.DATABASE_URL),
                "AIDA_TOKEN": aida_token or "",
                "BACKEND_API_URL": settings.BACKEND_API_URL,
            },
        }
    }
