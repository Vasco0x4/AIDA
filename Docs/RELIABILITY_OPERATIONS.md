# Reliability and security operations

This document covers the durable Kanban worker, the cached NVD critical-CVE digest, and the separately opt-in direct-host MCP tool.

## Durable Kanban execution

Task state is stored in PostgreSQL. A worker claims a queued task with an atomic `UPDATE ... WHERE status = 'queued'` and a dependency-ready predicate, stores an opaque lease token, and renews the lease only while that token remains current. Workers re-check task status around execution and recovery; startup and periodic recovery return expired claims to the queue. Manual recovery records `recovered_manual`, while lease recovery records `recovered_lease_expired`.

`tasks.version` implements optimistic concurrency. Drag/drop moves and general updates may include `expected_version`; stale writes receive HTTP 409 and the client reloads the board. Task events use descending `task_events.id` cursor pagination (`before_id`) and each page is returned chronologically. Parent/child dependencies are checked for missing tasks and cycles, and block a parent claim until every dependency is done.

Task history, result summaries, comments, attachments, dependencies, and lifecycle timestamps survive restarts. Automatic retries use capped exponential backoff persisted in `meta.retry_not_before` (base 1 second, maximum 30 seconds, at most 3 retries). An operator can explicitly retry a failed task or recover a stale running task from the detail drawer.

Operational endpoints:

- `POST /api/tasks/{id}/move` with `status`, `position`, and `expected_version`
- `PUT /api/tasks/{id}` with optional `expected_version`
- `PUT /api/tasks/{id}/dependencies` with `dependency_ids`
- `GET /api/tasks/{id}/events?before_id=...&limit=100`
- `POST /api/tasks/{id}/recover`
- `POST /api/tasks/{id}/retry`

The response models deliberately exclude lease fencing tokens. Database startup adds the reliability columns and indexes without deleting task data. Relevant indexes cover board ordering, queued candidate selection, expired lease recovery, and event pagination.

Prometheus series include `aida_task_claims_total`, `aida_task_recoveries_total{reason}`, `aida_task_retries_total{trigger}`, `aida_worker_active`, `aida_worker_job_duration_seconds`, `aida_task_attempts_total{status}`, and `aida_tasks_by_status`.

## Scheduled NVD critical-CVE digest

The backend scheduler checks the persistent NVD policy every 60 seconds (with a small loop delay) and performs due work in a thread with a fresh database session. A failed refresh never deletes cached CVEs and schedules the next retry one hour later; the UI continues to show the last successful digest with an age and warning. The cache retains one row per CVE, deduplicates products, stores bounded descriptions, and preserves the last successful query window.

Default schedule: enabled, every 24 hours, one-day lookback, at most 100 items, CVSS v3.1/v3.0 critical data. CVSS v4 can be enabled through the schedule API. NVD requests use pagination, timeout/retry handling, the API-key rate-limit delay when configured, and bounded response validation.

- Authenticated digest/status: `GET /api/nvd/digest`, `GET /api/nvd/status`
- Admin refresh: `POST /api/nvd/refresh`
- Admin schedule: `PUT /api/nvd/schedule`
- Admin key storage/removal: `PUT /api/nvd/key`, `DELETE /api/nvd/key`

`PUT /api/nvd/key` accepts `{"api_key":"..."}`. The key is encrypted with the platform crypto service in `PlatformSettings`; API responses expose only `api_key_configured` and its source. A process-level `NVD_API_KEY` deployment secret is also supported when no encrypted key is stored. Keys are never written to task events, returned in the digest, or included in scheduler status. Manual refresh and schedule/key changes are RBAC-protected and audited without secret values.

Metrics include `aida_nvd_refreshes_total{result}`, `aida_nvd_cache_age_seconds`, and `aida_nvd_cached_items`.

## Opt-in direct-host MCP execution

The existing `execute` and `python_exec` tools continue to use the normal assessment container. Direct host execution is a separate `host_execute` MCP tool and is absent from tool discovery unless every required policy setting is present. It accepts an action, an argv array (never a shell string), a working directory, and declared targets.

Copy `backend/.env.example` settings into the backend environment only after reviewing the host threat model:

```bash
AIDA_HOST_EXECUTION_ENABLED=true
AIDA_HOST_EXECUTION_ALLOWED_WORKING_DIRECTORIES=/srv/aida-work
AIDA_HOST_EXECUTION_ALLOWED_EXECUTABLES=echo,nmap
AIDA_HOST_EXECUTION_NETWORK_ACTIONS=nmap
AIDA_HOST_EXECUTION_ALLOWED_NETWORKS=192.0.2.0/24
AIDA_HOST_EXECUTION_ALLOWED_DNS_NAMES=target.example
AIDA_HOST_EXECUTION_TIMEOUT_SECONDS=30
AIDA_HOST_EXECUTION_MAX_OUTPUT_BYTES=65536
AIDA_HOST_EXECUTION_MAX_CONCURRENT_EXECUTIONS=4
AIDA_HOST_EXECUTION_MAX_OPERATION_HISTORY=100
```

All executable and network lists are exact allowlists; there are no wildcard or implicit public-network scopes. Shell interpreters, privilege escalation, destructive commands, target-list/config indirection, control characters, shell metacharacters, absolute file operands, and parent traversal are denied. Network arguments must machine-match the declared target set. Child processes receive a scrubbed environment and fixed safe `PATH`; stdout/stderr are separately bounded and redacted. Timeouts kill the process group. Concurrency and operation history are bounded.

Host execution is **not an OS sandbox**. Run the backend/MCP process as a dedicated unprivileged OS account whose filesystem and network permissions contain only the intended assessment data and targets. Do not run it as root, do not mount Docker control sockets, and keep application/cloud credentials out of that account. Review tool output and structured `host_execute audit` logs as operation evidence; arguments and output are redacted before being returned or logged.

`GET /api/host/status` is admin-only and reports policy/activity without exposing other host data. Metrics include `aida_host_executions_total{result}` and `aida_host_execution_duration_seconds{result}`.

## Verification

Run the standard suites from the repository:

```bash
cd backend
python -m pytest -q --tb=short
cd ../frontend
npm ci
npm run lint
npm run build
node --test src/services/nvdService.test.js
```

The focused reliability/security suites are `test_task_reliability_api.py`, `test_kanban_reliability.py`, `test_reliability_migrations.py`, `test_nvd_service.py`, `test_nvd_api.py`, `test_nvd_scheduler.py`, `test_host_execution.py`, `test_host_api.py`, and `test_mcp_host_execution.py`. `verification/e2e_api.py` exercises setup/login, authenticated NVD reads, host policy, and task lifecycle against an isolated live backend. External NVD tests mock HTTP; live safe host smoke tests use only `echo`. No test or verification path requires an external penetration-test target.
