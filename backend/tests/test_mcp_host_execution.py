"""Focused tests for the opt-in MCP direct-host execution tool."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

import pytest

_MODULES_DIR = Path(__file__).resolve().parent.parent / "mcp" / "modules"
if str(_MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULES_DIR))

import mcp_handlers  # noqa: E402
from mcp_tools import get_tool_definitions  # noqa: E402
from services.host_execution import (  # noqa: E402
    HostExecutionError, HostExecutionPolicy, HostExecutionService,
)


@pytest.fixture(autouse=True)
def clear_host_execution_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("AIDA_HOST_EXECUTION_"):
            monkeypatch.delenv(key, raising=False)


def _tool_names() -> set[str]:
    return {tool.name for tool in get_tool_definitions()}


def test_host_execute_is_absent_by_default():
    assert "host_execute" not in _tool_names()


async def test_host_execute_direct_call_is_denied_by_default(tmp_path):
    result = await mcp_handlers.handle_tool_call("host_execute", {
        "action": "echo",
        "args": ["must not run"],
        "working_directory": str(tmp_path),
        "targets": [],
    }, FakeMcpService())
    operation = json.loads(_text(result))
    assert operation["success"] is False
    assert operation["error"]["code"] == "disabled"


@pytest.mark.parametrize("missing", ["ALLOWED_WORKING_DIRECTORIES", "ALLOWED_EXECUTABLES"])
def test_host_execute_requires_complete_policy(monkeypatch, tmp_path, missing):
    _enable_host_execution(monkeypatch, tmp_path)
    monkeypatch.delenv(f"AIDA_HOST_EXECUTION_{missing}")
    assert "host_execute" not in _tool_names()


class FakeMcpService:
    async def initialize(self):
        pass


def _enable_host_execution(monkeypatch, working_directory: Path, **overrides):
    values = {
        "ENABLED": "true",
        "ALLOWED_WORKING_DIRECTORIES": str(working_directory),
        "ALLOWED_EXECUTABLES": "echo",
        **overrides,
    }
    for suffix, value in values.items():
        monkeypatch.setenv(f"AIDA_HOST_EXECUTION_{suffix}", value)


def _text(result) -> str:
    assert len(result) == 1
    return result[0].text


async def test_enabled_host_execute_schema_and_handler_success(tmp_path, monkeypatch):
    _enable_host_execution(
        monkeypatch,
        tmp_path,
        NETWORK_ACTIONS="echo",
        ALLOWED_NETWORKS="192.0.2.0/24",
    )

    host_tool = next(tool for tool in get_tool_definitions() if tool.name == "host_execute")
    assert host_tool.inputSchema["required"] == [
        "action", "args", "working_directory", "targets",
    ]
    assert host_tool.inputSchema["additionalProperties"] is False
    assert "command" not in host_tool.inputSchema["properties"]
    assert host_tool.inputSchema["properties"]["args"]["type"] == "array"

    spawned = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"hello from argv\n", b""

    async def fake_exec(*args, **kwargs):
        spawned["args"] = args
        spawned["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await mcp_handlers.handle_tool_call("host_execute", {
        "action": "echo",
        "args": ["hello from argv", "192.0.2.10"],
        "working_directory": str(tmp_path),
        "targets": ["192.0.2.10"],
    }, FakeMcpService())

    operation = json.loads(_text(result))
    assert operation["success"] is True
    assert operation["stdout"] == "hello from argv\n"
    assert operation["targets"] == ["192.0.2.10"]
    assert spawned["args"][0].endswith("/echo")
    assert spawned["args"][1:] == ("hello from argv", "192.0.2.10")
    assert spawned["kwargs"]["cwd"] == str(tmp_path)
    assert spawned["kwargs"].get("shell", False) is False


async def test_host_execute_policy_denial_does_not_spawn(tmp_path, monkeypatch):
    _enable_host_execution(monkeypatch, tmp_path, ALLOWED_EXECUTABLES="curl")

    async def spawn_must_not_be_called(*args, **kwargs):
        raise AssertionError("denied action reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    result = await mcp_handlers.handle_tool_call("host_execute", {
        "action": "echo",
        "args": ["not allowed"],
        "working_directory": str(tmp_path),
        "targets": [],
    }, FakeMcpService())

    operation = json.loads(_text(result))
    assert operation["success"] is False
    assert operation["status"] == "denied"
    assert operation["error"]["code"] == "action_denied"


async def test_host_execute_rejects_shell_strings_and_metacharacters(tmp_path, monkeypatch):
    _enable_host_execution(monkeypatch, tmp_path)
    spawn_count = 0

    async def fake_exec(*args, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        raise AssertionError("shell input reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    base = {
        "action": "echo",
        "working_directory": str(tmp_path),
        "targets": [],
    }
    string_result = await mcp_handlers.handle_tool_call(
        "host_execute", {**base, "args": "hello; id"}, FakeMcpService(),
    )
    metachar_result = await mcp_handlers.handle_tool_call(
        "host_execute", {**base, "args": ["hello; id"]}, FakeMcpService(),
    )

    assert json.loads(_text(string_result))["error"]["code"] == "invalid_arguments"
    assert json.loads(_text(metachar_result))["error"]["code"] == "unsafe_argument"
    assert spawn_count == 0


async def test_host_execute_returns_bounded_redacted_operation_output(tmp_path, monkeypatch):
    _enable_host_execution(monkeypatch, tmp_path, MAX_OUTPUT_BYTES="96")

    class Process:
        returncode = 0

        async def communicate(self):
            return (
                b"sk-abcdefghijklmnop token=hunter2 " + b"x" * 200,
                b"password=correcthorse " + b"y" * 200,
            )

    async def fake_exec(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await mcp_handlers.handle_tool_call("host_execute", {
        "action": "echo",
        "args": ["--api-key=hunter2"],
        "working_directory": str(tmp_path),
        "targets": [],
    }, FakeMcpService())

    response_text = _text(result)
    operation = json.loads(response_text)
    assert operation["success"] is True
    assert operation["args"] == ["--api-key=***REDACTED***"]
    assert "sk-abcdefghijklmnop" not in response_text
    assert "hunter2" not in response_text
    assert "correcthorse" not in response_text
    assert len(operation["stdout"].encode()) <= 96
    assert len(operation["stderr"].encode()) <= 96
    assert operation["stdout_truncated"] is True
    assert operation["stderr_truncated"] is True


async def test_host_execute_audit_log_uses_sanitized_argv(tmp_path, monkeypatch, caplog):
    _enable_host_execution(monkeypatch, tmp_path)

    class Process:
        returncode = 0

        async def communicate(self):
            return b"done\n", b""

    async def fake_exec(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with caplog.at_level(logging.INFO, logger="aida-mcp"):
        result = await mcp_handlers.handle_tool_call("host_execute", {
            "action": "echo",
            "args": ["--token=hunter2"],
            "working_directory": str(tmp_path),
            "targets": [],
        }, FakeMcpService())

    operation = json.loads(_text(result))
    assert "host_execute audit" in caplog.text
    assert operation["operation_id"] in caplog.text
    assert "***REDACTED***" in caplog.text
    assert "hunter2" not in caplog.text


@pytest.mark.parametrize(("action", "args"), [
    ("curl", ["target.example", "--config", "more-targets.txt"]),
    ("wget", ["target.example", "--input-file", "more-targets.txt"]),
    ("nmap", ["192.0.2.10", "-iL", "more-targets.txt"]),
    ("nuclei", ["-u", "target.example", "-list", "more-targets.txt"]),
])
async def test_network_actions_reject_indirect_target_files(tmp_path, monkeypatch, action, args):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({action}),
        allowed_networks=("192.0.2.0/24",),
        allowed_dns_names=frozenset({"target.example"}),
    ))

    async def spawn_must_not_be_called(*spawn_args, **kwargs):
        raise AssertionError("indirect target input reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(action=action, args=args, working_directory=str(tmp_path),
                              targets=[args[1] if action == "nuclei" else args[0]])
    assert exc_info.value.code == "dangerous_argument"


@pytest.mark.parametrize("arg", ["/etc/passwd", "../../etc/passwd", "--output=/tmp/outside"])
async def test_file_arguments_cannot_escape_working_roots(tmp_path, monkeypatch, arg):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"cat"}),
    ))

    async def spawn_must_not_be_called(*spawn_args, **kwargs):
        raise AssertionError("out-of-root file path reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(action="cat", args=[arg], working_directory=str(tmp_path))
    assert exc_info.value.code == "unsafe_argument"
