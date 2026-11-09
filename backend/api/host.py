"""Admin-only API for policy-constrained direct host execution."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_admin
from services.host_execution import HostExecutionPolicy, HostExecutionService

router = APIRouter(
    prefix="/host",
    tags=["host-execution"],
    dependencies=[Depends(require_admin)],
)

host_execution_service = HostExecutionService(HostExecutionPolicy.from_env())


def get_host_execution_service() -> HostExecutionService:
    return host_execution_service


@router.get("/policy")
def get_policy(service: HostExecutionService = Depends(get_host_execution_service)):
    policy = service.policy
    return {
        "enabled": policy.enabled,
        "allowed_working_directories": list(policy.allowed_working_directories),
        "allowed_executables": sorted(policy.allowed_executables),
        "network_actions": sorted(policy.network_actions),
        "allowed_networks": list(policy.allowed_networks),
        "allowed_dns_names": sorted(policy.allowed_dns_names),
        "timeout_seconds": policy.timeout_seconds,
        "max_output_bytes": policy.max_output_bytes,
        "max_concurrent_executions": policy.max_concurrent_executions,
        "max_operation_history": policy.max_operation_history,
    }


@router.get("/status")
def get_status(service: HostExecutionService = Depends(get_host_execution_service)):
    """Return non-sensitive resource usage for the operator dashboard."""
    return {
        "enabled": service.policy.enabled,
        "active_executions": service.active_count,
        "operation_count": len(service.list_operations()),
        "max_concurrent_executions": service.policy.max_concurrent_executions,
        "max_operation_history": service.policy.max_operation_history,
    }
