"""Security and resource-limit tests for opt-in direct host execution."""
from __future__ import annotations

import asyncio
import os

import pytest

from services.host_execution import (
    HostExecutionError,
    HostExecutionPolicy,
    HostExecutionService,
)


async def test_execution_is_disabled_by_default(tmp_path):
    service = HostExecutionService(HostExecutionPolicy())

    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo",
            args=["hello"],
            working_directory=str(tmp_path),
        )

    assert exc_info.value.code == "disabled"
    assert service.list_operations() == []


async def test_allowlisted_command_runs_as_argv_in_allowed_directory(tmp_path):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
    ))

    result = await service.execute(
        action="echo",
        args=["hello from argv"],
        working_directory=str(tmp_path),
    )

    assert result["success"] is True
    assert result["status"] == "completed"
    assert result["returncode"] == 0
    assert result["stdout"] == "hello from argv\n"
    assert result["stderr"] == ""
    assert result["operation_id"]
    assert service.get_operation(result["operation_id"])["status"] == "completed"


@pytest.mark.parametrize("argument", [
    "hello;id",
    "hello && id",
    "hello | id",
    "$(id)",
    "`id`",
    "hello > /tmp/pwned",
    "line one\nline two",
    "null\x00byte",
])
async def test_shell_metacharacters_and_control_characters_are_rejected(
    tmp_path, monkeypatch, argument,
):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
    ))

    async def spawn_must_not_be_called(*args, **kwargs):
        raise AssertionError("unsafe input reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo", args=[argument], working_directory=str(tmp_path),
        )

    assert exc_info.value.code == "unsafe_argument"


@pytest.mark.parametrize(("action", "args", "code"), [
    ("sudo", ["id"], "dangerous_action"),
    ("bash", ["-c", "id"], "dangerous_action"),
    ("python3", ["-c", "import os"], "dangerous_action"),
    ("rm", ["-rf", "/"], "dangerous_action"),
    ("dd", ["if=/dev/zero", "of=/dev/sda"], "dangerous_action"),
    ("docker", ["run", "alpine"], "dangerous_action"),
    ("shutdown", ["now"], "dangerous_action"),
    ("stress-ng", ["--cpu", "0"], "dangerous_action"),
    ("nmap", ["--interactive"], "dangerous_argument"),
    ("nmap", ["--script", "smb-os-discovery"], "dangerous_argument"),
    ("echo", ["--exec=id"], "dangerous_argument"),
    ("echo", ["--flood"], "dangerous_argument"),
])
async def test_dangerous_actions_privilege_escalation_and_dos_are_rejected(
    tmp_path, monkeypatch, action, args, code,
):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({action}),
    ))

    async def spawn_must_not_be_called(*spawn_args, **kwargs):
        raise AssertionError("dangerous input reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action=action, args=args, working_directory=str(tmp_path),
        )

    assert exc_info.value.code == code


async def test_working_directory_traversal_is_rejected_before_spawn(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (tmp_path / "outside").mkdir()
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(allowed),),
        allowed_executables=frozenset({"echo"}),
    ))

    async def spawn_must_not_be_called(*args, **kwargs):
        raise AssertionError("path traversal reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo", args=["hello"],
            working_directory=str(allowed / ".." / "outside"),
        )

    assert exc_info.value.code == "working_directory_denied"


async def test_symlink_escape_from_allowlisted_directory_is_rejected(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()
    (allowed / "escape").symlink_to(outside, target_is_directory=True)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(allowed),),
        allowed_executables=frozenset({"echo"}),
    ))

    async def spawn_must_not_be_called(*args, **kwargs):
        raise AssertionError("symlink escape reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo", args=["hello"], working_directory=str(allowed / "escape"),
        )

    assert exc_info.value.code == "working_directory_denied"


@pytest.mark.parametrize("target", [
    "192.0.2.10",
    "192.0.2.0/24",
    "2001:db8::10",
    "target.example",
    "TARGET.EXAMPLE.",
])
async def test_network_actions_allow_only_explicitly_authorized_targets(tmp_path, target):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
        network_actions=frozenset({"echo"}),
        allowed_networks=("192.0.2.0/24", "2001:db8::/32"),
        allowed_dns_names=frozenset({"target.example"}),
    ))

    result = await service.execute(
        action="echo", args=[target], working_directory=str(tmp_path), targets=[target],
    )

    assert result["success"] is True
    assert result["targets"] == [target.rstrip(".").lower()]


