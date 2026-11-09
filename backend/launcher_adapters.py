"""Pure AI CLI launcher adapters shared by ``aida.py`` and backend tests.

Adapters build argv/environment overlays only. They never launch a process,
read credentials, or mutate a client's persistent configuration.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

MCP_SERVER_PATH = Path(__file__).parent / "mcp" / "aida_mcp_server.py"

# Capability matrix is intentionally factual: installed detection is separate
# from protocol/config verification and never indicates provider authentication.
CLI_CAPABILITIES: dict[str, dict[str, Any]] = {
    "claude": {"executable": "claude", "config": ".aida/mcp-config.json", "transports": ("stdio", "http"), "instructions": "--system-prompt"},
    "codex": {"executable": "codex", "config": "ephemeral -c overrides", "transports": ("stdio", "http"), "instructions": "developer_instructions", "verified": "Codex 0.167 launch + real MCP tool"},
    "kimi": {"executable": "kimi", "config": "workspace .kimi-code/mcp.json", "transports": ("stdio", "http"), "instructions": ".kimi-code/AGENTS.md"},
    "qwen": {"executable": "qwen", "config": "workspace .qwen/settings.json", "transports": ("stdio", "http"), "instructions": "QWEN.md"},
    "gemini": {"executable": "gemini", "config": "workspace .gemini/settings.json", "transports": ("stdio", "http"), "instructions": ".gemini/AIDA.md", "verified": "Gemini 0.31 config + MCP registration"},
    "cursor": {"executable": "agent", "config": "workspace .cursor/mcp.json", "transports": ("stdio", "http"), "instructions": ".cursor/rules/aida.mdc", "verified": "Cursor Agent 2026.11 flags + MCP registration"},
}
CLI_PRIORITY = ("claude", "codex", "kimi", "qwen", "gemini", "cursor")


def detect_available_clis(which: Optional[Callable[[str], Optional[str]]] = None) -> dict[str, dict[str, Any]]:
    """Return installed/path fields without invoking or authenticating a CLI."""
    finder = which or shutil.which
    result = {}
    for name, capabilities in CLI_CAPABILITIES.items():
        path = finder(capabilities["executable"])
        result[name] = {**capabilities, "installed": bool(path), "path": path}
    return result


def _toml_value(value) -> str:
    """Serialize simple command-line override values as TOML."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # JSON strings use the escaping needed by TOML basic strings.
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML value type: {type(value).__name__}")


def _codex_override(key: str, value) -> list[str]:
    return ["--config", f"{key}={_toml_value(value)}"]


def build_codex_mcp_args(
    *,
    python_bin: Optional[str] = None,
    http_url: Optional[str] = None,
    mcp_server_path: Optional[str] = None,
) -> list[str]:
    """Build ephemeral Codex MCP overrides without persisting credentials."""
    prefix = "mcp_servers.aida-mcp"
    args: list[str] = []
    if http_url:
        args.extend(_codex_override(f"{prefix}.url", http_url))
        args.extend(_codex_override(f"{prefix}.bearer_token_env_var", "AIDA_MCP_API_KEY"))
    else:
        args.extend(_codex_override(f"{prefix}.command", python_bin or "python3"))
        args.extend(_codex_override(
            f"{prefix}.args",
            [str(Path(mcp_server_path).absolute()) if mcp_server_path else str(MCP_SERVER_PATH.absolute())],
        ))
        args.extend(_codex_override(
            f"{prefix}.env_vars",
            ["AIDA_TOKEN", "BACKEND_API_URL", "DATABASE_URL", "PYTHONPATH"],
        ))

    args.extend(_codex_override(f"{prefix}.required", True))
    args.extend(_codex_override(f"{prefix}.startup_timeout_sec", 30))
    # Scan and human-approval tools can exceed Codex's default 60 seconds.
    args.extend(_codex_override(f"{prefix}.tool_timeout_sec", 900))
    return args


