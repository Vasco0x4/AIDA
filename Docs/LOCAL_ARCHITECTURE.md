# Extended edition architecture

The React/Vite frontend talks to FastAPI through Nginx `/api`. PostgreSQL stores accounts, Assessments, tasks, schedules, profiles and finding records. WebSocket events refresh operational views. Docker provides the execution container through the configured socket proxy. Evidence and logs use persistent volumes.

## Work execution

Task Board changes task state through the task service. The runner claims queued work, tracks leases/heartbeats and executes the runtime with configured concurrency and budgets. The planner may split work into dependent tasks. The runtime uses model-provider calls and tools; it is separate from an external CLI launched by `aida.py`.

The scheduler evaluates cron in the configured timezone, locks a schedule, rechecks that it is still due/enabled and creates a queued run. It advances the schedule cursor transactionally. A global scheduler setting and the runner's enabled setting are separate. Use one backend process for this installation; distributed execution semantics have not been established by the UI tests.

Scan profiles snapshot applicable limits into run metadata. Safe web baseline uses bounded GET requests. Evidence storage and finding snapshots support provenance and comparisons. A report is a presentation of recorded results, not independent proof of coverage.

## Authentication and boundaries

JWT authentication, coarse role middleware, optional OTP and OIDC protect application routes. HTTP MCP has its own API-key and network-policy handling; stdio MCP uses launcher-provided context. The Docker socket proxy narrows the API surface but does not make arbitrary execution harmless. Scope parsing for free-form commands is a best-effort check, not a network sandbox. Structured safe HTTP checks are more constrained but also require network-level isolation for stronger guarantees.

## Local storage

The active project is `aida-prod`, with code at `/path/to/AIDA`. Production owns the `aida_prod_*` volumes. Source folders, Docker images, database contents and evidence volumes are separate resources; deleting a source tree does not delete its database, and removing a container does not necessarily remove its named volumes.

The cleanup procedure preserves shared production evidence/log volumes and removes obsolete containers by inspected identity. See [Operations](OPERATIONS.md) and [Upstream comparison](UPSTREAM_COMPARISON.md).