@pytest.mark.parametrize(("argument", "declared_target"), [
    ("198.51.100.10", "198.51.100.10"),
    ("192.0.3.0/24", "192.0.3.0/24"),
    ("evil.example", "evil.example"),
    ("https://evil.example/private", "evil.example"),
    ("198.51.100.10", "192.0.2.10"),
])
async def test_network_actions_block_out_of_scope_and_mismatched_targets(
    tmp_path, monkeypatch, argument, declared_target,
):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
        network_actions=frozenset({"echo"}),
        allowed_networks=("192.0.2.0/24",),
        allowed_dns_names=frozenset({"target.example"}),
    ))

    async def spawn_must_not_be_called(*args, **kwargs):
        raise AssertionError("out-of-scope target reached subprocess creation")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_must_not_be_called)
    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo", args=[argument], working_directory=str(tmp_path),
            targets=[declared_target],
        )

    assert exc_info.value.code in {"target_denied", "target_mismatch"}


async def test_network_action_requires_machine_checkable_targets(tmp_path):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
        network_actions=frozenset({"echo"}),
        allowed_networks=("192.0.2.0/24",),
    ))

    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo", args=["192.0.2.10"], working_directory=str(tmp_path),
        )

    assert exc_info.value.code == "target_required"


async def test_subprocess_environment_is_scrubbed_and_shell_is_never_used(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-leak")
    monkeypatch.setenv("SECRET_KEY", "must-not-leak-either")
    captured = {}

    class Process:
        returncode = 0

        async def communicate(self):
            return b"scrubbed\n", b""

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
    ))
    result = await service.execute(
        action="echo", args=["scrubbed"], working_directory=str(tmp_path),
    )

    assert result["success"] is True
    assert captured["kwargs"].get("shell", False) is False
    environment = captured["kwargs"]["env"]
    assert "AWS_SECRET_ACCESS_KEY" not in environment
    assert "SECRET_KEY" not in environment
    assert environment["HOME"] == str(tmp_path)
    assert set(environment) <= {"PATH", "HOME", "LANG", "LC_ALL", "TERM", "NO_COLOR"}


async def test_execution_timeout_kills_process_and_records_timeout(tmp_path):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"sleep"}),
        timeout_seconds=0.05,
    ))

    result = await service.execute(
        action="sleep", args=["5"], working_directory=str(tmp_path),
    )

    assert result["success"] is False
    assert result["status"] == "timeout"
    assert result["returncode"] is not None
    assert "timed out" in result["stderr"]
    assert service.get_operation(result["operation_id"])["status"] == "timeout"


async def test_timeout_kills_the_entire_subprocess_group(tmp_path, monkeypatch):
    killed_groups = []
    captured = {}

    class Process:
        pid = 424242
        returncode = None
        killed = False

        async def communicate(self):
            if self.killed:
                self.returncode = -9
                return b"", b""
            await asyncio.Future()

        def kill(self):
            raise AssertionError("only the process leader was killed")

    process = Process()

    async def fake_exec(*args, **kwargs):
        captured.update(kwargs)
        return process

    def fake_killpg(pid, sig):
        killed_groups.append((pid, sig))
        process.killed = True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(os, "killpg", fake_killpg)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"sleep"}),
        timeout_seconds=0.001,
    ))

    result = await service.execute(
        action="sleep", args=["5"], working_directory=str(tmp_path),
    )

    assert result["status"] == "timeout"
    assert captured["start_new_session"] is True
    assert killed_groups == [(process.pid, 9)]


async def test_stdout_and_stderr_have_independent_byte_limits(tmp_path, monkeypatch):
    class Stream:
        def __init__(self, chunks):
            self._chunks = iter(chunks)

        async def read(self, size=-1):
            return next(self._chunks, b"")

    class Process:
        returncode = 0
        stdout = Stream([b"a" * 20, b"a" * 20])
        stderr = Stream([b"b" * 20, b"b" * 20])

        async def communicate(self):
            raise AssertionError("unbounded communicate() must not be used")

        async def wait(self):
            return self.returncode

    async def fake_exec(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
        max_output_bytes=32,
    ))

    result = await service.execute(
        action="echo", args=["hello"], working_directory=str(tmp_path),
    )

    assert result["stdout"] == "a" * 32
    assert result["stderr"] == "b" * 32
    assert result["stdout_truncated"] is True
    assert result["stderr_truncated"] is True


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
async def test_redacted_output_is_capped_again_in_its_final_representation(
    tmp_path, monkeypatch, stream,
):
    raw = b"token=x " + b"A" * 24 + b"discarded"
    outputs = {"stdout": b"", "stderr": b""}
    outputs[stream] = raw

    class Process:
        returncode = 0

        async def communicate(self):
            return outputs["stdout"], outputs["stderr"]

    async def fake_exec(*args, **kwargs):
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
        max_output_bytes=32,
    ))

    result = await service.execute(
        action="echo", args=["hello"], working_directory=str(tmp_path),
    )

    assert "token=x" not in result[stream]
    assert len(result[stream].encode("utf-8")) <= 32
    assert result[f"{stream}_truncated"] is True