def build_codex_command(
    *,
    workspace_path: str,
    preprompt_content: str,
    explicit_model: Optional[str] = None,
    no_mcp: bool = False,
    http_url: Optional[str] = None,
    mcp_api_key: Optional[str] = None,
    db_url: str,
    backend_url: str,
    token: str,
    codex_mcp_python: Optional[str] = None,
    project_root: Optional[str] = None,
    prompt: Sequence[str] = (),
    yes: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """Return Codex argv and only the environment values AIDA must add.

    Secret values stay out of argv. MCP receives either an environment-variable
    name for HTTP bearer auth or a small allowlist of stdio variable names.
    """
    args = [
        "codex",
        "--cd", workspace_path,
        "--sandbox", "workspace-write",
        "--ask-for-approval", "on-request",
    ]
    # Codex has no --system-prompt. Preserve built-in instructions and append
    # AIDA's instructions through the documented one-run configuration surface.
    args.extend(_codex_override("developer_instructions", preprompt_content))
    if explicit_model:
        args.extend(["--model", explicit_model])

    env: dict[str, str] = {}
    if not no_mcp:
        if http_url:
            if not mcp_api_key:
                raise ValueError("HTTP MCP requires an API key")
            env["AIDA_MCP_API_KEY"] = mcp_api_key
            args.extend(build_codex_mcp_args(http_url=http_url))
        else:
            env.update({
                "AIDA_TOKEN": token,
                "BACKEND_API_URL": backend_url,
                "DATABASE_URL": db_url,
                "PYTHONPATH": str(Path(__file__).parent.absolute()),
            })
            args.extend(build_codex_mcp_args(python_bin=codex_mcp_python or "python3"))

    if project_root and project_root != workspace_path:
        args.extend(["--add-dir", project_root])

    if yes:
        approval_index = args.index("--ask-for-approval")
        del args[approval_index:approval_index + 2]
        sandbox_index = args.index("--sandbox")
        del args[sandbox_index:sandbox_index + 2]
        args.append("--dangerously-bypass-approvals-and-sandbox")
    if prompt:
        args.append(" ".join(prompt))
    return args, env


def build_qwen_mcp_servers(
    *,
    token: str,
    backend_url: str,
    db_url: str,
    no_mcp: bool = False,
    http_url: Optional[str] = None,
    mcp_api_key: Optional[str] = None,
    python_bin: str = "python3",
) -> dict[str, Any]:
    """Return the ``mcpServers`` object for Qwen's scoped settings file."""
    if no_mcp:
        return {}
    if http_url:
        if not mcp_api_key:
            raise ValueError("HTTP MCP requires an API key")
        return {"aida-mcp": {
            "url": http_url,
            "headers": {"Authorization": f"Bearer {mcp_api_key}"},
        }}
    return {"aida-mcp": {
        "command": python_bin,
        "args": [str(MCP_SERVER_PATH)],
        "env": {
            "PYTHONPATH": str(Path(__file__).parent.absolute()),
            "DATABASE_URL": db_url,
            "AIDA_TOKEN": token,
            "BACKEND_API_URL": backend_url,
        },
    }}


def build_qwen_command(
    *, explicit_model: Optional[str], prompt: Sequence[str] = (), yes: bool = False,
) -> list[str]:
    """Qwen 0.26 command builder; YOLO is only added after explicit opt-in."""
    args = ["qwen"]
    if explicit_model:
        args.extend(["--model", explicit_model])
    if yes:
        args.append("--yolo")
    if prompt:
        args.extend(["--prompt", " ".join(prompt)])
    return args


def build_gemini_command(
    *, explicit_model: Optional[str], prompt: Sequence[str] = (), yes: bool = False,
) -> list[str]:
    """Gemini 0.31 command builder; interactive when no prompt is supplied."""
    args = ["gemini"]
    if explicit_model:
        args.extend(["--model", explicit_model])
    if yes:
        args.append("--yolo")
    if prompt:
        args.extend(["--prompt", " ".join(prompt)])
    return args


def build_cursor_command(
    *, workspace_path: str, explicit_model: Optional[str],
    prompt: Sequence[str] = (), yes: bool = False,
) -> list[str]:
    """Native Cursor Agent command (not the ``cursor`` editor binary)."""
    args = ["agent", "--workspace", workspace_path]
    if explicit_model:
        args.extend(["--model", explicit_model])
    if yes:
        # Both are explicit-opt-in: shell writes and automatic MCP approval.
        args.extend(["--force", "--approve-mcps"])
    if prompt:
        args.append(" ".join(prompt))
    return args
