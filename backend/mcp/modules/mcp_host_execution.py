"""Runtime adapter for opt-in direct host execution in MCP handlers."""
from __future__ import annotations

from services.host_execution import (
    HostExecutionError,
    HostExecutionPolicy,
    HostExecutionService,
)


def get_host_execution_policy() -> HostExecutionPolicy | None:
    """Return a complete opt-in policy, or None when the tool must stay hidden."""
    try:
        policy = HostExecutionPolicy.from_env()
    except ValueError:
        return None
    if not (
        policy.enabled
        and policy.allowed_working_directories
        and policy.allowed_executables
    ):
        return None
    return policy


def get_host_execution_service(mcp_service) -> HostExecutionService:
    """Lazily attach one service without changing MCP service constructors."""
    service = getattr(mcp_service, "_host_execution_service", None)
    if service is not None:
        return service

    policy = get_host_execution_policy()
    if policy is None:
        raise HostExecutionError(
            "disabled", "Direct host execution is disabled or its policy is incomplete",
        )
    service = HostExecutionService(policy)
    mcp_service._host_execution_service = service
    return service