async def test_concurrency_cap_rejects_excess_execution_without_spawning(tmp_path, monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    spawn_count = 0

    class Process:
        returncode = 0

        async def communicate(self):
            started.set()
            await release.wait()
            return b"done\n", b""

    async def fake_exec(*args, **kwargs):
        nonlocal spawn_count
        spawn_count += 1
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"sleep", "echo"}),
        max_concurrent_executions=1,
    ))
    first = asyncio.create_task(service.execute(
        action="sleep", args=["1"], working_directory=str(tmp_path),
    ))
    await asyncio.wait_for(started.wait(), timeout=1)

    with pytest.raises(HostExecutionError) as exc_info:
        await service.execute(
            action="echo", args=["no"], working_directory=str(tmp_path),
        )

    assert exc_info.value.code == "concurrency_limit"
    assert spawn_count == 1
    release.set()
    assert (await first)["success"] is True


async def test_secret_arguments_and_output_are_redacted_in_operation_history(
    tmp_path, monkeypatch,
):
    spawned = []

    class Process:
        returncode = 0

        async def communicate(self):
            return b"sk-abcdefghijklmnop\n", b"token=hunter2\n"

    async def fake_exec(*args, **kwargs):
        spawned.extend(args)
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
    ))
    secret_args = ["--api-key=hunter2", "--password", "correct horse", "sk-abcdefghijklmnop"]

    result = await service.execute(
        action="echo", args=secret_args, working_directory=str(tmp_path),
    )

    assert spawned[1:] == secret_args
    assert result["args"] == ["--api-key=***REDACTED***", "--password", "***REDACTED***", "***REDACTED_KEY***"]
    assert "sk-abcdefghijklmnop" not in result["stdout"]
    assert result["stderr"] == "token=***REDACTED***\n"
    assert "hunter2" not in str(service.get_operation(result["operation_id"]))
    assert "correct horse" not in str(service.list_operations())


async def test_operation_history_is_bounded_and_evicts_oldest(tmp_path):
    service = HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo"}),
        max_operation_history=2,
    ))
    operation_ids = []
    for value in ("first", "second", "third"):
        result = await service.execute(
            action="echo", args=[value], working_directory=str(tmp_path),
        )
        operation_ids.append(result["operation_id"])

    operations = service.list_operations()
    assert len(operations) == 2
    assert service.get_operation(operation_ids[0]) is None
    assert {item["operation_id"] for item in operations} == set(operation_ids[1:])


def test_policy_loads_explicit_opt_in_and_limits_from_environment():
    policy = HostExecutionPolicy.from_env({
        "AIDA_HOST_EXECUTION_ENABLED": "true",
        "AIDA_HOST_EXECUTION_ALLOWED_WORKING_DIRECTORIES": "/srv/one, /srv/two",
        "AIDA_HOST_EXECUTION_ALLOWED_EXECUTABLES": "echo, curl",
        "AIDA_HOST_EXECUTION_NETWORK_ACTIONS": "curl",
        "AIDA_HOST_EXECUTION_ALLOWED_NETWORKS": "192.0.2.0/24, 2001:db8::/32",
        "AIDA_HOST_EXECUTION_ALLOWED_DNS_NAMES": "Target.Example, other.example",
        "AIDA_HOST_EXECUTION_TIMEOUT_SECONDS": "1.5",
        "AIDA_HOST_EXECUTION_MAX_OUTPUT_BYTES": "4096",
        "AIDA_HOST_EXECUTION_MAX_CONCURRENT_EXECUTIONS": "2",
        "AIDA_HOST_EXECUTION_MAX_OPERATION_HISTORY": "25",
    })

    assert policy.enabled is True
    assert policy.allowed_working_directories == ("/srv/one", "/srv/two")
    assert policy.allowed_executables == frozenset({"echo", "curl"})
    assert policy.network_actions == frozenset({"curl"})
    assert policy.allowed_networks == ("192.0.2.0/24", "2001:db8::/32")
    assert policy.allowed_dns_names == frozenset({"Target.Example", "other.example"})
    assert policy.timeout_seconds == 1.5
    assert policy.max_output_bytes == 4096
    assert policy.max_concurrent_executions == 2
    assert policy.max_operation_history == 25
    assert HostExecutionPolicy.from_env({}).enabled is False


@pytest.mark.parametrize(("name", "value"), [
    ("ENABLED", "maybe"),
    ("TIMEOUT_SECONDS", "0"),
    ("TIMEOUT_SECONDS", "nan"),
    ("MAX_OUTPUT_BYTES", "0"),
    ("MAX_CONCURRENT_EXECUTIONS", "0"),
    ("MAX_OPERATION_HISTORY", "0"),
])
def test_policy_rejects_invalid_environment_limits(name, value):
    with pytest.raises(ValueError, match=f"AIDA_HOST_EXECUTION_{name}"):
        HostExecutionPolicy.from_env({f"AIDA_HOST_EXECUTION_{name}": value})
