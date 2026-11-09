"""API tests for the opt-in, admin-only host execution surface."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.host import get_host_execution_service, router
from auth import get_current_user
from database import get_db
from services.host_execution import HostExecutionPolicy, HostExecutionService


@pytest.fixture()
def host_service(tmp_path):
    return HostExecutionService(HostExecutionPolicy(
        enabled=True,
        allowed_working_directories=(str(tmp_path),),
        allowed_executables=frozenset({"echo", "sleep"}),
    ))


def make_client(db, user, service):
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_host_execution_service] = lambda: service
    return TestClient(app)


@pytest.fixture()
def host_client(db, admin_user, host_service):
    return make_client(db, admin_user, host_service)


def test_policy_is_available_to_admin(host_client, host_service):
    response = host_client.get("/api/host/policy")

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["allowed_executables"] == ["echo", "sleep"]
    assert body["allowed_working_directories"] == list(
        host_service.policy.allowed_working_directories,
    )
    assert body["timeout_seconds"] == host_service.policy.timeout_seconds
    assert body["max_output_bytes"] == host_service.policy.max_output_bytes
    assert body["max_concurrent_executions"] == host_service.policy.max_concurrent_executions
    assert body["max_operation_history"] == host_service.policy.max_operation_history


def test_status_reports_resource_usage(host_client, host_service):
    response = host_client.get("/api/host/status")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": host_service.policy.enabled,
        "active_executions": 0,
        "operation_count": 0,
        "max_concurrent_executions": host_service.policy.max_concurrent_executions,
        "max_operation_history": host_service.policy.max_operation_history,
    }
