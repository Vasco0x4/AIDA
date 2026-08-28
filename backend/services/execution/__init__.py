"""
Execution backends — abstraction over "where does a command actually run".

Historically AIDA always ran commands inside the `aida-pentest` Docker
container via `docker exec`. Starting with deployment mode "localhost",
commands can instead be proxied through a Unix-socket host-agent that
executes on the host itself (for users who want to target their own
machine rather than a sandboxed pentest container).

This module keeps the higher-level ContainerService oblivious to which
backend is in use. Callers construct a backend via `get_execution_backend()`
and the service layer calls `exec_shell`, `exec_python`, and
`ensure_workspace` uniformly.
"""
from .base import ExecResult, ExecutionBackend
from .container import ContainerExecutionBackend
from .host_agent import HostAgentExecutionBackend


def get_execution_backend(container_name: str = None) -> ExecutionBackend:
    """Build the execution backend that matches the current deployment mode.

    Args:
        container_name: Only consulted in container mode. Ignored for
            localhost mode (the single target is the host itself).

    Returns:
        Freshly constructed backend instance. Backends are cheap to build;
        instances hold no persistent state that needs sharing across
        requests, so we don't bother with a singleton.
    """
    from config import settings

    if settings.DEPLOYMENT_MODE == "localhost":
        return HostAgentExecutionBackend(
            socket_path=settings.HOST_AGENT_SOCKET,
            token_path=settings.HOST_AGENT_TOKEN_PATH,
            label=settings.LOCALHOST_CONTAINER_LABEL,
        )

    return ContainerExecutionBackend(
        container_name=container_name or settings.DEFAULT_CONTAINER_NAME,
    )


__all__ = [
    "ExecResult",
    "ExecutionBackend",
    "ContainerExecutionBackend",
    "HostAgentExecutionBackend",
    "get_execution_backend",
]
