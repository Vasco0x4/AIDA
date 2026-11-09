"""Pure launcher adapter tests; no Codex credentials or subprocess required."""
from __future__ import annotations

import json

import pytest

from launcher_adapters import (
    _toml_value,
    build_codex_command,
    build_codex_mcp_args,
    build_cursor_command,
    build_gemini_command,
    build_qwen_command,
    build_qwen_mcp_servers,
    CLI_CAPABILITIES,
    detect_available_clis,
)


def test_toml_values_escape_prompt_and_keep_booleans():
    assert _toml_value(True) == "true"
    assert _toml_value(False) == "false"
    assert _toml_value('line 1\n"line 2"') == '"line 1\\n\\"line 2\\""'
    assert _toml_value(["AIDA_TOKEN", "PYTHONPATH"]) == '["AIDA_TOKEN", "PYTHONPATH"]'


def test_http_mcp_config_uses_secret_env_name_not_secret_argv():
    args = build_codex_mcp_args(http_url="https://aida.example/mcp")
    joined = "\n".join(args)
    assert 'mcp_servers.aida-mcp.url="https://aida.example/mcp"' in joined
    assert 'mcp_servers.aida-mcp.bearer_token_env_var="AIDA_MCP_API_KEY"' in joined
    assert "tool_timeout_sec=900" in joined
    assert "AIDA_MCP_API_KEY" in joined  # variable name is safe
    assert "command=" not in joined


def test_stdio_mcp_config_forwards_only_named_environment_variables():
    args = build_codex_mcp_args(python_bin="/opt/aida/python")
    joined = "\n".join(args)
    assert 'mcp_servers.aida-mcp.command="/opt/aida/python"' in joined
    assert "AIDA_TOKEN" in joined
    assert "BACKEND_API_URL" in joined
    assert "DATABASE_URL" in joined
    assert "PYTHONPATH" in joined


def _command(**overrides):
    options = dict(
        workspace_path="/work/engagement",
        preprompt_content='Assess only the authorized scope.\nUse "evidence".',
        explicit_model="gpt-5.2-codex",
        no_mcp=False,
        http_url=None,
        mcp_api_key=None,
        db_url="postgresql://db/aida",
        backend_url="http://localhost:8001/api",
        token="session-secret",
        codex_mcp_python="/opt/aida/python",
        prompt=("review", "the evidence"),
        yes=False,
    )
    options.update(overrides)
    return build_codex_command(**options)


def test_codex_command_preserves_workspace_prompt_model_and_secret_boundaries():
    args, env = _command()
    assert args[:7] == [
        "codex", "--cd", "/work/engagement", "--sandbox", "workspace-write",
        "--ask-for-approval", "on-request",
    ]
    assert args[-1] == "review the evidence"
    assert ["--model", "gpt-5.2-codex"] == args[args.index("--model"):args.index("--model") + 2]
    assert env["AIDA_TOKEN"] == "session-secret"
    assert env["BACKEND_API_URL"] == "http://localhost:8001/api"
    assert "session-secret" not in "\n".join(args)
    assert 'Assess only the authorized scope.\\nUse \\"evidence\\".' in "\n".join(args)


def test_codex_http_command_forwards_bearer_only_through_environment():
    args, env = _command(http_url="https://aida.example/mcp", mcp_api_key="mcp-secret")
    assert env["AIDA_MCP_API_KEY"] == "mcp-secret"
    assert "AIDA_TOKEN" not in env
    assert "mcp-secret" not in "\n".join(args)
    assert "bearer_token_env_var" in "\n".join(args)


def test_codex_no_mcp_adds_no_server_or_credentials():
    args, env = _command(no_mcp=True)
    assert env == {}
    assert "mcp_servers" not in "\n".join(args)


def test_codex_yes_is_an_explicit_unsandboxed_opt_in():
    args, _ = _command(yes=True)
    assert "--dangerously-bypass-approvals-and-sandbox" in args
    assert "--sandbox" not in args
    assert "--ask-for-approval" not in args


def test_codex_rejects_unsupported_toml_values():
    with pytest.raises(TypeError):
        _toml_value({"nested": "not-supported"})
    # Ensure json remains the escaping reference for arbitrary prompt strings.
    assert _toml_value("backslash\\tab\t") == json.dumps("backslash\\tab\t")


def test_qwen_stdio_mcp_receives_session_and_backend_url():
    servers = build_qwen_mcp_servers(
        token="session-secret",
        backend_url="http://localhost:18001/api",
        db_url="postgresql://example/aida",
        python_bin="python3.11",
    )
    env = servers["aida-mcp"]["env"]
    assert env["AIDA_TOKEN"] == "session-secret"
    assert env["BACKEND_API_URL"] == "http://localhost:18001/api"
    assert env["DATABASE_URL"] == "postgresql://example/aida"
    assert "PYTHONPATH" in env


def test_qwen_http_mcp_uses_streamable_http_not_a_local_server():
    servers = build_qwen_mcp_servers(
        token="unused", backend_url="unused", db_url="unused",
        http_url="https://aida.example/mcp", mcp_api_key="mcp-secret",
    )
    assert servers == {"aida-mcp": {
        "url": "https://aida.example/mcp",
        "headers": {"Authorization": "Bearer mcp-secret"},
    }}


def test_qwen_command_forwards_model_prompt_and_explicit_yolo():
    args = build_qwen_command(explicit_model="qwen3-coder", prompt=["inspect", "scope"], yes=True)
    assert args == [
        "qwen", "--model", "qwen3-coder", "--yolo", "--prompt", "inspect scope",
    ]


def test_qwen_no_mcp_returns_no_servers():
    assert build_qwen_mcp_servers(
        token="secret", backend_url="backend", db_url="database", no_mcp=True,
    ) == {}


def test_gemini_command_matches_verified_cli_contract():
    assert build_gemini_command(explicit_model="gemini-3-pro", prompt=["inspect", "scope"], yes=True) == [
        "gemini", "--model", "gemini-3-pro", "--yolo", "--prompt", "inspect scope",
    ]


def test_cursor_command_uses_native_agent_workspace_and_explicit_force():
    assert build_cursor_command(
        workspace_path="/work/assessment", explicit_model="composer-2",
        prompt=["inspect", "scope"], yes=True,
    ) == [
        "agent", "--workspace", "/work/assessment", "--model", "composer-2",
        "--force", "--approve-mcps", "inspect scope",
    ]


def test_registry_detection_uses_native_cursor_agent_executable():
    available = {"codex": "/usr/bin/codex", "gemini": "/usr/bin/gemini", "agent": "/usr/bin/agent"}
    detected = detect_available_clis(which=available.get)
    assert detected["codex"]["installed"] is True
    assert detected["cursor"]["installed"] is True
    assert detected["cursor"]["executable"] == "agent"
    assert detected["claude"]["installed"] is False
    assert set(CLI_CAPABILITIES) == {"claude", "codex", "kimi", "qwen", "gemini", "cursor"}
    assert CLI_CAPABILITIES["claude"]["config"] == ".aida/mcp-config.json"
    assert CLI_CAPABILITIES["kimi"]["config"] == "workspace .kimi-code/mcp.json"
    assert CLI_CAPABILITIES["qwen"]["instructions"] == "QWEN.md"
